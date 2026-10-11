"""
app/components/charts.py

Thin Plotly wrappers so every page renders charts with the same clean,
light styling instead of re-specifying colors/layout each time.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.components.style import COLORS

ACCENT = COLORS["accent"]
# Restrained categorical palette: accent blue first, then muted, distinct hues.
PALETTE = ["#2952CC", "#0F8B8D", "#D08C1F", "#7C5CC4", "#C2415D", "#64748B", "#3E9C5A", "#9C6B3E"]

_EMPTY_MESSAGE = "No data yet. Run a search (and let dbt finish) to populate this chart."

_LAYOUT_DEFAULTS = dict(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif", size=12, color="#334155"),
    margin=dict(l=8, r=8, t=16, b=8),
    height=320,
    hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=COLORS["border"], font_color=COLORS["text"]),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
)

_PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}


def _style(fig: go.Figure, title: Optional[str] = None) -> go.Figure:
    fig.update_layout(**_LAYOUT_DEFAULTS)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=14, color=COLORS["text"])), margin=dict(t=44))
    fig.update_xaxes(gridcolor="#EEF0F3", linecolor=COLORS["border"], zeroline=False, title_text="")
    fig.update_yaxes(gridcolor="#EEF0F3", linecolor=COLORS["border"], zeroline=False, title_text="")
    return fig


def _show(fig: go.Figure, title: Optional[str], **layout_overrides) -> None:
    fig = _style(fig, title)
    if layout_overrides:
        fig.update_layout(**layout_overrides)
    st.plotly_chart(fig, use_container_width=True, theme=None, config=_PLOTLY_CONFIG)


def line_chart(df: pd.DataFrame, x: str, y: str, color: Optional[str] = None, title: Optional[str] = None) -> None:
    if df.empty:
        st.caption(_EMPTY_MESSAGE)
        return
    fig = px.line(df, x=x, y=y, color=color, markers=True, color_discrete_sequence=PALETTE)
    fig.update_traces(line=dict(width=2), marker=dict(size=5))
    _show(fig, title)


def bar_chart(
    df: pd.DataFrame, x: str, y: str, color: Optional[str] = None, title: Optional[str] = None, horizontal: bool = False
) -> None:
    if df.empty:
        st.caption(_EMPTY_MESSAGE)
        return
    orientation = "h" if horizontal else "v"
    fig = px.bar(
        df,
        x=y if horizontal else x,
        y=x if horizontal else y,
        color=color,
        orientation=orientation,
        color_discrete_sequence=PALETTE,
    )
    fig.update_traces(marker_line_width=0)
    fig.update_layout(bargap=0.35)
    if horizontal:
        fig.update_yaxes(autorange="reversed")
    _show(fig, title)


def pie_chart(df: pd.DataFrame, names: str, values: str, title: Optional[str] = None) -> None:
    if df.empty:
        st.caption(_EMPTY_MESSAGE)
        return
    fig = px.pie(df, names=names, values=values, color_discrete_sequence=PALETTE, hole=0.6)
    fig.update_traces(textinfo="percent", marker=dict(line=dict(color="#FFFFFF", width=2)))
    _show(fig, title, legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02, title_text=""))


def histogram(df: pd.DataFrame, x: str, title: Optional[str] = None, nbins: int = 30) -> None:
    if df.empty:
        st.caption(_EMPTY_MESSAGE)
        return
    fig = px.histogram(df, x=x, nbins=nbins, color_discrete_sequence=[ACCENT])
    fig.update_traces(marker_line_width=0)
    fig.update_layout(bargap=0.08)
    _show(fig, title)
