# S&P 500 Performance Dashboard

A Streamlit dashboard for analyzing current S&P 500 stock performance across custom date ranges using Wikipedia constituents and Yahoo Finance batch pricing.

## Features

- Custom `From` / `To` date range controls with quick presets: `WTD`, `MTD`, `YTD`, `1M`, `3M`, `6M`, `1Y`
- Manual `Load` workflow so the app stays fast on startup
- Cached Wikipedia constituent scrape and cached Yahoo Finance batch download for 1 hour
- KPI summary cards for loaded stock count, breadth, average return, and best/worst names
- Plotly charts for top performers, bottom performers, and sector average return
- Ranked table with sector filtering, return coloring, and CSV export

## Run Locally

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Notes

- The app uses the current S&P 500 constituent list from Wikipedia, so membership updates are picked up automatically after cache expiry.
- Returns are based on the first available daily `Open` and last available daily `Close` inside the selected range.
- Tickers with incomplete or missing pricing data are skipped gracefully and surfaced in the UI.
