"""Daily ETL script — fetches S&P 500 data from FMP and upserts into Supabase.

Usage
-----
Run daily after market close (e.g. 6 PM ET) via Windows Task Scheduler:

    python etl.py

One-time historical backfill (run once to seed the last year of data):

    python etl.py backfill
    python etl.py backfill 2024-01-01 2025-04-04   # custom date range

The daily run uses ~101 FMP API requests, well under the free-tier 250/day cap.
The backfill also uses ~101 requests (batch historical covers all dates at once).
"""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta

import requests
from supabase import Client, create_client

# Load credentials from .env
from config import (
    ETL_BATCH_SIZE,
    FMP_API_KEY,
    FMP_BASE_URL,
    REQUEST_TIMEOUT,
    SUPABASE_SERVICE_KEY,
    SUPABASE_URL,
)


# ---------------------------------------------------------------------------
# Supabase client (service role — write access)
# ---------------------------------------------------------------------------

def _get_db() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# ---------------------------------------------------------------------------
# FMP API helpers
# ---------------------------------------------------------------------------

def _fetch_constituents() -> list[dict]:
    """Return the current S&P 500 constituent list from FMP (1 API request)."""
    url = f"{FMP_BASE_URL}/sp500_constituent?apikey={FMP_API_KEY}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _fetch_quotes_batch(tickers: list[str]) -> list[dict]:
    """Return real-time quote data for up to ETL_BATCH_SIZE tickers (1 request).

    Each quote includes today's open, latest price (used as close), and
    market cap. Run this after 4 PM ET so 'price' reflects the day's close.
    """
    symbols = ",".join(tickers)
    url = f"{FMP_BASE_URL}/quote/{symbols}?apikey={FMP_API_KEY}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    # FMP returns a dict (not a list) for a single ticker
    return data if isinstance(data, list) else [data]


def _fetch_historical_batch(tickers: list[str], from_date: str, to_date: str) -> list[dict]:
    """Return OHLC rows for up to ETL_BATCH_SIZE tickers across a date range (1 request).

    Returns a flat list of dicts with keys: ticker, date, open, close.
    """
    symbols = ",".join(tickers)
    url = (
        f"{FMP_BASE_URL}/historical-price-full/{symbols}"
        f"?from={from_date}&to={to_date}&apikey={FMP_API_KEY}"
    )
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    rows: list[dict] = []

    # Multi-ticker response
    if "historicalStockList" in data:
        for stock in data["historicalStockList"]:
            ticker = stock["symbol"]
            for day in stock.get("historical", []):
                rows.append({
                    "ticker": ticker,
                    "date": day["date"],
                    "open": day.get("open"),
                    "close": day.get("close"),
                    "market_cap": None,
                })
    # Single-ticker response
    elif "historical" in data:
        ticker = data.get("symbol", tickers[0])
        for day in data.get("historical", []):
            rows.append({
                "ticker": ticker,
                "date": day["date"],
                "open": day.get("open"),
                "close": day.get("close"),
                "market_cap": None,
            })

    return rows


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def _upsert_in_chunks(db: Client, table: str, rows: list[dict], chunk_size: int = 500) -> None:
    """Upsert rows in chunks to stay within Supabase's request-body limit."""
    for i in range(0, len(rows), chunk_size):
        db.table(table).upsert(rows[i : i + chunk_size]).execute()


# ---------------------------------------------------------------------------
# Daily ETL
# ---------------------------------------------------------------------------

def run_daily_etl() -> None:
    """Fetch today's S&P 500 prices and upsert into Supabase.

    Steps:
    1. Pull the current constituent list from FMP and refresh the DB table.
    2. Fetch today's quote (open + close + market_cap) for all tickers in
       batches of ETL_BATCH_SIZE.
    3. Upsert into daily_prices.

    Run after US market close (4 PM ET / 9 PM UTC) so 'price' is the EOD close.
    """
    db = _get_db()
    today = date.today().isoformat()

    print("Fetching S&P 500 constituents...")
    raw_constituents = _fetch_constituents()
    constituent_rows = [
        {"ticker": c["symbol"], "name": c["name"], "sector": c.get("sector", "")}
        for c in raw_constituents
        if c.get("symbol") and c.get("name")
    ]
    _upsert_in_chunks(db, "constituents", constituent_rows)
    print(f"  {len(constituent_rows)} constituents upserted")

    tickers = [r["ticker"] for r in constituent_rows]

    print(f"Fetching today's quotes for {len(tickers)} tickers...")
    price_rows: list[dict] = []
    total_batches = (len(tickers) + ETL_BATCH_SIZE - 1) // ETL_BATCH_SIZE

    for i in range(0, len(tickers), ETL_BATCH_SIZE):
        batch = tickers[i : i + ETL_BATCH_SIZE]
        batch_num = i // ETL_BATCH_SIZE + 1

        try:
            quotes = _fetch_quotes_batch(batch)
            for q in quotes:
                open_price = q.get("open")
                close_price = q.get("price")  # 'price' = latest/EOD price
                if open_price is None or close_price is None:
                    continue
                price_rows.append({
                    "ticker": q["symbol"],
                    "date": today,
                    "open": open_price,
                    "close": close_price,
                    "market_cap": q.get("marketCap"),
                })
        except Exception as exc:
            print(f"  Batch {batch_num}/{total_batches} failed: {exc}")

        if batch_num % 20 == 0:
            print(f"  {batch_num}/{total_batches} batches done...")

        time.sleep(0.2)  # stay well under FMP's per-second rate limit

    if price_rows:
        _upsert_in_chunks(db, "daily_prices", price_rows)
        print(f"  {len(price_rows)} price rows upserted for {today}")
    else:
        print("  No price data returned — market may be closed today, or run after 4 PM ET.")

    print("Daily ETL complete.")


# ---------------------------------------------------------------------------
# One-time backfill
# ---------------------------------------------------------------------------

def run_backfill(from_date: str, to_date: str) -> None:
    """Seed the database with historical OHLC data for the given date range.

    Uses the FMP batch historical endpoint — one request returns all dates for
    ETL_BATCH_SIZE tickers, so the total request count is the same as a single
    day (~101 requests for 500 tickers). Run once; the daily ETL handles
    everything after that.

    Args:
        from_date: ISO date string, e.g. ``"2024-01-01"``.
        to_date:   ISO date string, e.g. ``"2025-04-04"``.
    """
    db = _get_db()

    print("Fetching S&P 500 constituents for backfill...")
    raw_constituents = _fetch_constituents()
    constituent_rows = [
        {"ticker": c["symbol"], "name": c["name"], "sector": c.get("sector", "")}
        for c in raw_constituents
        if c.get("symbol") and c.get("name")
    ]
    _upsert_in_chunks(db, "constituents", constituent_rows)
    tickers = [r["ticker"] for r in constituent_rows]

    print(f"Backfilling {len(tickers)} tickers from {from_date} to {to_date}...")
    all_rows: list[dict] = []
    total_batches = (len(tickers) + ETL_BATCH_SIZE - 1) // ETL_BATCH_SIZE

    for i in range(0, len(tickers), ETL_BATCH_SIZE):
        batch = tickers[i : i + ETL_BATCH_SIZE]
        batch_num = i // ETL_BATCH_SIZE + 1

        try:
            rows = _fetch_historical_batch(batch, from_date, to_date)
            all_rows.extend(rows)
        except Exception as exc:
            print(f"  Batch {batch_num}/{total_batches} failed: {exc}")

        if batch_num % 10 == 0:
            print(f"  {batch_num}/{total_batches} batches done, {len(all_rows)} rows so far...")

        time.sleep(0.3)

    print(f"Upserting {len(all_rows)} rows into Supabase...")
    _upsert_in_chunks(db, "daily_prices", all_rows)
    print(f"Backfill complete: {len(all_rows)} rows loaded.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        _from = sys.argv[2] if len(sys.argv) > 2 else (date.today() - timedelta(days=365)).isoformat()
        _to = sys.argv[3] if len(sys.argv) > 3 else date.today().isoformat()
        run_backfill(_from, _to)
    else:
        run_daily_etl()
