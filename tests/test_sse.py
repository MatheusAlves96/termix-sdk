from __future__ import annotations

import pytest

from termix_sdk._sse import aiter_sse_events, iter_sse_events


def test_single_event_with_name():
    chunks = [b'event: tunnel_status\ndata: {"status": "connected"}\n\n']
    events = list(iter_sse_events(iter(chunks)))
    assert len(events) == 1
    assert events[0].event == "tunnel_status"
    assert events[0].json() == {"status": "connected"}


def test_bare_data_event_has_no_name():
    chunks = [b'data: {"a": 1}\n\n']
    events = list(iter_sse_events(iter(chunks)))
    assert events[0].event is None
    assert events[0].json() == {"a": 1}


def test_multiple_events_in_one_chunk():
    chunks = [b'data: {"a": 1}\n\ndata: {"a": 2}\n\n']
    events = list(iter_sse_events(iter(chunks)))
    assert [e.json() for e in events] == [{"a": 1}, {"a": 2}]


def test_event_split_across_chunks():
    chunks = [b'data: {"a"', b": 1}\n", b"\n"]
    events = list(iter_sse_events(iter(chunks)))
    assert events[0].json() == {"a": 1}


def test_keepalive_comment_line_is_swallowed():
    chunks = [b': keepalive\n\ndata: {"a": 1}\n\n']
    events = list(iter_sse_events(iter(chunks)))
    assert len(events) == 1
    assert events[0].json() == {"a": 1}


def test_multiline_data_joined_with_newline():
    chunks = [b"data: line1\ndata: line2\n\n"]
    events = list(iter_sse_events(iter(chunks)))
    assert events[0].data == "line1\nline2"


def test_trailing_incomplete_block_is_dropped():
    chunks = [b'data: {"a": 1}\n\ndata: incomplete-no-terminator']
    events = list(iter_sse_events(iter(chunks)))
    assert len(events) == 1


def test_crlf_line_endings():
    chunks = [b'event: x\r\ndata: {"a": 1}\r\n\r\n']
    events = list(iter_sse_events(iter(chunks)))
    assert events[0].event == "x"
    assert events[0].json() == {"a": 1}


@pytest.mark.asyncio
async def test_async_iter_sse_events():
    async def gen():
        yield b'event: x\ndata: {"a": 1}\n\n'
        yield b'data: {"a": 2}\n\n'

    events = [e async for e in aiter_sse_events(gen())]
    assert [e.json() for e in events] == [{"a": 1}, {"a": 2}]
