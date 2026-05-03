"""
ORC Research Dashboard - Design System
Enterprise-grade, minimalist UI with full dark/light theme support.
Call apply_styles() at the top of every page (after set_page_config).
"""

import streamlit as st

# ── Colour palette ────────────────────────────────────────────────────────────
# WCAG AA-compliant contrast in both modes; inspired by GitHub's design system.

DARK = {
    "bg":       "#0d1117",
    "surface":  "#161b22",
    "surface2": "#21262d",
    "border":   "#30363d",
    "accent":   "#2f81f7",
    "accent2":  "#a371f7",
    "success":  "#3fb950",
    "warning":  "#d29922",
    "error":    "#f85149",
    "text":     "#e6edf3",
    "text2":    "#8b949e",
    "muted":    "#6e7681",
}

LIGHT = {
    "bg":       "#ffffff",
    "surface":  "#f6f8fa",
    "surface2": "#edf2f7",
    "border":   "#d0d7de",
    "accent":   "#0969da",
    "accent2":  "#8250df",
    "success":  "#1a7f37",
    "warning":  "#9a6700",
    "error":    "#cf222e",
    "text":     "#1f2328",
    "text2":    "#656d76",
    "muted":    "#6e7781",
}

# ── Theme-aware chart helpers ─────────────────────────────────────────────────

def get_theme() -> str:
    """Return 'dark' or 'light' based on session state (defaults to dark)."""
    return st.session_state.get("theme_mode", "dark")


def chart_colors() -> list:
    """Return ordered chart colours tuned for the active theme."""
    c = DARK if get_theme() == "dark" else LIGHT
    return [
        c["accent"], c["accent2"], c["success"], c["warning"],
        "#e11d48", "#0891b2", "#f97316", "#059669",
    ]


def chart_layout(title: str = "", height: int = 0) -> dict:
    """Return a Plotly layout dict that matches the active theme."""
    c = DARK if get_theme() == "dark" else LIGHT
    base = {
        "plot_bgcolor":  "rgba(0,0,0,0)",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "font":   {"color": c["text2"], "family": "Inter, system-ui, sans-serif", "size": 12},
        "xaxis":  {
            "gridcolor": c["border"], "linecolor": c["border"],
            "tickcolor": c["border"], "tickfont": {"color": c["text2"]},
            "title_font": {"color": c["text2"]},
        },
        "yaxis":  {
            "gridcolor": c["border"], "linecolor": c["border"],
            "tickcolor": c["border"], "tickfont": {"color": c["text2"]},
            "title_font": {"color": c["text2"]},
        },
        "legend": {"font": {"color": c["text2"]}, "bgcolor": "rgba(0,0,0,0)"},
        "margin": {"l": 8, "r": 8, "t": 36 if title else 12, "b": 8},
        "hoverlabel": {
            "bgcolor": c["surface2"], "font_color": c["text"],
            "bordercolor": c["border"],
        },
    }
    if title:
        base["title"] = {
            "text": title,
            "font": {"color": c["text"], "size": 14, "family": "Inter, sans-serif"},
            "x": 0, "xanchor": "left", "pad": {"l": 4},
        }
    if height:
        base["height"] = height
    return base


# ── Base CSS (theme-independent) ──────────────────────────────────────────────
_BASE_CSS = """
<style>
/* ── Hide Streamlit chrome ──────────────────────────── */
#MainMenu, footer, .stDeployButton { visibility: hidden !important; display: none !important; }
[data-testid="stToolbar"]          { display: none !important; }

/* ── Typography ─────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, sans-serif !important; }

/* ── Layout ─────────────────────────────────────────── */
.block-container { padding-top: 1.5rem !important; max-width: 1200px !important; }

/* ── Smooth transitions ─────────────────────────────── */
.stApp { transition: background-color 0.2s ease; }

/* ── Card ───────────────────────────────────────────── */
.orc-card {
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 0.75rem;
    transition: box-shadow 0.18s ease, transform 0.14s ease;
}
.orc-card:hover { transform: translateY(-1px); }

/* ── Metric card ─────────────────────────────────────── */
.orc-metric {
    border-radius: 8px;
    padding: 1.5rem 1.25rem;
    text-align: center;
    transition: transform 0.14s ease, box-shadow 0.18s ease;
}
.orc-metric:hover { transform: translateY(-2px); }
.orc-metric .orc-metric-icon { font-size: 1.4rem; margin-bottom: 0.45rem; opacity: 0.8; }
.orc-metric .orc-metric-val  {
    font-size: 1.9rem; font-weight: 700; line-height: 1.1;
    letter-spacing: -0.02em;
}
.orc-metric .orc-metric-lbl  {
    font-size: 0.7rem; font-weight: 600; margin-top: 0.3rem;
    text-transform: uppercase; letter-spacing: 0.07em; opacity: 0.55;
}

/* ── Publication card ───────────────────────────────── */
.orc-pub {
    border-radius: 8px;
    padding: 1rem 1.25rem 1rem 1.5rem;
    margin-bottom: 0.5rem;
    border-left: 3px solid transparent;
    transition: box-shadow 0.18s ease, transform 0.14s ease;
    position: relative;
}
.orc-pub:hover { transform: translateX(3px); }
.orc-pub .orc-pub-title { font-size: 0.95rem; font-weight: 600; margin: 0 0 0.3rem; line-height: 1.45; }
.orc-pub .orc-pub-meta  { font-size: 0.79rem; margin: 0.1rem 0 0; opacity: 0.72; }

/* ── Badges ─────────────────────────────────────────── */
.orc-badge {
    display: inline-block;
    font-size: 0.67rem; font-weight: 600;
    padding: 0.1rem 0.45rem;
    border-radius: 4px;
    margin-right: 0.25rem;
    text-transform: uppercase; letter-spacing: 0.04em;
    vertical-align: middle;
}

/* ── Hero ───────────────────────────────────────────── */
.orc-hero {
    border-radius: 10px;
    padding: 1.75rem 2rem;
    margin-bottom: 1.5rem;
    overflow: hidden;
}
.orc-hero h1 { font-size: 1.7rem; font-weight: 700; margin: 0 0 0.3rem; letter-spacing: -0.025em; }
.orc-hero p  { font-size: 0.875rem; margin: 0; font-weight: 400; opacity: 0.6; }

/* ── Status dot ─────────────────────────────────────── */
.orc-dot {
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; margin-right: 5px; vertical-align: middle;
}

/* ── Section heading ─────────────────────────────────── */
.orc-section-title {
    font-size: 0.7rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.1em;
    margin: 1.75rem 0 0.875rem;
    padding-bottom: 0.5rem;
}

/* ── Streamlit widget overrides ─────────────────────── */
hr { margin: 1.25rem 0 !important; }
[data-testid="stChatMessage"] { border-radius: 8px !important; }
[data-testid="stExpander"]    { border-radius: 8px !important; }
.streamlit-expanderHeader { font-size: 0.85rem !important; font-weight: 600 !important; }
[data-testid="stMetricValue"] {
    font-size: 1.75rem !important; font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.72rem !important; font-weight: 600 !important;
    text-transform: uppercase; letter-spacing: 0.06em !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 0; }
.stTabs [data-baseweb="tab"] {
    font-size: 0.85rem; font-weight: 500;
    padding: 0.55rem 1rem;
    border-radius: 6px 6px 0 0;
}

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 768px) {
    .orc-hero { padding: 1.25rem; }
    .orc-hero h1 { font-size: 1.35rem; }
    .orc-metric .orc-metric-val { font-size: 1.5rem; }
    .orc-pub { padding: 0.85rem 1rem 0.85rem 1.25rem; }
    .block-container { padding-top: 1rem !important; }
}
</style>
"""

# ── Dark-mode overrides ───────────────────────────────────────────────────────
_DARK_CSS = """
<style>
/* Global */
.stApp                                  {{ background-color: {bg}; }}
.stApp, .stApp p, .stApp span,
.stApp li, .stApp label                 {{ color: {text}; }}
.stApp h1,.stApp h2,.stApp h3,
.stApp h4,.stApp h5,.stApp h6           {{ color: {text} !important; }}

/* Streamlit chrome */
.stMetric label                         {{ color: {text2} !important; }}
.stMetric [data-testid="stMetricValue"] {{ color: {text}  !important; }}
[data-testid="stSidebar"]               {{ background-color: {surface}; border-right: 1px solid {border}; }}
hr                                      {{ border-color: {border} !important; opacity: 1 !important; }}

/* Inputs */
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea      {{ background: {surface2} !important; border-color: {border} !important; color: {text} !important; border-radius: 6px !important; }}
[data-baseweb="select"] > div           {{ background: {surface2} !important; color: {text}  !important; border-color: {border} !important; border-radius: 6px !important; }}
[data-baseweb="select"] li              {{ background: {surface2} !important; color: {text}  !important; }}
[data-baseweb="popover"] [role="option"] {{ background: {surface2} !important; color: {text}  !important; }}

/* Buttons */
.stButton > button                      {{ background: {surface2}; border: 1px solid {border}; color: {text}; font-weight: 500; border-radius: 6px; transition: border-color 0.15s, color 0.15s; }}
.stButton > button:hover                {{ border-color: {accent}; color: {accent}; }}
.stButton > button[kind="primary"]      {{ background: {accent}; border-color: {accent}; color: #ffffff; }}
.stButton > button[kind="primary"]:hover {{ opacity: 0.87; }}

/* Tabs */
.stTabs [data-baseweb="tab-list"]   {{ background: transparent; border-bottom: 1px solid {border}; }}
.stTabs [data-baseweb="tab"]        {{ color: {text2}; background: transparent; border-bottom: 2px solid transparent; margin-bottom: -1px; }}
.stTabs [aria-selected="true"]      {{ color: {accent} !important; border-bottom-color: {accent} !important; background: transparent !important; font-weight: 600 !important; }}

/* Expander */
.streamlit-expanderHeader           {{ color: {text} !important; }}
[data-testid="stExpander"]          {{ border: 1px solid {border}; background: {surface}; }}

/* Cards */
.orc-card    {{ background: {surface};  border: 1px solid {border}; box-shadow: 0 1px 3px rgba(1,4,9,.6); }}
.orc-metric  {{ background: {surface};  border: 1px solid {border}; box-shadow: 0 1px 3px rgba(1,4,9,.6); }}
.orc-metric .orc-metric-val {{ color: {text};  }}
.orc-metric .orc-metric-lbl {{ color: {text2}; }}
.orc-pub     {{ background: {surface};  border-left-color: {accent}; box-shadow: 0 1px 3px rgba(1,4,9,.4); }}
.orc-pub .orc-pub-title {{ color: {text};  }}
.orc-pub .orc-pub-meta  {{ color: {text2}; }}

/* Hero */
.orc-hero    {{ background: linear-gradient(135deg, {surface} 0%, {surface2} 100%); border: 1px solid {border}; }}
.orc-hero h1 {{ color: {text};  }}
.orc-hero p  {{ color: {text2}; }}

/* Badges */
.orc-badge-oa     {{ background: rgba(63,185,80,.12);  color: {success}; }}
.orc-badge-year   {{ background: rgba(47,129,247,.12); color: {accent};  }}
.orc-badge-cite   {{ background: rgba(163,113,247,.12);color: {accent2}; }}
.orc-badge-closed {{ background: rgba(110,118,129,.15);color: {muted};   }}

/* Section title */
.orc-section-title {{ color: {text2}; border-bottom: 1px solid {border}; }}
</style>
"""

# ── Light-mode overrides ──────────────────────────────────────────────────────
_LIGHT_CSS = """
<style>
/* Global */
.stApp                                  {{ background-color: {bg}; }}
.stApp, .stApp p, .stApp span,
.stApp li, .stApp label                 {{ color: {text}; }}
.stApp h1,.stApp h2,.stApp h3,
.stApp h4,.stApp h5,.stApp h6           {{ color: {text} !important; }}

/* Streamlit chrome */
.stMetric label                         {{ color: {text2} !important; }}
.stMetric [data-testid="stMetricValue"] {{ color: {text}  !important; }}
[data-testid="stSidebar"]               {{ background-color: {surface}; border-right: 1px solid {border}; }}
hr                                      {{ border-color: {border} !important; opacity: 1 !important; }}

/* Inputs */
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea      {{ background: {bg}     !important; border-color: {border} !important; color: {text} !important; border-radius: 6px !important; }}
[data-baseweb="select"] > div           {{ background: {bg}     !important; color: {text}   !important; border-color: {border} !important; border-radius: 6px !important; }}
[data-baseweb="select"] li              {{ background: {surface} !important; color: {text}  !important; }}
[data-baseweb="popover"] [role="option"] {{ background: {surface} !important; color: {text} !important; }}

/* Buttons */
.stButton > button                      {{ background: {bg}; border: 1px solid {border}; color: {text}; font-weight: 500; border-radius: 6px; transition: border-color 0.15s, color 0.15s, background 0.15s; }}
.stButton > button:hover                {{ border-color: {accent}; color: {accent}; background: {surface}; }}
.stButton > button[kind="primary"]      {{ background: {accent}; border-color: {accent}; color: #ffffff; }}
.stButton > button[kind="primary"]:hover {{ opacity: 0.88; }}

/* Tabs */
.stTabs [data-baseweb="tab-list"]   {{ background: transparent; border-bottom: 1px solid {border}; }}
.stTabs [data-baseweb="tab"]        {{ color: {text2}; background: transparent; border-bottom: 2px solid transparent; margin-bottom: -1px; }}
.stTabs [aria-selected="true"]      {{ color: {accent} !important; border-bottom-color: {accent} !important; background: transparent !important; font-weight: 600 !important; }}

/* Expander */
.streamlit-expanderHeader           {{ color: {text} !important; }}
[data-testid="stExpander"]          {{ border: 1px solid {border}; background: {surface}; }}

/* Cards */
.orc-card    {{ background: {surface};  border: 1px solid {border}; box-shadow: 0 1px 2px rgba(31,35,40,.06); }}
.orc-metric  {{ background: {surface};  border: 1px solid {border}; box-shadow: 0 1px 2px rgba(31,35,40,.06); }}
.orc-metric .orc-metric-val {{ color: {text};  }}
.orc-metric .orc-metric-lbl {{ color: {text2}; }}
.orc-pub     {{ background: {surface};  border-left-color: {accent}; box-shadow: 0 1px 2px rgba(31,35,40,.06); }}
.orc-pub .orc-pub-title {{ color: {text};  }}
.orc-pub .orc-pub-meta  {{ color: {text2}; }}

/* Hero */
.orc-hero    {{ background: linear-gradient(135deg, {surface} 0%, {surface2} 100%); border: 1px solid {border}; }}
.orc-hero h1 {{ color: {text};  }}
.orc-hero p  {{ color: {text2}; }}

/* Badges */
.orc-badge-oa     {{ background: rgba(26,127,55,.1);   color: {success}; }}
.orc-badge-year   {{ background: rgba(9,105,218,.1);   color: {accent};  }}
.orc-badge-cite   {{ background: rgba(130,80,223,.1);  color: {accent2}; }}
.orc-badge-closed {{ background: rgba(110,119,129,.1); color: {muted};   }}

/* Section title */
.orc-section-title {{ color: {text2}; border-bottom: 1px solid {border}; }}
</style>
"""


# ── Public API ────────────────────────────────────────────────────────────────

def apply_styles():
    """
    Inject global CSS into the current page.
    Must be called on every page after set_page_config().
    Also syncs the theme from query params so the toggle propagates.
    """
    params = st.query_params
    if "theme" in params:
        st.session_state.theme_mode = params["theme"]
    elif "theme_mode" not in st.session_state:
        st.session_state.theme_mode = "dark"

    theme  = get_theme()
    colors = DARK if theme == "dark" else LIGHT

    st.markdown(_BASE_CSS, unsafe_allow_html=True)
    st.markdown((_DARK_CSS if theme == "dark" else _LIGHT_CSS).format(**colors),
                unsafe_allow_html=True)


# ── HTML component helpers ────────────────────────────────────────────────────

def metric_card_html(icon: str, value: str, label: str) -> str:
    return (
        f'<div class="orc-metric">'
        f'  <div class="orc-metric-icon">{icon}</div>'
        f'  <div class="orc-metric-val">{value}</div>'
        f'  <div class="orc-metric-lbl">{label}</div>'
        f'</div>'
    )


def badge_html(text: str, kind: str = "year") -> str:
    """kind: 'oa' | 'year' | 'cite' | 'closed'"""
    return f'<span class="orc-badge orc-badge-{kind}">{text}</span>'


def pub_card_html(title: str, authors: list, journal: str, year,
                  citations: int, is_oa: bool, abstract: str = "") -> str:
    auth_html = ""
    if authors:
        shown = ", ".join(str(a) for a in authors[:3] if a)
        if len(authors) > 3:
            shown += f" +{len(authors) - 3}"
        auth_html = f'<div class="orc-pub-meta">👥 {shown}</div>'

    badges = ""
    if year:
        badges += badge_html(str(year), "year")
    badges += badge_html("Open Access", "oa") if is_oa else badge_html("Subscription", "closed")
    if citations:
        badges += badge_html(f"{citations:,} citations", "cite")

    abs_html = ""
    if abstract:
        snippet = abstract[:220] + ("…" if len(abstract) > 220 else "")
        abs_html = (
            f'<div class="orc-pub-meta" style="margin-top:0.5rem;font-style:italic;opacity:0.65">'
            f'{snippet}</div>'
        )

    return (
        f'<div class="orc-pub">'
        f'  <div class="orc-pub-title">{title}</div>'
        f'  {auth_html}'
        f'  <div class="orc-pub-meta" style="margin-top:0.3rem">📰 {journal}</div>'
        f'  <div style="margin-top:0.45rem">{badges}</div>'
        f'  {abs_html}'
        f'</div>'
    )


def hero_html(title: str, subtitle: str) -> str:
    return (
        f'<div class="orc-hero">'
        f'  <h1>{title}</h1>'
        f'  <p>{subtitle}</p>'
        f'</div>'
    )


def section_title_html(text: str) -> str:
    return f'<p class="orc-section-title">{text}</p>'


def theme_toggle_html() -> str:
    return "☀️ Light" if get_theme() == "dark" else "🌙 Dark"


def footer_html(extra: str = "") -> str:
    c = DARK if get_theme() == "dark" else LIGHT
    extra_line = f"<p style='margin:0.1rem 0 0'>{extra}</p>" if extra else ""
    return (
        f'<div style="text-align:center;color:{c["muted"]};font-size:0.78rem;padding:0.5rem 0 1rem">'
        f'  <p style="margin:0">ORC Research Dashboard · v1.0</p>'
        f'  {extra_line}'
        f'  <p style="margin:0.2rem 0 0">Built by '
        f'    <a href="https://www.linkedin.com/in/fahad-al-jubalie-55973926/" '
        f'       target="_blank" style="color:{c["accent"]};text-decoration:none;font-weight:500">'
        f'      Fahad Al-Jubalie</a>'
        f'  </p>'
        f'</div>'
    )
