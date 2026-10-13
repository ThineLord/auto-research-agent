"""Session-local visual tokens shared by the shell, widgets, tables and charts."""

from __future__ import annotations

DEFAULT_THEME = "day"
THEME_LABEL_KEYS = {"day": "theme_day", "dark": "theme_dark"}
THEME_VALUES: dict[str, dict[str, str]] = {
    "day": {
        "app_bg": "#f7f8f5",
        "main_bg": "#f7f8f5",
        "sidebar_bg": "#eef1ec",
        "surface": "#ffffff",
        "surface_alt": "#f0f3ee",
        "border": "#dce3da",
        "text": "#293a34",
        "muted": "#5f7066",
        "primary": "#466b59",
        "primary_hover": "#355644",
        "primary_text": "#ffffff",
        "input_bg": "#fbfcfa",
        "input_border": "#d5dfd4",
        "code_bg": "#edf1ec",
        "code_text": "#33473d",
        "success_bg": "#edf5ee",
        "success_text": "#355a42",
        "warning_bg": "#f7f1e5",
        "warning_text": "#795e29",
        "error_bg": "#f9eeeb",
        "error_text": "#8a493d",
        "info_bg": "#edf2f3",
        "info_text": "#45616b",
        "shadow": "0 6px 28px rgba(36, 58, 43, .035)",
    },
    "dark": {
        "app_bg": "#18221f",
        "main_bg": "#18221f",
        "sidebar_bg": "#131c19",
        "surface": "#202d27",
        "surface_alt": "#29392f",
        "border": "#36483d",
        "text": "#e3ebe2",
        "muted": "#a1b3a5",
        "primary": "#b0c9ac",
        "primary_hover": "#c8dcc4",
        "primary_text": "#1c3023",
        "input_bg": "#1b2721",
        "input_border": "#405348",
        "code_bg": "#152019",
        "code_text": "#d4e2d1",
        "success_bg": "#24392a",
        "success_text": "#bed9bb",
        "warning_bg": "#383326",
        "warning_text": "#ddc99b",
        "error_bg": "#3e2b29",
        "error_text": "#e6b4ab",
        "info_bg": "#26383c",
        "info_text": "#b2cbd1",
        "shadow": "0 6px 28px rgba(0, 0, 0, .10)",
    },
}


def normalize_theme(theme: str | None) -> str:
    return str(theme) if theme in THEME_LABEL_KEYS else DEFAULT_THEME


def build_theme_css(theme: str | None) -> str:
    theme = normalize_theme(theme)
    tokens = THEME_VALUES[theme]
    variables = "\n".join(
        f"  --ara-{key.replace('_', '-')}: {value};" for key, value in tokens.items()
    )
    scheme = "dark" if theme == "dark" else "light"
    return (
        "<style>\n:root {\n"
        + variables
        + f"\n  color-scheme: {scheme};\n}}\n"
        + r"""
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
  background: var(--ara-app-bg) !important;
  color: var(--ara-text) !important;
}
.stApp, input, textarea, button {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { color: var(--ara-muted); }
.stAppDeployButton { display: none; }
[data-testid="stMainBlockContainer"] {
  max-width: 1140px;
  padding: 3.2rem 3.5rem 4rem;
}
[data-testid="stSidebar"] {
  background: var(--ara-sidebar-bg) !important;
  border-right: 1px solid var(--ara-border);
  min-width: 250px; max-width: 280px;
}
[data-testid="stSidebarContent"] { background: var(--ara-sidebar-bg); }
[data-testid="stSidebarUserContent"] { padding: 2rem 1.4rem; }
.ara-brand { display: flex; gap: .8rem; align-items: center; margin: 0 0 2.5rem; }
.ara-brand > div { font-size: 1.12rem; font-weight: 600; letter-spacing: -.035em; }
.ara-brand-mark { color: var(--ara-primary); font-size: 2.35rem; font-weight: 400; }
.ara-brand small { display: block; font-size: .56rem; letter-spacing: .16em;
  font-weight: 500; margin-top: .3rem; color: var(--ara-muted); }
.ara-page-header { padding: .2rem 0 1.6rem; }
.ara-eyebrow { font-size: .68rem; letter-spacing: .14em; color: var(--ara-muted);
  font-weight: 600; margin-bottom: .9rem; overflow-wrap: anywhere; }
.ara-page-header h1 { font-size: clamp(1.85rem, 3.1vw, 2.6rem); font-weight: 500;
  letter-spacing: -.045em; line-height: 1.3; padding: 0 0 .7rem; }
.ara-page-header p { color: var(--ara-muted) !important; font-size: .93rem; margin: 0; }
h1, h2, h3, h4, h5, h6, [data-testid="stMarkdownContainer"],
[data-testid="stWidgetLabel"], [data-testid="stMetricLabel"],
[data-testid="stMetricValue"], [data-testid="stText"] { color: var(--ara-text); }
h2, h3 { letter-spacing: -.025em; font-weight: 550 !important; }
h3 { font-size: 1.12rem !important; padding-top: .4rem !important; }
p, label { line-height: 1.6; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
p[data-testid="stCaption"], .stCaption, .stCaption p {
  color: var(--ara-muted) !important; font-size: .8rem; opacity: 1;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap: 1.9rem; border-bottom: 1px solid var(--ara-border); margin-bottom: 1.5rem;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
  background: transparent; color: var(--ara-muted); padding: 0 0 .7rem;
  height: 2.7rem; white-space: nowrap; font-weight: 500;
}
[data-testid="stTabs"] [data-baseweb="tab"] p { color: inherit; }
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
  color: var(--ara-primary); font-weight: 650;
}
[data-baseweb="tab-highlight"] { background: var(--ara-primary) !important; height: 2px; }
[data-baseweb="tab-border"] { background: transparent !important; }
[data-testid="stVerticalBlockBorderWrapper"] > div, .st-key-brief_card,
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][style*="border"] {
  border-color: var(--ara-border) !important; background: var(--ara-surface);
  border-radius: 16px !important; padding: 1.4rem !important; box-shadow: var(--ara-shadow);
}
[data-testid="stExpander"] { border: 1px solid var(--ara-border) !important;
  border-radius: 10px; overflow: hidden; background: var(--ara-surface); }
[data-testid="stExpander"] summary { color: var(--ara-muted) !important;
  background: transparent !important; font-size: .86rem; }
[data-testid="stExpander"] summary:hover { color: var(--ara-primary) !important; }
[data-testid="stSidebar"] [data-testid="stExpander"] {
  background: transparent; margin-top: .5rem; }
[data-testid="stMetric"] { background: var(--ara-surface); border: 1px solid var(--ara-border);
  border-radius: 12px; padding: .8rem .7rem; box-shadow: var(--ara-shadow); }
[data-testid="stMetricLabel"] { color: var(--ara-muted); font-size: .8rem; }
[data-testid="stMetricLabel"] p { white-space: normal; overflow: visible; text-overflow: clip; line-height: 1.4; }
[data-testid="stMetricValue"] { font-size: 1.35rem; font-weight: 500; letter-spacing: -.04em; }
.stButton > button, .stDownloadButton > button {
  background: var(--ara-surface); border: 1px solid var(--ara-input-border);
  color: var(--ara-text); border-radius: 9px; min-height: 2.65rem;
  padding: .5rem .9rem; box-shadow: none; transition: background .15s, border-color .15s;
}
.stButton > button p, .stDownloadButton > button p { color: inherit !important; }
.stButton > button:hover, .stDownloadButton > button:hover {
  background: var(--ara-surface-alt); border-color: var(--ara-primary); color: var(--ara-primary);
}
.stButton > button[kind="primary"] { background: var(--ara-primary);
  border-color: var(--ara-primary); color: var(--ara-primary-text); }
.stButton > button[kind="primary"]:hover { background: var(--ara-primary-hover); }
.stButton > button:disabled { background: var(--ara-surface-alt); color: var(--ara-muted);
  border-color: var(--ara-border); opacity: .55; }
button:focus-visible, input:focus-visible, textarea:focus-visible, summary:focus-visible {
  outline: 2px solid var(--ara-primary) !important; outline-offset: 3px;
}
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"],
[data-baseweb="select"] > div {
  background: var(--ara-input-bg) !important; border-color: var(--ara-input-border) !important;
  color: var(--ara-text) !important; border-radius: 9px;
}
input, textarea, [data-baseweb="select"] { color: var(--ara-text) !important;
  caret-color: var(--ara-primary); }
input, textarea { background: var(--ara-input-bg) !important; }
textarea { line-height: 1.75 !important; font-size: .9rem !important; }
textarea::placeholder, input::placeholder { color: var(--ara-muted) !important; }
[data-baseweb="select"] svg, [data-baseweb="input"] svg, [data-baseweb="popover"] svg {
  fill: var(--ara-muted); }
[data-baseweb="popover"], [data-baseweb="popover"] > div,
[data-baseweb="menu"], [role="listbox"], [role="option"] {
  background: var(--ara-surface) !important; color: var(--ara-text) !important;
  border-color: var(--ara-border) !important;
}
[role="option"]:hover, [role="option"][aria-selected="true"] {
  background: var(--ara-surface-alt) !important; }
[data-baseweb="tag"] { background: var(--ara-surface-alt); color: var(--ara-text); }
[data-testid="stRadio"] label, [data-testid="stCheckbox"] label,
[data-testid="stToggle"] label { color: var(--ara-text); }
[data-baseweb="radio"] > div:first-child { background-color: var(--ara-muted); }
[data-baseweb="radio"] > div:first-child > div { background-color: var(--ara-surface); }
[data-baseweb="checkbox"] > span:first-child {
  background-color: var(--ara-input-bg); border-color: var(--ara-input-border); }
[data-testid="stSidebarCollapseButton"] button, [data-testid="stExpandSidebarButton"],
[data-testid="stBaseButton-headerNoPadding"], [data-testid="stBaseButton-header"] {
  color: var(--ara-muted) !important; }
[data-baseweb="radio"]:has(input:checked) > div:first-child {
  background-color: var(--ara-primary); }
[data-baseweb="radio"]:has(input:checked) > div:first-child > div {
  background-color: var(--ara-surface); }
[data-baseweb="checkbox"]:has(input:checked) > span:first-child {
  background-color: var(--ara-primary); border-color: var(--ara-primary); }
[data-testid="stNumberInput"] button { color: var(--ara-text); background: var(--ara-surface-alt); }
pre, code, [data-testid="stCode"], [data-testid="stCodeBlock"], [data-testid="stJson"] {
  background: var(--ara-code-bg) !important; color: var(--ara-code-text) !important;
  border-color: var(--ara-border) !important;
}
[data-testid="stCode"] span { color: inherit; }
:is([data-testid="stAlert"], [data-testid="stAlertContainer"]) { border-radius: 10px; border: 1px solid var(--ara-border); }
:is([data-testid="stAlert"], [data-testid="stAlertContainer"]):has([data-testid="stAlertContentSuccess"]) {
  background: var(--ara-success-bg) !important; color: var(--ara-success-text) !important; }
:is([data-testid="stAlert"], [data-testid="stAlertContainer"]):has([data-testid="stAlertContentWarning"]) {
  background: var(--ara-warning-bg) !important; color: var(--ara-warning-text) !important; }
:is([data-testid="stAlert"], [data-testid="stAlertContainer"]):has([data-testid="stAlertContentError"]) {
  background: var(--ara-error-bg) !important; color: var(--ara-error-text) !important; }
:is([data-testid="stAlert"], [data-testid="stAlertContainer"]):has([data-testid="stAlertContentInfo"]) {
  background: var(--ara-info-bg) !important; color: var(--ara-info-text) !important; }
:is([data-testid="stAlert"], [data-testid="stAlertContainer"]) [data-testid="stMarkdownContainer"],
:is([data-testid="stAlert"], [data-testid="stAlertContainer"]) [data-testid^="stAlertContent"],
:is([data-testid="stAlert"], [data-testid="stAlertContainer"]) p { color: inherit !important; }
[data-testid="stDataFrame"], [data-testid="stTable"] {
  border-color: var(--ara-border); color: var(--ara-text); }
a { color: var(--ara-primary); }
hr { border-color: var(--ara-border); }
@media (max-width: 900px) {
  [data-testid="stMainBlockContainer"] { padding: 2.5rem 1.5rem; }
  [data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 1.2rem; }
}
@media (max-width: 600px) {
  [data-testid="stMainBlockContainer"] { padding: 2rem 1rem; }
  .ara-page-header h1 { font-size: 1.8rem; }
  [data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 1rem; }
  [data-testid="stMetric"] { padding: .7rem; }
  [data-testid="stMetricValue"] { font-size: 1.4rem; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
"""
    )
