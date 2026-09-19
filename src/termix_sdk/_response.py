# Adapted from stripe-python (stripe/_stripe_response.py), MIT License,
# Copyright (c) 2010-2018 Stripe. See NOTICE for the full license text.
"""Thin wrappers around a raw HTTP response, before it becomes a TermixObject
or model instance.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any


class TermixResponseBase:
    status_code: int
    headers: Mapping[str, str]

    def __init__(self, status_code: int, headers: Mapping[str, str]) -> None:
        self.status_code = status_code
        self.headers = headers


class TermixResponse(TermixResponseBase):
    """A response `_api_requestor.py` has already decided the outcome for.

    `data` is passed in already parsed (or `None` when the body isn't
    JSON) — this class does not parse JSON itself. It used to
    (`json.loads(body) if body else None` in `__init__`), which meant a
    genuinely non-JSON body (real CSV/RSS/HTML — see
    `_api_requestor.py`'s comment on why some endpoints fall through to
    this) crashed with an uncaught `JSONDecodeError` right in the
    constructor, in the exact branch whose whole point was to hand back
    the raw body gracefully instead of raising.
    """

    body: bytes
    data: Any

    def __init__(
        self, body: bytes, data: Any, status_code: int, headers: Mapping[str, str]
    ) -> None:
        super().__init__(status_code, headers)
        self.body = body
        self.data = data


class TermixStreamResponse(TermixResponseBase):
    """A binary or text response the caller wants to consume in chunks
    (file downloads, `application/octet-stream`).
    """

    def __init__(
        self,
        iter_bytes: Iterator[bytes],
        status_code: int,
        headers: Mapping[str, str],
    ) -> None:
        super().__init__(status_code, headers)
        self._iter_bytes = iter_bytes

    def iter_bytes(self) -> Iterator[bytes]:
        return self._iter_bytes

    def read(self) -> bytes:
        return b"".join(self._iter_bytes)


class AsyncTermixStreamResponse(TermixResponseBase):
    def __init__(
        self,
        aiter_bytes: AsyncIterator[bytes],
        status_code: int,
        headers: Mapping[str, str],
    ) -> None:
        super().__init__(status_code, headers)
        self._aiter_bytes = aiter_bytes

    def aiter_bytes(self) -> AsyncIterator[bytes]:
        return self._aiter_bytes

    async def read(self) -> bytes:
        chunks = []
        async for chunk in self._aiter_bytes:
            chunks.append(chunk)
        return b"".join(chunks)


class SSEEvent:
    """One `event:`/`data:` pair from a `text/event-stream` response.

    `event` is `None` for a bare `data:` line (the backend's default,
    unnamed event). `: keepalive` heartbeat comments are swallowed by the
    SSE iterator in `_sse.py` and never surface here.
    """

    __slots__ = ("event", "data")

    def __init__(self, event: str | None, data: str) -> None:
        self.event = event
        self.data = data

    def json(self) -> Any:
        return json.loads(self.data)

    def __repr__(self) -> str:
        return f"SSEEvent(event={self.event!r}, data={self.data!r})"
