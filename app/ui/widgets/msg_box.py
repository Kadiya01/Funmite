"""Helpers that keep QMessageBox dialogs fully visible on screen.

QMessageBox auto-sizes to its content and centres on the parent window; on
small displays (or when the parent window is larger than the screen) the box
can extend past the visible area, cutting the message off on the right.
``fit_message_box`` word-wraps the text, hard-caps the box within the
available screen geometry and repositions it so every part of the dialog
(including the buttons) is visible — without otherwise changing Qt's default
content alignment.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

SCREEN_MARGIN = 16
MAX_TEXT_WIDTH = 560


def fit_message_box(box: QMessageBox) -> QMessageBox:
    """Word-wrap text and hard-cap *box* so the whole dialog fits on screen.

    Returns the same *box* so callers can chain it before ``exec()``.
    """
    parent_widget = box.parentWidget()
    window = parent_widget.window() if parent_widget is not None else None

    screen = None
    if window is not None and window.isVisible():
        screen = window.screen()
    if screen is None:
        screen = QApplication.primaryScreen()

    avail = screen.availableGeometry() if screen is not None else None
    if avail is None:
        return box

    max_width = avail.width() - 2 * SCREEN_MARGIN
    max_height = avail.height() - 2 * SCREEN_MARGIN
    text_limit = min(MAX_TEXT_WIDTH, max_width)

    for label in box.findChildren(QLabel):
        if label.pixmap() is not None:
            continue
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setMaximumWidth(text_limit)

    box.adjustSize()

    box.setMaximumWidth(max_width)
    box.setMaximumHeight(max_height)
    width = min(box.sizeHint().width(), max_width)
    height = min(box.sizeHint().height(), max_height)
    box.resize(width, height)

    centre = avail.center()
    if window is not None and window.frameGeometry().isValid():
        centre = window.frameGeometry().center()
    x = min(max(avail.left(), centre.x() - width // 2), avail.right() - width)
    y = min(max(avail.top(), centre.y() - height // 2), avail.bottom() - height)
    box.move(x, y)
    return box