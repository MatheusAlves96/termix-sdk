from __future__ import annotations

import pytest

from termix_sdk._response import SSEEvent, TermixResponse, TermixStreamResponse


def test_termix_response_parses_json_body():
    resp = TermixResponse(b'{"id": 1, "name": "web-1"}', 200, {"content-type": "application/json"})
    assert resp.data == {"id": 1, "name": "web-1"}
    assert resp.status_code == 200


def test_termix_response_empty_body_is_none_data():
    resp = TermixResponse(b"", 204, {})
    assert resp.data is None


def test_stream_response_read_concatenates_chunks():
    resp = TermixStreamResponse(iter([b"ab", b"cd"]), 200, {})
    assert resp.read() == b"abcd"


def test_stream_response_iter_bytes():
    resp = TermixStreamResponse(iter([b"a", b"b"]), 200, {})
    assert list(resp.iter_bytes()) == [b"a", b"b"]


def test_sse_event_json():
    event = SSEEvent(event="tunnel_status", data='{"status": "connected"}')
    assert event.json() == {"status": "connected"}
    assert "tunnel_status" in repr(event)


def test_sse_event_default_event_is_none():
    event = SSEEvent(event=None, data="{}")
    assert event.event is None


@pytest.mark.asyncio
async def test_async_stream_response_read():
    from termix_sdk._response import AsyncTermixStreamResponse

    async def gen():
        yield b"x"
        yield b"y"

    resp = AsyncTermixStreamResponse(gen(), 200, {})
    assert await resp.read() == b"xy"
