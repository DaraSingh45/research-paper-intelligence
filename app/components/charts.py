"""
app/components/charts.py

Thin Plotly wrappers so every page renders charts with the same dark-theme
styling instead of re-specifying colors/layout each time.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ACCENT = "#C9A227"
PALETTE = ["#C9A227", "#6F9CEB", "#7FBF8A", "#D97A6C", "#9A7FD4", "#5EC7C0"]

_LAYOUT_DEFAULTS = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#E7E5DE",
    margin=dict(l=10, r=10, t=40, b=10),
)


def _style(fig: go.Figure, title: Optional[str] = None) -> go.Figure:
    fig.update_layout(**_LAYOUT_DEFAULTS)
    if title:
        fig.update_layout(title=title)
    fig.update_xaxes(gridcolor="#2A2E3C")
    fig.update_yaxes(gridcolor="#2A2E3C")
    return fig


def line_chart(df: pd.DataFrame, x: str, y: str, color: Optional[str] = None, title: Optional[str] = None) -> None:
    if df.empty:
        st.info("No data yet. Run a research job (and let dbt finish) to populate this chart.")
        return
    fig = px.line(df, x=x, y=y, color=color, markers=True, color_discrete_sequence=PALETTE)
    st.plotly_chart(_style(fig, title), use_container_width=True)


def bar_chart(
    df: pd.DataFrame, x: str, y: str, color: Optional[str] = None, title: Optional[str] = None, horizontal: bool = False
) -> None:
    if df.empty:
        st.info("No data yet. Run a research job (and let dbt finish) to populate this chart.")
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
    st.plotly_chart(_style(fig, title), use_container_width=True)


def pie_chart(df: pd.DataFrame, names: str, values: str, title: Optional[str] = None) -> None:
    if df.empty:
        st.info("No data yet. Run a research job (and let dbt finish) to populate this chart.")
        return
    fig = px.pie(df, names=names, values=values, color_discrete_sequence=PALETTE, hole=0.45)
    st.plotly_chart(_style(fig, title), use_container_width=True)


def histogram(df: pd.DataFrame, x: str, title: Optional[str] = None, nbins: int = 30) -> None:
    if df.empty:
        st.info("No data yet. Run a research job (and let dbt finish) to populate this chart.")
        return
    fig = px.histogram(df, x=x, nbins=nbins, color_discrete_sequence=[ACCENT])
    st.plotly_chart(_style(fig, title), use_container_width=True)
