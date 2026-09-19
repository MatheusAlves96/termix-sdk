# Adapted from stripe-python (stripe/_error.py), MIT License, Copyright (c) 2010-2018 Stripe.
# See NOTICE for the full license text and attribution.
"""Exception hierarchy for the Termix SDK.

Every exception carries the raw fields the Termix API can return in an
error body (`error`, `code`, `details`), plus the HTTP status and the raw
response, so callers never have to re-parse `body` themselves. See
docs/api-schema-validation.md and spec/termix-openapi.json's `Error` schema
for the shapes this is built from.
"""

from __future__ import annotations

from typing import Any


class TermixError(Exception):
    """Base class for every exception the SDK raises."""

    def __init__(
        self,
        message: str | None = None,
        *,
        http_status: int | None = None,
        http_body: str | None = None,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self._message = message
        self.http_status = http_status
        self.http_body = http_body
        self.body = body or {}
        self.headers = headers or {}
        self.code = code
        # Termix error bodies sometimes carry extra detail beyond `error`/`code`.
        self.details: str | None = self.body.get("details")

    def __str__(self) -> str:
        return self._message or "<empty message>"

    @property
    def user_message(self) -> str | None:
        return self._message

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(message={self._message!r}, "
            f"http_status={self.http_status!r}, code={self.code!r})"
        )


class APIConnectionError(TermixError):
    """Raised when the request never reached the server (DNS, TCP, TLS, timeout)."""

    def __init__(self, message: str, *, should_retry: bool = False) -> None:
        super().__init__(message)
        self.should_retry = should_retry


class APIStatusError(TermixError):
    """Base class for every error the API answered with a non-2xx status."""


class InvalidRequestError(APIStatusError):
    """400 / 409 / 422 — malformed input, or a state conflict."""


class AuthenticationError(APIStatusError):
    """401 — missing, invalid, or expired credentials.

    Covers the middleware's own 401 bodies (`Missing authentication token`,
    `Invalid token`, `SESSION_NOT_FOUND`, `SESSION_EXPIRED`), not just login
    failures. See `TOTPRequiredError` and `SessionExpiredError` for the two
    401 variants callers usually need to branch on.
    """


class TOTPRequiredError(AuthenticationError):
    """401 with `code: "TOTP_REQUIRED"` — the account needs a second factor."""


class SessionExpiredError(AuthenticationError):
    """401 with `code: "SESSION_NOT_FOUND"` or `"SESSION_EXPIRED"`."""


class PermissionError(APIStatusError):
    """403 — authenticated, but not allowed (includes admin-only endpoints
    and `IMPERSONATION_NOT_ALLOWED` when impersonation is attempted with an
    API key instead of a JWT).
    """


class NotFoundError(APIStatusError):
    """404."""


class RateLimitError(APIStatusError):
    """429. Login lockouts and TOTP lockouts both use this; `remaining_time`
    is populated from the body's `remainingTime` field when present.
    """

    def __init__(self, *args: Any, remaining_time: float | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.remaining_time = remaining_time


class DataLockedError(APIStatusError):
    """423 with `code: "DATA_LOCKED"` — the instance's encrypted data hasn't
    been unlocked yet (see `requireDataAccess` in the backend).
    """


class ServerError(APIStatusError):
    """5xx."""


def error_for_status(
    status: int,
    *,
    message: str | None,
    code: str | None,
    body: dict[str, Any],
    http_body: str | None,
    headers: dict[str, str] | None,
) -> APIStatusError:
    """Pick the most specific exception class for a given status/code pair."""
    kwargs: dict[str, Any] = dict(
        http_status=status,
        http_body=http_body,
        body=body,
        headers=headers,
        code=code,
    )

    if status == 401:
        if code == "TOTP_REQUIRED":
            return TOTPRequiredError(message, **kwargs)
        if code in ("SESSION_NOT_FOUND", "SESSION_EXPIRED"):
            return SessionExpiredError(message, **kwargs)
        return AuthenticationError(message, **kwargs)
    if status == 403:
        return PermissionError(message, **kwargs)
    if status == 404:
        return NotFoundError(message, **kwargs)
    if status == 423:
        return DataLockedError(message, **kwargs)
    if status == 429:
        remaining_time = body.get("remainingTime")
        return RateLimitError(message, remaining_time=remaining_time, **kwargs)
    if status in (400, 409, 422):
        return InvalidRequestError(message, **kwargs)
    if status >= 500:
        return ServerError(message, **kwargs)
    return APIStatusError(message, **kwargs)
