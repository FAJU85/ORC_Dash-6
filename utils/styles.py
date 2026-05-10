"""
ORC Research Dashboard - Design System
Enterprise-grade, minimalist UI with full dark/light theme support.
Call apply_styles() at the top of every page (after set_page_config).
"""

import html as _html
import streamlit as st

# ── Colour palette ────────────────────────────────────────────────────────────
# ORC brand palette:
#   Steel Azure  #0C539F  — primary/accent
#   Carrot Orange #FA9F37  — warm accent / CTAs
#   Powder Blue  #B3CBE6  — surface tints & borders
#   Wisteria Blue #87A2D2  — secondary text & subtle accents
#   White        #FCFCFB  — base background (light mode)

DARK = {
    "bg":       "#08111e",
    "surface":  "#0d1c2e",
    "surface2": "#152843",
    "border":   "#1d3a58",
    "accent":   "#2e81d4",   # lightened Steel Azure for dark-bg readability
    "accent2":  "#FA9F37",   # Carrot Orange
    "success":  "#3fb950",
    "warning":  "#FA9F37",
    "error":    "#f85149",
    "text":     "#FCFCFB",   # White
    "text2":    "#87A2D2",   # Wisteria Blue
    "muted":    "#B3CBE6",   # Powder Blue
}

LIGHT = {
    "bg":       "#FCFCFB",   # White
    "surface":  "#eef3fa",
    "surface2": "#dce8f4",   # Powder Blue light
    "border":   "#B3CBE6",   # Powder Blue
    "accent":   "#0C539F",   # Steel Azure
    "accent2":  "#FA9F37",   # Carrot Orange
    "success":  "#1a7f37",
    "warning":  "#9a6700",
    "error":    "#cf222e",
    "text":     "#09152a",
    "text2":    "#3d6a9e",   # mid Steel Azure
    "muted":    "#87A2D2",   # Wisteria Blue
}

# ── Theme-aware chart helpers ─────────────────────────────────────────────────

def get_theme() -> str:
    """
    Determine the active UI theme mode from the Streamlit session.
    
    Returns:
        str: 'dark' or 'light' representing the active theme; defaults to 'dark' if no theme is set in session state.
    """
    return st.session_state.get("theme_mode", "dark")


def chart_colors() -> list:
    """
    Provide an ordered list of hex color strings for charts based on the active theme.
    
    Returns:
        colors (list): Ordered list of hex color strings — theme accent colors first, followed by a fixed set of fallback colors.
    """
    c = DARK if get_theme() == "dark" else LIGHT
    return [
        c["accent"], c["accent2"], c["success"], c["warning"],
        "#e11d48", "#0891b2", "#f97316", "#059669",
    ]


PLOTLY_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "toImageButtonOptions": {"format": "png", "filename": "orc_chart", "scale": 2},
}


def chart_layout(title: str = "", height: int = 0) -> dict:
    """
    Builds a Plotly layout dictionary configured for the current theme.
    
    Parameters:
        title (str): Optional chart title; when provided a left-aligned title block is added to the layout.
        height (int): Optional layout height in pixels; when non-zero the layout's `height` field is set.
    
    Returns:
        layout (dict): A Plotly-compatible layout dictionary with colors, fonts, axes, legend, margins, and hoverlabel styling matching the active theme.
    """
    c = DARK if get_theme() == "dark" else LIGHT
    base = {
        "plot_bgcolor":  c["surface"],
        "paper_bgcolor": c["surface"],
        "font":   {"color": c["text"], "family": "'Exo 2', system-ui, sans-serif", "size": 13},
        "xaxis":  {
            "gridcolor": c["border"], "linecolor": c["border"],
            "tickcolor": c["border"],
            "tickfont": {"color": c["text"], "size": 12},
            "title_font": {"color": c["text"], "size": 13},
        },
        "yaxis":  {
            "gridcolor": c["border"], "linecolor": c["border"],
            "tickcolor": c["border"],
            "tickfont": {"color": c["text"], "size": 12},
            "title_font": {"color": c["text"], "size": 13},
        },
        "legend": {"font": {"color": c["text"], "size": 12}, "bgcolor": "rgba(0,0,0,0)"},
        "margin": {"l": 8, "r": 8, "t": 36 if title else 12, "b": 8},
        "hoverlabel": {
            "bgcolor": c["surface2"], "font_color": c["text"],
            "bordercolor": c["border"],
        },
    }
    if title:
        base["title"] = {
            "text": title,
            "font": {"color": c["text"], "size": 15, "family": "'Exo 2', sans-serif"},
            "x": 0, "xanchor": "left", "pad": {"l": 4},
        }
    if height:
        base["height"] = height
    return base


# ── Base CSS (theme-independent) ──────────────────────────────────────────────
_BASE_CSS = """
<style>
/* ── Hide Streamlit chrome ──────────────────────────── */
#MainMenu, footer, .stDeployButton          { visibility: hidden !important; display: none !important; }
[data-testid="stToolbar"]                   { display: none !important; }
[data-testid="stHeader"]                    { display: none !important; }
[data-testid="stSidebarNav"]                { display: none !important; }
[data-testid="collapsedControl"]            { display: none !important; }
[data-testid="stSidebarCollapsedControl"]   { display: none !important; }
[data-testid="stSidebarOpenButton"]         { display: none !important; }
[data-testid="stDecoration"]                { display: none !important; }
button[aria-label="Open sidebar"]           { display: none !important; }
section[data-testid="stSidebar"]            { display: none !important; }

/* ── Google Fonts ───────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Baloo+Bhaijaan+2:wght@400;500;600;700;800&family=Exo+2:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500&family=Zain:wght@300;400;700&display=swap');

/* ── Material Symbols Outlined ──────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
.material-symbols-outlined {
    font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    font-size: 1.1em;
    vertical-align: middle;
    line-height: 1;
    user-select: none;
}

/* ── Typography ─────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Zain', 'Exo 2', system-ui, -apple-system, sans-serif !important;
}
h1, h2, h3, .orc-hero h1, .orc-nav-logo {
    font-family: 'Baloo Bhaijaan 2', 'Exo 2', sans-serif !important;
}
code, pre, kbd, samp,
[data-testid="stCode"], [data-testid="stChatMessage"] code,
[data-testid="stChatMessage"] pre {
    font-family: 'JetBrains Mono', 'Courier New', monospace !important;
}

/* ── Font zoom (driven by --orc-zoom CSS variable) ──── */
:root { --orc-zoom: 1; }
html  { font-size: calc(16px * var(--orc-zoom)); }

/* ── Layout ─────────────────────────────────────────── */
.block-container,
[data-testid="stMainBlockContainer"] { padding-top: 0.5rem !important; max-width: 1200px !important; }

/* ── Top navigation bar ─────────────────────────────── */
.orc-navbar {
    display: flex;
    align-items: center;
    gap: 0.15rem;
    padding: 0.35rem 0.75rem;
    margin: -0.5rem -1rem 1.25rem;
    border-bottom-width: 1px;
    border-bottom-style: solid;
    position: sticky;
    top: 0;
    z-index: 999;
    flex-wrap: wrap;
}
.orc-nav-logo {
    font-size: 0.95rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin-right: 0.75rem;
    padding-right: 0.75rem;
    border-right-width: 1px;
    border-right-style: solid;
    white-space: nowrap;
}
.orc-nav-item {
    text-decoration: none !important;
    padding: 0.3rem 0.6rem;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 500;
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    transition: background 0.15s, color 0.15s;
}
@media (max-width: 768px) {
    .orc-navbar { gap: 0.1rem; padding: 0.3rem 0.5rem; }
    .orc-nav-logo { display: none; }
    .orc-nav-item { padding: 0.25rem 0.4rem; font-size: 0.75rem; }
}

/* ── Card ───────────────────────────────────────────── */
.orc-card {
    border-radius: 12px;
    padding: 1.1rem 1.4rem;
    margin-bottom: 0.65rem;
    transition: box-shadow 0.2s;
}

/* ── Metric card ─────────────────────────────────────── */
.orc-metric {
    border-radius: 12px;
    padding: 1.4rem 1.1rem;
    text-align: center;
    transition: box-shadow 0.2s;
}
.orc-metric .orc-metric-icon { font-size: 1.3rem; margin-bottom: 0.4rem; opacity: 0.75; }
.orc-metric .orc-metric-val  {
    font-family: 'Exo 2', sans-serif;
    font-size: 1.85rem; font-weight: 700; line-height: 1.1;
    letter-spacing: -0.02em;
}
.orc-metric .orc-metric-lbl  {
    font-size: 0.68rem; font-weight: 600; margin-top: 0.3rem;
    text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.55;
}

/* ── Publication card ───────────────────────────────── */
.orc-pub {
    border-radius: 12px;
    padding: 0.9rem 1.1rem 0.9rem 1.4rem;
    margin-bottom: 0.45rem;
    border-left: 3px solid transparent;
    position: relative;
    transition: box-shadow 0.2s;
}
.orc-pub .orc-pub-title { font-size: 0.93rem; font-weight: 600; margin: 0 0 0.25rem; line-height: 1.45; }
.orc-pub .orc-pub-meta  { font-size: 0.77rem; margin: 0.1rem 0 0; opacity: 0.7; }

/* ── Badges ─────────────────────────────────────────── */
.orc-badge {
    display: inline-block;
    font-size: 0.67rem; font-weight: 600;
    padding: 0.1rem 0.45rem;
    border-radius: 6px;
    margin-right: 0.25rem;
    text-transform: uppercase; letter-spacing: 0.04em;
    vertical-align: middle;
}

/* ── Hero ───────────────────────────────────────────── */
.orc-hero {
    border-radius: 14px;
    padding: 1.75rem 2rem;
    margin-bottom: 1.5rem;
    overflow: hidden;
}
.orc-hero h1 {
    font-family: 'Baloo Bhaijaan 2', sans-serif;
    font-size: 1.8rem; font-weight: 700; margin: 0 0 0.3rem; letter-spacing: -0.02em;
}
.orc-hero p  { font-size: 0.9rem; margin: 0; font-weight: 400; opacity: 0.65; }

/* ── Status dot ─────────────────────────────────────── */
.orc-dot {
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; margin-right: 5px; vertical-align: middle;
}

/* ── Section heading ─────────────────────────────────── */
.orc-section-title {
    font-family: 'Exo 2', sans-serif;
    font-size: 0.7rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.1em;
    margin: 1.75rem 0 0.875rem;
    padding-bottom: 0.5rem;
}

/* ── Streamlit widget overrides ─────────────────────── */
hr { margin: 1.25rem 0 !important; }
[data-testid="stChatMessage"] { border-radius: 12px !important; }
[data-testid="stExpander"]    { border-radius: 12px !important; }
.streamlit-expanderHeader { font-size: 0.85rem !important; font-weight: 600 !important; }
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stChatInputContainer"],
[data-testid="stChatInputContainer"] > div { border-radius: 12px !important; }
[data-testid="stMetricValue"] {
    font-family: 'Exo 2', sans-serif !important;
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
    border-radius: 8px 8px 0 0;
}

/* Buttons — rounder for Material feel */
.stButton > button {
    border-radius: 8px !important;
    font-family: 'Exo 2', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    transition: box-shadow 0.15s, opacity 0.15s !important;
}

/* ── Page link navigation (st.page_link) ────────────── */
[data-testid="stPageLink"] { min-width: 0; }
[data-testid="stPageLink"] a {
    text-decoration: none !important;
    padding: 0.28rem 0.5rem !important;
    border-radius: 8px !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    white-space: nowrap !important;
    display: block !important;
    text-align: center !important;
    transition: background 0.15s, color 0.15s !important;
}
.orc-nav-logo {
    display: flex;
    align-items: center;
    padding: 0.35rem 0;
}

/* ── Font zoom controls ──────────────────────────────── */
.orc-zoom-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.78rem;
    opacity: 0.75;
}
.orc-zoom-bar button {
    padding: 0.15rem 0.5rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.8rem;
    line-height: 1.4;
}

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 768px) {
    .orc-hero { padding: 1.1rem; }
    .orc-hero h1 { font-size: 1.25rem; }
    .orc-hero p  { font-size: 0.8rem; }
    .orc-metric  { padding: 0.85rem 0.6rem; }
    .orc-metric .orc-metric-val  { font-size: 1.35rem; }
    .orc-metric .orc-metric-icon { font-size: 1.05rem; }
    .orc-pub { padding: 0.75rem 0.85rem 0.75rem 1rem; }
    .block-container { padding-top: 0.75rem !important; padding-left: 0.75rem !important; padding-right: 0.75rem !important; }
    .orc-card { padding: 0.75rem 0.9rem !important; }
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
    [data-testid="column"] { min-width: 45% !important; flex: 1 1 45% !important; }
    .stButton > button { min-height: 2.5rem !important; }
    .orc-nav-item { padding: 0.3rem 0.45rem !important; font-size: 0.72rem !important; }
    [data-testid="stPageLink"] a { font-size: 0.72rem !important; padding: 0.25rem 0.3rem !important; }
}
@media (max-width: 480px) {
    .orc-hero h1 { font-size: 1.1rem; }
    .orc-section-title { font-size: 0.65rem !important; }
}
</style>

<script>
/* Font-zoom: persist in localStorage, apply via CSS custom property */
(function () {{
    var STEP = 0.1, MIN = 1.0, MAX = 2.0, KEY = 'orc_font_zoom';
    var zoom = parseFloat(localStorage.getItem(KEY) || '1');
    zoom = Math.min(MAX, Math.max(MIN, zoom));
    document.documentElement.style.setProperty('--orc-zoom', zoom);
}})();
</script>
"""

# ── Dark-mode overrides ───────────────────────────────────────────────────────
_DARK_CSS = """
<style>
/* Global — covers all known Streamlit 1.x container selectors */
.stApp,
[data-testid="stApp"]                   {{ background-color: {bg} !important; color: {text} !important; }}
.stApp *, [data-testid="stApp"] *       {{ color: {text}; }}
.stApp p, .stApp span,
.stApp li, .stApp label                 {{ color: {text} !important; }}
.stApp h1,.stApp h2,.stApp h3,
.stApp h4,.stApp h5,.stApp h6           {{ color: {text} !important; }}
[data-testid="stAppViewContainer"]      {{ background-color: {bg} !important; }}
[data-testid="stMain"]                  {{ background-color: {bg} !important; }}
[data-testid="stMainBlockContainer"]    {{ background-color: {bg} !important; }}
.main, .main .block-container           {{ background-color: {bg} !important; }}
body                                    {{ background-color: {bg} !important; }}

/* Streamlit chrome */
.stMetric label                         {{ color: {text2} !important; }}
.stMetric [data-testid="stMetricValue"] {{ color: {text}  !important; }}
[data-testid="stSidebar"]               {{ background-color: {surface} !important; border-right: 1px solid {border}; }}
hr                                      {{ border-color: {border} !important; opacity: 1 !important; }}

/* Inputs */
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea      {{ background: {surface2} !important; border-color: {border} !important; color: {text} !important; border-radius: 8px !important; }}
[data-baseweb="select"] > div           {{ background: {surface2} !important; color: {text}  !important; border-color: {border} !important; border-radius: 8px !important; }}
[data-baseweb="select"] li              {{ background: {surface2} !important; color: {text}  !important; }}
[data-baseweb="popover"] [role="option"] {{ background: {surface2} !important; color: {text}  !important; }}

/* Buttons */
.stButton > button                      {{ background: {surface2} !important; border: 1px solid {border} !important; color: {text} !important; font-weight: 500 !important; }}
.stButton > button:hover                {{ border-color: {accent2} !important; color: {accent2} !important; box-shadow: 0 2px 8px rgba(250,159,55,.18) !important; }}
.stButton > button[kind="primary"]      {{ background: {accent} !important; border-color: {accent} !important; color: #ffffff !important; }}
.stButton > button[kind="primary"]:hover {{ opacity: 0.87 !important; box-shadow: 0 3px 10px rgba(46,129,212,.35) !important; }}
[data-testid="stFormSubmitButton"] > button {{ background: {accent} !important; border-color: {accent} !important; color: #ffffff !important; }}

/* Download button */
[data-testid="stDownloadButton"] > button {{ background: {accent2} !important; border-color: {accent2} !important; color: #ffffff !important; font-weight: 500 !important; }}

/* Tabs */
.stTabs [data-baseweb="tab-list"]   {{ background: transparent !important; border-bottom: 1px solid {border}; }}
.stTabs [data-baseweb="tab"]        {{ color: {text2} !important; background: transparent !important; border-bottom: 2px solid transparent; margin-bottom: -1px; }}
.stTabs [aria-selected="true"]      {{ color: {accent} !important; border-bottom-color: {accent} !important; background: transparent !important; font-weight: 600 !important; }}

/* Expander */
.streamlit-expanderHeader           {{ color: {text} !important; }}
[data-testid="stExpander"]          {{ border: 1px solid {border} !important; background: {surface} !important; border-radius: 12px !important; }}

/* Cards */
.orc-card    {{ background: {surface} !important; color: {text} !important; border: 1px solid {border}; box-shadow: 0 2px 8px rgba(1,4,9,.4); }}
.orc-card *  {{ color: {text} !important; }}
.orc-metric  {{ background: {surface} !important;  border: 1px solid {border}; box-shadow: 0 2px 8px rgba(1,4,9,.4); }}
.orc-metric .orc-metric-val {{ color: {text};  }}
.orc-metric .orc-metric-lbl {{ color: {text2}; }}
.orc-pub     {{ background: {surface} !important;  border-left-color: {accent}; box-shadow: 0 1px 4px rgba(1,4,9,.3); }}
.orc-pub .orc-pub-title {{ color: {text};  }}
.orc-pub .orc-pub-meta  {{ color: {text2}; }}

/* Hero — Steel Azure gradient */
.orc-hero    {{ background: linear-gradient(135deg, {surface} 0%, #0e2240 60%, #152843 100%) !important; border: 1px solid {border}; }}
.orc-hero h1 {{ color: {text} !important;  }}
.orc-hero p  {{ color: {text2} !important; }}

/* Badges */
.orc-badge-oa     {{ background: rgba(63,185,80,.14);   color: {success}; }}
.orc-badge-year   {{ background: rgba(46,129,212,.18);  color: {accent};  }}
.orc-badge-cite   {{ background: rgba(250,159,55,.18);  color: {accent2}; }}
.orc-badge-closed {{ background: rgba(135,162,210,.12); color: {muted};   }}

/* Section title */
.orc-section-title {{ color: {text2} !important; border-bottom: 1px solid {border}; }}

/* Alert/info boxes */
[data-testid="stAlert"]             {{ border-radius: 10px !important; }}

/* Chat input bar */
[data-testid="stBottom"]            {{ background: {bg} !important; }}
[data-testid="stBottom"] > div      {{ background: {bg} !important; }}
[data-testid="stChatInputContainer"]       {{ background: {surface} !important; border: 1px solid {border} !important; border-radius: 12px !important; }}
[data-testid="stChatInputContainer"] textarea {{ background: {surface} !important; color: {text} !important; }}

/* Chat messages */
[data-testid="stChatMessage"]       {{ background: {surface} !important; }}
[data-testid="stChatMessage"] *     {{ color: {text} !important; }}
[data-testid="stChatMessage"] code  {{ background: {surface2} !important; border-radius: 4px !important; padding: 0.1rem 0.35rem !important; }}
[data-testid="stChatMessage"] pre   {{ background: {surface2} !important; border-radius: 8px !important; padding: 0.65rem !important; }}

/* Markdown containers */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] strong,
[data-testid="stMarkdownContainer"] em     {{ color: {text} !important; }}
[data-testid="stText"]                     {{ color: {text} !important; }}
[data-testid="stCaption"]                  {{ color: {text2} !important; }}

/* Dropdown popover items */
[data-baseweb="menu"]                      {{ background: {surface2} !important; }}
[data-baseweb="menu"] li,
[data-baseweb="option"]                    {{ background: {surface2} !important; color: {text} !important; }}

/* Toggle / checkbox labels */
[data-testid="stToggle"] label,
[data-testid="stCheckbox"] label,
[data-testid="stRadio"] label              {{ color: {text} !important; }}

/* Select slider value */
[data-testid="stSlider"] [data-testid="stTickBarMin"],
[data-testid="stSlider"] [data-testid="stTickBarMax"] {{ color: {text2} !important; }}

/* Navbar */
.orc-navbar  {{ background: {surface} !important; border-bottom-color: {border}; }}
.orc-nav-logo {{ color: {text} !important; border-right-color: {border}; }}
.orc-nav-item {{ color: {text2} !important; }}
.orc-nav-item:hover {{ background: {surface2} !important; color: {text} !important; }}
.orc-nav-item.active {{ background: {surface2} !important; color: {accent} !important; font-weight: 600; }}

/* Icon / emoji containers — ensure contrast */
.orc-metric .orc-metric-icon {{ filter: none; }}
.orc-dot {{ border: 1px solid rgba(255,255,255,0.1); }}

/* Page link nav (st.page_link) */
[data-testid="stPageLink"] a {{ color: {text2} !important; }}
[data-testid="stPageLink"] a:hover {{ background: {surface2} !important; color: {text} !important; }}
[data-testid="stPageLink"] a[aria-current="page"] {{
    background: {surface2} !important;
    color: {accent} !important;
    font-weight: 600 !important;
}}

/* ── Chat bubbles ── */
[data-testid="stChatMessage"] {{
    background: transparent !important;
    border: none !important;
    padding: 0.25rem 0 !important;
}}
[data-testid="stChatMessage"][data-testid*="user"] .stMarkdown,
[data-testid="stChatMessageContent"] {{
    background: transparent;
}}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) .stMarkdown p,
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) .stMarkdown {{
    background: {accent} !important;
    color: #FCFCFB !important;
    border-radius: 18px 18px 4px 18px;
    padding: 0.65rem 1rem !important;
    margin-left: auto;
    max-width: 82%;
    word-break: break-word;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
}}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) .stMarkdown {{
    background: {surface2} !important;
    color: {text} !important;
    border-radius: 18px 18px 18px 4px;
    padding: 0.65rem 1rem !important;
    max-width: 88%;
    word-break: break-word;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}}
[data-testid="stChatInput"] {{
    border-radius: 24px !important;
    border: 1.5px solid {border} !important;
    background: {surface} !important;
}}
[data-testid="stChatInput"] textarea {{
    background: transparent !important;
    color: {text} !important;
    font-family: 'Zain', sans-serif !important;
    font-size: calc(0.95rem * var(--orc-zoom)) !important;
}}
</style>
"""

# ── Light-mode overrides ──────────────────────────────────────────────────────
_LIGHT_CSS = """
<style>
/* Global — covers all known Streamlit 1.x container selectors */
.stApp,
[data-testid="stApp"]                   {{ background-color: {bg} !important; color: {text} !important; }}
.stApp *, [data-testid="stApp"] *       {{ color: {text}; }}
.stApp p, .stApp span,
.stApp li, .stApp label                 {{ color: {text} !important; }}
.stApp h1,.stApp h2,.stApp h3,
.stApp h4,.stApp h5,.stApp h6           {{ color: {text} !important; }}
[data-testid="stAppViewContainer"]      {{ background-color: {bg} !important; }}
[data-testid="stMain"]                  {{ background-color: {bg} !important; }}
[data-testid="stMainBlockContainer"]    {{ background-color: {bg} !important; }}
.main, .main .block-container           {{ background-color: {bg} !important; }}
body                                    {{ background-color: {bg} !important; }}

/* Streamlit chrome */
.stMetric label                         {{ color: {text2} !important; }}
.stMetric [data-testid="stMetricValue"] {{ color: {text}  !important; }}
[data-testid="stSidebar"]               {{ background-color: {surface} !important; border-right: 1px solid {border}; }}
hr                                      {{ border-color: {border} !important; opacity: 1 !important; }}

/* Inputs */
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea      {{ background: {bg}     !important; border-color: {border} !important; color: {text} !important; border-radius: 8px !important; }}
[data-baseweb="select"] > div           {{ background: {bg}     !important; color: {text}   !important; border-color: {border} !important; border-radius: 8px !important; }}
[data-baseweb="select"] li              {{ background: {surface} !important; color: {text}  !important; }}
[data-baseweb="popover"] [role="option"] {{ background: {surface} !important; color: {text} !important; }}

/* Buttons */
.stButton > button                      {{ background: {bg} !important; border: 1px solid {border} !important; color: {text} !important; font-weight: 500 !important; }}
.stButton > button:hover                {{ border-color: {accent2} !important; color: {accent2} !important; background: {surface} !important; box-shadow: 0 2px 6px rgba(250,159,55,.2) !important; }}
.stButton > button[kind="primary"]      {{ background: {accent} !important; border-color: {accent} !important; color: #ffffff !important; }}
.stButton > button[kind="primary"]:hover {{ opacity: 0.88 !important; box-shadow: 0 3px 10px rgba(12,83,159,.3) !important; }}
[data-testid="stFormSubmitButton"] > button {{ background: {accent} !important; border-color: {accent} !important; color: #ffffff !important; }}

/* Download button */
[data-testid="stDownloadButton"] > button {{ background: {accent2} !important; border-color: {accent2} !important; color: #ffffff !important; font-weight: 500 !important; }}

/* Tabs */
.stTabs [data-baseweb="tab-list"]   {{ background: transparent !important; border-bottom: 1px solid {border}; }}
.stTabs [data-baseweb="tab"]        {{ color: {text2} !important; background: transparent !important; border-bottom: 2px solid transparent; margin-bottom: -1px; }}
.stTabs [aria-selected="true"]      {{ color: {accent} !important; border-bottom-color: {accent} !important; background: transparent !important; font-weight: 600 !important; }}

/* Expander */
.streamlit-expanderHeader           {{ color: {text} !important; }}
[data-testid="stExpander"]          {{ border: 1px solid {border} !important; background: {surface} !important; border-radius: 12px !important; }}

/* Cards */
.orc-card    {{ background: {surface} !important; color: {text} !important; border: 1px solid {border}; box-shadow: 0 1px 4px rgba(12,83,159,.08); }}
.orc-card *  {{ color: {text} !important; }}
.orc-metric  {{ background: {surface} !important;  border: 1px solid {border}; box-shadow: 0 1px 4px rgba(12,83,159,.08); }}
.orc-metric .orc-metric-val {{ color: {text};  }}
.orc-metric .orc-metric-lbl {{ color: {text2}; }}
.orc-pub     {{ background: {surface} !important;  border-left-color: {accent}; box-shadow: 0 1px 3px rgba(12,83,159,.06); }}
.orc-pub .orc-pub-title {{ color: {text};  }}
.orc-pub .orc-pub-meta  {{ color: {text2}; }}

/* Hero — light Powder Blue gradient */
.orc-hero    {{ background: linear-gradient(135deg, {surface} 0%, {surface2} 100%) !important; border: 1px solid {border}; }}
.orc-hero h1 {{ color: {text} !important;  }}
.orc-hero p  {{ color: {text2} !important; }}

/* Badges */
.orc-badge-oa     {{ background: rgba(26,127,55,.1);    color: {success}; }}
.orc-badge-year   {{ background: rgba(12,83,159,.1);    color: {accent};  }}
.orc-badge-cite   {{ background: rgba(250,159,55,.15);  color: #a05800;   }}
.orc-badge-closed {{ background: rgba(135,162,210,.15); color: {muted};   }}

/* Section title */
.orc-section-title {{ color: {text2} !important; border-bottom: 1px solid {border}; }}

/* Alert/info boxes */
[data-testid="stAlert"]             {{ border-radius: 10px !important; }}

/* Chat input bar */
[data-testid="stBottom"]            {{ background: {bg} !important; }}
[data-testid="stBottom"] > div      {{ background: {bg} !important; }}
[data-testid="stChatInputContainer"]       {{ background: {surface} !important; border: 1px solid {border} !important; border-radius: 12px !important; }}
[data-testid="stChatInputContainer"] textarea {{ background: {surface} !important; color: {text} !important; }}

/* Chat messages */
[data-testid="stChatMessage"]       {{ background: {surface} !important; }}
[data-testid="stChatMessage"] *     {{ color: {text} !important; }}
[data-testid="stChatMessage"] code  {{ background: {surface2} !important; border-radius: 4px !important; padding: 0.1rem 0.35rem !important; }}
[data-testid="stChatMessage"] pre   {{ background: {surface2} !important; border-radius: 8px !important; padding: 0.65rem !important; }}

/* Markdown containers */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] strong,
[data-testid="stMarkdownContainer"] em     {{ color: {text} !important; }}
[data-testid="stText"]                     {{ color: {text} !important; }}
[data-testid="stCaption"]                  {{ color: {text2} !important; }}

/* Dropdown popover items */
[data-baseweb="menu"]                      {{ background: {surface2} !important; }}
[data-baseweb="menu"] li,
[data-baseweb="option"]                    {{ background: {surface2} !important; color: {text} !important; }}

/* Toggle / checkbox / radio labels */
[data-testid="stToggle"] label,
[data-testid="stCheckbox"] label,
[data-testid="stRadio"] label              {{ color: {text} !important; }}

/* Navbar — light mode */
.orc-navbar  {{ background: {surface} !important; border-bottom-color: {border}; }}
.orc-nav-logo {{ color: {text} !important; border-right-color: {border}; }}
.orc-nav-item {{ color: {text2} !important; }}
.orc-nav-item:hover {{ background: {surface2} !important; color: {text} !important; }}
.orc-nav-item.active {{ background: {surface2} !important; color: {accent} !important; font-weight: 600; }}

/* Icon / emoji containers — light-mode contrast */
.orc-dot {{ border: 1px solid rgba(0,0,0,0.08); }}

/* Page link nav (st.page_link) */
[data-testid="stPageLink"] a {{ color: {text2} !important; }}
[data-testid="stPageLink"] a:hover {{ background: {surface2} !important; color: {text} !important; }}
[data-testid="stPageLink"] a[aria-current="page"] {{
    background: {surface2} !important;
    color: {accent} !important;
    font-weight: 600 !important;
}}

/* ── Chat bubbles ── */
[data-testid="stChatMessage"] {{
    background: transparent !important;
    border: none !important;
    padding: 0.25rem 0 !important;
}}
[data-testid="stChatMessage"][data-testid*="user"] .stMarkdown,
[data-testid="stChatMessageContent"] {{
    background: transparent;
}}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) .stMarkdown p,
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) .stMarkdown {{
    background: {accent} !important;
    color: #1a1a2e !important;
    border-radius: 18px 18px 4px 18px;
    padding: 0.65rem 1rem !important;
    margin-left: auto;
    max-width: 82%;
    word-break: break-word;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
}}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) .stMarkdown {{
    background: {surface2} !important;
    color: {text} !important;
    border-radius: 18px 18px 18px 4px;
    padding: 0.65rem 1rem !important;
    max-width: 88%;
    word-break: break-word;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}}
[data-testid="stChatInput"] {{
    border-radius: 24px !important;
    border: 1.5px solid {border} !important;
    background: {surface} !important;
}}
[data-testid="stChatInput"] textarea {{
    background: transparent !important;
    color: {text} !important;
    font-family: 'Zain', sans-serif !important;
    font-size: calc(0.95rem * var(--orc-zoom)) !important;
}}
</style>
"""


# ── Public API ────────────────────────────────────────────────────────────────

def apply_styles() -> None:
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
    # Re-apply zoom from localStorage on every navigation (SPA page switches reset the DOM)
    st.markdown(
        "<script>(function(){var z=parseFloat(localStorage.getItem('orc_font_zoom')||'1');"
        "z=Math.min(2,Math.max(1,z));"
        "document.documentElement.style.setProperty('--orc-zoom',z);})();</script>",
        unsafe_allow_html=True,
    )


def render_font_zoom_controls() -> None:
    """Render +/- zoom buttons that persist font size (100–200%) in localStorage."""
    c = DARK if get_theme() == "dark" else LIGHT
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:0.5rem;'
        f'font-size:0.78rem;color:{c["text2"]};margin-bottom:0.5rem">'
        f'<span>Text size</span>'
        f'<button onclick="(function(){{'
        f'var k=\'orc_font_zoom\',s=0.1,mn=1,mx=2;'
        f'var z=Math.max(mn,parseFloat(localStorage.getItem(k)||\'1\')-s);'
        f'localStorage.setItem(k,z.toFixed(1));'
        f'document.documentElement.style.setProperty(\'--orc-zoom\',z);'
        f'}})()" style="padding:0.15rem 0.55rem;border-radius:6px;cursor:pointer;'
        f'background:{c["surface2"]};border:1px solid {c["border"]};color:{c["text"]}">'
        f'A−</button>'
        f'<button onclick="(function(){{'
        f'var k=\'orc_font_zoom\',s=0.1,mn=1,mx=2;'
        f'var z=Math.min(mx,parseFloat(localStorage.getItem(k)||\'1\')+s);'
        f'localStorage.setItem(k,z.toFixed(1));'
        f'document.documentElement.style.setProperty(\'--orc-zoom\',z);'
        f'}})()" style="padding:0.15rem 0.55rem;border-radius:6px;cursor:pointer;'
        f'background:{c["surface2"]};border:1px solid {c["border"]};color:{c["text"]}">'
        f'A+</button>'
        f'<button onclick="(function(){{'
        f'localStorage.setItem(\'orc_font_zoom\',\'1\');'
        f'document.documentElement.style.setProperty(\'--orc-zoom\',1);'
        f'}})()" style="padding:0.15rem 0.45rem;border-radius:6px;cursor:pointer;'
        f'background:{c["surface2"]};border:1px solid {c["border"]};color:{c["text2"]};font-size:0.72rem">'
        f'reset</button>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── HTML component helpers ────────────────────────────────────────────────────

def metric_card_html(icon: str, value: str, label: str) -> str:
    """
    Generate an HTML snippet for a compact metric card containing an icon, value, and label.
    
    Parameters:
        icon (str): HTML or plain text to render as the metric icon (e.g., emoji, SVG, or icon markup).
        value (str): Primary metric value to display; may include simple HTML.
        label (str): Secondary label or description for the metric; may include simple HTML.
    
    Returns:
        str: A small HTML block for an `.orc-metric` card ready to render with `unsafe_allow_html`.
    """
    return (
        f'<div class="orc-metric">'
        f'  <div class="orc-metric-icon">{icon}</div>'
        f'  <div class="orc-metric-val">{value}</div>'
        f'  <div class="orc-metric-lbl">{label}</div>'
        f'</div>'
    )


def badge_html(text: str, kind: str = "year") -> str:
    """
    Produce an HTML span element styled as a badge.
    
    Parameters:
        text (str): Visible text to place inside the badge.
        kind (str): Badge variant; one of `'oa'`, `'year'`, `'cite'`, or `'closed'`. This selects the `orc-badge-{kind}` CSS modifier.
    
    Returns:
        html (str): HTML string for a `<span>` element with classes `orc-badge` and `orc-badge-{kind}` containing `text`.
    """
    return f'<span class="orc-badge orc-badge-{kind}">{text}</span>'


def _esc(v) -> str:
    from html import escape
    return escape("" if v is None else str(v), quote=True)


def _safe_title(v) -> str:
    """Escape HTML but preserve <sub> and <sup> tags (chemical formulas, etc.)."""
    from html import escape
    safe = escape("" if v is None else str(v), quote=False)
    safe = safe.replace("&lt;sub&gt;", "<sub>").replace("&lt;/sub&gt;", "</sub>")
    safe = safe.replace("&lt;sup&gt;", "<sup>").replace("&lt;/sup&gt;", "</sup>")
    return safe


def pub_card_html(title: str, authors: list, journal: str, year,
                  citations: int, is_oa: bool, abstract: str = "") -> str:
    auth_html = ""
    if authors:
        shown = ", ".join(_esc(a) for a in authors[:3] if a)
        if len(authors) > 3:
            shown += f" +{len(authors) - 3}"
        auth_html = f'<div class="orc-pub-meta">👥 {shown}</div>'

    badges = ""
    if year:
        badges += badge_html(_esc(year), "year")
    badges += badge_html("Open Access", "oa") if is_oa else badge_html("Subscription", "closed")
    if citations:
        badges += badge_html(f"{citations:,} citations", "cite")

    abs_html = ""
    if abstract:
        snippet = _esc(abstract[:220]) + ("…" if len(abstract) > 220 else "")
        abs_html = (
            f'<div class="orc-pub-meta" style="margin-top:0.5rem;font-style:italic;opacity:0.65">'
            f'{snippet}</div>'
        )

    return (
        f'<div class="orc-pub">'
        f'  <div class="orc-pub-title">{_safe_title(title)}</div>'
        f'  {auth_html}'
        f'  <div class="orc-pub-meta" style="margin-top:0.3rem">📰 {_esc(journal)}</div>'
        f'  <div style="margin-top:0.45rem">{badges}</div>'
        f'  {abs_html}'
        f'</div>'
    )


def hero_html(title: str, subtitle: str) -> str:
    """
    Render a hero section as an HTML string containing a title and subtitle.
    
    Parameters:
        title (str): The heading text for the hero section.
        subtitle (str): The descriptive subtitle or subheading text.
    
    Returns:
        html (str): HTML markup for a `.orc-hero` block with the given title and subtitle.
    """
    return (
        f'<div class="orc-hero">'
        f'  <h1>{title}</h1>'
        f'  <p>{subtitle}</p>'
        f'</div>'
    )


def section_title_html(text: str) -> str:
    """
    Create an HTML paragraph element styled as a section title.
    
    Returns:
        An HTML string for a <p> element with class "orc-section-title" containing the provided text.
    """
    return f'<p class="orc-section-title">{text}</p>'


def theme_toggle_html() -> str:
    return "☀️ Light" if get_theme() == "dark" else "🌙 Dark"


def render_navbar() -> None:
    """
    Render a horizontal top navigation bar using st.page_link() for true SPA
    routing (no full page reload on navigation). Includes the theme toggle so
    it is available on every page without repeating code in each page file.
    """
    _PAGES = [
        ("pages/0_Home.py",           "🏠", "Home"),
        ("pages/1_Publications.py",   "📚", "Publications"),
        ("pages/2_AI_Assistant.py",   "🤖", "AI"),
        ("pages/7_Bioinformatics.py", "🧬", "Bioinformatics"),
        ("pages/4_Analytics.py",      "📊", "Analytics"),
        ("pages/6_Settings.py",       "⚙️", "Settings"),
        ("pages/5_Bug_Report.py",     "🐛", "Report"),
        ("pages/3_Admin.py",          "🔐", "Admin"),
    ]
    all_cols = st.columns([1.5] + [1] * len(_PAGES) + [0.85])
    logo_col  = all_cols[0]
    nav_cols  = all_cols[1:-1]
    theme_col = all_cols[-1]

    with logo_col:
        st.markdown('<div class="orc-nav-logo">🔬 ORC</div>', unsafe_allow_html=True)
    for col, (path, icon, label) in zip(nav_cols, _PAGES):
        with col:
            st.page_link(path, label=f"{icon} {label}", use_container_width=True)
    with theme_col:
        if st.button(theme_toggle_html(), use_container_width=True, key="_nav_theme_toggle"):
            new_theme = "light" if get_theme() == "dark" else "dark"
            st.session_state.theme_mode = new_theme
            st.query_params["theme"] = new_theme
            st.rerun()
    st.markdown('<hr style="margin:0 0 1.25rem !important">', unsafe_allow_html=True)


def footer_html(extra: str = "") -> str:
    c = DARK if get_theme() == "dark" else LIGHT
    extra_line = f"<p style='margin:0.1rem 0 0'>{extra}</p>" if extra else ""
    # CMS footer note (loaded lazily to avoid circular imports)
    cms_note = ""
    try:
        import streamlit as _st
        _cms = _st.session_state.get("_cms_override") or {}
        _note = _cms.get("footer_note", "").strip()
        if not _note:
            from utils.hf_data import load_cms_content as _lcms
            _note = _lcms().get("footer_note", "").strip()
        if _note:
            cms_note = f"<p style='margin:0.1rem 0 0'>{_html.escape(_note)}</p>"
    except Exception:
        pass
    return (
        f'<div style="text-align:center;color:{c["muted"]};font-size:0.78rem;padding:0.5rem 0 1rem">'
        f'  <p style="margin:0">ORC Research Dashboard · v1.0</p>'
        f'  {extra_line}'
        f'  {cms_note}'
        f'  <p style="margin:0.2rem 0 0">Built by '
        f'    <a href="https://www.linkedin.com/in/fahad-al-jubalie-55973926/" '
        f'       target="_blank" rel="noopener noreferrer" style="color:{c["accent"]};text-decoration:none;font-weight:500">'
        f'      Fahad Al-Jubalie</a>'
        f'  </p>'
        f'</div>'
    )
