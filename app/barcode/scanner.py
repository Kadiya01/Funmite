"""Scanner input handling.

A USB barcode scanner presents itself as a keyboard: it types the barcode
quickly and finishes with an Enter keypress. This module normalises the raw
typed value; the Qt widget that captures it lives in
``app/ui/widgets/barcode_input.py`` so the UI and the barcode layer stay
separate.
"""

from __future__ import annotations

_SCAN_STRIP = " \t\r\n\f\v"


def normalize_scan(value: str) -> str:
    """Trim the framing characters a scanner/keyboard may add."""
    return value.strip(_SCAN_STRIP)
