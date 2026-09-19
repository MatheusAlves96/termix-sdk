"""Server-Sent Events parsing (docs/sdk-plan.md phase F6).

3 endpoints stream `text/event-stream` instead of answering with a
single JSON body: `GET /ssh/tunnel/status/stream`,
`GET /proxmox/discover/stream`, `POST /ai/chat/stream`. None of them
declare a response schema in the spec (spec-gen has no signal to
document SSE framing from — see tools/spec-gen/docs/
spec-generation-strategy.md's own note on this), so which operations
get this treatment is a hardcoded `"sse": true` flag in
tools/sdk-gen/config/resource-map.json, not something the generator
infers from spec/termix-openapi.json the way it does everything else.

The `: keepalive` comment line the tunnel status stream sends every 30s
is swallowed here like any other SSE comment line — it never becomes
an `SSEEvent`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from ._response import SSEEvent


def _parse_block(block: str) -> SSEEvent | None:
    """One SSE block: consecutive `field: value` lines (and `:
    comment` lines, ignored), terminated by the blank line that
    already split it off from the next block. No `data:` line at all
    means no event (a heartbeat is exactly this — comment lines only).
    """
    event_name: str | None = None
    data_lines: list[str] = []
    for line in block.splitlines():
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
        # Other SSE fields (id:, retry:) exist in the spec but none of
        # this SDK's 3 SSE endpoints use them, so they're not modeled.
    if not data_lines:
        return None
    return SSEEvent(event=event_name, data="\n".join(data_lines))


def _split_blocks(buffer: str) -> tuple[list[str], str]:
    """Split `buffer` on blank-line block separators (`\\n\\n` or
    `\\r\\n\\r\\n`). Returns the complete blocks found and whatever's
    left over (a possibly-incomplete final block, kept for the next
    chunk).
    """
    normalized = buffer.replace("\r\n", "\n")
    parts = normalized.split("\n\n")
    return parts[:-1], parts[-1]


def iter_sse_events(byte_chunks: Iterator[bytes]) -> Iterator[SSEEvent]:
    buffer = ""
    for chunk in byte_chunks:
        buffer += chunk.decode("utf-8", errors="replace")
        blocks, buffer = _split_blocks(buffer)
        for block in blocks:
            event = _parse_block(block)
            if event is not None:
                yield event
    # A trailing block with no terminating blank line is dropped, per
    # the SSE spec's own framing — the stream ended mid-event.


async def aiter_sse_events(byte_chunks: AsyncIterator[bytes]) -> AsyncIterator[SSEEvent]:
    buffer = ""
    async for chunk in byte_chunks:
        buffer += chunk.decode("utf-8", errors="replace")
        blocks, buffer = _split_blocks(buffer)
        for block in blocks:
            event = _parse_block(block)
            if event is not None:
                yield event
