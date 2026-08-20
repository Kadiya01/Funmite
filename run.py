"""Entry point for Funmite POS.

Used by PyInstaller and for direct ``python run.py`` execution.
"""

from __future__ import annotations

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
