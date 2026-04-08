"""Shared constants used across the dashboard.

This module centralizes values that are reused in more than one place, such as:
- labels and page metadata
- remote source URLs and request settings
- cache durations
- default UI values
- shared color tokens used by the UI and charts

Keeping them here avoids repeating literal values across modules and makes small
app-wide changes easier.
"""

APP_TITLE = "S&P 500 Performance Dashboard"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
WIKI_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
REQUEST_TIMEOUT = 30
PRICE_CACHE_TTL_SECONDS = 3600
STATIC_CACHE_TTL_SECONDS = 86400
PRICE_BOUNDARY_WINDOW_DAYS = 14
DEFAULT_TOP_N = 20

# Treat near-zero values as neutral so tiny floating-point artifacts do not skew counts or styling.
RETURN_TOLERANCE = 1e-10

POSITIVE_DARK = "#14804A"
POSITIVE_LIGHT = "#D9F3E4"
NEGATIVE_DARK = "#C0392B"
NEGATIVE_LIGHT = "#F7D8D5"
NEUTRAL_BG = "#EEF3F8"
TEXT_COLOR = "#16202A"
MUTED_TEXT = "#657180"
GRID_COLOR = "#E7EDF4"
PANEL_BG = "#F7F9FC"
BORDER_COLOR = "#E2E8F0"

PRESET_OPTIONS = ("WTD", "MTD", "YTD", "1M", "3M", "6M", "1Y")
