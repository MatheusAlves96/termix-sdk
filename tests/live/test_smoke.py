"""Smoke suite: the SDK against a real Termix instance (sync client).

Scope is deliberately narrow — auth, error mapping, and CRUD on the
resources that are pure JSON with no external dependency (nothing else to
stand up, nothing side-effecting outside the row itself). Nothing here
opens an SSH session, a Docker container or a tmux session, drives a
third-party integration (Tailscale, Proxmox, an AI provider, 1Password),
or touches admin-only/instance-wide state; see CONTRIBUTING.md, "Live
smoke", for why.
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
    # `localVersion` is the running instance; `version`/`remoteVersion` are
    # the newest release GitHub knows about, which this endpoint reports so
    # the UI can offer an update. Reading `version` first compared
    # SPEC_VERSION against upstream's latest release instead of against the
    # instance under test, so the warning never fired for an outdated
    # instance and fired for an up-to-date one.
    local = version.get("localVersion") or version.get("version")
    assert local, f"no version field in {version!r}"

    # Not an assertion: `docker/live/compose.yml`'s local default tracks
    # `SPEC_VERSION`, but `live.yml`'s weekly run tracks `:latest` on
    # purpose — a newer Termix is expected to show up here first, and
    # surfacing that drift is the point of that schedule.
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
    name = f"{run_prefix}-snippet"
    created = client.snippets.create(name=name, content="echo live-smoke")
    snippet_id = str(created.id)

    assert client.snippets.retrieve(snippet_id).content == "echo live-smoke"
    assert name in [snippet["name"] for snippet in client.snippets.list()]

    # Partial update: only `content` is sent, so `name` has to survive it.
    client.snippets.update(snippet_id, content="echo live-smoke-updated")
    updated = client.snippets.retrieve(snippet_id)
    assert updated.content == "echo live-smoke-updated"
    assert updated.name == name

    client.snippets.delete(snippet_id)
    with pytest.raises(NotFoundError):
        client.snippets.retrieve(snippet_id)


def test_workspaces_crud(client: TermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-workspace"
    created = client.workspaces.create(name=name, color="#336699", payload={"tabs": []})
    workspace_id = str(created.to_dict()["id"])

    assert workspace_id in [str(w["id"]) for w in client.workspaces.list()]

    renamed = f"{name}-renamed"
    client.workspaces.update(workspace_id, name=renamed)
    client.workspaces.set_content(workspace_id, payload={"tabs": [{"id": "1"}]})

    duplicate = client.workspaces.duplicate(workspace_id, name=f"{renamed}-dup")
    duplicate_id = str(duplicate.to_dict()["id"])
    assert duplicate.to_dict()["payload"] == {"tabs": [{"id": "1"}]}

    client.workspaces.set_default(workspace_id)
    assert any(str(w["id"]) == workspace_id and w["isDefault"] for w in client.workspaces.list())
    client.workspaces.unset_default(workspace_id)

    applied = client.workspaces.apply(workspace_id)
    assert str(applied.to_dict()["id"]) == workspace_id

    client.workspaces.save_last_session(payload={"tabs": []})
    assert client.workspaces.get_last_session() is not None

    client.workspaces.delete(workspace_id)
    client.workspaces.delete(duplicate_id)
    with pytest.raises(NotFoundError):
        client.workspaces.update(workspace_id, name="gone")


def test_tunnel_presets_crud(client: TermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-tunnel-preset"
    created = client.tunnel_presets.create(name=name, config=[])
    preset_id = str(created.to_dict()["id"])

    assert name in [p["name"] for p in client.tunnel_presets.list()]

    renamed = f"{name}-renamed"
    client.tunnel_presets.update(preset_id, name=renamed)
    assert renamed in [p["name"] for p in client.tunnel_presets.list()]

    client.tunnel_presets.delete(preset_id)
    with pytest.raises(NotFoundError):
        client.tunnel_presets.update(preset_id, name="gone")


def test_open_tabs_crud(client: TermixClient, run_prefix: str) -> None:
    tab_id = f"{run_prefix}-tab"
    label = f"{run_prefix} tab"
    client.open_tabs.upsert(id=tab_id, tabType="home", label=label, tabOrder=0)

    tabs = {t.to_dict()["id"]: t.to_dict() for t in client.open_tabs.list()}
    assert tabs[tab_id]["label"] == label

    client.open_tabs.update(tab_id, label=f"{label}-renamed")
    tabs = {t.to_dict()["id"]: t.to_dict() for t in client.open_tabs.list()}
    assert tabs[tab_id]["label"] == f"{label}-renamed"

    assert client.open_tabs.list_active_sessions() == []

    client.open_tabs.replace_all(
        tabs=[{"id": tab_id, "tabType": "home", "label": label, "tabOrder": 0}]
    )
    tabs = {t.to_dict()["id"]: t.to_dict() for t in client.open_tabs.list()}
    assert tabs[tab_id]["label"] == label

    client.open_tabs.delete(tab_id)
    assert tab_id not in {t.to_dict()["id"] for t in client.open_tabs.list()}


def test_alerts_notification_channels_crud(client: TermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-channel"
    created = client.alerts.create_channel(
        name=name, type="webhook", config={"url": "https://example.invalid/webhook"}, enabled=False
    )
    channel_id = str(created.to_dict()["id"])

    assert name in [c.to_dict()["name"] for c in client.alerts.list_channels()]

    renamed = f"{name}-renamed"
    client.alerts.update_channel(channel_id, name=renamed)
    assert renamed in [c.to_dict()["name"] for c in client.alerts.list_channels()]

    client.alerts.delete_channel(channel_id)
    with pytest.raises(NotFoundError):
        client.alerts.update_channel(channel_id, name="gone")


def test_credentials_crud(client: TermixClient, run_prefix: str) -> None:
    """Excludes `apply_to_host`/`deploy_to_host`: both connect to a real host
    over SSH, out of scope for this suite (see the module docstring).
    """
    name = f"{run_prefix}-credential"
    created = client.credentials.create(
        name=name, authType="password", username="root", password="hunter2"
    )
    credential_id = str(created.to_dict()["id"])

    assert client.credentials.retrieve(credential_id).name == name
    assert name in [c["name"] for c in client.credentials.list()]
    assert client.credentials.hosts(credential_id) == []
    client.credentials.rename_folder(oldName=f"{run_prefix}-old", newName=f"{run_prefix}-new")

    key_pair = client.credentials.generate_key_pair(keyType="ssh-rsa", keySize=2048)
    private_key, public_key = key_pair.privateKey, key_pair.publicKey

    assert client.credentials.generate_public_key(privateKey=private_key).publicKey == public_key
    assert client.credentials.detect_key_type(privateKey=private_key).keyType == "ssh-rsa"
    assert client.credentials.detect_public_key_type(publicKey=public_key).keyType == "ssh-rsa"
    assert client.credentials.validate_key_pair(
        privateKey=private_key, publicKey=public_key
    ).isValid

    renamed = f"{name}-renamed"
    client.credentials.update(credential_id, name=renamed)
    assert client.credentials.retrieve(credential_id).name == renamed

    duplicate = client.credentials.duplicate(credential_id, name=f"{renamed}-dup")
    duplicate_id = str(duplicate.to_dict()["id"])
    client.credentials.reorder(
        positions=[
            {"id": int(credential_id), "sortOrder": 0},
            {"id": int(duplicate_id), "sortOrder": 1},
        ]
    )

    client.credentials.delete(credential_id)
    client.credentials.delete(duplicate_id)
    with pytest.raises(NotFoundError):
        client.credentials.retrieve(credential_id)


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
