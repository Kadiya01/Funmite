"""Centralized design tokens and QSS stylesheet generator for Funmite POS.

Flat Design · Industrial Slate + Emerald Green · Data-Dense Desktop POS
Based on ui-ux-pro-max recommendations for Inventory & Stock Management.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Design Tokens
# ---------------------------------------------------------------------------

class C:
    """Color palette — Inventory & Stock Management (ui-ux-pro-max)."""
    PRIMARY = "#334155"
    PRIMARY_LIGHT = "#475569"
    PRIMARY_DARK = "#1E293B"
    ON_PRIMARY = "#FFFFFF"

    SECONDARY = "#475569"
    ON_SECONDARY = "#FFFFFF"

    ACCENT = "#059669"
    ACCENT_HOVER = "#047857"
    ACCENT_LIGHT = "#D1FAE5"
    ON_ACCENT = "#FFFFFF"

    BG = "#F8FAFC"
    BG_PAGE = "#F1F5F9"
    FG = "#0F172A"
    FG_SECONDARY = "#334155"

    CARD = "#FFFFFF"
    CARD_FG = "#0F172A"

    MUTED = "#F2F3F4"
    MUTED_FG = "#64748B"

    BORDER = "#E2E8F0"
    BORDER_LIGHT = "#F1F5F9"
    DIVIDER = "#CBD5E1"

    DESTRUCTIVE = "#DC2626"
    DESTRUCTIVE_LIGHT = "#FEE2E2"
    ON_DESTRUCTIVE = "#FFFFFF"

    WARNING = "#F59E0B"
    WARNING_LIGHT = "#FEF3C7"
    SUCCESS = "#059669"
    SUCCESS_LIGHT = "#D1FAE5"

    RING = "#334155"
    FOCUS_RING = "#93C5FD"

    TABLE_HEADER_BG = "#334155"
    TABLE_HEADER_FG = "#FFFFFF"
    TABLE_ALT_ROW = "#F8FAFC"
    TABLE_HOVER = "#F1F5F9"
    TABLE_SELECTION = "#ECFDF5"

    SIDEBAR_BG = "#1E293B"
    SIDEBAR_FG = "#CBD5E1"
    SIDEBAR_HOVER = "#334155"
    SIDEBAR_ACTIVE_BG = "#334155"
    SIDEBAR_ACTIVE_FG = "#FFFFFF"
    SIDEBAR_ACCENT = "#059669"

    SCROLLBAR_BG = "#F1F5F9"
    SCROLLBAR_HANDLE = "#CBD5E1"
    SCROLLBAR_HANDLE_HOVER = "#94A3B8"


class F:
    """Typography tokens."""
    FAMILY = '"Segoe UI", "Noto Sans", "Helvetica Neue", Arial, sans-serif'
    FAMILY_MONO = '"Cascadia Code", "Consolas", "Courier New", monospace'

    SIZE_XS = "11px"
    SIZE_SM = "12px"
    SIZE_BASE = "13px"
    SIZE_MD = "14px"
    SIZE_LG = "16px"
    SIZE_XL = "18px"
    SIZE_2XL = "20px"
    SIZE_3XL = "24px"
    SIZE_4XL = "28px"

    WEIGHT_NORMAL = "400"
    WEIGHT_MEDIUM = "500"
    WEIGHT_SEMIBOLD = "600"
    WEIGHT_BOLD = "700"

    LINE_HEIGHT_TIGHT = "1.2"
    LINE_HEIGHT_BASE = "1.5"


class S:
    """Spacing tokens (multiples of 4)."""
    XS = "2px"
    SM = "4px"
    MD = "8px"
    LG = "12px"
    XL = "16px"
    XXL = "24px"
    XXXL = "32px"

    RADIUS_SM = "4px"
    RADIUS_MD = "6px"
    RADIUS_LG = "8px"
    RADIUS_XL = "12px"
    RADIUS_FULL = "9999px"


# ---------------------------------------------------------------------------
# Sidebar Navigation Items  (unicode-safe, no external icon dependency)
# ---------------------------------------------------------------------------

NAV_ICONS: dict[str, str] = {
    "Dashboard": "\u25A2",   # ▢  square
    "POS":       "\u25B6",   # ▶  play
    "Products":  "\u25CB",   # ◯  circle
    "Inventory": "\u25A3",   # ▣  square with inner square
    "Customers": "\u2663",   # ♣  club
    "Purchases": "\u25A0",   # ■  filled square
    "Suppliers": "\u25C6",   # ◆  diamond
    "Expenses":  "\u25AC",   # ▬  filled rectangle
    "Reports":   "\u2591",   # ░  light shade
    "Settings":  "\u2699",   # ⚙  gear
}


# ---------------------------------------------------------------------------
# QSS Helpers
# ---------------------------------------------------------------------------

def _btn(
    bg: str = C.PRIMARY,
    fg: str = C.ON_PRIMARY,
    hover: str | None = None,
    border: str = "none",
    font_size: str = F.SIZE_BASE,
    padding: str = f"{S.MD} {S.XL}",
    min_height: str = "32px",
    border_radius: str = S.RADIUS_SM,
) -> str:
    h = hover or _darken(bg)
    return f"""
        background-color: {bg};
        color: {fg};
        border: {border};
        border-radius: {border_radius};
        padding: {padding};
        font-size: {font_size};
        font-family: {F.FAMILY};
        font-weight: {F.WEIGHT_MEDIUM};
        min-height: {min_height};
    """


def _darken(hex_color: str, amount: int = 15) -> str:
    """Darken a hex color by a percentage."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    r = max(0, r - amount)
    g = max(0, g - amount)
    b = max(0, b - amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def _lighten(hex_color: str, amount: int = 15) -> str:
    """Lighten a hex color by a percentage."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    r = min(255, r + amount)
    g = min(255, g + amount)
    b = min(255, b + amount)
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------------------
# Global Stylesheet Generator
# ---------------------------------------------------------------------------

def generate_stylesheet() -> str:
    """Return the full QSS stylesheet for the application."""
    return f"""
/* ===== Funmite POS — Global Stylesheet ================================ */

/* --- Base --- */
QMainWindow, QDialog {{
    background-color: {C.BG};
    font-family: {F.FAMILY};
    font-size: {F.SIZE_BASE};
    color: {C.FG};
}}

QWidget {{
    font-family: {F.FAMILY};
    font-size: {F.SIZE_BASE};
    color: {C.FG};
}}

/* --- Labels --- */
QLabel {{
    background: transparent;
    border: none;
    font-size: {F.SIZE_BASE};
}}

/* --- Buttons --- */
QPushButton {{
    {_btn()}
}}
QPushButton:hover {{
    background-color: {_darken(C.PRIMARY)};
}}
QPushButton:pressed {{
    background-color: {_darken(C.PRIMARY, 25)};
}}
QPushButton:disabled {{
    background-color: {C.MUTED};
    color: {C.MUTED_FG};
    border: 1px solid {C.BORDER};
}}

/* Primary / Accent buttons via objectName */
QPushButton#btnPrimary, QPushButton[cssClass="primary"] {{
    {_btn(C.ACCENT, C.ON_ACCENT, C.ACCENT_HOVER, min_height="36px")}
}}
QPushButton#btnPrimary:hover, QPushButton[cssClass="primary"]:hover {{
    background-color: {C.ACCENT_HOVER};
}}
QPushButton#btnPrimary:pressed, QPushButton[cssClass="primary"]:pressed {{
    background-color: {_darken(C.ACCENT, 25)};
}}

QPushButton#btnDanger, QPushButton[cssClass="danger"] {{
    {_btn(C.DESTRUCTIVE, C.ON_DESTRUCTIVE, _darken(C.DESTRUCTIVE))}
}}
QPushButton#btnDanger:hover, QPushButton[cssClass="danger"]:hover {{
    background-color: {_darken(C.DESTRUCTIVE)};
}}

QPushButton#btnSecondary, QPushButton[cssClass="secondary"] {{
    {_btn(C.MUTED, C.FG_SECONDARY, _lighten(C.MUTED), border=f"1px solid {C.BORDER}")}
}}
QPushButton#btnSecondary:hover, QPushButton[cssClass="secondary"]:hover {{
    background-color: {_lighten(C.MUTED)};
    border: 1px solid {C.DIVIDER};
}}

QPushButton#btnSuccess, QPushButton[cssClass="success"] {{
    {_btn(C.ACCENT, C.ON_ACCENT, C.ACCENT_HOVER, min_height="40px", font_size=F.SIZE_MD)}
}}

/* --- Line Edits, Combo Boxes, Spin Boxes, Date Edits --- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit {{
    background-color: {C.CARD};
    border: 1px solid {C.BORDER};
    border-radius: {S.RADIUS_SM};
    padding: 6px 10px;
    font-size: {F.SIZE_BASE};
    font-family: {F.FAMILY};
    color: {C.FG};
    min-height: 20px;
    selection-background-color: {C.ACCENT_LIGHT};
    selection-color: {C.FG};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {C.ACCENT};
}}

QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDateEdit:disabled {{
    background-color: {C.MUTED};
    color: {C.MUTED_FG};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 24px;
    border: none;
    border-left: 1px solid {C.BORDER};
    border-radius: 0 {S.RADIUS_SM} {S.RADIUS_SM} 0;
    background-color: {C.MUTED};
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {C.MUTED_FG};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {C.CARD};
    border: 1px solid {C.BORDER};
    border-radius: {S.RADIUS_SM};
    padding: 4px 0;
    selection-background-color: {C.ACCENT_LIGHT};
    selection-color: {C.FG};
    outline: none;
}}

QDateEdit::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 24px;
    border: none;
    border-left: 1px solid {C.BORDER};
    border-radius: 0 {S.RADIUS_SM} {S.RADIUS_SM} 0;
    background-color: {C.MUTED};
}}

/* --- Tables --- */
QTableWidget, QTableView {{
    background-color: {C.CARD};
    border: 1px solid {C.BORDER};
    border-radius: {S.RADIUS_MD};
    gridline-color: {C.BORDER_LIGHT};
    selection-background-color: {C.TABLE_SELECTION};
    selection-color: {C.FG};
    font-size: {F.SIZE_BASE};
    outline: none;
    alternate-background-color: {C.TABLE_ALT_ROW};
}}
QTableWidget::item, QTableView::item {{
    padding: 6px 10px;
    border-bottom: 1px solid {C.BORDER_LIGHT};
    min-height: 36px;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {C.TABLE_SELECTION};
    color: {C.FG};
}}

QHeaderView::section {{
    background-color: {C.TABLE_HEADER_BG};
    color: {C.TABLE_HEADER_FG};
    border: none;
    border-right: 1px solid {_darken(C.PRIMARY, 10)};
    border-bottom: 2px solid {C.PRIMARY_DARK};
    padding: 8px 10px;
    font-size: {F.SIZE_SM};
    font-weight: {F.WEIGHT_SEMIBOLD};
    text-transform: uppercase;
    min-height: 20px;
}}
QHeaderView::section:last {{
    border-right: none;
}}
QHeaderView::section:hover {{
    background-color: {_darken(C.PRIMARY, 5)};
}}

/* --- Tabs --- */
QTabWidget::pane {{
    border: 1px solid {C.BORDER};
    border-radius: 0 0 {S.RADIUS_MD} {S.RADIUS_MD};
    background-color: {C.CARD};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {C.MUTED};
    color: {C.MUTED_FG};
    border: 1px solid {C.BORDER};
    border-bottom: none;
    border-radius: {S.RADIUS_SM} {S.RADIUS_SM} 0 0;
    padding: 8px 20px;
    font-size: {F.SIZE_SM};
    font-weight: {F.WEIGHT_MEDIUM};
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {C.CARD};
    color: {C.ACCENT};
    border-bottom: 2px solid {C.ACCENT};
    font-weight: {F.WEIGHT_SEMIBOLD};
}}
QTabBar::tab:hover:!selected {{
    background-color: {C.BORDER_LIGHT};
    color: {C.FG_SECONDARY};
}}

/* --- Group Box --- */
QGroupBox {{
    background-color: {C.CARD};
    border: 1px solid {C.BORDER};
    border-radius: {S.RADIUS_MD};
    margin-top: 16px;
    padding: 16px 12px 12px 12px;
    font-size: {F.SIZE_BASE};
    font-weight: {F.WEIGHT_SEMIBOLD};
    color: {C.FG_SECONDARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: 4px;
    padding: 0 6px;
    background-color: {C.CARD};
    color: {C.FG_SECONDARY};
    font-size: {F.SIZE_SM};
    font-weight: {F.WEIGHT_SEMIBOLD};
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* --- Tool Bar --- */
QToolBar {{
    background-color: {C.CARD};
    border-bottom: 1px solid {C.BORDER};
    padding: 4px 8px;
    spacing: 6px;
}}
QToolBar QLabel {{
    font-size: {F.SIZE_SM};
    color: {C.MUTED_FG};
    padding: 0 4px;
}}

/* --- Status Bar --- */
QStatusBar {{
    background-color: {C.CARD};
    border-top: 1px solid {C.BORDER};
    color: {C.MUTED_FG};
    font-size: {F.SIZE_XS};
    padding: 2px 8px;
}}

/* --- Scroll Bars --- */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background-color: {C.SCROLLBAR_HANDLE};
    border-radius: 4px;
    min-height: 30px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {C.SCROLLBAR_HANDLE_HOVER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    background: none;
    border: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background-color: {C.SCROLLBAR_HANDLE};
    border-radius: 4px;
    min-width: 30px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {C.SCROLLBAR_HANDLE_HOVER};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    background: none;
    border: none;
}}
QScrollBar::add-page:horizontal, SScrollBar::sub-page:horizontal {{
    background: transparent;
}}

/* --- Message Box --- */
QMessageBox {{
    background-color: {C.CARD};
}}
QMessageBox QLabel {{
    font-size: {F.SIZE_BASE};
    color: {C.FG};
    min-width: 300px;
}}

/* --- Input Dialog --- */
QInputDialog {{
    background-color: {C.CARD};
}}

/* --- Splitter --- */
QSplitter::handle {{
    background-color: {C.BORDER};
}}

/* --- Tool Tips --- */
QToolTip {{
    background-color: {C.PRIMARY_DARK};
    color: {C.ON_PRIMARY};
    border: none;
    border-radius: {S.RADIUS_SM};
    padding: 6px 10px;
    font-size: {F.SIZE_SM};
}}
"""
