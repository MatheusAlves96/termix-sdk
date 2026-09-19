from __future__ import annotations

import pytest

from termix_sdk._async_client import AsyncTermixClient
from termix_sdk._client import TermixClient

from .http_client_mock import MockAsyncHTTPClient, MockHTTPClient


def test_client_low_level_request(client: TermixClient, mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(status_code=200, body={"status": "ok"})
    resp = client.request("GET", "/health")
    assert resp.data == {"status": "ok"}


def test_client_context_manager_closes(mock_http_client: MockHTTPClient):
    closed = {"value": False}
    mock_http_client.close = lambda: closed.update(value=True)  # type: ignore[method-assign]
    with TermixClient(base_url="http://x", api_key="tmx_a", _http_client=mock_http_client):
        pass
    assert closed["value"] is True


def test_client_rejects_missing_credentials():
    with pytest.raises(ValueError):
        TermixClient(base_url="http://x")


@pytest.mark.asyncio
async def test_async_client_low_level_request(
    async_client: AsyncTermixClient, mock_async_http_client: MockAsyncHTTPClient
):
    mock_async_http_client.queue_response(status_code=200, body={"status": "ok"})
    resp = await async_client.request("GET", "/health")
    assert resp.data == {"status": "ok"}


@pytest.mark.asyncio
async def test_async_client_context_manager_closes(mock_async_http_client: MockAsyncHTTPClient):
    closed = {"value": False}

    async def fake_close():
        closed["value"] = True

    mock_async_http_client.close = fake_close  # type: ignore[method-assign]
    client = AsyncTermixClient(
        base_url="http://x", api_key="tmx_a", _http_client=mock_async_http_client
    )
    async with client:
        pass
    assert closed["value"] is True
