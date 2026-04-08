"""Plotly chart builders for the dashboard.

This module contains the visualization-specific logic for the app:
- top and bottom performer bar charts
- sector average return chart
- shared chart layout styling
- helper functions for color interpolation
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from analytics import format_percent
from config import GRID_COLOR, NEGATIVE_DARK, NEGATIVE_LIGHT, POSITIVE_DARK, POSITIVE_LIGHT, TEXT_COLOR


def build_top_bottom_chart(performance_df: pd.DataFrame, top_n: int, mode: str) -> go.Figure:
    """Create a top-performers or bottom-performers horizontal bar chart.

    Args:
        performance_df: Ranked stock-level performance table.
        top_n: Number of rows to include in the chart.
        mode: Either ``"top"`` or ``"bottom"``.

    Returns:
        A configured Plotly ``Figure``.
    """
    if mode == "top":
        chart_df = performance_df.nlargest(top_n, "Return %").sort_values("Return %", ascending=True)
        colors = make_color_gradient(POSITIVE_LIGHT, POSITIVE_DARK, len(chart_df))
        title = f"Top {top_n} Performers"
    elif mode == "bottom":
        chart_df = performance_df.nsmallest(top_n, "Return %").sort_values("Return %", ascending=False)
        colors = make_color_gradient(NEGATIVE_LIGHT, NEGATIVE_DARK, len(chart_df))
        title = f"Bottom {top_n} Performers"
    else:
        raise ValueError(f"Unsupported chart mode: {mode}")

    figure = go.Figure(
        go.Bar(
            x=chart_df["Return %"],
            y=chart_df["Ticker"],
            orientation="h",
            marker={"color": colors, "line": {"color": "#FFFFFF", "width": 0.6}},
            text=[format_percent(value) for value in chart_df["Return %"]],
            textposition="outside",
            customdata=chart_df[["Name", "Sector"]],
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Company: %{customdata[0]}<br>"
                "Sector: %{customdata[1]}<br>"
                "Return: %{x:.2%}<extra></extra>"
            ),
        )
    )
    apply_common_chart_layout(figure, title)
    figure.update_xaxes(tickformat=".1%", title_text="Return %")
    figure.update_yaxes(title_text=None)
    return figure


def build_sector_chart(sector_df: pd.DataFrame) -> go.Figure:
    """Create the sector average return chart.

    Args:
        sector_df: Sector-level average return summary.

    Returns:
        A Plotly ``Figure`` with a diverging red-to-green color scale centered
        around zero.
    """
    max_abs_return = max(abs(float(sector_df["Return %"].min())), abs(float(sector_df["Return %"].max())), 0.001)

    figure = go.Figure(
        go.Bar(
            x=sector_df["Return %"],
            y=sector_df["Sector"],
            orientation="h",
            marker={
                "color": sector_df["Return %"],
                "colorscale": [
                    [0.0, NEGATIVE_DARK],
                    [0.5, "#F8FBFF"],
                    [1.0, POSITIVE_DARK],
                ],
                "cmin": -max_abs_return,
                "cmax": max_abs_return,
                "line": {"color": "#FFFFFF", "width": 0.6},
            },
            text=[format_percent(value) for value in sector_df["Return %"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Average return: %{x:.2%}<extra></extra>",
        )
    )
    apply_common_chart_layout(figure, "Sector Average Return")
    figure.update_xaxes(tickformat=".1%", title_text="Average Return %", zeroline=True, zerolinecolor="#C7D2E0")
    figure.update_yaxes(title_text=None)
    return figure


def apply_common_chart_layout(figure: go.Figure, title: str) -> None:
    """Apply the dashboard's shared Plotly layout settings.

    Args:
        figure: The Plotly figure to update in place.
        title: Chart title text.
    """
    figure.update_layout(
        title={"text": title, "x": 0.01, "xanchor": "left"},
        height=460,
        margin={"l": 10, "r": 10, "t": 56, "b": 24},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font={"color": TEXT_COLOR, "size": 13},
        title_font={"size": 18, "color": TEXT_COLOR},
        xaxis={"gridcolor": GRID_COLOR, "linecolor": GRID_COLOR},
        yaxis={"gridcolor": "#FFFFFF"},
        hoverlabel={"bgcolor": "#FFFFFF", "font": {"color": TEXT_COLOR}},
        showlegend=False,
    )


def make_color_gradient(start_hex: str, end_hex: str, count: int) -> list[str]:
    """Generate evenly spaced colors between two hex endpoints.

    Args:
        start_hex: Starting hex color such as ``"#D9F3E4"``.
        end_hex: Ending hex color such as ``"#14804A"``.
        count: Number of colors to produce.

    Returns:
        A list of Plotly-ready ``rgb(...)`` strings.
    """
    if count <= 1:
        return [end_hex]

    start_rgb = hex_to_rgb(start_hex)
    end_rgb = hex_to_rgb(end_hex)
    colors: list[str] = []

    for index in range(count):
        ratio = index / (count - 1)
        red = round(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio)
        green = round(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio)
        blue = round(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio)
        colors.append(f"rgb({red}, {green}, {blue})")

    return colors


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a six-digit hex color string to an RGB tuple.

    Args:
        hex_color: Color string such as ``"#14804A"``.

    Returns:
        A tuple of ``(red, green, blue)`` integer values.
    """
    hex_value = hex_color.lstrip("#")
    return tuple(int(hex_value[index : index + 2], 16) for index in (0, 2, 4))
