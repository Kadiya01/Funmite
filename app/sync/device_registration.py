"""Device registration with the cloud sync service.

On first setup the Admin registers this PC with the cloud by calling
``/api/sync/devices/register``.  The returned credentials are stored in
``sync_credentials.json`` inside the data directory.  Subsequent app
launches read the stored credentials to authenticate sync requests.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.domain.services.device_service import DeviceIdentity

log = logging.getLogger(__name__)


@dataclass
class RegistrationResult:
    success: bool
    device_id: str = ""
    api_key: str = ""
    error: str = ""


def _credentials_path(data_dir: Path) -> Path:
    return data_dir / "sync_credentials.json"


def load_credentials(data_dir: Path) -> dict | None:
    """Load stored sync credentials, or None if not registered."""
    path = _credentials_path(data_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.exception("Failed to read sync credentials")
        return None


def save_credentials(data_dir: Path, cloud_url: str, api_key: str) -> None:
    """Persist sync credentials (api_key only — device_id comes from DeviceIdentity)."""
    device = DeviceIdentity(data_dir)
    creds = {
        "cloud_url": cloud_url,
        "device_id": device.device_id,
        "api_key": api_key,
    }
    path = _credentials_path(data_dir)
    path.write_text(json.dumps(creds, indent=2), encoding="utf-8")
    log.info("Sync credentials saved for device %s", device.device_id)


def is_registered(data_dir: Path) -> bool:
    """Return True if this device has sync credentials stored."""
    return _credentials_path(data_dir).exists()


def register_device(data_dir: Path, cloud_url: str, device_name: str) -> RegistrationResult:
    """Register this device with the cloud sync service.

    Calls the cloud API, stores credentials on success, and returns
    the result.  Never exposes the api_key in logs.
    """
    import httpx

    device = DeviceIdentity(data_dir)
    url = f"{cloud_url.rstrip('/')}/api/sync/devices/register"

    try:
        resp = httpx.post(
            url,
            json={"device_name": device_name},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

        api_key = data["api_key"]
        save_credentials(data_dir, cloud_url, api_key)

        return RegistrationResult(
            success=True,
            device_id=data["device_id"],
            api_key=api_key,
        )
    except httpx.ConnectError:
        return RegistrationResult(success=False, error="Cannot connect to cloud server. Check the URL and your internet connection.")
    except httpx.HTTPStatusError as exc:
        return RegistrationResult(success=False, error=f"Server returned error: {exc.response.status_code}")
    except Exception as exc:
        return RegistrationResult(success=False, error=f"Registration failed: {exc}")
