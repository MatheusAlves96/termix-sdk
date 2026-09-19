from __future__ import annotations

import pytest

from termix_sdk._api_requestor import APIRequestor, AsyncAPIRequestor
from termix_sdk._client_options import ClientOptions
from termix_sdk._error import AuthenticationError, NotFoundError, RateLimitError
from termix_sdk._request_options import ADMIN_TARGET_USER_HEADER

from .http_client_mock import MockAsyncHTTPClient, MockHTTPClient


def _requestor(mock_http_client: MockHTTPClient, **opts) -> APIRequestor:
    options = ClientOptions(base_url="http://gateway", api_key="tmx_test", **opts)
    return APIRequestor(options, http_client=mock_http_client)


def test_resolves_url_against_default_base(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={"ok": True})
    req.request("GET", "/health")
    assert mock_http_client.requests[0].url == "http://gateway/health"


def test_resolves_url_against_service_override(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client, service_urls={"metrics": "http://localhost:30005"})
    mock_http_client.queue_response(status_code=200, body={"ok": True})
    req.request("GET", "/status", service="metrics")
    assert mock_http_client.requests[0].url == "http://localhost:30005/status"


def test_sends_bearer_auth_header(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={"ok": True})
    req.request("GET", "/health")
    assert mock_http_client.requests[0].headers["Authorization"] == "Bearer tmx_test"


def test_anonymous_options_send_no_authorization_header(mock_http_client: MockHTTPClient):
    options = ClientOptions.anonymous(base_url="http://gateway")
    req = APIRequestor(options, http_client=mock_http_client)
    mock_http_client.queue_response(status_code=200, body={"ok": True})
    req.request("POST", "/users/login", json_body={"username": "a", "password": "b"})
    assert "Authorization" not in mock_http_client.requests[0].headers


def test_impersonation_header_from_options(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={"ok": True})
    req.request("GET", "/users/me", options={"impersonate_user": "alice"})
    assert mock_http_client.requests[0].headers[ADMIN_TARGET_USER_HEADER] == "alice"


def test_json_body_sent_as_json_when_no_files(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={"ok": True})
    req.request("POST", "/host/db/host", json_body={"name": "web-1"})
    assert mock_http_client.requests[0].json == {"name": "web-1"}
    assert mock_http_client.requests[0].data is None


def test_multipart_uses_data_not_json_when_files_present(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={"ok": True})
    req.request(
        "POST",
        "/host/db/host",
        json_body={"name": "web-1"},
        files={"key": ("id_rsa", b"...")},
    )
    sent = mock_http_client.requests[0]
    assert sent.data == {"name": "web-1"}
    assert sent.json is None
    assert sent.files == {"key": ("id_rsa", b"...")}


def test_query_params_forwarded(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={"logs": [], "total": 0})
    req.request("GET", "/audit-logs", query={"page": 1, "limit": 50})
    assert mock_http_client.requests[0].params == {"page": 1, "limit": 50}


def test_2xx_returns_parsed_response(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={"id": 1})
    resp = req.request("GET", "/host/db/host/1")
    assert resp is not None
    assert resp.data == {"id": 1}
    assert resp.status_code == 200


def test_non_json_2xx_body_does_not_crash(mock_http_client: MockHTTPClient):
    # GET /audit-logs/export (and similar) can answer 200 with a real
    # CSV/text body and no application/json content-type. This used to
    # crash with an uncaught JSONDecodeError inside TermixResponse's own
    # constructor — see _response.py's docstring on TermixResponse.
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(
        status_code=200,
        body=b"action,username\nlogin,alice",
        headers={"content-type": "text/csv"},
    )
    resp = req.request("GET", "/audit-logs/export")
    assert resp is not None
    assert resp.data is None
    assert resp.body == b"action,username\nlogin,alice"


def test_204_returns_none(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=204, body=None)
    resp = req.request("DELETE", "/host/db/host/1")
    assert resp is None


def test_404_raises_not_found_error(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=404, body={"error": "Target user not found"})
    with pytest.raises(NotFoundError, match="Target user not found"):
        req.request("GET", "/users/admin/export/nope")


def test_401_raises_authentication_error(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=401, body={"error": "Missing authentication token"})
    with pytest.raises(AuthenticationError):
        req.request("GET", "/users/me")


def test_429_rate_limit_carries_remaining_time(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(
        status_code=429,
        body={"error": "Too many login attempts. Please try again later.", "remainingTime": 30},
    )
    with pytest.raises(RateLimitError) as excinfo:
        req.request("POST", "/users/login", json_body={"username": "a", "password": "b"})
    assert excinfo.value.remaining_time == 30


def test_options_override_timeout_and_retries(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={"ok": True})
    req.request("GET", "/health", options={"timeout": 5.0})
    assert mock_http_client.requests[0].timeout == 5.0


@pytest.mark.asyncio
async def test_async_requestor_round_trip(mock_async_http_client: MockAsyncHTTPClient):
    options = ClientOptions(base_url="http://gateway", api_key="tmx_test")
    req = AsyncAPIRequestor(options, http_client=mock_async_http_client)
    mock_async_http_client.queue_response(status_code=200, body={"id": 1})
    resp = await req.request("GET", "/host/db/host/1")
    assert resp.data == {"id": 1}
    assert mock_async_http_client.requests[0].headers["Authorization"] == "Bearer tmx_test"


def test_request_sse_yields_events(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(
        status_code=200, body=b'event: tunnel_status\ndata: {"status": "connected"}\n\n'
    )
    events = list(req.request_sse("GET", "/ssh/tunnel/status/stream"))
    assert len(events) == 1
    assert events[0].event == "tunnel_status"
    assert events[0].json() == {"status": "connected"}
    assert mock_http_client.requests[0].headers["Accept"] == "text/event-stream"


def test_request_sse_error_status_raises(mock_http_client: MockHTTPClient):
    req = _requestor(mock_http_client)
    mock_http_client.queue_response(status_code=401, body={"error": "Authentication required"})
    with pytest.raises(AuthenticationError):
        list(req.request_sse("GET", "/ssh/tunnel/status/stream"))


@pytest.mark.asyncio
async def test_async_request_sse_yields_events(mock_async_http_client: MockAsyncHTTPClient):
    options = ClientOptions(base_url="http://gateway", api_key="tmx_test")
    req = AsyncAPIRequestor(options, http_client=mock_async_http_client)
    mock_async_http_client.queue_response(status_code=200, body=b'data: {"a": 1}\n\n')
    aiterator = await req.request_sse("GET", "/proxmox/discover/stream")
    events = [e async for e in aiterator]
    assert events[0].json() == {"a": 1}


@pytest.mark.asyncio
async def test_async_requestor_raises_typed_error(mock_async_http_client: MockAsyncHTTPClient):
    options = ClientOptions(base_url="http://gateway", api_key="tmx_test")
    req = AsyncAPIRequestor(options, http_client=mock_async_http_client)
    mock_async_http_client.queue_response(status_code=403, body={"error": "Admin access required"})
    from termix_sdk._error import PermissionError as TermixPermissionError

    with pytest.raises(TermixPermissionError):
        await req.request("POST", "/users/api-keys")
