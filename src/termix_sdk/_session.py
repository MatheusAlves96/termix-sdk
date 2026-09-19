"""SSH session lifecycle helper (docs/sdk-plan.md phase F5).

`file_manager` and `docker` open an SSH-backed session server-side
(`connect` -> caller-supplied `sessionId`, kept alive with `keepalive`,
closed with `disconnect`); every other method on those two services
takes that same `sessionId`. The generated methods already take it as
an explicit keyword (docs/sdk-plan.md section 2, item 5: "the generated
code keeps exposing the raw methods with an explicit session_id") -
this module is purely an ergonomic layer on top, not something the
generated methods depend on.

Deliberately *not* wired in as a `.session()` method on the generated
`FileManagerService`/`DockerService` classes: doing that would mean
teaching the generator to special-case exactly two modules out of the
41 it produces, for a convenience the raw calls don't need. Call it as
a free function instead:

    with ssh_session(client.file_manager, host_id=5) as fm:
        fm.list_files(path="/")
    # disconnected automatically, even on error

    async with async_ssh_session(async_client.docker, host_id=5) as docker:
        await docker.list_containers()

`tunnel` and `metrics`/`proxmox_stats` were considered and excluded:
`tunnel.connect()` starts a named port-forward, not a session other
calls key off of, and `proxmox_stats`'s register_viewer/heartbeat/
unregister_viewer is a "viewer" pattern, not connect/disconnect - see
docs/sdk-plan.md section 4 for what each module actually covers.
"""

from __future__ import annotations

import contextlib
import inspect
import threading
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any, Protocol


# Callable attributes rather than method signatures: the generated services
# type `connect(*, options=..., **params: Unpack[<TypedDict>])`, which a
# `def connect(self, **params: Any)` protocol member rejects (restricted
# keyword set vs. arbitrary kwargs). `Callable[..., ...]` matches any
# keyword shape, which is all ssh_session() relies on.
class _SyncSessionService(Protocol):
    @property
    def connect(self) -> Callable[..., Any]: ...
    @property
    def disconnect(self) -> Callable[..., Any]: ...
    @property
    def keepalive(self) -> Callable[..., Any]: ...


class _AsyncSessionService(Protocol):
    @property
    def connect(self) -> Callable[..., Awaitable[Any]]: ...
    @property
    def disconnect(self) -> Callable[..., Awaitable[Any]]: ...
    @property
    def keepalive(self) -> Callable[..., Awaitable[Any]]: ...


class SessionHandle:
    """Wraps a service instance so every call through it automatically
    carries the session's id — `fm.list_files(path="/")` inside a `with
    ssh_session(...) as fm:` block is exactly
    `client.file_manager.list_files(sessionId=sid, path="/")`.

    The generated methods aren't consistent about that id's spelling,
    because they aren't consistent about *how* the spec's `sessionId`
    reaches them (docs/sdk-plan.md section 8): a path parameter like
    `GET /docker/containers/{sessionId}` becomes a snake_cased positional
    argument (`session_id`), while a query/body field like `sessionId`
    on `GET /ssh/file_manager/ssh/listFiles` keeps its original spelling
    as a `**params` key, because that key is sent to the wire as-is.
    A handful of methods (file_manager's trash endpoints) take neither,
    since the underlying route has no concept of a session — calling
    those through the handle just forwards whatever kwargs are passed.

    `__getattr__` inspects each attribute's real signature once, per
    call, to pick the right one of those three cases, so a caller
    doesn't have to know which applies session model.

    Calls through the handle are **keyword-only** — pass a path
    parameter like `container_id=...` by name, not positionally. This
    is what makes injecting the session id safe regardless of which
    positional slot it would otherwise occupy.
    """

    __slots__ = ("_service", "session_id")

    def __init__(self, service: Any, session_id: str) -> None:
        self._service = service
        self.session_id = session_id

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._service, name)
        if not callable(attr):
            return attr

        parameters = inspect.signature(attr).parameters
        takes_session_id_arg = "session_id" in parameters
        takes_var_keyword = any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
        )

        def call(**kwargs: Any) -> Any:
            if takes_session_id_arg:
                kwargs.setdefault("session_id", self.session_id)
            elif takes_var_keyword:
                kwargs.setdefault("sessionId", self.session_id)
            return attr(**kwargs)

        return call


@contextlib.contextmanager
def ssh_session(
    service: _SyncSessionService,
    *,
    host_id: int | str,
    keepalive: bool = False,
    keepalive_interval: float = 25.0,
    session_id: str | None = None,
    **connect_params: Any,
) -> Iterator[SessionHandle]:
    """`service` is `client.file_manager` or `client.docker` (anything
    with `connect`/`disconnect`/`keepalive` methods taking `sessionId`).
    `keepalive=True` starts a best-effort background thread pinging
    `keepalive` every `keepalive_interval` seconds — opt-in per
    docs/sdk-plan.md's 2026-09-19 decision, off by default so no hidden
    thread starts without the caller asking for one.
    """
    sid = session_id or str(uuid.uuid4())
    service.connect(sessionId=sid, hostId=host_id, **connect_params)

    stop_event = threading.Event()
    thread: threading.Thread | None = None
    if keepalive:
        thread = threading.Thread(
            target=_keepalive_loop,
            args=(service, sid, keepalive_interval, stop_event),
            daemon=True,
        )
        thread.start()

    try:
        yield SessionHandle(service, sid)
    finally:
        stop_event.set()
        if thread is not None:
            thread.join(timeout=keepalive_interval)
        with contextlib.suppress(Exception):
            service.disconnect(sessionId=sid)


def _keepalive_loop(
    service: _SyncSessionService,
    session_id: str,
    interval: float,
    stop_event: threading.Event,
) -> None:
    while not stop_event.wait(interval):
        with contextlib.suppress(Exception):
            # Best-effort: a failed keepalive doesn't tear the session
            # down here — the next real call the caller makes against
            # an actually-dead session will surface its own error.
            service.keepalive(sessionId=session_id)


@contextlib.asynccontextmanager
async def async_ssh_session(
    service: _AsyncSessionService,
    *,
    host_id: int | str,
    keepalive: bool = False,
    keepalive_interval: float = 25.0,
    session_id: str | None = None,
    **connect_params: Any,
) -> AsyncIterator[SessionHandle]:
    """Async mirror of `ssh_session()` — see its docstring. The keepalive
    loop runs as an `asyncio.Task`, not a thread.
    """
    import asyncio

    sid = session_id or str(uuid.uuid4())
    await service.connect(sessionId=sid, hostId=host_id, **connect_params)

    task: asyncio.Task[None] | None = None
    if keepalive:
        task = asyncio.ensure_future(_async_keepalive_loop(service, sid, keepalive_interval))

    try:
        yield SessionHandle(service, sid)
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        with contextlib.suppress(Exception):
            await service.disconnect(sessionId=sid)


async def _async_keepalive_loop(
    service: _AsyncSessionService, session_id: str, interval: float
) -> None:
    import asyncio

    while True:
        await asyncio.sleep(interval)
        with contextlib.suppress(Exception):
            await service.keepalive(sessionId=session_id)
