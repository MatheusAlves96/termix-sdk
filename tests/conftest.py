from __future__ import annotations

import pytest

from termix_sdk._async_client import AsyncTermixClient
from termix_sdk._client import TermixClient

from .http_client_mock import MockAsyncHTTPClient, MockHTTPClient

BASE_URL = "http://localhost:8080"


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry backoff in _http_client.py is real (0.25-5s per attempt) so
    it behaves correctly against a real Termix instance. Tests exercise the
    retry *logic*, not the *timing*, so sleeping is stubbed out here.
    """
    import asyncio

    monkeypatch.setattr("termix_sdk._http_client.time.sleep", lambda _seconds: None)

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)


@pytest.fixture()
def mock_http_client() -> MockHTTPClient:
    return MockHTTPClient()


@pytest.fixture()
def mock_async_http_client() -> MockAsyncHTTPClient:
    return MockAsyncHTTPClient()


@pytest.fixture()
def client(mock_http_client: MockHTTPClient) -> TermixClient:
    return TermixClient(
        base_url=BASE_URL,
        api_key="tmx_test_key",
        _http_client=mock_http_client,
    )


@pytest.fixture()
def async_client(mock_async_http_client: MockAsyncHTTPClient) -> AsyncTermixClient:
    return AsyncTermixClient(
        base_url=BASE_URL,
        api_key="tmx_test_key",
        _http_client=mock_async_http_client,
    )
