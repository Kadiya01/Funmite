"""Domain-level exceptions.

These cross the service boundary: the UI shows their messages without ever
exposing passwords, secrets or raw stack traces.
"""

from __future__ import annotations


class AuthenticationError(Exception):
    """Raised when credentials cannot be verified."""


class AuthorizationError(Exception):
    """Raised when the current user lacks the required permission."""


class ValidationError(Exception):
    """Raised when user-supplied data fails validation or a uniqueness rule."""


class NotFoundError(Exception):
    """Raised when a record that a service expected does not exist."""
