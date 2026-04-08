"""Analytics helpers for the S&P 500 dashboard.

This module turns raw downloaded market data into the derived tables and display
helpers used by the UI:
- per-stock return calculations from boundary price windows
- sector average summaries
- return formatting
- market-cap formatting
- conditional styling for the ranked table
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from config import NEUTRAL_BG, RETURN_TOLERANCE, TEXT_COLOR


def calculate_performance(
    constituents: pd.DataFrame, start_history: pd.DataFrame, end_history: pd.DataFrame
) -> tuple[pd.DataFrame, list[str]]:
    """Create the ranked stock-performance table for the selected date range.

    For each constituent, the function uses:
    - the first available ``Open`` from a small price window near the selected
      start date
    - the last available ``Close`` from a small price window near the selected
      end date

    That gives the same period-return calculation as a full-range download while
    moving far less data over the network.

    Args:
        constituents: Normalized constituent table containing ticker, company
            name, sector, and Yahoo Finance ticker symbol.
        start_history: Batch-downloaded Yahoo Finance OHLC data covering a small
            window near the selected start date.
        end_history: Batch-downloaded Yahoo Finance OHLC data covering a small
            window near the selected end date.

    Returns:
        A tuple containing:
        - the ranked performance DataFrame
        - a list of tickers skipped because of missing or incomplete data
    """
    records: list[dict[str, Any]] = []
    failed_tickers: list[str] = []

    start_tickers = extract_available_tickers(start_history, constituents)
    end_tickers = extract_available_tickers(end_history, constituents)

    for row in constituents.itertuples(index=False):
        if row.YF_Ticker not in start_tickers or row.YF_Ticker not in end_tickers:
            failed_tickers.append(row.Ticker)
            continue

        start_ticker_history = extract_ticker_history(start_history, row.YF_Ticker).copy()
        end_ticker_history = extract_ticker_history(end_history, row.YF_Ticker).copy()

        open_series = pd.to_numeric(start_ticker_history.get("Open"), errors="coerce").dropna()
        close_series = pd.to_numeric(end_ticker_history.get("Close"), errors="coerce").dropna()

        if open_series.empty or close_series.empty:
            failed_tickers.append(row.Ticker)
            continue

        open_price = float(open_series.iloc[0])
        close_price = float(close_series.iloc[-1])

        if open_price == 0:
            failed_tickers.append(row.Ticker)
            continue

        records.append(
            {
                "Ticker": row.Ticker,
                "YF_Ticker": row.YF_Ticker,
                "Name": row.Name,
                "Sector": row.Sector,
                "Open Price": open_price,
                "Close Price": close_price,
                "Return %": (close_price / open_price) - 1,
                "Return $": close_price - open_price,
            }
        )

    performance_df = pd.DataFrame(
        records,
        columns=[
            "Ticker",
            "YF_Ticker",
            "Name",
            "Sector",
            "Open Price",
            "Close Price",
            "Return %",
            "Return $",
        ],
    )
    if performance_df.empty:
        return performance_df, failed_tickers

    performance_df = performance_df.sort_values("Return %", ascending=False).reset_index(drop=True)
    performance_df.insert(0, "Rank", range(1, len(performance_df) + 1))
    return performance_df, failed_tickers


def extract_available_tickers(history: pd.DataFrame, constituents: pd.DataFrame) -> set[str]:
    """Return the ticker symbols available in a Yahoo batch download result."""
    if isinstance(history.columns, pd.MultiIndex):
        return set(history.columns.get_level_values(0))
    return set(constituents["YF_Ticker"])


def extract_ticker_history(history: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Return the per-ticker OHLC slice from a batch download result."""
    if isinstance(history.columns, pd.MultiIndex):
        return history[ticker]
    return history


def build_sector_summary(performance_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate average returns by sector.

    Args:
        performance_df: Ranked stock-level performance table.

    Returns:
        A DataFrame with one row per sector and the mean return percentage used
        by the sector chart.
    """
    if performance_df.empty:
        return pd.DataFrame(columns=["Sector", "Return %"])

    return (
        performance_df.groupby("Sector", as_index=False)["Return %"]
        .mean()
        .sort_values("Return %", ascending=True)
        .reset_index(drop=True)
    )


def format_percent(value: float) -> str:
    """Format a decimal value as a signed percentage string.

    Example:
        ``0.0342`` becomes ``"+3.42%"``.
    """
    return f"{value:+.2%}"


def format_market_cap(value: Any) -> str:
    """Format a market-cap number into a compact dollar string.

    Examples:
        ``3_700_000_000_000`` becomes ``"$3.70T"``.
        ``850_000_000_000`` becomes ``"$850.00B"``.
    """
    if pd.isna(value):
        return ""

    absolute_value = abs(float(value))
    if absolute_value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if absolute_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if absolute_value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def style_return_cell(value: Any) -> str:
    """Build a CSS style string for a return cell in the ranked table.

    Positive values receive a green background, negative values receive a red
    background, and near-zero values receive a neutral background. The color
    intensity scales with the absolute size of the move.

    Args:
        value: The cell value from the ``Return %`` column.

    Returns:
        A CSS declaration string understood by ``pandas.Styler``.
    """
    if pd.isna(value):
        return ""

    absolute_return = min(abs(float(value)) / 0.20, 1.0)
    alpha = 0.12 + (absolute_return * 0.38)

    if float(value) > RETURN_TOLERANCE:
        return f"background-color: rgba(20, 128, 74, {alpha:.3f}); color: #0B3D24;"
    if float(value) < -RETURN_TOLERANCE:
        return f"background-color: rgba(192, 57, 43, {alpha:.3f}); color: #5C1812;"
    return f"background-color: {NEUTRAL_BG}; color: {TEXT_COLOR};"
