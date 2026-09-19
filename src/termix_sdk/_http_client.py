# Adapted from stripe-python (stripe/_http_client.py), MIT License,
# Copyright (c) 2010-2018 Stripe. See NOTICE for the full license text.
"""HTTP transport, isolated behind a small interface so `_api_requestor.py`
never imports httpx directly.

Unlike stripe's `_http_client.py` (which supports requests/urllib/pycurl as
alternate backends), this SDK settled on httpx only (docs/sdk-plan.md
section 10) — sync via `HTTPXClient`, async via `AsyncHTTPXClient`. The
retry loop and backoff formula are ported as-is from stripe; what decides
*whether* a given failure is retryable is injected by `_api_requestor.py`
via `should_retry`, since that decision depends on Termix's own status
codes, not Stripe's.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from typing import (
    Any,
)

from . import _util

try:
    import httpx
except ImportError:  # pragma: no cover - exercised by test_http_client.py
    httpx = None  # type: ignore[assignment]


class NoImportFoundError(Exception):
    """Raised when httpx isn't installed. httpx is a runtime dependency of
    this package, so seeing this means the environment is broken, not that
    an alternate backend needs configuring (there isn't one).
    """


MAX_DELAY = 5.0
INITIAL_DELAY = 0.5

# A connection error, or one of these statuses, is worth retrying.
RETRIABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

ShouldRetry = Callable[[int, int | None, Mapping[str, str]], bool]
"""(num_retries_so_far, http_status_or_None, response_headers) -> bool.
`http_status` is `None` when the failure was a connection error rather than
a completed response — see `_api_requestor.py` for the concrete predicate
this SDK uses.
"""


def _sleep_time_seconds(num_retries: int) -> float:
    sleep_seconds = min(INITIAL_DELAY * (2 ** (num_retries - 1)), MAX_DELAY)
    sleep_seconds *= 0.5 * (1 + random.uniform(0, 1))  # jitter
    return max(INITIAL_DELAY, sleep_seconds)


class HTTPClient:
    """Sync transport. `request_with_retries` is the entry point used by
    `_api_requestor.py`; `request` (a single attempt) is what a concrete
    backend implements.
    """

    def __init__(self, *, verify: bool = True, timeout: float = 30.0) -> None:
        self._verify = verify
        self._timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> tuple[bytes, int, Mapping[str, str]]:
        raise NotImplementedError

    def request_stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        timeout: float | None = None,
    ) -> tuple[Iterator[bytes], int, Mapping[str, str]]:
        """One attempt, never retried (a partially-streamed body can't be
        safely replayed). Used for `application/octet-stream` downloads.
        """
        raise NotImplementedError

    def close(self) -> None:
        pass

    def request_with_retries(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        timeout: float | None = None,
        max_retries: int = 2,
        should_retry: ShouldRetry = lambda *_: False,
    ) -> tuple[bytes, int, Mapping[str, str]]:
        num_retries = 0
        while True:
            try:
                content, status_code, resp_headers = self.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    data=data,
                    files=files,
                    timeout=timeout,
                )
            except _ConnectionFailure as exc:
                if num_retries < max_retries and should_retry(num_retries + 1, None, {}):
                    num_retries += 1
                    _util.log_debug(
                        "Encountered a connection error, retrying",
                        attempt=num_retries,
                        method=method,
                        url=url,
                    )
                    time.sleep(_sleep_time_seconds(num_retries))
                    continue
                raise exc.to_termix_error() from exc
            retryable = should_retry(num_retries + 1, status_code, resp_headers)
            if num_retries < max_retries and retryable:
                num_retries += 1
                _util.log_debug(
                    "Encountered a retryable status, retrying",
                    attempt=num_retries,
                    method=method,
                    url=url,
                    status=status_code,
                )
                time.sleep(_sleep_time_seconds(num_retries))
                continue
            return content, status_code, resp_headers


class _ConnectionFailure(Exception):
    """Internal signal used to carry a transport-level failure from a
    backend's `request()` up to `request_with_retries`'s retry loop, without
    the backend needing to know about `TermixError` at all.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def to_termix_error(self):
        from ._error import APIConnectionError

        return APIConnectionError(self.message)


def _require_httpx() -> None:
    if httpx is None:
        raise NoImportFoundError(
            "httpx is required by termix-sdk but isn't importable. Install "
            "it with `pip install httpx` (it should already be pulled in "
            "as a dependency of termix-sdk)."
        )


class HTTPXClient(HTTPClient):
    def __init__(self, *, verify: bool = True, timeout: float = 30.0) -> None:
        super().__init__(verify=verify, timeout=timeout)
        _require_httpx()
        self._client = httpx.Client(verify=verify, timeout=timeout)

    def request(
        self,
        method,
        url,
        *,
        headers,
        params=None,
        json=None,
        data=None,
        files=None,
        timeout=None,
    ):
        try:
            response = self._client.request(
                method,
                url,
                headers=dict(headers),
                params=params,
                json=json,
                data=data,
                files=files,
                timeout=timeout if timeout is not None else self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise _ConnectionFailure(f"Request to {url} timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise _ConnectionFailure(f"Could not reach {url}: {exc}") from exc
        return response.content, response.status_code, response.headers

    def request_stream(self, method, url, *, headers, params=None, json=None, timeout=None):
        try:
            request = self._client.build_request(
                method,
                url,
                headers=dict(headers),
                params=params,
                json=json,
                timeout=timeout if timeout is not None else self._timeout,
            )
            response = self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise _ConnectionFailure(f"Request to {url} timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise _ConnectionFailure(f"Could not reach {url}: {exc}") from exc

        def iterator() -> Iterator[bytes]:
            try:
                yield from response.iter_bytes()
            finally:
                response.close()

        return iterator(), response.status_code, response.headers

    def close(self) -> None:
        self._client.close()


class AsyncHTTPClient:
    """Async mirror of `HTTPClient`. Kept as a separate hierarchy (rather
    than sync/async variants of the same class) because `_client.py` and
    `_async_client.py` are themselves separate classes — see
    docs/sdk-plan.md section 2, item 7.
    """

    def __init__(self, *, verify: bool = True, timeout: float = 30.0) -> None:
        self._verify = verify
        self._timeout = timeout

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> tuple[bytes, int, Mapping[str, str]]:
        raise NotImplementedError

    async def request_stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        timeout: float | None = None,
    ) -> tuple[AsyncIterator[bytes], int, Mapping[str, str]]:
        """See `HTTPClient.request_stream`: one attempt, never retried."""
        raise NotImplementedError

    async def close(self) -> None:
        pass

    async def request_with_retries(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        timeout: float | None = None,
        max_retries: int = 2,
        should_retry: ShouldRetry = lambda *_: False,
    ) -> tuple[bytes, int, Mapping[str, str]]:
        num_retries = 0
        while True:
            try:
                content, status_code, resp_headers = await self.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    data=data,
                    files=files,
                    timeout=timeout,
                )
            except _ConnectionFailure as exc:
                if num_retries < max_retries and should_retry(num_retries + 1, None, {}):
                    num_retries += 1
                    await asyncio.sleep(_sleep_time_seconds(num_retries))
                    continue
                raise exc.to_termix_error() from exc
            retryable = should_retry(num_retries + 1, status_code, resp_headers)
            if num_retries < max_retries and retryable:
                num_retries += 1
                await asyncio.sleep(_sleep_time_seconds(num_retries))
                continue
            return content, status_code, resp_headers


class AsyncHTTPXClient(AsyncHTTPClient):
    def __init__(self, *, verify: bool = True, timeout: float = 30.0) -> None:
        super().__init__(verify=verify, timeout=timeout)
        _require_httpx()
        self._client = httpx.AsyncClient(verify=verify, timeout=timeout)

    async def request(
        self,
        method,
        url,
        *,
        headers,
        params=None,
        json=None,
        data=None,
        files=None,
        timeout=None,
    ):
        try:
            response = await self._client.request(
                method,
                url,
                headers=dict(headers),
                params=params,
                json=json,
                data=data,
                files=files,
                timeout=timeout if timeout is not None else self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise _ConnectionFailure(f"Request to {url} timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise _ConnectionFailure(f"Could not reach {url}: {exc}") from exc
        return response.content, response.status_code, response.headers

    async def request_stream(self, method, url, *, headers, params=None, json=None, timeout=None):
        try:
            request = self._client.build_request(
                method,
                url,
                headers=dict(headers),
                params=params,
                json=json,
                timeout=timeout if timeout is not None else self._timeout,
            )
            response = await self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise _ConnectionFailure(f"Request to {url} timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise _ConnectionFailure(f"Could not reach {url}: {exc}") from exc

        async def aiterator():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()

        return aiterator(), response.status_code, response.headers

    async def close(self) -> None:
        await self._client.aclose()
