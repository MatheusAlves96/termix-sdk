from __future__ import annotations

import pytest

from termix_sdk._async_client import AsyncTermixClient
from termix_sdk._auth import AsyncPendingTOTP, PendingTOTP
from termix_sdk._client import TermixClient
from termix_sdk._error import AuthenticationError, RateLimitError, TermixError

from .http_client_mock import MockAsyncHTTPClient, MockHTTPClient

BASE_URL = "http://gateway"


def test_login_sends_native_app_header(mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(
        status_code=200,
        body={"success": True, "is_admin": False, "username": "alice", "token": "jwt_abc"},
    )
    client = TermixClient.login(
        base_url=BASE_URL, username="alice", password="pw", _http_client=mock_http_client
    )
    assert isinstance(client, TermixClient)
    sent = mock_http_client.requests[0]
    assert sent.headers["X-Electron-App"] == "true"
    assert "Authorization" not in sent.headers
    assert sent.json == {"username": "alice", "password": "pw", "rememberMe": False}


def test_login_success_returns_authenticated_client(mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(
        status_code=200,
        body={"success": True, "is_admin": True, "username": "alice", "token": "jwt_abc"},
    )
    client = TermixClient.login(
        base_url=BASE_URL, username="alice", password="pw", _http_client=mock_http_client
    )
    assert isinstance(client, TermixClient)

    mock_http_client.queue_response(status_code=200, body={"status": "ok"})
    client.request("GET", "/health")
    assert mock_http_client.requests[1].headers["Authorization"] == "Bearer jwt_abc"


def test_login_without_totp_and_without_native_header_raises(mock_http_client: MockHTTPClient):
    # A real Termix instance would never hit this given we always send
    # X-Electron-App, but guard the invariant explicitly.
    mock_http_client.queue_response(
        status_code=200, body={"success": True, "is_admin": False, "username": "alice"}
    )
    with pytest.raises(TermixError, match="without a token"):
        TermixClient.login(
            base_url=BASE_URL, username="alice", password="pw", _http_client=mock_http_client
        )


def test_login_requires_totp_returns_pending(mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(
        status_code=200,
        body={
            "success": True,
            "requires_totp": True,
            "temp_token": "temp_xyz",
            "rememberMe": True,
        },
    )
    result = TermixClient.login(
        base_url=BASE_URL,
        username="alice",
        password="pw",
        remember_me=True,
        _http_client=mock_http_client,
    )
    assert isinstance(result, PendingTOTP)
    assert result.temp_token == "temp_xyz"
    assert result.remember_me is True


def test_pending_totp_verify_sends_temp_token_and_code(mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(
        status_code=200,
        body={
            "success": True,
            "requires_totp": True,
            "temp_token": "temp_xyz",
            "rememberMe": False,
        },
    )
    pending = TermixClient.login(
        base_url=BASE_URL, username="alice", password="pw", _http_client=mock_http_client
    )
    assert isinstance(pending, PendingTOTP)

    mock_http_client.queue_response(
        status_code=200, body={"success": True, "is_admin": False, "token": "jwt_after_totp"}
    )
    client = pending.verify("123456")
    assert isinstance(client, TermixClient)
    sent = mock_http_client.requests[1]
    assert sent.json == {"temp_token": "temp_xyz", "totp_code": "123456", "rememberMe": False}

    mock_http_client.queue_response(status_code=200, body={"status": "ok"})
    client.request("GET", "/health")
    assert mock_http_client.requests[2].headers["Authorization"] == "Bearer jwt_after_totp"


def test_login_incorrect_password_raises_authentication_error(mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(status_code=401, body={"error": "Incorrect password"})
    with pytest.raises(AuthenticationError, match="Incorrect password"):
        TermixClient.login(
            base_url=BASE_URL, username="alice", password="wrong", _http_client=mock_http_client
        )


def test_login_rate_limited_carries_remaining_time(mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(
        status_code=429,
        body={"error": "Too many login attempts. Please try again later.", "remainingTime": 55},
    )
    with pytest.raises(RateLimitError) as excinfo:
        TermixClient.login(
            base_url=BASE_URL, username="alice", password="pw", _http_client=mock_http_client
        )
    assert excinfo.value.remaining_time == 55


@pytest.mark.asyncio
async def test_async_login_success(mock_async_http_client: MockAsyncHTTPClient):
    mock_async_http_client.queue_response(
        status_code=200, body={"success": True, "is_admin": False, "token": "jwt_async"}
    )
    client = await AsyncTermixClient.login(
        base_url=BASE_URL, username="alice", password="pw", _http_client=mock_async_http_client
    )
    assert isinstance(client, AsyncTermixClient)

    mock_async_http_client.queue_response(status_code=200, body={"status": "ok"})
    await client.request("GET", "/health")
    assert mock_async_http_client.requests[1].headers["Authorization"] == "Bearer jwt_async"


@pytest.mark.asyncio
async def test_async_login_requires_totp_then_verify(mock_async_http_client: MockAsyncHTTPClient):
    mock_async_http_client.queue_response(
        status_code=200,
        body={"success": True, "requires_totp": True, "temp_token": "temp_a", "rememberMe": False},
    )
    pending = await AsyncTermixClient.login(
        base_url=BASE_URL, username="alice", password="pw", _http_client=mock_async_http_client
    )
    assert isinstance(pending, AsyncPendingTOTP)

    mock_async_http_client.queue_response(
        status_code=200, body={"success": True, "token": "jwt_totp_async"}
    )
    client = await pending.verify("654321")
    assert isinstance(client, AsyncTermixClient)


def test_login_client_has_resource_attributes(mock_http_client: MockHTTPClient):
    """`_with_options()` builds the client with `cls.__new__`, skipping
    `__init__` — so it has to wire the resources itself. It didn't, and
    every `client.users` / `client.hosts` on a logged-in client raised
    `AttributeError` (found by the live smoke against a real Termix).
    """
    mock_http_client.queue_response(
        status_code=200, body={"success": True, "is_admin": True, "token": "jwt_abc"}
    )
    client = TermixClient.login(
        base_url=BASE_URL, username="alice", password="pw", _http_client=mock_http_client
    )
    assert isinstance(client, TermixClient)

    mock_http_client.queue_response(status_code=200, body={"username": "alice"})
    assert client.users.get_me().username == "alice"
    assert mock_http_client.requests[1].headers["Authorization"] == "Bearer jwt_abc"


def test_totp_verified_client_has_resource_attributes(mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(
        status_code=200,
        body={"success": True, "requires_totp": True, "temp_token": "temp_xyz"},
    )
    pending = TermixClient.login(
        base_url=BASE_URL, username="alice", password="pw", _http_client=mock_http_client
    )
    assert isinstance(pending, PendingTOTP)

    mock_http_client.queue_response(status_code=200, body={"success": True, "token": "jwt_totp"})
    client = pending.verify("123456")

    mock_http_client.queue_response(status_code=200, body={"status": "ok"})
    assert client.system.health().status == "ok"
    assert mock_http_client.requests[2].headers["Authorization"] == "Bearer jwt_totp"


@pytest.mark.asyncio
async def test_async_login_client_has_resource_attributes(
    mock_async_http_client: MockAsyncHTTPClient,
):
    mock_async_http_client.queue_response(
        status_code=200, body={"success": True, "token": "jwt_async"}
    )
    client = await AsyncTermixClient.login(
        base_url=BASE_URL, username="alice", password="pw", _http_client=mock_async_http_client
    )
    assert isinstance(client, AsyncTermixClient)

    mock_async_http_client.queue_response(status_code=200, body={"username": "alice"})
    me = await client.users.get_me()
    assert me.username == "alice"


@pytest.mark.asyncio
async def test_async_totp_verified_client_has_resource_attributes(
    mock_async_http_client: MockAsyncHTTPClient,
):
    mock_async_http_client.queue_response(
        status_code=200,
        body={"success": True, "requires_totp": True, "temp_token": "temp_a"},
    )
    pending = await AsyncTermixClient.login(
        base_url=BASE_URL, username="alice", password="pw", _http_client=mock_async_http_client
    )
    assert isinstance(pending, AsyncPendingTOTP)

    mock_async_http_client.queue_response(
        status_code=200, body={"success": True, "token": "jwt_totp_async"}
    )
    client = await pending.verify("654321")

    mock_async_http_client.queue_response(status_code=200, body={"status": "ok"})
    health = await client.system.health()
    assert health.status == "ok"
