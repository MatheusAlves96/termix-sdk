# Adapted from stripe-python (tests/http_client_mock.py), MIT License,
# Copyright (c) 2010-2018 Stripe. See NOTICE for the full license text.
"""A scriptable fake transport: queue up responses (or connection failures),
then assert on what was actually sent. Used instead of hitting a real
Termix instance or mocking httpx internals directly, so tests exercise the
exact `HTTPClient`/`AsyncHTTPClient` interface `_api_requestor.py` depends
on.
"""

from __future__ import annotations

import json as _json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from termix_sdk._http_client import AsyncHTTPClient, HTTPClient, _ConnectionFailure


@dataclass
class RecordedRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    params: Mapping[str, Any] | None
    json: Any | None
    data: Any | None
    files: Any | None
    timeout: float | None


@dataclass
class QueuedResponse:
    status_code: int = 200
    body: Any = None
    headers: Mapping[str, str] = field(default_factory=lambda: {"content-type": "application/json"})
    raise_connection_error: str | None = None

    def as_content(self) -> bytes:
        if self.body is None:
            return b""
        if isinstance(self.body, (bytes, bytearray)):
            return bytes(self.body)
        return _json.dumps(self.body).encode("utf-8")


class MockHTTPClient(HTTPClient):
    def __init__(self) -> None:
        super().__init__()
        self.queue: list[QueuedResponse] = []
        self.requests: list[RecordedRequest] = []
        self.attempts = 0

    def queue_response(self, **kwargs: Any) -> None:
        self.queue.append(QueuedResponse(**kwargs))

    def request(
        self, method, url, *, headers, params=None, json=None, data=None, files=None, timeout=None
    ):
        self.attempts += 1
        self.requests.append(
            RecordedRequest(method, url, headers, params, json, data, files, timeout)
        )
        if not self.queue:
            raise AssertionError("MockHTTPClient: no queued response left")
        response = self.queue.pop(0)
        if response.raise_connection_error:
            raise _ConnectionFailure(response.raise_connection_error)
        return response.as_content(), response.status_code, response.headers

    def request_stream(self, method, url, *, headers, params=None, json=None, timeout=None):
        content, status_code, headers_out = self.request(
            method, url, headers=headers, params=params, json=json, timeout=timeout
        )

        def iterator() -> Iterator[bytes]:
            chunk_size = 8192
            for i in range(0, len(content), chunk_size):
                yield content[i : i + chunk_size]

        return iterator(), status_code, headers_out

    def close(self) -> None:
        pass


class MockAsyncHTTPClient(AsyncHTTPClient):
    def __init__(self) -> None:
        super().__init__()
        self.queue: list[QueuedResponse] = []
        self.requests: list[RecordedRequest] = []
        self.attempts = 0

    def queue_response(self, **kwargs: Any) -> None:
        self.queue.append(QueuedResponse(**kwargs))

    async def request(
        self, method, url, *, headers, params=None, json=None, data=None, files=None, timeout=None
    ):
        self.attempts += 1
        self.requests.append(
            RecordedRequest(method, url, headers, params, json, data, files, timeout)
        )
        if not self.queue:
            raise AssertionError("MockAsyncHTTPClient: no queued response left")
        response = self.queue.pop(0)
        if response.raise_connection_error:
            raise _ConnectionFailure(response.raise_connection_error)
        return response.as_content(), response.status_code, response.headers

    async def close(self) -> None:
        pass
