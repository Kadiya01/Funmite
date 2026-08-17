"""Shared presentation helpers (no business logic)."""

from __future__ import annotations

from decimal import Decimal

NAIRA = "₦"


def format_money(value) -> str:
    """Render a Decimal as naira, e.g. ``₦55,000`` or ``₦1,250.50``.

    Whole amounts omit the decimal places (matching the approved wireframes);
    fractional amounts keep two places.
    """
    number = Decimal(value)
    if number == number.to_integral():
        text = f"{number:,.0f}"
    else:
        text = f"{number:,.2f}"
    return f"{NAIRA}{text}"


def format_file_size(size_bytes: int) -> str:
    """Render bytes as a human-readable size string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
