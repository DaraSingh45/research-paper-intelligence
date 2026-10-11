"""
app/components/style.py

The app's visual design system, applied once per page load from app/main.py.

Design approach: clean, quiet and professional.
  - Light theme, white canvas, a single restrained blue accent used only for
    primary actions, selection and focus. Everything else is neutral slate.
  - One sans-serif family for everything (system stack, no font CDN, so the
    UI renders identically offline -- consistent with the project's
    local-first, privacy-first positioning).
  - Hairline borders and generous whitespace instead of heavy fills/shadows.
  - Numbers use tabular figures so stat cards and tables line up.

Base colors also live in .streamlit/config.toml [theme] (Streamlit's own
theme engine only reads that file). Keep the two in sync. This module
handles everything the native theme can't reach (typography scale, chrome,
stat cards, badges).
"""
from __future__ import annotations

import html

import streamlit as st

# Keep in sync with .streamlit/config.toml [theme]
COLORS = {
    "bg": "#FFFFFF",
    "surface": "#F5F6F8",
    "surface_2": "#EEF0F4",
    "text": "#0F172A",
    "text_muted": "#64748B",
    "text_subtle": "#94A3B8",
    "accent": "#2952CC",
    "accent_soft": "#EEF2FC",
    "border": "#E4E7EC",
    "success": "#157F3D",
    "success_soft": "#EAF6EE",
    "warning": "#B25E09",
    "warning_soft": "#FDF3E7",
    "danger": "#B42318",
    "danger_soft": "#FDECEA",
}

SANS_STACK = (
    "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif"
)
MONO_STACK = "'SF Mono', 'JetBrains Mono', 'Cascadia Code', Menlo, Consolas, monospace"


def inject_base_styles() -> None:
    """Call once per page load (main.py does this before rendering the
    active page)."""
    c = COLORS
    st.markdown(
        f"""
        <style>
        :root {{
            --rpi-bg: {c['bg']};
            --rpi-surface: {c['surface']};
            --rpi-surface-2: {c['surface_2']};
            --rpi-text: {c['text']};
            --rpi-text-muted: {c['text_muted']};
            --rpi-text-subtle: {c['text_subtle']};
            --rpi-accent: {c['accent']};
            --rpi-accent-soft: {c['accent_soft']};
            --rpi-border: {c['border']};
            --rpi-success: {c['success']};
            --rpi-success-soft: {c['success_soft']};
            --rpi-warning: {c['warning']};
            --rpi-warning-soft: {c['warning_soft']};
            --rpi-danger: {c['danger']};
            --rpi-danger-soft: {c['danger_soft']};
            --rpi-radius: 10px;
        }}

        /* ---------- Chrome ---------- */
        #MainMenu, footer, [data-testid="stDecoration"] {{
            visibility: hidden;
            height: 0;
        }}
        [data-testid="stHeader"] {{ background: transparent; }}

        /* ---------- Layout ---------- */
        .block-container, [data-testid="stAppViewBlockContainer"] {{
            max-width: 1180px;
            padding-top: 2.2rem !important;
            padding-bottom: 4rem !important;
        }}

        /* ---------- Typography ---------- */
        html, body, [class*="css"], .stMarkdown, button, input, textarea, select {{
            font-family: {SANS_STACK};
        }}
        h1, h2, h3, h4 {{
            font-family: {SANS_STACK} !important;
            color: var(--rpi-text) !important;
            letter-spacing: -0.015em;
        }}
        h1 {{ font-size: 1.6rem !important; font-weight: 650 !important; padding: 0 !important; }}
        h2 {{ font-size: 1.2rem !important; font-weight: 600 !important; }}
        h3 {{ font-size: 1.02rem !important; font-weight: 600 !important; }}
        p, li {{ line-height: 1.55; }}
        [data-testid="stCaptionContainer"], .stCaption {{ color: var(--rpi-text-muted) !important; }}
        [data-testid="stWidgetLabel"] p {{
            font-size: 0.84rem !important;
            font-weight: 500 !important;
            color: #334155 !important;
        }}

        /* ---------- Page header ---------- */
        .rpi-header {{
            padding-bottom: 1rem;
            margin-bottom: 1.5rem;
            border-bottom: 1px solid var(--rpi-border);
        }}
        .rpi-header-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
        }}
        .rpi-header h1 {{ margin: 0 !important; }}
        .rpi-subtitle {{
            color: var(--rpi-text-muted);
            font-size: 0.93rem;
            margin-top: 0.3rem;
        }}

        /* ---------- Section heading ---------- */
        .rpi-section {{ margin: 0.25rem 0 0.75rem 0; }}
        .rpi-section-title {{
            font-size: 0.98rem;
            font-weight: 600;
            color: var(--rpi-text);
        }}
        .rpi-section-desc {{
            font-size: 0.84rem;
            color: var(--rpi-text-muted);
            margin-top: 0.1rem;
        }}

        /* ---------- Inputs ---------- */
        [data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{
            border-radius: 8px !important;
        }}

        /* ---------- Buttons ---------- */
        .stButton > button, .stDownloadButton > button, .stLinkButton > a {{
            border-radius: 8px !important;
            font-weight: 500 !important;
            min-height: 2.4rem;
            box-shadow: none !important;
        }}
        .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
            font-weight: 600 !important;
        }}

        /* ---------- Tabs ---------- */
        [data-baseweb="tab-list"] {{ gap: 1.25rem; border-bottom: 1px solid var(--rpi-border); }}
        [data-baseweb="tab"] {{ padding-left: 0 !important; padding-right: 0 !important; }}
        [data-baseweb="tab"] p {{ font-weight: 500; font-size: 0.9rem; }}

        /* ---------- Expanders ---------- */
        [data-testid="stExpander"] details {{
            border-radius: 10px !important;
            border-color: var(--rpi-border) !important;
        }}
        [data-testid="stExpander"] summary p {{ font-weight: 500; font-size: 0.9rem; }}

        /* ---------- Alerts: flatter, quieter ---------- */
        [data-testid="stAlert"] > div {{ border-radius: 10px; }}

        /* ---------- Dataframes ---------- */
        [data-testid="stDataFrame"] {{
            border: 1px solid var(--rpi-border);
            border-radius: 10px;
            overflow: hidden;
        }}

        /* ---------- Divider ---------- */
        hr {{
            border: none !important;
            border-top: 1px solid var(--rpi-border) !important;
            margin: 1.5rem 0 !important;
        }}

        /* ---------- Sidebar ---------- */
        [data-testid="stSidebar"] {{
            border-right: 1px solid var(--rpi-border);
        }}
        [data-testid="stSidebarNavLink"] {{
            border-radius: 8px;
            margin: 1px 0;
        }}
        [data-testid="stSidebarNavLink"] span {{ font-size: 0.9rem; }}
        /* Wordmark: shown at the very top of the sidebar, above the page
           menu. Streamlit renders the navigation before sidebar content, so
           the sidebar is turned into a flex column and our content is
           moved to the top with `order`. */
        [data-testid="stSidebarContent"] {{
            display: flex;
            flex-direction: column;
        }}
        [data-testid="stSidebarHeader"] {{ order: 0; }}
        [data-testid="stSidebarUserContent"] {{
            order: 1;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }}
        [data-testid="stSidebarNav"] {{ order: 2; }}
        [data-testid="stSidebarNavSeparator"] {{ display: none; }}
        /* Pull the wordmark up into the empty header row, beside the
           collapse arrow, so it sits in the top-left corner. */
        [data-testid="stSidebarHeader"] {{
            height: 0.75rem;
            min-height: 0;
            padding-top: 0.5rem;
            padding-bottom: 0;
            position: relative;
            z-index: 5;  /* keep the collapse arrow clickable above the wordmark */
        }}
        .rpi-brand {{
            pointer-events: none;  /* static text: let clicks reach the collapse arrow */
            padding: 0.35rem 0.25rem 1rem 0.25rem;
            margin: 0 0 1.4rem 0;
            border-bottom: 1px solid var(--rpi-border);
        }}
        .rpi-brand-name {{
            font-family: {SANS_STACK};
            font-weight: 800;
            font-size: 1.22rem;
            line-height: 1.15;
            letter-spacing: -0.025em;
            color: var(--rpi-text);
        }}
        .rpi-brand-name .rpi-brand-accent {{
            color: var(--rpi-accent);
        }}

        /* ---------- Stat cards ---------- */
        .rpi-stat-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 0.75rem;
            margin: 0.25rem 0 1.25rem 0;
        }}
        .rpi-stat {{
            border: 1px solid var(--rpi-border);
            border-radius: var(--rpi-radius);
            padding: 0.9rem 1rem;
            background: var(--rpi-bg);
            min-width: 0;
        }}
        .rpi-stat-label {{
            font-size: 0.72rem;
            font-weight: 600;
            color: var(--rpi-text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .rpi-stat-value {{
            font-size: 1.45rem;
            font-weight: 650;
            color: var(--rpi-text);
            line-height: 1.25;
            margin-top: 0.3rem;
            font-variant-numeric: tabular-nums;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .rpi-stat-value.rpi-stat-text {{ font-size: 0.98rem; font-weight: 550; white-space: normal; }}

        /* ---------- Identifiers ---------- */
        .rpi-mono {{
            font-family: {MONO_STACK};
            font-size: 0.82em;
            color: var(--rpi-text-muted);
            background: var(--rpi-surface);
            border: 1px solid var(--rpi-border);
            padding: 0.05rem 0.4rem;
            border-radius: 6px;
        }}

        /* ---------- Pills / badges ---------- */
        .rpi-pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 550;
            border: 1px solid transparent;
            white-space: nowrap;
        }}
        .rpi-pill::before {{
            content: "";
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: currentColor;
        }}
        .rpi-pill-ok      {{ background: var(--rpi-success-soft); color: var(--rpi-success); }}
        .rpi-pill-warn    {{ background: var(--rpi-danger-soft);  color: var(--rpi-danger); }}
        .rpi-pill-info    {{ background: var(--rpi-accent-soft);  color: var(--rpi-accent); }}
        .rpi-pill-caution {{ background: var(--rpi-warning-soft); color: var(--rpi-warning); }}
        .rpi-pill-neutral {{ background: var(--rpi-surface-2);    color: var(--rpi-text-muted); }}

        /* ---------- Key/value list (paper detail, settings) ---------- */
        .rpi-kv {{ display: grid; grid-template-columns: 170px 1fr; gap: 0.55rem 1rem; align-items: baseline; font-size: 0.9rem; }}
        .rpi-kv-key {{ color: var(--rpi-text-muted); font-size: 0.84rem; }}
        .rpi-kv-val {{ color: var(--rpi-text); font-size: 0.88rem; word-break: break-all; }}

        /* ---------- Health check rows ---------- */
        .rpi-health {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 1rem;
            padding: 0.8rem 0;
            border-bottom: 1px solid var(--rpi-border);
        }}
        .rpi-health:last-child {{ border-bottom: none; }}
        .rpi-health-name {{ font-weight: 600; font-size: 0.92rem; }}
        .rpi-health-msg {{ color: var(--rpi-text-muted); font-size: 0.84rem; margin-top: 0.15rem; }}

        /* ---------- Abstract text ---------- */
        .rpi-abstract {{
            font-size: 0.93rem;
            line-height: 1.65;
            color: #1E293B;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def rpi_page_header(title: str, subtitle: str | None = None, badge_html: str | None = None) -> None:
    """Page title + one-line muted subtitle with a hairline underneath.
    badge_html (optional) is rendered on the right of the title row."""
    sub = f'<div class="rpi-subtitle">{_esc(subtitle)}</div>' if subtitle else ""
    badge = f"<div>{badge_html}</div>" if badge_html else ""
    st.markdown(
        f'<div class="rpi-header"><div class="rpi-header-row"><h1>{_esc(title)}</h1>{badge}</div>{sub}</div>',
        unsafe_allow_html=True,
    )


def rpi_section(title: str, description: str | None = None) -> None:
    """A small section heading with an optional one-line description."""
    desc = f'<div class="rpi-section-desc">{_esc(description)}</div>' if description else ""
    st.markdown(
        f'<div class="rpi-section"><div class="rpi-section-title">{_esc(title)}</div>{desc}</div>',
        unsafe_allow_html=True,
    )


def rpi_sidebar_brand() -> None:
    """Text-only wordmark in the top-left corner of the sidebar."""
    st.markdown(
        '<div class="rpi-brand"><div class="rpi-brand-name">Research Paper '
        '<span class="rpi-brand-accent">Intelligence</span></div></div>',
        unsafe_allow_html=True,
    )


def rpi_stat_row(stats: list[tuple[str, str]]) -> None:
    """A row of stat cards. stats: list of (value, label).
    Long text values (e.g. category names) are rendered smaller automatically."""
    cards = []
    for value, label in stats:
        value_str = str(value)
        is_text = len(value_str) > 14 or any(ch.isalpha() for ch in value_str.replace(",", ""))
        cls = "rpi-stat-value rpi-stat-text" if is_text else "rpi-stat-value"
        cards.append(
            f'<div class="rpi-stat"><div class="rpi-stat-label">{_esc(label)}</div>'
            f'<div class="{cls}" title="{_esc(value_str)}">{_esc(value_str)}</div></div>'
        )
    st.markdown(f'<div class="rpi-stat-row">{"".join(cards)}</div>', unsafe_allow_html=True)


def rpi_mono(text: str) -> str:
    """Wraps an identifier (job id, DOI) in the monospace style for use
    inside other markdown strings."""
    return f'<span class="rpi-mono">{_esc(text)}</span>'


def rpi_pill(text: str, ok: bool | None = True, tone: str | None = None) -> str:
    """Small status badge. Either pass ok=True/False, or an explicit tone:
    'ok' | 'warn' | 'info' | 'caution' | 'neutral'."""
    if tone is None:
        tone = "ok" if ok else "warn"
    return f'<span class="rpi-pill rpi-pill-{tone}">{_esc(text)}</span>'


def rpi_status_pill(status: str) -> str:
    """Badge for a research job status."""
    tone = {
        "COMPLETED": "ok",
        "RUNNING": "info",
        "PENDING": "neutral",
        "FAILED": "warn",
        "CANCELLED": "neutral",
    }.get((status or "").upper(), "neutral")
    return rpi_pill((status or "unknown").capitalize(), tone=tone)
