"""
app/components/style.py

The app's visual design system, applied once from app/main.py.

Design approach: "a reading room, not a SaaS dashboard." The palette and
type pairing are chosen for a research-paper tool specifically, not a
generic dark-mode default:
  - A warm, muted brass/gold accent (not an acid-bright neon) evokes gilt
    lettering on a book spine or the desk lamp in a library reading room.
  - Headlines use a serif stack (evoking journal/book typesetting); UI and
    data use a clean sans stack (evoking the "engineering pipeline" half
    of the project). The two are kept deliberately distinct.
  - Fonts are system/OS stacks only -- no Google Fonts CDN call -- so the
    UI renders identically with zero network access, consistent with the
    project's local-first, privacy-first positioning.

Colors here are duplicated (not derived) from .streamlit/config.toml's
[theme] block, since Streamlit's own theme engine only reads that file;
this module's job is everything the native theme engine can't reach
(custom fonts, hiding default chrome, bespoke stat/choice cards).
"""
from __future__ import annotations

import streamlit as st

# Keep in sync with .streamlit/config.toml [theme]
COLORS = {
    "bg": "#12141C",
    "bg_elevated": "#1B1E29",
    "bg_elevated_2": "#232733",
    "text": "#E7E5DE",
    "text_muted": "#9B9A93",
    "accent": "#C9A227",
    "accent_soft": "rgba(201, 162, 39, 0.14)",
    "border": "#2A2E3C",
    "success": "#7FBF8A",
    "danger": "#D97A6C",
}

SERIF_STACK = "Georgia, 'Iowan Old Style', 'Palatino Linotype', 'Book Antiqua', serif"
SANS_STACK = (
    "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', "
    "Roboto, Helvetica, Arial, sans-serif"
)
MONO_STACK = "'IBM Plex Mono', 'SF Mono', 'Cascadia Code', Consolas, monospace"


def inject_base_styles() -> None:
    """Call once per page load (main.py does this before rendering the
    active page). Sets typography, hides default Streamlit chrome that
    makes the app look like a dev tool rather than a product, and defines
    CSS custom properties used by the HTML snippets below."""
    st.markdown(
        f"""
        <style>
        :root {{
            --rpi-bg: {COLORS['bg']};
            --rpi-bg-elevated: {COLORS['bg_elevated']};
            --rpi-bg-elevated-2: {COLORS['bg_elevated_2']};
            --rpi-text: {COLORS['text']};
            --rpi-text-muted: {COLORS['text_muted']};
            --rpi-accent: {COLORS['accent']};
            --rpi-accent-soft: {COLORS['accent_soft']};
            --rpi-border: {COLORS['border']};
            --rpi-success: {COLORS['success']};
            --rpi-danger: {COLORS['danger']};
            --rpi-radius: 10px;
        }}

        /* Hide Streamlit's default chrome (menu, footer, "Deploy" button)
           so this reads as a product, not a dev-mode app. */
        #MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {{
            visibility: hidden;
            height: 0;
        }}

        /* Headlines: serif, evokes journal/book typesetting */
        h1, h2, h3 {{
            font-family: {SERIF_STACK} !important;
            font-weight: 500 !important;
            letter-spacing: -0.01em;
        }}
        h1 {{ font-size: 1.9rem !important; margin-bottom: 0.15rem !important; }}
        h2 {{ font-size: 1.3rem !important; }}
        h3 {{ font-size: 1.05rem !important; }}

        /* Body/UI: clean sans throughout */
        html, body, [class*="css"] {{
            font-family: {SANS_STACK};
        }}

        /* Page subtitle convention: a single muted line right under an h1,
           produced by rpi_page_header() below. */
        .rpi-subtitle {{
            color: var(--rpi-text-muted);
            font-size: 0.92rem;
            margin-top: -0.35rem;
            margin-bottom: 1.1rem;
        }}

        /* Identifiers (job IDs, DOIs) get monospace -- functional, not decorative */
        .rpi-mono {{
            font-family: {MONO_STACK};
            font-size: 0.85em;
            color: var(--rpi-text-muted);
        }}

        /* Buttons: slightly tighter radius than Streamlit's default,
           consistent across primary/secondary */
        .stButton > button, .stDownloadButton > button, .stLinkButton > a {{
            border-radius: var(--rpi-radius) !important;
            font-weight: 500;
        }}

        /* Stat cards (see rpi_stat_row) */
        .rpi-stat-row {{
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
            margin-bottom: 0.5rem;
        }}
        .rpi-stat {{
            flex: 1 1 140px;
            border: 1px solid var(--rpi-border);
            border-radius: var(--rpi-radius);
            padding: 0.85rem 1rem;
            background: var(--rpi-bg-elevated);
        }}
        .rpi-stat .rpi-stat-value {{
            font-family: {SERIF_STACK};
            font-size: 1.7rem;
            color: var(--rpi-text);
            line-height: 1.15;
        }}
        .rpi-stat .rpi-stat-label {{
            font-size: 0.8rem;
            color: var(--rpi-text-muted);
            margin-top: 0.15rem;
        }}

        /* Choice cards (intensity picker, AI enrichment options) */
        .rpi-choice {{
            border: 1px solid var(--rpi-border);
            border-radius: var(--rpi-radius);
            padding: 0.9rem 1rem;
            background: var(--rpi-bg-elevated);
            height: 100%;
        }}
        .rpi-choice.rpi-choice-selected {{
            border-color: var(--rpi-accent);
            background: var(--rpi-accent-soft);
        }}
        .rpi-choice-title {{
            font-weight: 600;
            font-size: 0.95rem;
            margin-bottom: 0.2rem;
        }}
        .rpi-choice-desc {{
            font-size: 0.82rem;
            color: var(--rpi-text-muted);
            line-height: 1.35;
        }}

        /* Section dividers: hairline, quieter than Streamlit's default */
        hr {{
            border-color: var(--rpi-border) !important;
            margin: 1.1rem 0 !important;
        }}

        /* Sidebar wordmark block (see rpi_sidebar_brand) */
        .rpi-brand {{
            display: flex;
            align-items: baseline;
            gap: 0.45rem;
            margin-bottom: 0.1rem;
        }}
        .rpi-brand-mark {{
            color: var(--rpi-accent);
            font-family: {SERIF_STACK};
            font-size: 1.3rem;
        }}
        .rpi-brand-name {{
            font-family: {SERIF_STACK};
            font-size: 1.05rem;
            color: var(--rpi-text);
            line-height: 1.2;
        }}
        .rpi-brand-tagline {{
            color: var(--rpi-text-muted);
            font-size: 0.78rem;
            margin-bottom: 0.6rem;
        }}

        /* Status pill, used for source status / job status where a plain
           st.success/warning block would be too heavy */
        .rpi-pill {{
            display: inline-block;
            padding: 0.15rem 0.6rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 500;
        }}
        .rpi-pill-ok {{ background: rgba(127,191,138,0.15); color: var(--rpi-success); }}
        .rpi-pill-warn {{ background: rgba(217,122,108,0.15); color: var(--rpi-danger); }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def rpi_page_header(title: str, subtitle: str | None = None) -> None:
    """Consistent page title + one-line muted subtitle, replacing the
    ad-hoc mix of st.title/st.caption used previously."""
    st.markdown(f"# {title}")
    if subtitle:
        st.markdown(f'<div class="rpi-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def rpi_sidebar_brand() -> None:
    st.markdown(
        """
        <div class="rpi-brand">
            <span class="rpi-brand-mark">&#9679;</span>
            <span class="rpi-brand-name">Research Paper Intelligence</span>
        </div>
        <div class="rpi-brand-tagline">Local search &amp; analytics for academic papers</div>
        """,
        unsafe_allow_html=True,
    )


def rpi_stat_row(stats: list[tuple[str, str]]) -> None:
    """A row of stat cards. stats: list of (value, label)."""
    cards = "".join(
        f'<div class="rpi-stat"><div class="rpi-stat-value">{value}</div>'
        f'<div class="rpi-stat-label">{label}</div></div>'
        for value, label in stats
    )
    st.markdown(f'<div class="rpi-stat-row">{cards}</div>', unsafe_allow_html=True)


def rpi_mono(text: str) -> str:
    """Wraps an identifier (job id, DOI) in the monospace style for use
    inside other markdown strings."""
    return f'<span class="rpi-mono">{text}</span>'


def rpi_pill(text: str, ok: bool) -> str:
    cls = "rpi-pill-ok" if ok else "rpi-pill-warn"
    return f'<span class="rpi-pill {cls}">{text}</span>'
