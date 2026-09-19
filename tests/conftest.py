from __future__ import annotations

import pytest

from termix_sdk._async_client import AsyncTermixClient
from termix_sdk._client import TermixClient

from .http_client_mock import MockAsyncHTTPClient, MockHTTPClient

BASE_URL = "http://localhost:8080"


class _NoSleepTime:
    """A stand-in for the `time` module exposing only what _http_client.py
    actually uses, with `sleep` neutered. Swapping in an object like this
    for the *name* `time` inside `_http_client`'s own namespace (below)
    leaves the real, global `time` module — and any other module's own
    `import time` — untouched. An earlier version of this fixture instead
    did `monkeypatch.setattr("termix_sdk._http_client.time.sleep", ...)`,
    which resolves through to the *same* global `time` module object
    `_http_client.py`'s `import time` bound to, so it silently neutered
    `time.sleep` for the entire test session, in every module — including
    a real, deliberate `time.sleep()` a test elsewhere wanted for
    thread-timing (test_session.py's keepalive test), which then measured
    as instant and failed confusingly.
    """

    @staticmethod
    def sleep(_seconds: float) -> None:
        return None


class _NoSleepAsyncio:
    """Same idea as `_NoSleepTime`, for `asyncio.sleep` inside
    _http_client.py's own namespace only.
    """

    def __getattr__(self, name: str):
        import asyncio

        return getattr(asyncio, name)

    @staticmethod
    async def sleep(_seconds: float) -> None:
        return None


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry backoff in _http_client.py is real (0.25-5s per attempt) so
    it behaves correctly against a real Termix instance. Tests exercise the
    retry *logic*, not the *timing*, so sleeping is stubbed out here — only
    for _http_client.py's own use of `time`/`asyncio`, not globally (see
    `_NoSleepTime`'s docstring for why that distinction matters).
    """
    monkeypatch.setattr("termix_sdk._http_client.time", _NoSleepTime())
    monkeypatch.setattr("termix_sdk._http_client.asyncio", _NoSleepAsyncio())


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
