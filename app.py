"""Streamlit entry point for the S&P 500 dashboard.

This module owns the user interface layer of the app:
- page setup and visual styling
- date and preset controls
- load-button behavior and session-state management
- KPI, chart, and table rendering

Data collection and calculations live in separate modules so this file can stay
focused on how the dashboard is presented to the user.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from analytics import format_market_cap, format_percent, style_return_cell
from charts import build_sector_chart, build_top_bottom_chart
from config import APP_TITLE, BORDER_COLOR, DEFAULT_TOP_N, MUTED_TEXT, PANEL_BG, PRESET_OPTIONS, RETURN_TOLERANCE, TEXT_COLOR
from data_loader import load_dashboard_dataset


def main() -> None:
    """Run the full Streamlit page.

    The function configures the page, initializes session state, renders the
    controls, optionally loads data when the user clicks the button, and then
    displays the KPI row, charts, and ranked table.
    """
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="chart_with_upwards_trend",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    inject_styles()
    init_session_state()

    st.markdown(f"<div class='app-title'>{APP_TITLE}</div>", unsafe_allow_html=True)
    st.markdown(
        (
            "<div class='app-subtitle'>"
            "Analyze the current S&amp;P 500 constituents across custom date ranges with "
            "cached Wikipedia constituents and a single Yahoo Finance batch download."
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    render_controls()

    if st.session_state.get("load_requested"):
        load_data()
        st.session_state.load_requested = False

    dashboard_data = st.session_state.get("dashboard_data")
    if dashboard_data is None:
        st.info("Pick a date range, use a preset if you want, and click Load to fetch the dashboard data.")
        return

    performance_df = dashboard_data["performance"]
    sector_df = dashboard_data["sector"]
    total_constituents = dashboard_data["total_constituents"]
    failed_tickers = dashboard_data["failed_tickers"]
    loaded_range = dashboard_data["date_range"]

    if performance_df.empty:
        st.warning(
            "No pricing data was available for the selected range. Try a wider date range or include trading days."
        )
        return

    start_date, end_date = loaded_range
    st.caption(
        f"Loaded range: {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}. "
        "Returns use the first available trading-day open and last available trading-day close within the range."
    )

    if failed_tickers:
        preview = ", ".join(failed_tickers[:10])
        more = "" if len(failed_tickers) <= 10 else f" ... +{len(failed_tickers) - 10} more"
        st.warning(
            f"Skipped {len(failed_tickers)} ticker(s) with missing or incomplete pricing data: {preview}{more}"
        )

    render_kpis(performance_df, total_constituents)
    render_charts(performance_df, sector_df)
    render_ranked_table(performance_df)


def inject_styles() -> None:
    """Inject custom CSS for the dashboard.

    The styles keep the app close to the requested white-background, clean-grid,
    light-typography look and adjust the default Streamlit components so the KPI
    cards and controls feel more like a compact analytics dashboard.
    """
    st.markdown(
        f"""
        <style>
            .stApp {{
                background: #FFFFFF;
                color: {TEXT_COLOR};
            }}
            .block-container {{
                max-width: 1320px;
                padding-top: 1.4rem;
                padding-bottom: 2rem;
            }}
            .app-title {{
                color: {TEXT_COLOR};
                font-size: 2.2rem;
                font-weight: 700;
                letter-spacing: -0.03em;
                margin-bottom: 0.2rem;
            }}
            .app-subtitle {{
                color: {MUTED_TEXT};
                font-size: 1rem;
                margin-bottom: 1.25rem;
                max-width: 980px;
            }}
            .section-title {{
                color: {TEXT_COLOR};
                font-size: 1.1rem;
                font-weight: 600;
                margin: 0.35rem 0 0.85rem 0;
            }}
            div[data-testid="stMetric"] {{
                background: {PANEL_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: 16px;
                padding: 0.75rem 0.9rem;
                min-height: 130px;
            }}
            div[data-testid="stMetricLabel"] > div {{
                color: {MUTED_TEXT};
                font-weight: 600;
            }}
            div[data-testid="stMetricValue"] {{
                color: {TEXT_COLOR};
                font-weight: 700;
            }}
            div[data-testid="stMetricDelta"] {{
                font-weight: 600;
            }}
            div[data-testid="stVerticalBlockBorderWrapper"] {{
                border-radius: 18px;
            }}
            .stButton > button, .stDownloadButton > button {{
                border-radius: 12px;
                border: 1px solid {BORDER_COLOR};
            }}
            .stDateInput, .stNumberInput, .stSelectbox {{
                background: #FFFFFF;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session_state() -> None:
    """Seed Streamlit session state with default values.

    This function ensures the app has a starting date range, a default chart
    size for the top/bottom views, and placeholders for the most recently
    loaded dashboard dataset.
    """
    today = date.today()
    default_start, default_end = resolve_preset("1M", today)

    st.session_state.setdefault("start_date", default_start)
    st.session_state.setdefault("end_date", default_end)
    st.session_state.setdefault("top_n", DEFAULT_TOP_N)
    st.session_state.setdefault("dashboard_data", None)
    st.session_state.setdefault("load_requested", False)


def render_controls() -> None:
    """Render the control panel at the top of the page.

    The control area includes:
    - preset buttons such as WTD and YTD
    - explicit From and To date inputs
    - a numeric input for top/bottom chart size
    - the Load button that triggers data retrieval
    """
    st.markdown("<div class='section-title'>Date Range & Controls</div>", unsafe_allow_html=True)

    preset_columns = st.columns(len(PRESET_OPTIONS))
    for column, preset in zip(preset_columns, PRESET_OPTIONS):
        column.button(
            preset,
            key=f"preset_{preset}",
            use_container_width=True,
            on_click=apply_preset,
            args=(preset,),
        )

    controls = st.columns((1.2, 1.2, 0.7, 0.7))
    today = date.today()

    with controls[0]:
        st.date_input("From", key="start_date", max_value=today)
    with controls[1]:
        st.date_input("To", key="end_date", max_value=today)
    with controls[2]:
        st.number_input("Top / Bottom N", min_value=5, max_value=50, step=1, key="top_n")
    with controls[3]:
        st.markdown("<div style='height: 1.85rem;'></div>", unsafe_allow_html=True)
        if st.button("Load", type="primary", use_container_width=True):
            st.session_state.load_requested = True


def apply_preset(preset: str) -> None:
    """Apply a preset date window to session state.

    Args:
        preset: A supported preset label such as ``"1M"`` or ``"YTD"``.
    """
    start_date, end_date = resolve_preset(preset, date.today())
    st.session_state.start_date = start_date
    st.session_state.end_date = end_date


def resolve_preset(preset: str, today: date) -> tuple[date, date]:
    """Convert a preset label into concrete calendar dates.

    Args:
        preset: The requested preset window.
        today: The anchor date used as the preset end date.

    Returns:
        A ``(start_date, end_date)`` tuple.
    """
    today_ts = pd.Timestamp(today)

    if preset == "WTD":
        start_date = today - timedelta(days=today.weekday())
    elif preset == "MTD":
        start_date = today.replace(day=1)
    elif preset == "YTD":
        start_date = today.replace(month=1, day=1)
    elif preset == "1M":
        start_date = (today_ts - pd.DateOffset(months=1)).date()
    elif preset == "3M":
        start_date = (today_ts - pd.DateOffset(months=3)).date()
    elif preset == "6M":
        start_date = (today_ts - pd.DateOffset(months=6)).date()
    elif preset == "1Y":
        start_date = (today_ts - pd.DateOffset(years=1)).date()
    else:
        raise ValueError(f"Unsupported preset: {preset}")

    return start_date, today


def load_data() -> None:
    """Load dashboard data for the currently selected date range.

    This function validates the date inputs, shows the loading spinner, calls
    the cached data-loader function, and saves the assembled result into
    ``st.session_state`` so the rest of the page can render from it.
    """
    start_date = st.session_state.start_date
    end_date = st.session_state.end_date

    if start_date > end_date:
        st.error("The From date must be on or before the To date.")
        return

    try:
        with st.spinner("Fetching S&P 500 constituents and batch price data..."):
            performance_df, sector_df, failed_tickers, total_constituents = load_dashboard_dataset(
                start_date, end_date
            )
    except Exception as exc:
        st.error(f"Unable to load dashboard data right now: {exc}")
        return

    st.session_state.dashboard_data = {
        "performance": performance_df,
        "sector": sector_df,
        "failed_tickers": failed_tickers,
        "total_constituents": total_constituents,
        "date_range": (start_date, end_date),
    }


def render_kpis(performance_df: pd.DataFrame, total_constituents: int) -> None:
    """Render the KPI summary row.

    Args:
        performance_df: Ranked per-stock performance data for the selected range.
        total_constituents: Total number of index members discovered from the
            live constituent source before any failed ticker downloads are
            excluded.
    """
    st.markdown("<div class='section-title'>KPI Summary</div>", unsafe_allow_html=True)

    positive_count = int((performance_df["Return %"] > RETURN_TOLERANCE).sum())
    negative_count = int((performance_df["Return %"] < -RETURN_TOLERANCE).sum())
    neutral_count = len(performance_df) - positive_count - negative_count
    average_return = performance_df["Return %"].mean()
    best_row = performance_df.iloc[0]
    worst_row = performance_df.iloc[-1]

    metric_columns = st.columns(5)
    metric_columns[0].metric("Total Stocks Loaded", f"{len(performance_df):,}", f"of {total_constituents:,} current constituents")
    metric_columns[1].metric("Positive / Negative / Neutral", f"{positive_count} / {negative_count} / {neutral_count}")
    metric_columns[2].metric("Average Return", format_percent(average_return), None)
    metric_columns[3].metric("Best Performer", best_row["Ticker"], format_percent(best_row["Return %"]))
    metric_columns[4].metric("Worst Performer", worst_row["Ticker"], format_percent(worst_row["Return %"]))


def render_charts(performance_df: pd.DataFrame, sector_df: pd.DataFrame) -> None:
    """Render the three main dashboard charts.

    Args:
        performance_df: Ranked stock-level performance table.
        sector_df: Sector-level average return summary used for the sector chart.
    """
    st.markdown("<div class='section-title'>Charts</div>", unsafe_allow_html=True)

    top_n = min(int(st.session_state.top_n), len(performance_df))
    chart_columns = st.columns(2)

    with chart_columns[0]:
        st.plotly_chart(build_top_bottom_chart(performance_df, top_n=top_n, mode="top"), use_container_width=True)
    with chart_columns[1]:
        st.plotly_chart(build_top_bottom_chart(performance_df, top_n=top_n, mode="bottom"), use_container_width=True)

    if not sector_df.empty:
        st.plotly_chart(build_sector_chart(sector_df), use_container_width=True)


def render_ranked_table(performance_df: pd.DataFrame) -> None:
    """Render the full ranked stock table and CSV export control.

    The table can be filtered by sector, styled by return percentage, and
    downloaded as a CSV containing only the currently visible rows.

    Args:
        performance_df: Ranked stock-level performance table.
    """
    st.markdown("<div class='section-title'>Full Ranked Table</div>", unsafe_allow_html=True)

    sectors = ["All Sectors"] + sorted(performance_df["Sector"].dropna().unique().tolist())
    filter_columns = st.columns((1.1, 0.9))

    with filter_columns[0]:
        selected_sector = st.selectbox("Sector Filter", sectors, index=0)

    filtered_df = performance_df.copy()
    if selected_sector != "All Sectors":
        filtered_df = filtered_df[filtered_df["Sector"] == selected_sector].reset_index(drop=True)

    filtered_df = filtered_df.copy()
    filtered_df["Rank"] = range(1, len(filtered_df) + 1)
    display_df = filtered_df[
        [
            "Rank",
            "Ticker",
            "Name",
            "Sector",
            "Market Cap",
            "Open Price",
            "Close Price",
            "Return %",
            "Return $",
        ]
    ].copy()

    csv_bytes = display_df.to_csv(index=False).encode("utf-8")
    file_suffix = selected_sector.lower().replace(" ", "-").replace("/", "-")
    with filter_columns[1]:
        st.markdown("<div style='height: 1.85rem;'></div>", unsafe_allow_html=True)
        st.download_button(
            "Download CSV",
            data=csv_bytes,
            file_name=f"sp500-performance-{file_suffix}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    styled_table = (
        display_df.style.format(
            {
                "Market Cap": format_market_cap,
                "Open Price": "${:,.2f}",
                "Close Price": "${:,.2f}",
                "Return %": "{:+.2%}",
                "Return $": "${:+,.2f}",
            }
        )
        .map(style_return_cell, subset=["Return %"])
        .hide(axis="index")
    )

    st.dataframe(styled_table, use_container_width=True, height=min(760, 80 + len(filtered_df) * 34))


if __name__ == "__main__":
    main()
