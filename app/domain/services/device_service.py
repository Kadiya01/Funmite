"""Device identity — persistent unique ID for each PC installation.

Each Funmite installation generates a UUID on first launch and persists it
to ``{data_dir}/device.id``.  This ID is stamped on every ``sync_queue``
entry so the cloud can distinguish mutations originating from PC-A vs PC-B.
"""

from __future__ import annotations

import uuid
from pathlib import Path

_DEVICE_ID_FILE = "device.id"


class DeviceIdentity:
    """Read or generate the local device identifier."""

    def __init__(self, data_dir: str | Path) -> None:
        self._path = Path(data_dir) / _DEVICE_ID_FILE

    @property
    def device_id(self) -> str:
        """Return the device ID, generating one if it does not exist yet."""
        if self._path.exists():
            return self._path.read_text(encoding="utf-8").strip()
        return self._generate()

    def _generate(self) -> str:
        """Generate a new UUID, persist it, and return it."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        new_id = str(uuid.uuid4())
        self._path.write_text(new_id, encoding="utf-8")
        return new_id

    def reset(self) -> str:
        """Force-generate a new device ID (for testing or re-deployment)."""
        if self._path.exists():
            self._path.unlink()
        return self._generate()
