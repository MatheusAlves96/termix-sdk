from __future__ import annotations

import pytest

from termix_sdk._error import APIConnectionError

from .http_client_mock import MockAsyncHTTPClient, MockHTTPClient


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
