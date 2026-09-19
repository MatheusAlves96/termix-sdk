from __future__ import annotations

from termix_sdk._error import (
    AuthenticationError,
    DataLockedError,
    InvalidRequestError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
    SessionExpiredError,
    TOTPRequiredError,
    error_for_status,
)


def _err(status, **body):
    return error_for_status(
        status,
        message=body.get("error"),
        code=body.get("code"),
        body=body,
        http_body=None,
        headers={},
    )


def test_401_plain_is_authentication_error():
    err = _err(401, error="Missing authentication token")
    assert type(err) is AuthenticationError
    assert str(err) == "Missing authentication token"


def test_401_totp_required():
    err = _err(401, error="TOTP verification required", code="TOTP_REQUIRED")
    assert isinstance(err, TOTPRequiredError)
    assert isinstance(err, AuthenticationError)
    assert err.code == "TOTP_REQUIRED"


def test_401_session_expired_and_not_found():
    for code in ("SESSION_EXPIRED", "SESSION_NOT_FOUND"):
        err = _err(401, error="nope", code=code)
        assert isinstance(err, SessionExpiredError)


def test_403_is_permission_error():
    err = _err(403, error="Admin access required")
    assert type(err) is PermissionError


def test_404_is_not_found():
    err = _err(404, error="Target user not found")
    assert type(err) is NotFoundError


def test_423_data_locked():
    err = _err(423, error="Data is locked", code="DATA_LOCKED")
    assert isinstance(err, DataLockedError)


def test_429_rate_limit_carries_remaining_time():
    err = _err(429, error="Too many login attempts. Please try again later.", remainingTime=42)
    assert isinstance(err, RateLimitError)
    assert err.remaining_time == 42


def test_400_409_422_are_invalid_request():
    for status in (400, 409, 422):
        assert type(_err(status, error="bad")) is InvalidRequestError


def test_5xx_is_server_error():
    assert type(_err(500, error="boom")) is ServerError
    assert type(_err(503, error="boom")) is ServerError


def test_details_field_extracted():
    err = _err(400, error="bad", details="extra context")
    assert err.details == "extra context"


def test_repr_and_str():
    err = _err(404, error="not found")
    assert "not found" in str(err)
    assert "NotFoundError" in repr(err)
    assert "404" in repr(err)
