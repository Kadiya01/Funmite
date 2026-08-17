"""Barcode generation, labels and scanner handling (Phase 03)."""

from __future__ import annotations

from app.barcode.codes import (  # noqa: F401
    BARCODE_DIGIT_COUNT,
    DEFAULT_BARCODE_SEED,
    Luhn,
    NumericBarcodeGenerator,
)
from app.barcode.labels import (  # noqa: F401
    BARCODE_SYMBOLOGY,
    BarcodeLabel,
    LabelRenderer,
    SvgLabelRenderer,
)
from app.barcode.scanner import normalize_scan  # noqa: F401
