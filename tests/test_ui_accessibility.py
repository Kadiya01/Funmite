"""Phase 5 regression: WCAG AA contrast + visible focus state (finding #6).

The theme palette is locked to WCAG 2.1 AA for normal text (>= 4.5:1), the
focus ring must stay visibly distinct on the page background (>= 3:1,
WCAG 1.4.11), and no QSS may suppress the platform keyboard-focus outline.
"""

from __future__ import annotations

import pytest

from app.main import _SIDEBAR_QSS
from app.ui.theme import C, generate_stylesheet


def _channels(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _linearize(channel: float) -> float:
    channel /= 255.0
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def contrast(fg: str, bg: str) -> float:
    """WCAG 2.1 relative-luminance contrast ratio."""
    rgb_fg = _channels(fg)
    l1 = 0.2126 * _linearize(rgb_fg[0]) + 0.7152 * _linearize(rgb_fg[1]) + 0.0722 * _linearize(rgb_fg[2])
    rgb_bg = _channels(bg)
    l2 = 0.2126 * _linearize(rgb_bg[0]) + 0.7152 * _linearize(rgb_bg[1]) + 0.0722 * _linearize(rgb_bg[2])
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


NORMAL_TEXT_PAIRS = [
    (C.FG, C.BG),
    (C.FG, C.CARD),
    (C.CARD_FG, C.CARD),
    (C.PRIMARY_DARK, C.CARD),
    (C.ON_PRIMARY, C.PRIMARY),
    (C.ON_PRIMARY, C.PRIMARY_DARK),
    (C.ON_ACCENT, C.ACCENT),
    (C.ON_ACCENT, C.ACCENT_HOVER),
    (C.ON_DESTRUCTIVE, C.DESTRUCTIVE),
    (C.ACCENT, C.CARD),
    (C.SUCCESS, C.SUCCESS_LIGHT),
    (C.SUCCESS, C.CARD),
    (C.WARNING, C.WARNING_LIGHT),
    (C.WARNING, C.CARD),
    (C.DESTRUCTIVE, C.DESTRUCTIVE_LIGHT),
    (C.DESTRUCTIVE, C.CARD),
    (C.INFO, C.INFO_LIGHT),
    (C.INFO, C.CARD),
    (C.FG_SECONDARY, C.MUTED),
    (C.FG_SECONDARY, C.CARD),
    (C.MUTED_FG, C.CARD),
    (C.SIDEBAR_FG, C.SIDEBAR_BG),
    (C.SIDEBAR_FG, C.SIDEBAR_HOVER),
    (C.SIDEBAR_ACTIVE_FG, C.SIDEBAR_ACTIVE_BG),
    (C.PRIMARY, C.TABLE_ALT_ROW),
    (C.FG, C.TABLE_SELECTION),
    (C.FG, C.ACCENT_LIGHT),
]


@pytest.mark.parametrize("fg,bg", NORMAL_TEXT_PAIRS)
def test_normal_text_pairs_meet_wcag_aa(fg, bg):
    ratio = contrast(fg, bg)
    assert ratio >= 4.5, f"{fg} on {bg}: {ratio:.2f}:1 < 4.5:1"


@pytest.mark.parametrize("bg", [C.CARD, C.BG])
def test_focus_ring_is_visibly_distinct(bg):
    ratio = contrast(C.FOCUS_RING, bg)
    assert ratio >= 3.0, f"focus ring on {bg}: {ratio:.2f}:1 < 3:1"


def test_stylesheet_has_visible_focus_rules():
    css = generate_stylesheet()
    for selector in (
        "QPushButton:focus",
        "QPushButton#btnPrimary:focus",
        "QPushButton#btnDanger:focus",
        "QPushButton#btnSecondary:focus",
        "QPushButton#btnSuccess:focus",
        "QTabBar::tab:focus",
        "QLineEdit:focus",
    ):
        assert selector in css, f"missing focus rule: {selector}"


def test_no_qss_suppresses_keyboard_focus_outline():
    assert "outline: none" not in generate_stylesheet()
    assert "outline: none" not in _SIDEBAR_QSS