"""Remote data-access functions for the dashboard.

This module is responsible for pulling the external inputs used by the app:
- the current S&P 500 constituent list from Wikipedia
- historical price data from Yahoo Finance via ``yfinance``
- current market-cap snapshots from Yahoo Finance via ``fast_info``

It also assembles those raw inputs into the cached dataset returned to the UI.
To keep the dashboard responsive, price history is downloaded from small
boundary windows around the selected start and end dates instead of requesting
every day inside the full range.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from io import StringIO

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from analytics import build_sector_summary, calculate_performance
from config import (
    PRICE_BOUNDARY_WINDOW_DAYS,
    PRICE_CACHE_TTL_SECONDS,
    REQUEST_TIMEOUT,
    STATIC_CACHE_TTL_SECONDS,
    WIKI_HEADERS,
    WIKI_URL,
)


@st.cache_data(ttl=PRICE_CACHE_TTL_SECONDS, show_spinner=False)
def load_dashboard_dataset(
    start_date: date, end_date: date
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], int]:
    """Load the complete dataset needed by the dashboard for one date window.

    Args:
        start_date: Inclusive starting date selected by the user.
        end_date: Inclusive ending date selected by the user.

    Returns:
        A tuple containing:
        - the ranked stock-level performance table
        - the sector summary table
        - the list of failed tickers
        - the total number of live constituents discovered
    """
    constituents = fetch_sp500_constituents()
    start_history, end_history = download_price_boundaries(tuple(constituents["YF_Ticker"]), start_date, end_date)
    performance_df, failed_tickers = calculate_performance(constituents, start_history, end_history)
    if performance_df.empty:
        performance_df["Market Cap"] = pd.Series(dtype="float64")
    else:
        market_caps_df = fetch_market_caps(tuple(performance_df["YF_Ticker"]))
        performance_df = performance_df.merge(market_caps_df, on="YF_Ticker", how="left")
    sector_df = build_sector_summary(performance_df)
    return performance_df, sector_df, failed_tickers, len(constituents)


@st.cache_data(ttl=STATIC_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_sp500_constituents() -> pd.DataFrame:
    """Fetch and normalize the live S&P 500 constituent table from Wikipedia.

    The raw Wikipedia page can contain multiple HTML tables, so this function
    searches for the one containing symbol, company/security name, and sector
    columns, then standardizes those fields into a predictable schema for the
    rest of the app.

    Returns:
        A DataFrame with the columns ``Ticker``, ``Name``, ``Sector``, and
        ``YF_Ticker``.
    """
    response = requests.get(WIKI_URL, headers=WIKI_HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))
    for table in tables:
        column_map = {str(column).strip().lower(): column for column in table.columns}
        symbol_col = next((actual for key, actual in column_map.items() if "symbol" in key or "ticker" in key), None)
        name_col = next(
            (actual for key, actual in column_map.items() if key in {"security", "company", "name"} or "security" in key),
            None,
        )
        sector_col = next(
            (actual for key, actual in column_map.items() if "gics sector" in key or key == "sector"),
            None,
        )

        if not all((symbol_col, name_col, sector_col)):
            continue

        constituents = table[[symbol_col, name_col, sector_col]].copy()
        constituents.columns = ["Ticker", "Name", "Sector"]
        constituents = constituents.dropna(subset=["Ticker", "Name", "Sector"]).drop_duplicates(subset=["Ticker"])
        constituents["Ticker"] = constituents["Ticker"].astype(str).str.strip()
        constituents["Name"] = constituents["Name"].astype(str).str.strip()
        constituents["Sector"] = constituents["Sector"].astype(str).str.strip()
        constituents["YF_Ticker"] = constituents["Ticker"].str.replace(".", "-", regex=False)
        return constituents.sort_values("Ticker").reset_index(drop=True)

    raise ValueError("Could not find the S&P 500 constituents table on Wikipedia.")


@st.cache_data(ttl=PRICE_CACHE_TTL_SECONDS, show_spinner=False)
def download_price_boundaries(
    tickers: tuple[str, ...], start_date: date, end_date: date
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download only the boundary price windows needed to compute period return."""
    short_range_cutoff = timedelta(days=PRICE_BOUNDARY_WINDOW_DAYS)
    if (end_date - start_date) <= short_range_cutoff:
        history = download_price_window(tickers, start_date, end_date)
        return history, history

    start_window_end = min(end_date, start_date + short_range_cutoff)
    end_window_start = max(start_date, end_date - short_range_cutoff)
    start_history = download_price_window(tickers, start_date, start_window_end)
    end_history = download_price_window(tickers, end_window_start, end_date)
    return start_history, end_history


@st.cache_data(ttl=PRICE_CACHE_TTL_SECONDS, show_spinner=False)
def download_price_window(tickers: tuple[str, ...], window_start: date, window_end: date) -> pd.DataFrame:
    """Download a small date window of daily OHLC data for all requested tickers."""
    end_exclusive = window_end + timedelta(days=1)
    history = yf.download(
        tickers=list(tickers),
        start=window_start.isoformat(),
        end=end_exclusive.isoformat(),
        group_by="ticker",
        auto_adjust=False,
        actions=False,
        threads=True,
        progress=False,
        keepna=False,
        timeout=REQUEST_TIMEOUT,
    )

    if history is None or history.empty:
        raise ValueError("Yahoo Finance returned no data for the selected boundary window.")

    return history


@st.cache_data(ttl=STATIC_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_market_caps(tickers: tuple[str, ...]) -> pd.DataFrame:
    """Fetch the latest market-cap snapshot for each ticker from Yahoo Finance."""
    quotes = yf.Tickers(" ".join(tickers))

    def load_market_cap(ticker: str) -> dict[str, float | str | None]:
        try:
            market_cap = quotes.tickers[ticker].fast_info.get("marketCap")
        except Exception:
            market_cap = None

        return {"YF_Ticker": ticker, "Market Cap": market_cap}

    max_workers = min(10, max(1, len(tickers)))
    records: list[dict[str, float | str | None]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(load_market_cap, ticker) for ticker in tickers]
        for future in as_completed(futures):
            records.append(future.result())

    return pd.DataFrame(records).sort_values("YF_Ticker").reset_index(drop=True)
