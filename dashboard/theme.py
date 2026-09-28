"""ZeroTrace FX AI design system: colour tokens, typography and stylesheet.

Kept free of Qt imports so the palette and formatting helpers stay unit
testable (and importable) on machines without PySide6 installed.

The palette is shared with the Android companion app so the desktop terminal
and the phone monitor speak the same visual language.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Colour tokens
# ---------------------------------------------------------------------------

BG = "#0B0F17"            # window / canvas
SURFACE = "#10161F"       # panels, cards
SURFACE_2 = "#141B26"     # raised surfaces, table rows, inputs
RAISED = "#1A2330"        # hover surfaces, headers
BORDER = "#1E2836"        # hairlines, card borders
BORDER_SOFT = "#18202B"   # inner dividers

TEXT = "#E6EDF3"          # primary text
MUTED = "#8B98A9"         # secondary text, labels
FAINT = "#5B6878"         # placeholders, axis ticks

ACCENT = "#2EE6A6"        # brand mint: profit, healthy, primary actions
ACCENT_DEEP = "#12B886"   # gradient partner / pressed state
LOSS = "#FF5C7A"          # loss, danger, kill switch
WARN = "#FFB547"          # caution: drawdown creep, paused
INFO = "#58A6FF"          # informational: sessions, AI
VIOLET = "#A78BFA"        # adaptive-learning accents

# Font stacks (first available family wins). Windows gets Segoe UI Variable,
# macOS/Linux fall back gracefully; Inter is bundled in some installs.
FONT_STACK = ["Segoe UI Variable Text", "Segoe UI", "Inter", "IBM Plex Sans",
              "Helvetica Neue", "DejaVu Sans", "sans-serif"]
MONO_STACK = ["Cascadia Mono", "Consolas", "SF Mono", "JetBrains Mono",
              "DejaVu Sans Mono", "monospace"]

# Semantic tones ------------------------------------------------------------
GOOD = "good"
BAD = "bad"
WARN_TONE = "warn"
INFO_TONE = "info"
NEUTRAL = "neutral"

TONE_COLORS: dict[str, str] = {
    GOOD: ACCENT,
    BAD: LOSS,
    WARN_TONE: WARN,
    INFO_TONE: INFO,
    NEUTRAL: MUTED,
}


def tone_color(tone: str) -> str:
    """Resolve a semantic tone name to a hex colour."""
    return TONE_COLORS.get(tone, TEXT)


def pnl_tone(value: float) -> str:
    """Tone for a signed monetary value."""
    return GOOD if value >= 0 else BAD


def drawdown_tone(value: float) -> str:
    """Tone for drawdown percentage (higher is worse)."""
    if value >= 5.0:
        return BAD
    if value >= 2.0:
        return WARN_TONE
    return GOOD


# ---------------------------------------------------------------------------
# Formatting helpers (pure python, used by the UI and the tests)
# ---------------------------------------------------------------------------

def money(value: float, sign: bool = False) -> str:
    """`$12,345.67`, or `+$123.45` / `-$123.45` when ``sign`` is True."""
    if sign:
        return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"
    return f"${value:,.2f}"


def percent(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}%"


def price(value: float, digits: int = 5) -> str:
    return f"{value:.{digits}f}"


def confidence(value: float) -> str:
    return f"{value:.1f}"


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

def qss() -> str:
    """Build the application stylesheet from the palette tokens."""
    return f"""
/* ---- base ---------------------------------------------------------- */
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    selection-background-color: #1D3A57;
    selection-color: {TEXT};
    outline: none;
}}
QLabel {{ background-color: transparent; }}
QTableWidget, QTableWidget > QWidget {{ background-color: transparent; }}
QToolTip {{
    background-color: {RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
}}

/* ---- chrome -------------------------------------------------------- */
QFrame#headerBar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #121A26, stop:1 {BG});
    border: none;
    border-bottom: 1px solid {BORDER};
}}
QFrame#killBanner {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #3A0F1D, stop:0.5 #4A1424, stop:1 #3A0F1D);
    border-top: 1px solid rgba(255, 92, 122, 90);
    border-bottom: 1px solid rgba(255, 92, 122, 90);
}}
QLabel#killBannerText {{
    color: #FFD3DC;
    font-size: 12px;
    font-weight: 700;
    padding-left: 4px;
}}
QStatusBar {{
    background-color: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {MUTED};
    font-size: 11px;
    min-height: 26px;
}}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {MUTED}; padding: 0 8px; }}

/* ---- type ---------------------------------------------------------- */
QLabel#brandTitle {{ font-size: 16px; font-weight: 700; color: {TEXT}; }}
QLabel#brandSub {{ font-size: 10px; color: {FAINT}; }}
QLabel#sectionTitle {{ font-size: 11px; font-weight: 700; color: {MUTED}; }}
QLabel#cardTitle {{ font-size: 10px; font-weight: 700; color: {FAINT}; }}
QLabel#cardValue {{ font-size: 24px; font-weight: 700; color: {TEXT}; }}
QLabel#cardSub {{ font-size: 11px; color: {FAINT}; }}
QLabel#bigValue {{ font-size: 30px; font-weight: 700; color: {TEXT}; }}
QLabel#metaLabel {{ font-size: 11px; color: {MUTED}; }}
QLabel#metaValue {{ font-size: 11px; font-weight: 600; color: {TEXT}; }}
QLabel#clock {{ font-size: 12px; font-weight: 600; color: {MUTED}; }}
QLabel#emptyHint {{ font-size: 12px; color: {FAINT}; }}

/* ---- cards & panels ------------------------------------------------ */
QFrame#card, QFrame#panel {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#panelFlat {{
    background-color: transparent;
    border: none;
}}
QFrame#inset {{
    background-color: {BG};
    border: 1px solid {BORDER_SOFT};
    border-radius: 10px;
}}
QFrame#divider {{ background-color: {BORDER_SOFT}; border: none; }}

/* ---- buttons ------------------------------------------------------- */
QPushButton {{
    background-color: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 600;
    color: {TEXT};
}}
QPushButton:hover {{ background-color: {RAISED}; border-color: #2A3648; }}
QPushButton:pressed {{ background-color: #121924; }}
QPushButton:disabled {{ color: {FAINT}; background-color: {SURFACE}; }}
QPushButton#primary {{
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {ACCENT}, stop:1 {ACCENT_DEEP});
    border: none;
    color: #062B20;
    font-weight: 700;
}}
QPushButton#primary:hover {{ background-color: #43F0B6; }}
QPushButton#primary:pressed {{ background-color: {ACCENT_DEEP}; }}
QPushButton#danger {{
    background-color: rgba(255, 92, 122, 28);
    border: 1px solid rgba(255, 92, 122, 110);
    color: #FF8CA1;
    font-weight: 700;
}}
QPushButton#danger:hover {{ background-color: rgba(255, 92, 122, 46); }}
QPushButton#danger:pressed {{ background-color: rgba(255, 92, 122, 64); }}
QPushButton#ghost {{
    background-color: transparent;
    border: 1px solid {BORDER};
    color: {MUTED};
}}
QPushButton#ghost:hover {{ color: {TEXT}; background-color: {SURFACE_2}; }}

/* ---- tables -------------------------------------------------------- */
QTableWidget {{
    background-color: transparent;
    alternate-background-color: rgba(255, 255, 255, 5);
    border: none;
    gridline-color: transparent;
    font-size: 12px;
}}
QTableWidget::item {{ padding: 6px 10px; border: none; }}
QTableWidget::item:selected {{ background-color: #16283C; color: {TEXT}; }}
QHeaderView {{ background-color: transparent; }}
QHeaderView::section {{
    background-color: transparent;
    color: {FAINT};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px 10px;
    font-size: 10px;
    font-weight: 700;
}}
QTableCornerButton::section {{ background-color: transparent; border: none; }}

/* ---- tabs (segmented) ---------------------------------------------- */
QTabWidget::pane {{ border: none; background-color: transparent; }}
QTabBar {{ background-color: transparent; }}
QTabBar::tab {{
    background-color: transparent;
    color: {MUTED};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 9px 14px;
    font-size: 12px;
    font-weight: 600;
    margin-right: 4px;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

/* ---- scrollbars ---------------------------------------------------- */
QScrollBar:vertical {{
    background-color: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background-color: #263140;
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background-color: #33425A; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{
    background-color: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background-color: #263140;
    border-radius: 4px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{ background-color: #33425A; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

/* ---- misc widgets -------------------------------------------------- */
QScrollArea {{ border: none; background-color: transparent; }}
QTextEdit, QPlainTextEdit {{
    background-color: {BG};
    border: 1px solid {BORDER_SOFT};
    border-radius: 10px;
    color: {TEXT};
    font-size: 12px;
}}
QTextEdit#diagView {{
    font-family: 'Cascadia Mono', 'Consolas', 'SF Mono', 'DejaVu Sans Mono', monospace;
    font-size: 11px;
}}
QMessageBox {{ background-color: {SURFACE}; }}
QMessageBox QLabel {{ color: {TEXT}; font-size: 13px; }}
QMessageBox QPushButton {{ min-width: 96px; }}
"""


# Legacy alias kept for any tooling that referenced the old constant.
DARK_QSS = qss()
