"""Password hashing and verification.

Uses PBKDF2-HMAC-SHA256 from the standard library. No extra dependency is
required and no plaintext password is ever stored. The encoded form is::

    pbkdf2_sha256$<iterations>$<salt_hex>$<digest_hex>

The iteration count is configurable so tests can stay fast while production
uses the recommended count.
"""

from __future__ import annotations

import hashlib
import hmac
import os

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
_SALT_BYTES = 16


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Hash a password and return the encoded, self-describing hash string."""
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Compare a candidate password against an encoded hash string.

    Returns ``False`` for malformed hashes instead of raising, so callers never
    surface internals to the user.
    """
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
