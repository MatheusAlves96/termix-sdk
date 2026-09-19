"""Smoke suite: the SDK against a real Termix instance (sync client).

Scope is deliberately narrow — auth, the central read/write endpoints and
the error mapping. Nothing here opens an SSH session, a Docker container
or a tmux session; see CONTRIBUTING.md, "Live smoke", for why.
"""

from __future__ import annotations

import warnings
from typing import Any

import pytest

from termix_sdk import SPEC_VERSION, AuthenticationError, NotFoundError, TermixClient

pytestmark = pytest.mark.live


def test_health(client: TermixClient) -> None:
    assert client.system.health().status == "ok"


def test_version_matches_the_spec_the_sdk_was_generated_from(client: TermixClient) -> None:
    version = client.system.version().to_dict()
    local = version.get("version") or version.get("localVersion")
    assert local, f"no version field in {version!r}"

    # Not an assertion: a newer Termix is expected to show up here first,
    # and the weekly schedule surfacing it is the point of this suite.
    if f"release-{local}-tag" != SPEC_VERSION:
        warnings.warn(
            f"Termix {local} vs SPEC_VERSION {SPEC_VERSION}: the SDK may be "
            f"generated from an older release",
            stacklevel=1,
        )


def test_get_me(client: TermixClient) -> None:
    me = client.users.get_me()
    assert me.username == "ci"
    assert me.userId


def test_api_key_from_the_bootstrap_is_listed(client: TermixClient, run_prefix: str) -> None:
    names = [key["name"] for key in client.api_keys.list().apiKeys]
    assert run_prefix in names


def test_hosts_crud(client: TermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-host"
    payload: dict[str, Any] = {
        "ip": "10.0.0.1",
        "port": 22,
        "username": "root",
        "authType": "password",
        "name": name,
    }
    created = client.hosts.create(**payload)
    host_id = str(created.to_dict()["id"])

    assert client.hosts.retrieve(host_id).name == name

    renamed = f"{name}-renamed"
    client.hosts.update(host_id, **{**payload, "name": renamed})
    assert client.hosts.retrieve(host_id).name == renamed

    assert renamed in [host.to_dict()["name"] for host in client.hosts.list()]

    client.hosts.delete(host_id)
    with pytest.raises(NotFoundError):
        client.hosts.retrieve(host_id)


def test_snippets_crud(client: TermixClient, run_prefix: str) -> None:
    # No update leg: `PUT /snippets/{id}` has no documented request body in
    # the spec, so the generated `snippets.update()` takes no fields and
    # cannot change anything. Tracked separately; the update path is
    # covered by test_hosts_crud.
    name = f"{run_prefix}-snippet"
    created = client.snippets.create(name=name, content="echo live-smoke")
    snippet_id = str(created.id)

    assert client.snippets.retrieve(snippet_id).content == "echo live-smoke"
    assert name in [snippet["name"] for snippet in client.snippets.list()]

    client.snippets.delete(snippet_id)
    with pytest.raises(NotFoundError):
        client.snippets.retrieve(snippet_id)


def test_unknown_id_raises_not_found(client: TermixClient) -> None:
    with pytest.raises(NotFoundError) as excinfo:
        client.hosts.retrieve("999999999")
    assert excinfo.value.http_status == 404


def test_invalid_api_key_raises_authentication_error(base_url: str) -> None:
    with TermixClient(base_url=base_url, api_key="tmx_invalid") as bad:
        with pytest.raises(AuthenticationError) as excinfo:
            bad.hosts.list()
    assert excinfo.value.http_status == 401


def test_login_returns_a_usable_client(base_url: str, password: str) -> None:
    """The regression that started this suite: `login()` used to hand back
    a client with no resource attributes at all.
    """
    logged_in = TermixClient.login(base_url=base_url, username="ci", password=password)
    assert isinstance(logged_in, TermixClient)
    with logged_in:
        assert logged_in.users.get_me().username == "ci"
