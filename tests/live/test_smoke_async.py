"""The same smoke cases as `test_smoke.py`, through `AsyncTermixClient`.

The async client has its own requestor and transport, so "the sync one
works" says nothing about it — the `login()` regression this suite was
born from was present in both. See `test_smoke.py`'s module docstring for
this suite's scope.
"""

from __future__ import annotations

import json
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
    # See the sync suite: `localVersion` is the instance under test,
    # `version`/`remoteVersion` are upstream's newest release.
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


async def test_workspaces_crud(async_client: AsyncTermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-workspace-async"
    created = await async_client.workspaces.create(name=name, color="#336699", payload={"tabs": []})
    workspace_id = str(created.to_dict()["id"])

    assert workspace_id in [str(w["id"]) for w in await async_client.workspaces.list()]

    renamed = f"{name}-renamed"
    await async_client.workspaces.update(workspace_id, name=renamed)
    await async_client.workspaces.set_content(workspace_id, payload={"tabs": [{"id": "1"}]})

    duplicate = await async_client.workspaces.duplicate(workspace_id, name=f"{renamed}-dup")
    duplicate_id = str(duplicate.to_dict()["id"])
    assert duplicate.to_dict()["payload"] == {"tabs": [{"id": "1"}]}

    await async_client.workspaces.set_default(workspace_id)
    workspaces = await async_client.workspaces.list()
    assert any(str(w["id"]) == workspace_id and w["isDefault"] for w in workspaces)
    await async_client.workspaces.unset_default(workspace_id)

    applied = await async_client.workspaces.apply(workspace_id)
    assert str(applied.to_dict()["id"]) == workspace_id

    await async_client.workspaces.save_last_session(payload={"tabs": []})
    assert (await async_client.workspaces.get_last_session()) is not None

    await async_client.workspaces.delete(workspace_id)
    await async_client.workspaces.delete(duplicate_id)
    with pytest.raises(NotFoundError):
        await async_client.workspaces.update(workspace_id, name="gone")


async def test_tunnel_presets_crud(async_client: AsyncTermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-tunnel-preset-async"
    created = await async_client.tunnel_presets.create(name=name, config=[])
    preset_id = str(created.to_dict()["id"])

    assert name in [p["name"] for p in await async_client.tunnel_presets.list()]

    renamed = f"{name}-renamed"
    await async_client.tunnel_presets.update(preset_id, name=renamed)
    assert renamed in [p["name"] for p in await async_client.tunnel_presets.list()]

    await async_client.tunnel_presets.delete(preset_id)
    with pytest.raises(NotFoundError):
        await async_client.tunnel_presets.update(preset_id, name="gone")


async def test_open_tabs_crud(async_client: AsyncTermixClient, run_prefix: str) -> None:
    tab_id = f"{run_prefix}-tab-async"
    label = f"{run_prefix} tab async"
    await async_client.open_tabs.upsert(id=tab_id, tabType="home", label=label, tabOrder=0)

    tabs = {t.to_dict()["id"]: t.to_dict() for t in await async_client.open_tabs.list()}
    assert tabs[tab_id]["label"] == label

    await async_client.open_tabs.update(tab_id, label=f"{label}-renamed")
    tabs = {t.to_dict()["id"]: t.to_dict() for t in await async_client.open_tabs.list()}
    assert tabs[tab_id]["label"] == f"{label}-renamed"

    assert (await async_client.open_tabs.list_active_sessions()) == []

    await async_client.open_tabs.replace_all(
        tabs=[{"id": tab_id, "tabType": "home", "label": label, "tabOrder": 0}]
    )
    tabs = {t.to_dict()["id"]: t.to_dict() for t in await async_client.open_tabs.list()}
    assert tabs[tab_id]["label"] == label

    await async_client.open_tabs.delete(tab_id)
    remaining = await async_client.open_tabs.list()
    assert tab_id not in {t.to_dict()["id"] for t in remaining}


async def test_alerts_notification_channels_crud(
    async_client: AsyncTermixClient, run_prefix: str
) -> None:
    name = f"{run_prefix}-channel-async"
    created = await async_client.alerts.create_channel(
        name=name, type="webhook", config={"url": "https://example.invalid/webhook"}, enabled=False
    )
    channel_id = str(created.to_dict()["id"])

    channels = await async_client.alerts.list_channels()
    assert name in [c.to_dict()["name"] for c in channels]

    renamed = f"{name}-renamed"
    await async_client.alerts.update_channel(channel_id, name=renamed)
    channels = await async_client.alerts.list_channels()
    assert renamed in [c.to_dict()["name"] for c in channels]

    await async_client.alerts.delete_channel(channel_id)
    with pytest.raises(NotFoundError):
        await async_client.alerts.update_channel(channel_id, name="gone")


async def test_credentials_crud(async_client: AsyncTermixClient, run_prefix: str) -> None:
    """Excludes `apply_to_host`/`deploy_to_host`: both connect to a real host
    over SSH, out of scope for this suite (see test_smoke.py's docstring).
    """
    name = f"{run_prefix}-credential-async"
    created = await async_client.credentials.create(
        name=name, authType="password", username="root", password="hunter2"
    )
    credential_id = str(created.to_dict()["id"])

    assert (await async_client.credentials.retrieve(credential_id)).name == name
    assert name in [c["name"] for c in await async_client.credentials.list()]
    assert (await async_client.credentials.hosts(credential_id)) == []
    await async_client.credentials.rename_folder(
        oldName=f"{run_prefix}-old", newName=f"{run_prefix}-new"
    )

    key_pair = await async_client.credentials.generate_key_pair(keyType="ssh-rsa", keySize=2048)
    private_key, public_key = key_pair.privateKey, key_pair.publicKey

    generated_public = await async_client.credentials.generate_public_key(privateKey=private_key)
    assert generated_public.publicKey == public_key
    detected = await async_client.credentials.detect_key_type(privateKey=private_key)
    assert detected.keyType == "ssh-rsa"
    detected_public = await async_client.credentials.detect_public_key_type(publicKey=public_key)
    assert detected_public.keyType == "ssh-rsa"
    validated = await async_client.credentials.validate_key_pair(
        privateKey=private_key, publicKey=public_key
    )
    assert validated.isValid

    renamed = f"{name}-renamed"
    await async_client.credentials.update(credential_id, name=renamed)
    assert (await async_client.credentials.retrieve(credential_id)).name == renamed

    duplicate = await async_client.credentials.duplicate(credential_id, name=f"{renamed}-dup")
    duplicate_id = str(duplicate.to_dict()["id"])
    await async_client.credentials.reorder(
        positions=[
            {"id": int(credential_id), "sortOrder": 0},
            {"id": int(duplicate_id), "sortOrder": 1},
        ]
    )

    await async_client.credentials.delete(credential_id)
    await async_client.credentials.delete(duplicate_id)
    with pytest.raises(NotFoundError):
        await async_client.credentials.retrieve(credential_id)


async def test_network_topology_save_and_get(async_client: AsyncTermixClient) -> None:
    saved = await async_client.network_topology.save(
        topology=json.dumps({"nodes": [], "edges": []})
    )
    assert saved.to_dict()["success"] is True

    got = await async_client.network_topology.get()
    assert got is not None
    assert got.to_dict() == {"nodes": [], "edges": []}


async def test_preferences_get_and_set(async_client: AsyncTermixClient) -> None:
    await async_client.preferences.set_credential_sidebar(display={}, sort={}, filters={})
    assert (await async_client.preferences.get_credential_sidebar()).to_dict()["preferences"]

    await async_client.preferences.set_host_sidebar(display={}, sort={}, filters={})
    assert (await async_client.preferences.get_host_sidebar()).to_dict()["preferences"]

    await async_client.preferences.set_ui_preferences(overrides={}, onboarding={})
    assert (await async_client.preferences.get_ui_preferences()).to_dict()["preferences"]

    await async_client.preferences.set_user_preferences(theme="dark")
    assert (await async_client.preferences.get_user_preferences()).theme == "dark"

    await async_client.preferences.update_touch_input_settings(enabled=True)
    assert (await async_client.preferences.get_touch_input_settings()).enabled is True


async def test_dashboard_service_links_and_activity(
    async_client: AsyncTermixClient, run_prefix: str
) -> None:
    name = f"{run_prefix}-link-async"
    created = await async_client.dashboard.create_service_link(
        label=name, url="https://example.invalid"
    )
    link_id = str(created.to_dict()["id"])

    links = await async_client.dashboard.list_service_links()
    assert name in [link["label"] for link in links]

    renamed = f"{name}-renamed"
    await async_client.dashboard.update_service_link(link_id, label=renamed)
    links = await async_client.dashboard.list_service_links()
    assert renamed in [link["label"] for link in links]

    await async_client.dashboard.delete_service_link(link_id)
    with pytest.raises(NotFoundError):
        await async_client.dashboard.update_service_link(link_id, label="gone")

    host_name = f"{run_prefix}-dashboard-host-async"
    host = await async_client.hosts.create(
        ip="10.0.0.11", port=22, username="root", authType="password", name=host_name
    )
    host_id = str(host.to_dict()["id"])

    await async_client.dashboard.log_activity(
        type="terminal", hostId=int(host_id), hostName=host_name
    )
    activity = await async_client.dashboard.list_recent_activity()
    assert host_name in [a["hostName"] for a in activity]

    await async_client.dashboard.reset_activity()
    assert (await async_client.dashboard.list_recent_activity()) == []

    assert (await async_client.dashboard.uptime()).to_dict()["uptimeSeconds"] >= 0

    await async_client.hosts.delete(host_id)


async def test_homepage_items_and_layout(async_client: AsyncTermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-item-async"
    created = await async_client.homepage.create_item(
        typeId="bookmark", title=name, config={"url": "https://example.invalid"}
    )
    item_id = str(created.to_dict()["id"])

    items = await async_client.homepage.list_items()
    assert name in [item["title"] for item in items]

    renamed = f"{name}-renamed"
    await async_client.homepage.update_item(item_id, title=renamed)
    items = await async_client.homepage.list_items()
    assert renamed in [item["title"] for item in items]

    await async_client.homepage.set_layout(
        entries=[{"id": item_id, "x": 0, "y": 0}], pan={"x": 0, "y": 0}, zoom=1.0
    )
    layout = await async_client.homepage.get_layout()
    assert layout is not None
    assert layout.to_dict()["layout"]["entries"] == [{"id": item_id, "x": 0, "y": 0}]

    await async_client.homepage.delete_item(item_id)
    with pytest.raises(NotFoundError):
        await async_client.homepage.update_item(item_id, title="gone")


async def test_audit_list(async_client: AsyncTermixClient) -> None:
    """Excludes `export()`: see `test_smoke.py`'s sync version of this test."""
    actions = (await async_client.audit.list_actions()).to_dict()["actions"]
    assert "login" in actions

    logs = (await async_client.audit.list()).to_dict()
    assert any(entry["action"] == "login" for entry in logs["logs"])


async def test_vault_profiles_crud(async_client: AsyncTermixClient, run_prefix: str) -> None:
    name = f"{run_prefix}-vault-profile-async"
    created = await async_client.vault.create_profile(
        name=name, vaultAddr="https://vault.invalid:8200", sshRole=f"{run_prefix}-role-async"
    )
    profile_id = str(created.to_dict()["id"])

    profiles = await async_client.vault.list_profiles()
    assert name in [p["name"] for p in profiles]

    renamed = f"{name}-renamed"
    await async_client.vault.update_profile(profile_id, name=renamed)
    profiles = await async_client.vault.list_profiles()
    assert renamed in [p["name"] for p in profiles]

    await async_client.vault.delete_profile(profile_id)
    with pytest.raises(NotFoundError):
        await async_client.vault.update_profile(profile_id, name="gone")


async def test_rbac_roles_crud(async_client: AsyncTermixClient, run_prefix: str) -> None:
    catalog = (await async_client.rbac.permissions_catalog()).to_dict()["catalog"]
    assert catalog

    name = f"{run_prefix}-role-async"
    created = await async_client.rbac.create_role(name=name, displayName="Explore Role")
    role_id = str(created.to_dict()["roleId"])

    roles = (await async_client.rbac.list_roles()).to_dict()["roles"]
    assert name in [r["name"] for r in roles]

    await async_client.rbac.update_role(role_id, displayName="Explore Role Renamed")
    members = await async_client.rbac.list_role_members(role_id)
    assert members.to_dict()["members"] == []

    await async_client.rbac.delete_role(role_id)
    with pytest.raises(NotFoundError):
        await async_client.rbac.update_role(role_id, displayName="gone")


async def test_automations_crud(async_client: AsyncTermixClient, run_prefix: str) -> None:
    """Excludes `run()`/`trigger_webhook()`: see the sync version of this test."""
    name = f"{run_prefix}-automation-async"
    definition = {"version": 1, "trigger": {"kind": "webhook"}, "steps": []}
    created = await async_client.automations.create(name=name, enabled=False, definition=definition)
    automation_id = str(created.to_dict()["id"])

    automations = await async_client.automations.list()
    assert name in [a["name"] for a in automations]
    assert (await async_client.automations.retrieve(automation_id)).name == name

    renamed = f"{name}-renamed"
    await async_client.automations.update(automation_id, name=renamed)
    assert (await async_client.automations.retrieve(automation_id)).name == renamed

    history = await async_client.automations.list_run_history(automationId=automation_id)
    assert history == []

    await async_client.automations.delete(automation_id)
    with pytest.raises(NotFoundError):
        await async_client.automations.retrieve(automation_id)


async def test_session_logs_retention(async_client: AsyncTermixClient) -> None:
    """Excludes `list()`/`retrieve()`/`delete()`/`get_content()`: see the
    sync version of this test.
    """
    await async_client.session_logs.set_retention(retentionDays=30)
    assert (await async_client.session_logs.get_retention()).retentionDays == 30


async def test_termix_id_identity_and_ca(async_client: AsyncTermixClient, run_prefix: str) -> None:
    """Excludes `get_public_ca()` and `delete_key()`: see the sync version
    of this test for why.
    """
    handle = f"{run_prefix}-id-async"
    assert (await async_client.termix_id.check_handle(handle=handle)).available is True

    await async_client.termix_id.create(handle=handle, description="live smoke identity")
    me = await async_client.termix_id.get_me()
    assert me.to_dict()["identity"]["handle"] == handle

    generated = await async_client.termix_id.generate_key(
        type="ed25519", label="generated", saveCredential=False
    )
    generated_key_id = str(generated.to_dict()["key"]["id"])
    await async_client.termix_id.create_key(
        label="imported",
        publicKey="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklm",
    )

    identity_public_key = generated.to_dict()["key"]["publicKey"]
    key_stream = await async_client.termix_id.get_public_key(handle=handle, algo="ed25519")
    assert identity_public_key.encode() in (await key_stream.read())
    identity_stream = await async_client.termix_id.get_public_identity(handle=handle)
    assert handle.encode() in (await identity_stream.read())

    await async_client.termix_id.update_key(generated_key_id, label="generated-renamed")

    await async_client.termix_id.create_ca(validityDays=365)
    ca = await async_client.termix_id.get_ca()
    assert ca.to_dict()["ca"] is not None
    await async_client.termix_id.rotate_ca(validityDays=365)
    linked = await async_client.termix_id.list_linked_credentials()
    assert linked.to_dict()["credentialIds"] == []

    cert = await async_client.termix_id.issue_certificate(
        generated_key_id, validityDays=1, principals=["root"]
    )
    assert cert.to_dict()["principals"] == ["root"]

    await async_client.termix_id.delete_ca()
    ca = await async_client.termix_id.get_ca()
    assert ca.to_dict()["ca"] is None

    renamed_description = "renamed live smoke identity"
    await async_client.termix_id.update(description=renamed_description)
    me = await async_client.termix_id.get_me()
    assert me.to_dict()["identity"]["description"] == renamed_description

    await async_client.termix_id.delete()
    with pytest.raises(NotFoundError):
        await async_client.termix_id.update(description="gone")


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
