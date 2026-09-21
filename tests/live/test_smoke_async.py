"""The same smoke cases as `test_smoke.py`, through `AsyncTermixClient`.

The async client has its own requestor and transport, so "the sync one
works" says nothing about it — the `login()` regression this suite was
born from was present in both.
"""

from __future__ import annotations

import warnings
from typing import Any

import pytest

from termix_sdk import (
    SPEC_VERSION,
    AsyncTermixClient,
    AuthenticationError,
    NotFoundError,
)

pytestmark = pytest.mark.live


async def test_health(async_client: AsyncTermixClient) -> None:
    health = await async_client.system.health()
    assert health.status == "ok"


async def test_version_matches_the_spec_the_sdk_was_generated_from(
    async_client: AsyncTermixClient,
) -> None:
    version = (await async_client.system.version()).to_dict()
    # See test_smoke.py's sync twin for why `localVersion` comes first.
    local = version.get("localVersion") or version.get("version")
    assert local, f"no version field in {version!r}"
    if f"release-{local}-tag" != SPEC_VERSION:
        warnings.warn(
            f"Termix {local} vs SPEC_VERSION {SPEC_VERSION}: the SDK may be "
            f"generated from an older release",
            stacklevel=1,
        )


async def test_get_me(async_client: AsyncTermixClient) -> None:
    me = await async_client.users.get_me()
    assert me.username == "ci"
    assert me.userId


async def test_api_key_from_the_bootstrap_is_listed(
    async_client: AsyncTermixClient, run_prefix: str
) -> None:
    keys = await async_client.api_keys.list()
    assert run_prefix in [key["name"] for key in keys.apiKeys]


async def test_hosts_crud(async_client: AsyncTermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-host-async"
    payload: dict[str, Any] = {
        "ip": "10.0.0.2",
        "port": 22,
        "username": "root",
        "authType": "password",
        "name": name,
    }
    created = await async_client.hosts.create(**payload)
    host_id = str(created.to_dict()["id"])

    assert (await async_client.hosts.retrieve(host_id)).name == name

    renamed = f"{name}-renamed"
    await async_client.hosts.update(host_id, **{**payload, "name": renamed})
    assert (await async_client.hosts.retrieve(host_id)).name == renamed

    hosts = await async_client.hosts.list()
    assert renamed in [host.to_dict()["name"] for host in hosts]

    await async_client.hosts.delete(host_id)
    with pytest.raises(NotFoundError):
        await async_client.hosts.retrieve(host_id)


async def test_snippets_crud(async_client: AsyncTermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-snippet-async"
    created = await async_client.snippets.create(name=name, content="echo live-smoke")
    snippet_id = str(created.id)

    fetched = await async_client.snippets.retrieve(snippet_id)
    assert fetched.content == "echo live-smoke"
    snippets = await async_client.snippets.list()
    assert name in [snippet["name"] for snippet in snippets]

    # Partial update: only `content` is sent, so `name` has to survive it.
    await async_client.snippets.update(snippet_id, content="echo live-smoke-updated")
    updated = await async_client.snippets.retrieve(snippet_id)
    assert updated.content == "echo live-smoke-updated"
    assert updated.name == name

    await async_client.snippets.delete(snippet_id)
    with pytest.raises(NotFoundError):
        await async_client.snippets.retrieve(snippet_id)


async def test_unknown_id_raises_not_found(async_client: AsyncTermixClient) -> None:
    with pytest.raises(NotFoundError) as excinfo:
        await async_client.hosts.retrieve("999999999")
    assert excinfo.value.http_status == 404


async def test_invalid_api_key_raises_authentication_error(base_url: str) -> None:
    async with AsyncTermixClient(base_url=base_url, api_key="tmx_invalid") as bad:
        with pytest.raises(AuthenticationError) as excinfo:
            await bad.hosts.list()
    assert excinfo.value.http_status == 401


async def test_login_returns_a_usable_client(base_url: str, password: str) -> None:
    logged_in = await AsyncTermixClient.login(base_url=base_url, username="ci", password=password)
    assert isinstance(logged_in, AsyncTermixClient)
    async with logged_in:
        me = await logged_in.users.get_me()
        assert me.username == "ci"
