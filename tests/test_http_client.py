from __future__ import annotations

import httpx
import pytest

from termix_sdk._error import APIConnectionError
from termix_sdk._http_client import AsyncHTTPXClient, HTTPXClient

from .http_client_mock import MockAsyncHTTPClient, MockHTTPClient


def _redirect_once_handler(request: httpx.Request) -> httpx.Response:
    """Mimics nginx's trailing-slash redirect in front of the real Termix
    image (see CONTRIBUTING.md "Live smoke"): the bare path 301s, the
    trailing-slash path is where the real JSON lives.
    """
    if request.url.path == "/session_logs":
        return httpx.Response(301, headers={"location": "/session_logs/"})
    return httpx.Response(200, json={"logs": []})


def test_httpx_client_follows_redirects(monkeypatch: pytest.MonkeyPatch):
    """Regression test: httpx.Client defaults `follow_redirects` to False,
    so without passing it explicitly a 3xx response's tiny HTML/redirect
    body is returned as-is, which `_api_requestor.py` then can't parse as
    JSON and silently turns into `data=None` instead of an error or the
    real payload. See _http_client.py's HTTPXClient.__init__.
    """
    real_client_cls = httpx.Client

    def spy_client_cls(*args, **kwargs):
        assert kwargs.get("follow_redirects") is True
        transport = httpx.MockTransport(_redirect_once_handler)
        return real_client_cls(*args, **{**kwargs, "transport": transport})

    monkeypatch.setattr("termix_sdk._http_client.httpx.Client", spy_client_cls)

    client = HTTPXClient()
    content, status_code, _ = client.request("GET", "http://x/session_logs", headers={})

    assert status_code == 200
    assert content == b'{"logs":[]}'


@pytest.mark.asyncio
async def test_async_httpx_client_follows_redirects(monkeypatch: pytest.MonkeyPatch):
    real_client_cls = httpx.AsyncClient

    def spy_client_cls(*args, **kwargs):
        assert kwargs.get("follow_redirects") is True
        transport = httpx.MockTransport(_redirect_once_handler)
        return real_client_cls(*args, **{**kwargs, "transport": transport})

    monkeypatch.setattr("termix_sdk._http_client.httpx.AsyncClient", spy_client_cls)

    client = AsyncHTTPXClient()
    content, status_code, _ = await client.request("GET", "http://x/session_logs", headers={})

    assert status_code == 200
    assert content == b'{"logs":[]}'


def test_no_retry_when_should_retry_returns_false(mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(status_code=500, body={"error": "boom"})
    content, status, _ = mock_http_client.request_with_retries(
        "POST", "http://x/y", headers={}, should_retry=lambda *_: False
    )
    assert status == 500
    assert mock_http_client.attempts == 1


def test_retries_up_to_max_then_returns_last_response(mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(status_code=500, body={"error": "1"})
    mock_http_client.queue_response(status_code=500, body={"error": "2"})
    mock_http_client.queue_response(status_code=200, body={"ok": True})
    content, status, _ = mock_http_client.request_with_retries(
        "GET", "http://x/y", headers={}, max_retries=2, should_retry=lambda *a: True
    )
    assert status == 200
    assert mock_http_client.attempts == 3


def test_connection_failure_retried_then_raises(mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(raise_connection_error="dns fail")
    mock_http_client.queue_response(raise_connection_error="dns fail")
    with pytest.raises(APIConnectionError, match="dns fail"):
        mock_http_client.request_with_retries(
            "GET", "http://x/y", headers={}, max_retries=1, should_retry=lambda *a: True
        )
    assert mock_http_client.attempts == 2


def test_connection_failure_not_retried_when_should_retry_false(mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(raise_connection_error="dns fail")
    with pytest.raises(APIConnectionError):
        mock_http_client.request_with_retries(
            "GET", "http://x/y", headers={}, max_retries=3, should_retry=lambda *a: False
        )
    assert mock_http_client.attempts == 1


@pytest.mark.asyncio
async def test_async_retries(mock_async_http_client: MockAsyncHTTPClient):
    mock_async_http_client.queue_response(status_code=503, body={"error": "1"})
    mock_async_http_client.queue_response(status_code=200, body={"ok": True})
    content, status, _ = await mock_async_http_client.request_with_retries(
        "GET", "http://x/y", headers={}, max_retries=1, should_retry=lambda *a: True
    )
    assert status == 200
    assert mock_async_http_client.attempts == 2
