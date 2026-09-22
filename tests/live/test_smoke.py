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

import json
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


def test_network_topology_save_and_get(client: TermixClient) -> None:
    saved = client.network_topology.save(topology=json.dumps({"nodes": [], "edges": []}))
    assert saved.to_dict()["success"] is True

    got = client.network_topology.get()
    assert got is not None
    assert got.to_dict() == {"nodes": [], "edges": []}


def test_preferences_get_and_set(client: TermixClient) -> None:
    client.preferences.set_credential_sidebar(display={}, sort={}, filters={})
    assert client.preferences.get_credential_sidebar().to_dict()["preferences"]

    client.preferences.set_host_sidebar(display={}, sort={}, filters={})
    assert client.preferences.get_host_sidebar().to_dict()["preferences"]

    client.preferences.set_ui_preferences(overrides={}, onboarding={})
    assert client.preferences.get_ui_preferences().to_dict()["preferences"]

    client.preferences.set_user_preferences(theme="dark")
    assert client.preferences.get_user_preferences().theme == "dark"

    client.preferences.update_touch_input_settings(enabled=True)
    assert client.preferences.get_touch_input_settings().enabled is True


def test_dashboard_service_links_and_activity(client: TermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-link"
    created = client.dashboard.create_service_link(label=name, url="https://example.invalid")
    link_id = str(created.to_dict()["id"])

    assert name in [link["label"] for link in client.dashboard.list_service_links()]

    renamed = f"{name}-renamed"
    client.dashboard.update_service_link(link_id, label=renamed)
    assert renamed in [link["label"] for link in client.dashboard.list_service_links()]

    client.dashboard.delete_service_link(link_id)
    with pytest.raises(NotFoundError):
        client.dashboard.update_service_link(link_id, label="gone")

    host_name = f"{run_prefix}-dashboard-host"
    host = client.hosts.create(
        ip="10.0.0.10", port=22, username="root", authType="password", name=host_name
    )
    host_id = str(host.to_dict()["id"])

    client.dashboard.log_activity(type="terminal", hostId=int(host_id), hostName=host_name)
    assert host_name in [a["hostName"] for a in client.dashboard.list_recent_activity()]

    client.dashboard.reset_activity()
    assert client.dashboard.list_recent_activity() == []

    assert client.dashboard.uptime().to_dict()["uptimeSeconds"] >= 0

    client.hosts.delete(host_id)


def test_homepage_items_and_layout(client: TermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-item"
    created = client.homepage.create_item(
        typeId="bookmark", title=name, config={"url": "https://example.invalid"}
    )
    item_id = str(created.to_dict()["id"])

    assert name in [item["title"] for item in client.homepage.list_items()]

    renamed = f"{name}-renamed"
    client.homepage.update_item(item_id, title=renamed)
    assert renamed in [item["title"] for item in client.homepage.list_items()]

    client.homepage.set_layout(
        entries=[{"id": item_id, "x": 0, "y": 0}], pan={"x": 0, "y": 0}, zoom=1.0
    )
    layout = client.homepage.get_layout()
    assert layout is not None
    assert layout.to_dict()["layout"]["entries"] == [{"id": item_id, "x": 0, "y": 0}]

    client.homepage.delete_item(item_id)
    with pytest.raises(NotFoundError):
        client.homepage.update_item(item_id, title="gone")


def test_audit_list(client: TermixClient) -> None:
    """Excludes `export()`: the real endpoint answers with a CSV body the
    SDK currently can't parse (a spec/generator gap, not exercised here —
    see the flagged follow-up task).
    """
    actions = client.audit.list_actions().to_dict()["actions"]
    assert "login" in actions

    logs = client.audit.list().to_dict()
    assert any(entry["action"] == "login" for entry in logs["logs"])


def test_vault_profiles_crud(client: TermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-vault-profile"
    created = client.vault.create_profile(
        name=name, vaultAddr="https://vault.invalid:8200", sshRole=f"{run_prefix}-role"
    )
    profile_id = str(created.to_dict()["id"])

    assert name in [p["name"] for p in client.vault.list_profiles()]

    renamed = f"{name}-renamed"
    client.vault.update_profile(profile_id, name=renamed)
    assert renamed in [p["name"] for p in client.vault.list_profiles()]

    client.vault.delete_profile(profile_id)
    with pytest.raises(NotFoundError):
        client.vault.update_profile(profile_id, name="gone")


def test_rbac_roles_crud(client: TermixClient, run_prefix: str) -> None:
    catalog = client.rbac.permissions_catalog().to_dict()["catalog"]
    assert catalog

    name = f"{run_prefix}-role"
    created = client.rbac.create_role(name=name, displayName="Explore Role")
    role_id = str(created.to_dict()["roleId"])

    assert name in [r["name"] for r in client.rbac.list_roles().to_dict()["roles"]]

    client.rbac.update_role(role_id, displayName="Explore Role Renamed")
    assert client.rbac.list_role_members(role_id).to_dict()["members"] == []

    client.rbac.delete_role(role_id)
    with pytest.raises(NotFoundError):
        client.rbac.update_role(role_id, displayName="gone")


def test_automations_crud(client: TermixClient, run_prefix: str) -> None:
    """Excludes `run()`/`trigger_webhook()`: both actually execute the
    automation's steps, out of scope for this suite (see the module
    docstring).
    """
    name = f"{run_prefix}-automation"
    definition = {"version": 1, "trigger": {"kind": "webhook"}, "steps": []}
    created = client.automations.create(name=name, enabled=False, definition=definition)
    automation_id = str(created.to_dict()["id"])

    assert name in [a["name"] for a in client.automations.list()]
    assert client.automations.retrieve(automation_id).name == name

    renamed = f"{name}-renamed"
    client.automations.update(automation_id, name=renamed)
    assert client.automations.retrieve(automation_id).name == renamed

    assert client.automations.list_run_history(automationId=automation_id) == []

    client.automations.delete(automation_id)
    with pytest.raises(NotFoundError):
        client.automations.retrieve(automation_id)


def test_session_logs_retention(client: TermixClient) -> None:
    """Excludes `list()`/`retrieve()`/`delete()`/`get_content()`: they need
    a real session log row, which only a real SSH-backed session creates —
    out of scope for this suite (see the module docstring).
    """
    client.session_logs.set_retention(retentionDays=30)
    assert client.session_logs.get_retention().retentionDays == 30


def test_termix_id_identity_and_ca(client: TermixClient, run_prefix: str) -> None:
    """Excludes `get_public_ca()`: the real endpoint answers with a plain-text
    body the SDK currently can't parse (a spec/generator gap, not exercised
    here — see the flagged follow-up task).

    Excludes `delete_key()`: confirmed live that the real Termix 2.8.0
    backend always answers it with a 500 ("Failed to delete key") even
    though the key row is in fact removed — an upstream server bug, not
    something the SDK can paper over. `delete()`'s cascade (exercised at
    the end of this test) is what actually removes both keys created here.
    """
    handle = f"{run_prefix}-id"
    assert client.termix_id.check_handle(handle=handle).available is True

    client.termix_id.create(handle=handle, description="live smoke identity")
    assert client.termix_id.get_me().to_dict()["identity"]["handle"] == handle

    generated = client.termix_id.generate_key(
        type="ed25519", label="generated", saveCredential=False
    )
    generated_key_id = str(generated.to_dict()["key"]["id"])
    client.termix_id.create_key(
        label="imported",
        publicKey="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklm",
    )

    identity_public_key = generated.to_dict()["key"]["publicKey"]
    key_stream = client.termix_id.get_public_key(handle=handle, algo="ed25519")
    assert identity_public_key.encode() in key_stream.read()
    identity_stream = client.termix_id.get_public_identity(handle=handle)
    assert handle.encode() in identity_stream.read()

    client.termix_id.update_key(generated_key_id, label="generated-renamed")

    client.termix_id.create_ca(validityDays=365)
    assert client.termix_id.get_ca().to_dict()["ca"] is not None
    client.termix_id.rotate_ca(validityDays=365)
    assert client.termix_id.list_linked_credentials().to_dict()["credentialIds"] == []

    cert = client.termix_id.issue_certificate(generated_key_id, validityDays=1, principals=["root"])
    assert cert.to_dict()["principals"] == ["root"]

    client.termix_id.delete_ca()
    assert client.termix_id.get_ca().to_dict()["ca"] is None

    renamed_description = "renamed live smoke identity"
    client.termix_id.update(description=renamed_description)
    assert client.termix_id.get_me().to_dict()["identity"]["description"] == renamed_description

    client.termix_id.delete()
    with pytest.raises(NotFoundError):
        client.termix_id.update(description="gone")


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
