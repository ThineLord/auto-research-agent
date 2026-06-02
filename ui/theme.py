from __future__ import annotations

DEFAULT_THEME = "day"
THEME_LABEL_KEYS = {
    "day": "theme_day",
    "dark": "theme_dark",
}

THEME_VALUES: dict[str, dict[str, str]] = {
    "day": {
        "app_bg": "#f6f8fb",
        "main_bg": "#ffffff",
        "sidebar_bg": "#eef3f8",
        "surface": "#ffffff",
        "surface_alt": "#f8fafc",
        "border": "#d7dee8",
        "text": "#172033",
        "muted": "#5d6b82",
        "primary": "#2463eb",
        "primary_hover": "#1d4ed8",
        "primary_text": "#ffffff",
        "input_bg": "#ffffff",
        "input_border": "#cbd5e1",
        "code_bg": "#edf2f7",
        "code_text": "#172033",
        "success_bg": "#e8f7ef",
        "success_text": "#14532d",
        "warning_bg": "#fff6db",
        "warning_text": "#7c4a03",
        "error_bg": "#ffedf0",
        "error_text": "#8a1227",
        "info_bg": "#e8f1ff",
        "info_text": "#1d4ed8",
        "shadow": "0 1px 2px rgba(23, 32, 51, 0.08)",
    },
    "dark": {
        "app_bg": "#15171a",
        "main_bg": "#1b1f24",
        "sidebar_bg": "#111316",
        "surface": "#22272e",
        "surface_alt": "#2a3038",
        "border": "#3d444d",
        "text": "#eef2f4",
        "muted": "#adb8c2",
        "primary": "#53c7a7",
        "primary_hover": "#71dabd",
        "primary_text": "#06231d",
        "input_bg": "#15171a",
        "input_border": "#4d5662",
        "code_bg": "#101214",
        "code_text": "#f3f6f8",
        "success_bg": "#143525",
        "success_text": "#b7f7d0",
        "warning_bg": "#3b2f13",
        "warning_text": "#ffe4a3",
        "error_bg": "#3d1720",
        "error_text": "#ffc4cd",
        "info_bg": "#162943",
        "info_text": "#bfdbfe",
        "shadow": "0 1px 2px rgba(0, 0, 0, 0.35)",
    },
}


def normalize_theme(theme: str | None) -> str:
    if theme in THEME_LABEL_KEYS:
        return str(theme)
    return DEFAULT_THEME


def build_theme_css(theme: str | None) -> str:
    tokens = THEME_VALUES[normalize_theme(theme)]
    return f"""
<style>
:root {{
  --ara-app-bg: {tokens["app_bg"]};
  --ara-main-bg: {tokens["main_bg"]};
  --ara-sidebar-bg: {tokens["sidebar_bg"]};
  --ara-surface: {tokens["surface"]};
  --ara-surface-alt: {tokens["surface_alt"]};
  --ara-border: {tokens["border"]};
  --ara-text: {tokens["text"]};
  --ara-muted: {tokens["muted"]};
  --ara-primary: {tokens["primary"]};
  --ara-primary-hover: {tokens["primary_hover"]};
  --ara-primary-text: {tokens["primary_text"]};
  --ara-input-bg: {tokens["input_bg"]};
  --ara-input-border: {tokens["input_border"]};
  --ara-code-bg: {tokens["code_bg"]};
  --ara-code-text: {tokens["code_text"]};
  --ara-success-bg: {tokens["success_bg"]};
  --ara-success-text: {tokens["success_text"]};
  --ara-warning-bg: {tokens["warning_bg"]};
  --ara-warning-text: {tokens["warning_text"]};
  --ara-error-bg: {tokens["error_bg"]};
  --ara-error-text: {tokens["error_text"]};
  --ara-info-bg: {tokens["info_bg"]};
  --ara-info-text: {tokens["info_text"]};
  --ara-shadow: {tokens["shadow"]};
}}

html,
body,
.stApp,
[data-testid="stAppViewContainer"] {{
  background: var(--ara-app-bg) !important;
  color: var(--ara-text) !important;
}}

[data-testid="stHeader"],
[data-testid="stToolbar"] {{
  background: var(--ara-app-bg) !important;
  color: var(--ara-text) !important;
}}

[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {{
  background: var(--ara-sidebar-bg) !important;
  color: var(--ara-text) !important;
}}

[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
.main .block-container {{
  background: var(--ara-main-bg);
  color: var(--ara-text);
  border: none;
  border-radius: 0;
  box-shadow: none;
  margin-top: 1rem;
  padding-top: 2rem;
}}

h1, h2, h3, h4, h5, h6,
p, li, label, span,
[data-testid="stMarkdownContainer"],
[data-testid="stMetricLabel"],
[data-testid="stMetricValue"],
[data-testid="stMetricDelta"],
[data-testid="stCaptionContainer"] {{
  color: var(--ara-text) !important;
}}

[data-testid="stCaptionContainer"],
.stMarkdown small {{
  color: var(--ara-muted) !important;
}}

[data-testid="stMetric"],
[data-testid="stExpander"],
[data-testid="stDataFrame"],
[data-testid="stTable"],
[data-testid="stVerticalBlockBorderWrapper"] {{
  background: var(--ara-surface) !important;
  border-color: var(--ara-border) !important;
  color: var(--ara-text) !important;
}}

[data-testid="stExpander"] details,
[data-testid="stExpander"] summary {{
  background: var(--ara-surface) !important;
  color: var(--ara-text) !important;
}}

.stButton > button,
.stDownloadButton > button {{
  background: var(--ara-primary) !important;
  border: 1px solid var(--ara-primary) !important;
  color: var(--ara-primary-text) !important;
  border-radius: 8px !important;
  box-shadow: none !important;
}}

.stButton > button:hover,
.stDownloadButton > button:hover {{
  background: var(--ara-primary-hover) !important;
  border-color: var(--ara-primary-hover) !important;
  color: var(--ara-primary-text) !important;
}}

.stButton > button:disabled,
.stDownloadButton > button:disabled {{
  background: var(--ara-surface-alt) !important;
  border-color: var(--ara-border) !important;
  color: var(--ara-muted) !important;
}}

.stTextInput input,
.stTextArea textarea,
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea,
[data-baseweb="select"] > div,
[data-baseweb="base-input"],
[data-testid="stSelectbox"] div {{
  background: var(--ara-input-bg) !important;
  border-color: var(--ara-input-border) !important;
  color: var(--ara-text) !important;
}}

[data-baseweb="popover"],
[data-baseweb="popover"] > div,
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="popover"] [role="option"],
[data-baseweb="menu"],
ul[role="listbox"],
li[role="option"] {{
  background: var(--ara-surface) !important;
  border-color: var(--ara-border) !important;
  color: var(--ara-text) !important;
}}

[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [aria-selected="true"],
li[role="option"]:hover,
li[aria-selected="true"] {{
  background: var(--ara-surface-alt) !important;
  color: var(--ara-text) !important;
}}

.stCheckbox label,
[data-testid="stCheckbox"] label,
[data-testid="stCheckbox"] span {{
  color: var(--ara-text) !important;
}}

textarea::placeholder,
input::placeholder {{
  color: var(--ara-muted) !important;
}}

pre,
code,
[data-testid="stCodeBlock"],
[data-testid="stCodeBlock"] pre,
[data-testid="stJson"] {{
  background: var(--ara-code-bg) !important;
  color: var(--ara-code-text) !important;
  border-color: var(--ara-border) !important;
}}

[data-testid="stAlert"] {{
  border-radius: 8px !important;
  border: 1px solid var(--ara-border) !important;
}}

[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) {{
  background: var(--ara-success-bg) !important;
  color: var(--ara-success-text) !important;
}}

[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) {{
  background: var(--ara-warning-bg) !important;
  color: var(--ara-warning-text) !important;
}}

[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) {{
  background: var(--ara-error-bg) !important;
  color: var(--ara-error-text) !important;
}}

[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) {{
  background: var(--ara-info-bg) !important;
  color: var(--ara-info-text) !important;
}}

[data-testid="stAlert"] *,
[data-testid="stAlertContentSuccess"] *,
[data-testid="stAlertContentWarning"] *,
[data-testid="stAlertContentError"] *,
[data-testid="stAlertContentInfo"] * {{
  color: inherit !important;
}}

a {{
  color: var(--ara-primary) !important;
}}

hr {{
  border-color: var(--ara-border) !important;
}}
</style>
"""
