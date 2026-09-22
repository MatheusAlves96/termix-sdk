"""Gate and bootstrap for the live smoke suite.

Everything under `tests/live/` talks to a real Termix instance, so the
whole directory is skipped unless `TERMIX_LIVE=1` and `TERMIX_BASE_URL`
are set — `uv run pytest` keeps running only the mocked suites by
default. See CONTRIBUTING.md, "Live smoke", for how to run it.
"""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Iterator
from typing import Any

import pytest

from termix_sdk import (
    AsyncTermixClient,
    NotFoundError,
    PendingTOTP,
    TermixClient,
    TermixError,
)

BASE_URL = os.environ.get("TERMIX_BASE_URL", "")
PASSWORD = os.environ.get("TERMIX_LIVE_PASSWORD", "")
USERNAME = os.environ.get("TERMIX_LIVE_USER", "ci")

if os.environ.get("TERMIX_LIVE") != "1" or not BASE_URL:
    pytest.skip(
        "live smoke: set TERMIX_LIVE=1 and TERMIX_BASE_URL to run this suite",
        allow_module_level=True,
    )

HEALTH_TIMEOUT_SECONDS = 60
HEALTH_INTERVAL_SECONDS = 2.0


@pytest.fixture(autouse=True)
def _no_real_sleeping() -> None:
    """Override `tests/conftest.py`'s autouse fixture of the same name.

    That one neuters `time.sleep`/`asyncio.sleep` inside `_http_client`
    so the mocked suites don't pay the retry backoff. Against a real
    server the backoff is the point — without this override the SDK would
    burn its two retries instantly on a Termix that is merely slow.
    """
    return None


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def password() -> str:
    return PASSWORD


@pytest.fixture(scope="session")
def run_prefix() -> str:
    """Name prefix for everything this run creates, so the teardown can
    find its own leftovers and two runs never delete each other's.
    """
    return f"live-smoke-{secrets.token_hex(4)}"


@pytest.fixture(scope="session")
def _termix_is_up() -> None:
    """`GET /health` is public — poll it until the container is serving."""
    probe = TermixClient(base_url=BASE_URL, api_key="tmx_health_probe")
    deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            probe.system.health()
            return
        except TermixError as exc:  # not up yet, or still booting
            last_error = exc
            time.sleep(HEALTH_INTERVAL_SECONDS)
    pytest.fail(f"{BASE_URL}/health did not answer in {HEALTH_TIMEOUT_SECONDS}s: {last_error!r}")


@pytest.fixture(scope="session")
def jwt_client(_termix_is_up: None) -> TermixClient:
    """A JWT-authenticated client, registering the smoke user if needed.

    The first account created on an empty instance becomes the admin
    (verified against release-2.8.0-tag), and `api_keys.*` is admin-only,
    so on a fresh instance this user can mint the API key the rest of the
    suite runs on.
    """
    if not PASSWORD:
        pytest.fail("TERMIX_LIVE_PASSWORD is required when TERMIX_LIVE=1")

    anonymous = TermixClient(base_url=BASE_URL, api_key="tmx_bootstrap_probe")
    try:
        anonymous.users.register(username=USERNAME, password=PASSWORD)
    except TermixError as exc:
        # Already registered by an earlier run against the same instance;
        # the login below is what actually has to work.
        if exc.http_status is None or exc.http_status >= 500:
            raise

    client = TermixClient.login(base_url=BASE_URL, username=USERNAME, password=PASSWORD)
    if isinstance(client, PendingTOTP):
        pytest.fail("the smoke instance must not have TOTP enabled for the CI user")
    return client


@pytest.fixture(scope="session")
def me(jwt_client: TermixClient) -> dict[str, Any]:
    return jwt_client.users.get_me().to_dict()


@pytest.fixture(scope="session")
def api_key(jwt_client: TermixClient, me: dict[str, Any], run_prefix: str) -> Iterator[str]:
    """The API key the suite authenticates with — the path the README
    recommends. Skips (rather than fails) when the smoke user is not an
    admin, which happens when it was not the first account on the
    instance; `api_keys.*` is admin-only.
    """
    if not me.get("is_admin"):
        pytest.skip(f"{USERNAME} is not an admin on this instance; api_keys.* is admin-only")

    created = jwt_client.api_keys.create(name=run_prefix, userId=me["userId"])
    yield created.token
    try:
        jwt_client.api_keys.delete(created.id)
    except NotFoundError:
        pass


@pytest.fixture(scope="session")
def client(api_key: str, run_prefix: str) -> Iterator[TermixClient]:
    with TermixClient(base_url=BASE_URL, api_key=api_key) as live:
        yield live
        _cleanup(live, run_prefix)


@pytest.fixture()
async def async_client(api_key: str) -> Any:
    """Function-scoped on purpose: an `AsyncTermixClient` holds an httpx
    async transport, and pytest-asyncio gives each test its own event
    loop. Session scope here would bind the transport to a loop that is
    already closed by the second test.
    """
    async with AsyncTermixClient(base_url=BASE_URL, api_key=api_key) as live:
        yield live


def _cleanup(live: TermixClient, run_prefix: str) -> None:
    """Delete whatever this run created and did not delete itself."""
    for host in live.hosts.list():
        data = host.to_dict()
        if str(data.get("name", "")).startswith(run_prefix):
            _ignore_missing(lambda: live.hosts.delete(str(data["id"])))
    for snippet in live.snippets.list():
        data = snippet if isinstance(snippet, dict) else snippet.to_dict()
        if str(data.get("name", "")).startswith(run_prefix):
            _ignore_missing(lambda: live.snippets.delete(str(data["id"])))
    for workspace in live.workspaces.list():
        if str(workspace.get("name", "")).startswith(run_prefix):
            _ignore_missing(lambda: live.workspaces.delete(str(workspace["id"])))
    for preset in live.tunnel_presets.list():
        if str(preset.get("name", "")).startswith(run_prefix):
            _ignore_missing(lambda: live.tunnel_presets.delete(str(preset["id"])))
    for credential in live.credentials.list():
        if str(credential.get("name", "")).startswith(run_prefix):
            _ignore_missing(lambda: live.credentials.delete(str(credential["id"])))
    for channel in live.alerts.list_channels():
        data = channel.to_dict()
        if str(data.get("name", "")).startswith(run_prefix):
            _ignore_missing(lambda: live.alerts.delete_channel(str(data["id"])))
    for tab in live.open_tabs.list():
        data = tab.to_dict()
        if str(data.get("id", "")).startswith(run_prefix):
            _ignore_missing(lambda: live.open_tabs.delete(str(data["id"])))


def _ignore_missing(call: Any) -> None:
    try:
        call()
    except NotFoundError:
        pass
