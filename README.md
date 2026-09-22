# termix-sdk

Unofficial Python client SDK for the [Termix](https://github.com/Termix-SSH/Termix) REST API.

Generated from a spec this repo derives directly from the Termix backend
source, not from Termix's own hand-written `openapi.json` — see
[Generating our own Termix API spec](tools/spec-gen/docs/spec-generation-strategy.md)
for why. As of `release-2.8.0-tag`, that covers **516 of 531** real
endpoints; the rest are either genuinely out of scope (browser-redirect
OIDC flows, internal-only routes) or need a documented request/response
shape the spec doesn't have (3 `file_manager` streaming-upload endpoints).

## Install

```bash
pip install termix-sdk
```

Requires Python 3.10+. The only runtime dependencies are `httpx` and
`typing-extensions`.

## Quickstart

An API key (`tmx_...`, created in Termix under Settings → API Keys) is the
recommended way to authenticate — it skips the login/TOTP dance entirely:

```python
from termix_sdk import TermixClient

client = TermixClient(base_url="https://termix.example.com", api_key="tmx_...")

for host in client.hosts.list():
    print(host.name, host.ip)

client.close()
```

`TermixClient` is also a context manager:

```python
with TermixClient(base_url="https://termix.example.com", api_key="tmx_...") as client:
    host = client.hosts.retrieve("42")
```

### Username/password login

`TermixClient.login()` handles Termix's login quirk for you: the backend
only puts the JWT in the response body (rather than only in a cookie a
Python client can't use) when the request looks like it came from a
native app, so this always sends that header.

```python
from termix_sdk import TermixClient, PendingTOTP

result = TermixClient.login(
    base_url="https://termix.example.com",
    username="alice",
    password="...",
)

if isinstance(result, PendingTOTP):
    # The account has TOTP enabled and this device isn't trusted yet.
    client = result.verify(input("6-digit code: "))
else:
    client = result
```

### Async

Every resource has an async twin, via a separate client rather than
`_async` suffixed methods:

```python
import asyncio
from termix_sdk import AsyncTermixClient


async def main():
    async with AsyncTermixClient(
        base_url="https://termix.example.com", api_key="tmx_..."
    ) as client:
        hosts = await client.hosts.list()
        print([h.name for h in hosts])


asyncio.run(main())
```

### SSH-backed sessions (file manager, Docker)

`file_manager` and `docker` open an SSH-backed session server-side
before you can call anything else on them. `ssh_session()` (and its
async twin `async_ssh_session()`) manage that lifecycle — connect,
optional keepalive, disconnect on exit, even on error:

```python
from termix_sdk import ssh_session

with ssh_session(client.file_manager, host_id=42) as fm:
    for entry in fm.list_files(path="/"):
        print(entry)
# disconnected automatically here
```

Every method is still callable directly with an explicit `session_id` if
you'd rather manage the lifecycle yourself — `ssh_session()` is a
convenience layer on top, not a requirement.

### Errors

Every non-2xx response raises a typed subclass of `TermixError`:

```python
from termix_sdk import AuthenticationError, NotFoundError, RateLimitError, TermixError

try:
    client.hosts.retrieve("does-not-exist")
except NotFoundError as e:
    print(e.code, e.details)
except RateLimitError as e:
    print("retry after", e.remaining_time, "seconds")
except TermixError as e:
    print(e.http_status, e)
```

## Routes covered

<!-- routes-table start -->

**516** of **531** endpoints documented in [`spec/termix-openapi.json`](spec/termix-openapi.json) have a generated SDK call below, grouped by resource module (`client.<module>`). Every one also exists on `AsyncTermixClient` as an async twin — see [Async](#async). **53** are additionally exercised against a real Termix instance by the [live smoke suite](CONTRIBUTING.md#live-smoke) (marked ✅ below) — every other row is verified only against a synthetic contract test in `tests/contract/`, not a live instance. Rebuilt automatically by `python tools/sdk-gen/generate.py` (see [Development](#development)); don't edit this section by hand.

<details>
<summary><code>client.ai</code> (14 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/ai/chat/stream` | `client.ai.chat_stream(**params)` |  |
| GET | `/ai/conversations` | `client.ai.list_conversations()` |  |
| DELETE | `/ai/conversations/{id}` | `client.ai.delete_conversation(id)` |  |
| GET | `/ai/conversations/{id}` | `client.ai.get_conversation(id)` |  |
| POST | `/ai/probe-models` | `client.ai.probe_models(**params)` |  |
| POST | `/ai/proposals/{id}/apply` | `client.ai.apply_proposal(id)` |  |
| POST | `/ai/proposals/{id}/mark-run-in-terminal` | `client.ai.mark_proposal_run_in_terminal(id, **params)` |  |
| POST | `/ai/proposals/{id}/reject` | `client.ai.reject_proposal(id)` |  |
| GET | `/ai/providers` | `client.ai.list_providers()` |  |
| POST | `/ai/providers` | `client.ai.create_provider(**params)` |  |
| DELETE | `/ai/providers/{id}` | `client.ai.delete_provider(id)` |  |
| PATCH | `/ai/providers/{id}` | `client.ai.update_provider(id, **params)` |  |
| GET | `/ai/providers/{id}/models` | `client.ai.list_provider_models(id)` |  |
| GET | `/ai/status` | `client.ai.get_status()` |  |

</details>

<details>
<summary><code>client.alerts</code> (16 operations, 4 live-tested)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/alert-firings` | `client.alerts.list_firings(**params)` |  |
| POST | `/alert-firings/acknowledge-all` | `client.alerts.acknowledge_all_firings()` |  |
| POST | `/alert-firings/{id}/acknowledge` | `client.alerts.acknowledge_firing(id)` |  |
| GET | `/alert-rules` | `client.alerts.list_rules()` |  |
| POST | `/alert-rules` | `client.alerts.create_rule(**params)` |  |
| DELETE | `/alert-rules/{id}` | `client.alerts.delete_rule(id)` |  |
| PUT | `/alert-rules/{id}` | `client.alerts.update_rule(id, **params)` |  |
| GET | `/alerts` | `client.alerts.list()` |  |
| DELETE | `/alerts/dismiss` | `client.alerts.clear_dismissed()` |  |
| POST | `/alerts/dismiss` | `client.alerts.dismiss(**params)` |  |
| GET | `/alerts/dismissed` | `client.alerts.list_dismissed()` |  |
| GET | `/notification-channels` | `client.alerts.list_channels()` | ✅ |
| POST | `/notification-channels` | `client.alerts.create_channel(**params)` | ✅ |
| DELETE | `/notification-channels/{id}` | `client.alerts.delete_channel(id)` | ✅ |
| PUT | `/notification-channels/{id}` | `client.alerts.update_channel(id, **params)` | ✅ |
| POST | `/notification-channels/{id}/test` | `client.alerts.test_channel(id)` |  |

</details>

<details>
<summary><code>client.api_keys</code> (3 operations, 1 live-tested)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/users/api-keys` | `client.api_keys.list()` | ✅ |
| POST | `/users/api-keys` | `client.api_keys.create(**params)` |  |
| DELETE | `/users/api-keys/{keyId}` | `client.api_keys.delete(key_id)` |  |

</details>

<details>
<summary><code>client.audit</code> (3 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/audit-logs` | `client.audit.list(**params)` |  |
| GET | `/audit-logs/actions` | `client.audit.list_actions()` |  |
| GET | `/audit-logs/export` | `client.audit.export(**params)` |  |

</details>

<details>
<summary><code>client.automations</code> (9 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/automations` | `client.automations.list()` |  |
| POST | `/automations` | `client.automations.create(**params)` |  |
| GET | `/automations/runs/history` | `client.automations.list_run_history(**params)` |  |
| GET | `/automations/runs/{runId}/steps` | `client.automations.list_run_steps(run_id)` |  |
| POST | `/automations/webhook/{token}` | `client.automations.trigger_webhook(token)` |  |
| DELETE | `/automations/{id}` | `client.automations.delete(id)` |  |
| GET | `/automations/{id}` | `client.automations.retrieve(id)` |  |
| PUT | `/automations/{id}` | `client.automations.update(id, **params)` |  |
| POST | `/automations/{id}/run` | `client.automations.run(id, **params)` |  |

</details>

<details>
<summary><code>client.collab</code> (16 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/collab/guest/{token}` | `client.collab.get_guest_stage(token)` |  |
| GET | `/collab/rooms` | `client.collab.list_rooms()` |  |
| POST | `/collab/rooms` | `client.collab.create_room(**params)` |  |
| DELETE | `/collab/rooms/{id}` | `client.collab.delete_room(id)` |  |
| GET | `/collab/rooms/{id}` | `client.collab.get_room(id)` |  |
| POST | `/collab/rooms/{id}/control` | `client.collab.set_control(id, **params)` |  |
| POST | `/collab/rooms/{id}/control/request` | `client.collab.request_control(id)` |  |
| GET | `/collab/rooms/{id}/control/requests` | `client.collab.list_control_requests(id)` |  |
| DELETE | `/collab/rooms/{id}/control/requests/{userId}` | `client.collab.delete_control_request(id, user_id)` |  |
| POST | `/collab/rooms/{id}/end` | `client.collab.end_room(id)` |  |
| POST | `/collab/rooms/{id}/guest-link` | `client.collab.set_guest_link(id, **params)` |  |
| POST | `/collab/rooms/{id}/members` | `client.collab.invite_members(id, **params)` |  |
| DELETE | `/collab/rooms/{id}/members/{userId}` | `client.collab.remove_member(id, user_id)` |  |
| POST | `/collab/rooms/{id}/present` | `client.collab.present(id, **params)` |  |
| GET | `/collab/rooms/{id}/stage` | `client.collab.get_stage(id)` |  |
| POST | `/collab/rooms/{id}/stop` | `client.collab.stop_presenting(id)` |  |

</details>

<details>
<summary><code>client.credentials</code> (17 operations, 14 live-tested)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/credentials` | `client.credentials.list()` | ✅ |
| POST | `/credentials` | `client.credentials.create(**params)` | ✅ |
| POST | `/credentials/detect-key-type` | `client.credentials.detect_key_type(**params)` | ✅ |
| POST | `/credentials/detect-public-key-type` | `client.credentials.detect_public_key_type(**params)` | ✅ |
| GET | `/credentials/folders` | `client.credentials.list_folders()` |  |
| PUT | `/credentials/folders/rename` | `client.credentials.rename_folder(**params)` | ✅ |
| POST | `/credentials/generate-key-pair` | `client.credentials.generate_key_pair(**params)` | ✅ |
| POST | `/credentials/generate-public-key` | `client.credentials.generate_public_key(**params)` | ✅ |
| PUT | `/credentials/reorder` | `client.credentials.reorder(**params)` | ✅ |
| POST | `/credentials/validate-key-pair` | `client.credentials.validate_key_pair(**params)` | ✅ |
| DELETE | `/credentials/{id}` | `client.credentials.delete(id)` | ✅ |
| GET | `/credentials/{id}` | `client.credentials.retrieve(id)` | ✅ |
| PUT | `/credentials/{id}` | `client.credentials.update(id, **params)` | ✅ |
| POST | `/credentials/{id}/apply-to-host/{hostId}` | `client.credentials.apply_to_host(id, host_id)` |  |
| POST | `/credentials/{id}/deploy-to-host` | `client.credentials.deploy_to_host(id, **params)` |  |
| POST | `/credentials/{id}/duplicate` | `client.credentials.duplicate(id, **params)` | ✅ |
| GET | `/credentials/{id}/hosts` | `client.credentials.hosts(id)` | ✅ |

</details>

<details>
<summary><code>client.dashboard</code> (8 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/activity/log` | `client.dashboard.log_activity(**params)` |  |
| GET | `/activity/recent` | `client.dashboard.list_recent_activity(**params)` |  |
| DELETE | `/activity/reset` | `client.dashboard.reset_activity()` |  |
| GET | `/service-links` | `client.dashboard.list_service_links()` |  |
| POST | `/service-links` | `client.dashboard.create_service_link(**params)` |  |
| DELETE | `/service-links/{id}` | `client.dashboard.delete_service_link(id)` |  |
| PUT | `/service-links/{id}` | `client.dashboard.update_service_link(id, **params)` |  |
| GET | `/uptime` | `client.dashboard.uptime()` |  |

</details>

<details>
<summary><code>client.database</code> (6 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/database/export` | `client.database.export()` |  |
| POST | `/database/export/preview` | `client.database.preview_export(**params)` |  |
| POST | `/database/import` | `client.database.import_data(file)` |  |
| GET | `/database/migration/history` | `client.database.migration_history()` |  |
| GET | `/database/migration/status` | `client.database.migration_status()` |  |
| POST | `/database/restore` | `client.database.restore(**params)` |  |

</details>

<details>
<summary><code>client.docker</code> (17 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/docker/containers/{sessionId}` | `client.docker.list_containers(session_id, **params)` |  |
| GET | `/docker/containers/{sessionId}/{containerId}` | `client.docker.get_container(session_id, container_id)` |  |
| GET | `/docker/containers/{sessionId}/{containerId}/logs` | `client.docker.get_container_logs(session_id, container_id, **params)` |  |
| POST | `/docker/containers/{sessionId}/{containerId}/pause` | `client.docker.pause(session_id, container_id)` |  |
| DELETE | `/docker/containers/{sessionId}/{containerId}/remove` | `client.docker.remove_container(session_id, container_id, **params)` |  |
| POST | `/docker/containers/{sessionId}/{containerId}/restart` | `client.docker.restart(session_id, container_id)` |  |
| POST | `/docker/containers/{sessionId}/{containerId}/start` | `client.docker.start(session_id, container_id)` |  |
| GET | `/docker/containers/{sessionId}/{containerId}/stats` | `client.docker.get_container_stats(session_id, container_id)` |  |
| POST | `/docker/containers/{sessionId}/{containerId}/stop` | `client.docker.stop(session_id, container_id)` |  |
| POST | `/docker/containers/{sessionId}/{containerId}/unpause` | `client.docker.unpause(session_id, container_id)` |  |
| POST | `/docker/ssh/connect` | `client.docker.connect(**params)` |  |
| POST | `/docker/ssh/connect-totp` | `client.docker.connect_totp(**params)` |  |
| POST | `/docker/ssh/connect-warpgate` | `client.docker.connect_warpgate(**params)` |  |
| POST | `/docker/ssh/disconnect` | `client.docker.disconnect(**params)` |  |
| POST | `/docker/ssh/keepalive` | `client.docker.keepalive(**params)` |  |
| GET | `/docker/ssh/status` | `client.docker.get_status(**params)` |  |
| GET | `/docker/validate/{sessionId}` | `client.docker.validate_session(session_id)` |  |

</details>

<details>
<summary><code>client.encryption</code> (4 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/encryption/initialize` | `client.encryption.initialize()` |  |
| POST | `/encryption/regenerate` | `client.encryption.regenerate()` |  |
| POST | `/encryption/regenerate-jwt` | `client.encryption.regenerate_jwt()` |  |
| GET | `/encryption/status` | `client.encryption.get_status()` |  |

</details>

<details>
<summary><code>client.file_manager</code> (36 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/ssh/file_manager/ssh/activeTransfers` | `client.file_manager.list_active_transfers()` |  |
| POST | `/ssh/file_manager/ssh/changePermissions` | `client.file_manager.change_permissions(**params)` |  |
| POST | `/ssh/file_manager/ssh/compressFiles` | `client.file_manager.compress_files(**params)` |  |
| POST | `/ssh/file_manager/ssh/connect` | `client.file_manager.connect(**params)` |  |
| POST | `/ssh/file_manager/ssh/connect-totp` | `client.file_manager.connect_totp(**params)` |  |
| POST | `/ssh/file_manager/ssh/connect-warpgate` | `client.file_manager.connect_warpgate(**params)` |  |
| POST | `/ssh/file_manager/ssh/copyItem` | `client.file_manager.copy_item(**params)` |  |
| POST | `/ssh/file_manager/ssh/createFile` | `client.file_manager.create_file(**params)` |  |
| POST | `/ssh/file_manager/ssh/createFolder` | `client.file_manager.create_folder(**params)` |  |
| DELETE | `/ssh/file_manager/ssh/deleteItem` | `client.file_manager.delete_item()` |  |
| POST | `/ssh/file_manager/ssh/disconnect` | `client.file_manager.disconnect(**params)` |  |
| POST | `/ssh/file_manager/ssh/downloadFile` | `client.file_manager.download_file(**params)` |  |
| POST | `/ssh/file_manager/ssh/executeFile` | `client.file_manager.execute_file(**params)` |  |
| POST | `/ssh/file_manager/ssh/extractArchive` | `client.file_manager.extract_archive(**params)` |  |
| GET | `/ssh/file_manager/ssh/identifySymlink` | `client.file_manager.identify_symlink(**params)` |  |
| POST | `/ssh/file_manager/ssh/keepalive` | `client.file_manager.keepalive(**params)` |  |
| GET | `/ssh/file_manager/ssh/listFiles` | `client.file_manager.list_files(**params)` |  |
| PUT | `/ssh/file_manager/ssh/moveItem` | `client.file_manager.move_item(**params)` |  |
| GET | `/ssh/file_manager/ssh/readFile` | `client.file_manager.read_file(**params)` |  |
| PUT | `/ssh/file_manager/ssh/renameItem` | `client.file_manager.rename_item(**params)` |  |
| GET | `/ssh/file_manager/ssh/resolvePath` | `client.file_manager.resolve_path(**params)` |  |
| GET | `/ssh/file_manager/ssh/status` | `client.file_manager.status(**params)` |  |
| POST | `/ssh/file_manager/ssh/transferCancel/{transferId}` | `client.file_manager.cancel_transfer(transfer_id)` |  |
| POST | `/ssh/file_manager/ssh/transferCleanup/{transferId}` | `client.file_manager.cleanup_transfer(transfer_id)` |  |
| POST | `/ssh/file_manager/ssh/transferMethodPreview` | `client.file_manager.transfer_method_preview(**params)` |  |
| POST | `/ssh/file_manager/ssh/transferRetry/{transferId}` | `client.file_manager.retry_transfer(transfer_id)` |  |
| GET | `/ssh/file_manager/ssh/transferStatus/{transferId}` | `client.file_manager.get_transfer_status(transfer_id)` |  |
| POST | `/ssh/file_manager/ssh/transferToHost` | `client.file_manager.transfer_to_host(**params)` |  |
| DELETE | `/ssh/file_manager/ssh/trash` | `client.file_manager.empty_trash()` |  |
| GET | `/ssh/file_manager/ssh/trash` | `client.file_manager.list_trash()` |  |
| PUT | `/ssh/file_manager/ssh/trash-retention` | `client.file_manager.set_trash_retention(**params)` |  |
| DELETE | `/ssh/file_manager/ssh/trash/{id}` | `client.file_manager.delete_trash_item(id)` |  |
| POST | `/ssh/file_manager/ssh/trash/{id}/restore` | `client.file_manager.restore_trash_item(id)` |  |
| POST | `/ssh/file_manager/ssh/uploadFile` | `client.file_manager.upload_file(**params)` |  |
| POST | `/ssh/file_manager/ssh/writeFile` | `client.file_manager.write_file(**params)` |  |
| POST | `/ssh/file_manager/sudo-password` | `client.file_manager.sudo_password(**params)` |  |

</details>

<details>
<summary><code>client.fleets</code> (14 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/fleets` | `client.fleets.list()` |  |
| POST | `/fleets` | `client.fleets.create(**params)` |  |
| DELETE | `/fleets/{id}` | `client.fleets.delete(id)` |  |
| PATCH | `/fleets/{id}` | `client.fleets.update(id, **params)` |  |
| POST | `/fleets/{id}/execute` | `client.fleets.execute(id, **params)` |  |
| GET | `/fleets/{id}/inventory` | `client.fleets.get_inventory(id)` |  |
| POST | `/fleets/{id}/inventory` | `client.fleets.refresh_inventory(id)` |  |
| GET | `/fleets/{id}/members` | `client.fleets.list_members(id)` |  |
| POST | `/fleets/{id}/members` | `client.fleets.add_member(id, **params)` |  |
| DELETE | `/fleets/{id}/members/{hostId}` | `client.fleets.remove_member(id, host_id)` |  |
| POST | `/fleets/{id}/packages` | `client.fleets.packages_action(id, **params)` |  |
| POST | `/fleets/{id}/share` | `client.fleets.share(id, **params)` |  |
| POST | `/fleets/{id}/transfer/pull` | `client.fleets.transfer_pull(id, **params)` |  |
| POST | `/fleets/{id}/transfer/push` | `client.fleets.transfer_push(id, file, **params)` |  |

</details>

<details>
<summary><code>client.guacamole</code> (4 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/guacamole/connect-host/{hostId}` | `client.guacamole.connect_host(host_id, **params)` |  |
| GET | `/guacamole/connection/{connectId}` | `client.guacamole.get_connection(connect_id)` |  |
| GET | `/guacamole/status` | `client.guacamole.get_status()` |  |
| POST | `/guacamole/token` | `client.guacamole.create_token(**params)` |  |

</details>

<details>
<summary><code>client.homepage</code> (10 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/homepage/favicon` | `client.homepage.get_favicon(**params)` |  |
| GET | `/homepage/items` | `client.homepage.list_items()` |  |
| POST | `/homepage/items` | `client.homepage.create_item(**params)` |  |
| DELETE | `/homepage/items/{id}` | `client.homepage.delete_item(id)` |  |
| PUT | `/homepage/items/{id}` | `client.homepage.update_item(id, **params)` |  |
| GET | `/homepage/layout` | `client.homepage.get_layout()` |  |
| PUT | `/homepage/layout` | `client.homepage.set_layout(**params)` |  |
| GET | `/homepage/ping` | `client.homepage.ping(**params)` |  |
| GET | `/homepage/proxy` | `client.homepage.proxy(**params)` |  |
| GET | `/homepage/rss` | `client.homepage.rss(**params)` |  |

</details>

<details>
<summary><code>client.host_file_manager</code> (9 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| DELETE | `/host/file_manager/pinned` | `client.host_file_manager.remove_pinned()` |  |
| GET | `/host/file_manager/pinned` | `client.host_file_manager.list_pinned(**params)` |  |
| POST | `/host/file_manager/pinned` | `client.host_file_manager.add_pinned(**params)` |  |
| DELETE | `/host/file_manager/recent` | `client.host_file_manager.clear_recent()` |  |
| GET | `/host/file_manager/recent` | `client.host_file_manager.list_recent(**params)` |  |
| POST | `/host/file_manager/recent` | `client.host_file_manager.add_recent(**params)` |  |
| DELETE | `/host/file_manager/shortcuts` | `client.host_file_manager.remove_shortcut()` |  |
| GET | `/host/file_manager/shortcuts` | `client.host_file_manager.list_shortcuts(**params)` |  |
| POST | `/host/file_manager/shortcuts` | `client.host_file_manager.add_shortcut(**params)` |  |

</details>

<details>
<summary><code>client.hosts</code> (32 operations, 5 live-tested)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| DELETE | `/host/autostart/disable` | `client.hosts.disable_autostart()` |  |
| POST | `/host/autostart/enable` | `client.hosts.enable_autostart(**params)` |  |
| GET | `/host/autostart/status` | `client.hosts.get_autostart_status()` |  |
| POST | `/host/bulk-import` | `client.hosts.bulk_import(**params)` |  |
| PATCH | `/host/bulk-update` | `client.hosts.bulk_update(**params)` |  |
| DELETE | `/host/command-history` | `client.hosts.clear_command_history()` |  |
| GET | `/host/command-history/{hostId}` | `client.hosts.get_command_history(host_id)` |  |
| GET | `/host/db/host` | `client.hosts.list()` | ✅ |
| POST | `/host/db/host` | `client.hosts.create(**params)` | ✅ |
| DELETE | `/host/db/host/{id}` | `client.hosts.delete(id)` | ✅ |
| GET | `/host/db/host/{id}` | `client.hosts.retrieve(id)` | ✅ |
| PUT | `/host/db/host/{id}` | `client.hosts.update(id, **params)` | ✅ |
| GET | `/host/db/host/{id}/export` | `client.hosts.export(id)` |  |
| GET | `/host/db/host/{id}/local-connection-auth` | `client.hosts.get_local_connection_auth(id)` |  |
| GET | `/host/db/host/{id}/password` | `client.hosts.get_password(id, **params)` |  |
| PATCH | `/host/db/host/{id}/terminal-config` | `client.hosts.update_terminal_config(id, **params)` |  |
| POST | `/host/db/host/{id}/wake` | `client.hosts.wake(id)` |  |
| GET | `/host/db/hosts/export` | `client.hosts.export_all(**params)` |  |
| POST | `/host/db/proxy/test` | `client.hosts.test_proxy(**params)` |  |
| POST | `/host/enroll` | `client.hosts.enroll(**params)` |  |
| GET | `/host/folders` | `client.hosts.list_folders()` |  |
| PUT | `/host/folders/metadata` | `client.hosts.update_folder_metadata(**params)` |  |
| PUT | `/host/folders/rename` | `client.hosts.rename_folder(**params)` |  |
| PUT | `/host/folders/reorder` | `client.hosts.reorder_folders(**params)` |  |
| DELETE | `/host/folders/{name}/hosts` | `client.hosts.remove_hosts_from_folder(name)` |  |
| POST | `/host/quick-connect` | `client.hosts.quick_connect(**params)` |  |
| PUT | `/host/reorder` | `client.hosts.reorder(**params)` |  |
| POST | `/host/ssh-config-import` | `client.hosts.ssh_config_import(**params)` |  |
| DELETE | `/host/ssh/opkssh/token/{hostId}` | `client.hosts.delete_opkssh_token(host_id)` |  |
| GET | `/host/ssh/opkssh/token/{hostId}` | `client.hosts.get_opkssh_token(host_id)` |  |
| GET | `/host/transfer/recent` | `client.hosts.get_recent_transfer(**params)` |  |
| POST | `/host/transfer/recent` | `client.hosts.record_recent_transfer(**params)` |  |

</details>

<details>
<summary><code>client.instance_settings</code> (45 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/users/acme-ssl-request` | `client.instance_settings.acme_ssl_request()` |  |
| GET | `/users/acme-ssl-settings` | `client.instance_settings.get_acme_ssl_settings()` |  |
| PATCH | `/users/acme-ssl-settings` | `client.instance_settings.update_acme_ssl_settings(**params)` |  |
| GET | `/users/ai-enabled` | `client.instance_settings.get_ai_enabled()` |  |
| PATCH | `/users/ai-enabled` | `client.instance_settings.update_ai_enabled(**params)` |  |
| GET | `/users/ai-private-endpoints` | `client.instance_settings.get_ai_private_endpoints()` |  |
| PATCH | `/users/ai-private-endpoints` | `client.instance_settings.update_ai_private_endpoints(**params)` |  |
| GET | `/users/analytics-enabled` | `client.instance_settings.get_analytics_enabled()` |  |
| PATCH | `/users/analytics-enabled` | `client.instance_settings.update_analytics_enabled(**params)` |  |
| GET | `/users/audit-forwarding` | `client.instance_settings.get_audit_forwarding()` |  |
| PATCH | `/users/audit-forwarding` | `client.instance_settings.update_audit_forwarding(**params)` |  |
| GET | `/users/branding` | `client.instance_settings.get_branding()` |  |
| PATCH | `/users/branding` | `client.instance_settings.update_branding(**params)` |  |
| GET | `/users/command-history-enabled` | `client.instance_settings.get_command_history_enabled()` |  |
| PATCH | `/users/command-history-enabled` | `client.instance_settings.update_command_history_enabled(**params)` |  |
| GET | `/users/guacamole-settings` | `client.instance_settings.get_guacamole_settings()` |  |
| PATCH | `/users/guacamole-settings` | `client.instance_settings.update_guacamole_settings(**params)` |  |
| GET | `/users/host-defaults` | `client.instance_settings.get_host_defaults()` |  |
| PATCH | `/users/host-defaults` | `client.instance_settings.update_host_defaults(**params)` |  |
| GET | `/users/log-level` | `client.instance_settings.get_log_level()` |  |
| PATCH | `/users/log-level` | `client.instance_settings.update_log_level(**params)` |  |
| POST | `/users/manual-ssl-upload` | `client.instance_settings.manual_ssl_upload(**params)` |  |
| GET | `/users/oidc-auto-provision` | `client.instance_settings.get_oidc_auto_provision()` |  |
| PATCH | `/users/oidc-auto-provision` | `client.instance_settings.update_oidc_auto_provision(**params)` |  |
| DELETE | `/users/oidc-config` | `client.instance_settings.delete_oidc_config()` |  |
| GET | `/users/oidc-config` | `client.instance_settings.get_oidc_config()` |  |
| POST | `/users/oidc-config` | `client.instance_settings.set_oidc_config(**params)` |  |
| GET | `/users/oidc-config/admin` | `client.instance_settings.get_oidc_config_admin()` |  |
| GET | `/users/oidc-silent-login-default` | `client.instance_settings.get_oidc_silent_login_default()` |  |
| PATCH | `/users/oidc-silent-login-default` | `client.instance_settings.update_oidc_silent_login_default(**params)` |  |
| GET | `/users/password-login-allowed` | `client.instance_settings.get_password_login_allowed()` |  |
| PATCH | `/users/password-login-allowed` | `client.instance_settings.update_password_login_allowed(**params)` |  |
| GET | `/users/password-reset-allowed` | `client.instance_settings.get_password_reset_allowed()` |  |
| PATCH | `/users/password-reset-allowed` | `client.instance_settings.update_password_reset_allowed(**params)` |  |
| GET | `/users/registration-allowed` | `client.instance_settings.get_registration_allowed()` |  |
| PATCH | `/users/registration-allowed` | `client.instance_settings.update_registration_allowed(**params)` |  |
| GET | `/users/session-sharing-enabled` | `client.instance_settings.get_session_sharing_enabled()` |  |
| PATCH | `/users/session-sharing-enabled` | `client.instance_settings.update_session_sharing_enabled(**params)` |  |
| GET | `/users/session-timeout` | `client.instance_settings.get_session_timeout()` |  |
| PATCH | `/users/session-timeout` | `client.instance_settings.update_session_timeout(**params)` |  |
| GET | `/users/setup-required` | `client.instance_settings.get_setup_required()` |  |
| GET | `/users/step-ca-settings` | `client.instance_settings.get_step_ca_settings()` |  |
| PATCH | `/users/step-ca-settings` | `client.instance_settings.update_step_ca_settings(**params)` |  |
| GET | `/users/tailscale-settings` | `client.instance_settings.get_tailscale_settings()` |  |
| PATCH | `/users/tailscale-settings` | `client.instance_settings.update_tailscale_settings(**params)` |  |

</details>

<details>
<summary><code>client.metrics</code> (50 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/clear-connections` | `client.metrics.clear_connections()` |  |
| GET | `/global-settings` | `client.metrics.get_global_settings()` |  |
| POST | `/global-settings` | `client.metrics.set_global_settings(**params)` |  |
| GET | `/global-settings/history` | `client.metrics.get_global_settings_history()` |  |
| POST | `/global-settings/history` | `client.metrics.save_global_settings_history(**params)` |  |
| POST | `/host-deleted` | `client.metrics.notify_host_deleted(**params)` |  |
| GET | `/host-metrics/managers/cron/{id}` | `client.metrics.get_cron(id)` |  |
| POST | `/host-metrics/managers/cron/{id}` | `client.metrics.set_cron(id, **params)` |  |
| GET | `/host-metrics/managers/disk-breakdown/{id}` | `client.metrics.get_disk_breakdown(id)` |  |
| GET | `/host-metrics/managers/firewall/{id}` | `client.metrics.get_firewall(id)` |  |
| POST | `/host-metrics/managers/firewall/{id}/persist` | `client.metrics.persist_firewall(id)` |  |
| POST | `/host-metrics/managers/firewall/{id}/rule` | `client.metrics.add_firewall_rule(id, **params)` |  |
| GET | `/host-metrics/managers/health/{id}` | `client.metrics.get_health(id)` |  |
| POST | `/host-metrics/managers/health/{id}/config` | `client.metrics.configure_health(id, **params)` |  |
| POST | `/host-metrics/managers/health/{id}/run` | `client.metrics.run_health_check(id)` |  |
| GET | `/host-metrics/managers/logs/{id}` | `client.metrics.get_logs(id, **params)` |  |
| GET | `/host-metrics/managers/logs/{id}/files` | `client.metrics.list_log_files(id)` |  |
| GET | `/host-metrics/managers/packages/{id}` | `client.metrics.get_packages(id)` |  |
| POST | `/host-metrics/managers/packages/{id}/action` | `client.metrics.run_package_action(id, **params)` |  |
| GET | `/host-metrics/managers/processes/{id}` | `client.metrics.get_processes(id)` |  |
| POST | `/host-metrics/managers/processes/{id}/signal` | `client.metrics.signal_process(id, **params)` |  |
| GET | `/host-metrics/managers/services/{id}` | `client.metrics.get_services(id)` |  |
| POST | `/host-metrics/managers/services/{id}/action` | `client.metrics.run_service_action(id, **params)` |  |
| GET | `/host-metrics/managers/ssl/{id}` | `client.metrics.get_ssl(id)` |  |
| POST | `/host-metrics/managers/ssl/{id}/issue` | `client.metrics.issue_ssl(id, **params)` |  |
| POST | `/host-metrics/managers/ssl/{id}/renew` | `client.metrics.renew_ssl(id, **params)` |  |
| POST | `/host-metrics/managers/ssl/{id}/revoke` | `client.metrics.revoke_ssl(id, **params)` |  |
| GET | `/host-metrics/managers/tailscale/{id}` | `client.metrics.get_tailscale(id)` |  |
| POST | `/host-metrics/managers/tailscale/{id}/action` | `client.metrics.run_tailscale_action(id, **params)` |  |
| GET | `/host-metrics/managers/timers/{id}` | `client.metrics.get_timers(id)` |  |
| GET | `/host-metrics/managers/top-memory/{id}` | `client.metrics.get_top_memory(id)` |  |
| GET | `/host-metrics/managers/users/{id}` | `client.metrics.get_users(id)` |  |
| POST | `/host-metrics/managers/users/{id}/action` | `client.metrics.run_user_action(id, **params)` |  |
| GET | `/host-metrics/managers/wireguard/{id}` | `client.metrics.get_wireguard(id)` |  |
| POST | `/host-metrics/managers/wireguard/{id}/action` | `client.metrics.run_wireguard_action(id, **params)` |  |
| GET | `/host-metrics/platform/{id}` | `client.metrics.get_platform(id)` |  |
| GET | `/host-metrics/preferences/{id}` | `client.metrics.get_metrics_preferences(id)` |  |
| POST | `/host-metrics/preferences/{id}` | `client.metrics.set_metrics_preferences(id, **params)` |  |
| POST | `/host-updated` | `client.metrics.notify_host_updated(**params)` |  |
| POST | `/metrics/connect-totp` | `client.metrics.connect_totp(**params)` |  |
| POST | `/metrics/heartbeat` | `client.metrics.metrics_heartbeat(**params)` |  |
| GET | `/metrics/history/{id}` | `client.metrics.get_metrics_history(id)` |  |
| POST | `/metrics/register-viewer` | `client.metrics.register_metrics_viewer(**params)` |  |
| POST | `/metrics/start/{id}` | `client.metrics.start_metrics(id)` |  |
| POST | `/metrics/stop/{id}` | `client.metrics.stop_metrics(id, **params)` |  |
| POST | `/metrics/unregister-viewer` | `client.metrics.unregister_metrics_viewer(**params)` |  |
| GET | `/metrics/{id}` | `client.metrics.get_metrics(id)` |  |
| POST | `/refresh` | `client.metrics.refresh_polling()` |  |
| GET | `/status` | `client.metrics.list_statuses(**params)` |  |
| GET | `/status/{id}` | `client.metrics.get_status(id)` |  |

</details>

<details>
<summary><code>client.network_topology</code> (2 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/network-topology` | `client.network_topology.get()` |  |
| POST | `/network-topology` | `client.network_topology.save(**params)` |  |

</details>

<details>
<summary><code>client.open_tabs</code> (6 operations, 6 live-tested)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/open-tabs` | `client.open_tabs.list()` | ✅ |
| POST | `/open-tabs` | `client.open_tabs.upsert(**params)` | ✅ |
| PUT | `/open-tabs` | `client.open_tabs.replace_all(**params)` | ✅ |
| GET | `/open-tabs/active-sessions` | `client.open_tabs.list_active_sessions()` | ✅ |
| DELETE | `/open-tabs/{id}` | `client.open_tabs.delete(id)` | ✅ |
| PATCH | `/open-tabs/{id}` | `client.open_tabs.update(id, **params)` | ✅ |

</details>

<details>
<summary><code>client.preferences</code> (10 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/credential-sidebar/preferences` | `client.preferences.get_credential_sidebar()` |  |
| PUT | `/credential-sidebar/preferences` | `client.preferences.set_credential_sidebar(**params)` |  |
| GET | `/host-sidebar/preferences` | `client.preferences.get_host_sidebar()` |  |
| PUT | `/host-sidebar/preferences` | `client.preferences.set_host_sidebar(**params)` |  |
| GET | `/ui-preferences` | `client.preferences.get_ui_preferences()` |  |
| PUT | `/ui-preferences` | `client.preferences.set_ui_preferences(**params)` |  |
| GET | `/user-preferences` | `client.preferences.get_user_preferences()` |  |
| PUT | `/user-preferences` | `client.preferences.set_user_preferences(**params)` |  |
| GET | `/users/touch-input-settings` | `client.preferences.get_touch_input_settings()` |  |
| PATCH | `/users/touch-input-settings` | `client.preferences.update_touch_input_settings(**params)` |  |

</details>

<details>
<summary><code>client.proxmox</code> (3 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/proxmox/discover` | `client.proxmox.discover(**params)` |  |
| GET | `/proxmox/discover/stream` | `client.proxmox.discover_stream()` |  |
| POST | `/proxmox/sync` | `client.proxmox.sync(**params)` |  |

</details>

<details>
<summary><code>client.proxmox_stats</code> (7 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/proxmox-stats/heartbeat` | `client.proxmox_stats.heartbeat(**params)` |  |
| GET | `/proxmox-stats/history/{hostId}` | `client.proxmox_stats.get_history(host_id)` |  |
| POST | `/proxmox-stats/register-viewer` | `client.proxmox_stats.register_viewer(**params)` |  |
| POST | `/proxmox-stats/start/{id}` | `client.proxmox_stats.start(id)` |  |
| POST | `/proxmox-stats/stop/{id}` | `client.proxmox_stats.stop(id, **params)` |  |
| POST | `/proxmox-stats/unregister-viewer` | `client.proxmox_stats.unregister_viewer(**params)` |  |
| GET | `/proxmox-stats/{id}` | `client.proxmox_stats.retrieve(id)` |  |

</details>

<details>
<summary><code>client.rbac</code> (27 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/rbac/credential/{id}/access` | `client.rbac.list_credential_access(id)` |  |
| DELETE | `/rbac/credential/{id}/access/{accessId}` | `client.rbac.delete_credential_access(id, access_id)` |  |
| POST | `/rbac/credential/{id}/share` | `client.rbac.share_credential(id, **params)` |  |
| GET | `/rbac/folder/access` | `client.rbac.list_folder_access(**params)` |  |
| DELETE | `/rbac/folder/access/{id}` | `client.rbac.delete_folder_access(id)` |  |
| POST | `/rbac/folder/share` | `client.rbac.share_folder(**params)` |  |
| GET | `/rbac/host-access/{hostId}/auth/{protocol}` | `client.rbac.get_host_access_auth(host_id, protocol)` |  |
| PUT | `/rbac/host-access/{hostId}/auth/{protocol}` | `client.rbac.set_host_access_auth(host_id, protocol, **params)` |  |
| GET | `/rbac/host/{id}/access` | `client.rbac.list_host_access(id)` |  |
| DELETE | `/rbac/host/{id}/access/{accessId}` | `client.rbac.delete_host_access(id, access_id)` |  |
| PATCH | `/rbac/host/{id}/access/{accessId}` | `client.rbac.update_host_access(id, access_id, **params)` |  |
| POST | `/rbac/host/{id}/share` | `client.rbac.share_host(id, **params)` |  |
| GET | `/rbac/permissions/catalog` | `client.rbac.permissions_catalog()` |  |
| GET | `/rbac/roles` | `client.rbac.list_roles()` |  |
| POST | `/rbac/roles` | `client.rbac.create_role(**params)` |  |
| DELETE | `/rbac/roles/{id}` | `client.rbac.delete_role(id)` |  |
| PUT | `/rbac/roles/{id}` | `client.rbac.update_role(id, **params)` |  |
| GET | `/rbac/roles/{id}/members` | `client.rbac.list_role_members(id)` |  |
| GET | `/rbac/shared-hosts` | `client.rbac.list_shared_hosts()` |  |
| GET | `/rbac/shared-snippets` | `client.rbac.list_shared_snippets()` |  |
| POST | `/rbac/snippet-folder/share` | `client.rbac.share_snippet_folder(**params)` |  |
| GET | `/rbac/snippet/{id}/access` | `client.rbac.list_snippet_access(id)` |  |
| DELETE | `/rbac/snippet/{id}/access/{accessId}` | `client.rbac.delete_snippet_access(id, access_id)` |  |
| POST | `/rbac/snippet/{id}/share` | `client.rbac.share_snippet(id, **params)` |  |
| GET | `/rbac/users/{userId}/roles` | `client.rbac.list_user_roles(user_id)` |  |
| POST | `/rbac/users/{userId}/roles` | `client.rbac.assign_role(user_id, **params)` |  |
| DELETE | `/rbac/users/{userId}/roles/{roleId}` | `client.rbac.revoke_role(user_id, role_id)` |  |

</details>

<details>
<summary><code>client.secret_sources</code> (5 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/secret-sources` | `client.secret_sources.list()` |  |
| POST | `/secret-sources` | `client.secret_sources.create(**params)` |  |
| DELETE | `/secret-sources/{id}` | `client.secret_sources.delete(id)` |  |
| PUT | `/secret-sources/{id}` | `client.secret_sources.update(id, **params)` |  |
| POST | `/secret-sources/{id}/test` | `client.secret_sources.test(id)` |  |

</details>

<details>
<summary><code>client.session_logs</code> (6 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/session_logs` | `client.session_logs.list()` |  |
| GET | `/session_logs/retention` | `client.session_logs.get_retention()` |  |
| PUT | `/session_logs/retention` | `client.session_logs.set_retention(**params)` |  |
| DELETE | `/session_logs/{id}` | `client.session_logs.delete(id)` |  |
| GET | `/session_logs/{id}` | `client.session_logs.retrieve(id)` |  |
| GET | `/session_logs/{id}/content` | `client.session_logs.get_content(id)` |  |

</details>

<details>
<summary><code>client.session_sharing</code> (5 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/session-sharing/create` | `client.session_sharing.create(**params)` |  |
| GET | `/session-sharing/host/{hostId}/active` | `client.session_sharing.get_active_for_host(host_id)` |  |
| GET | `/session-sharing/resolve/{linkToken}` | `client.session_sharing.resolve(link_token)` |  |
| DELETE | `/session-sharing/{shareId}` | `client.session_sharing.delete(share_id)` |  |
| POST | `/session-sharing/{shareId}/end` | `client.session_sharing.end(share_id)` |  |

</details>

<details>
<summary><code>client.snippets</code> (14 operations, 5 live-tested)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/snippets` | `client.snippets.list()` | ✅ |
| POST | `/snippets` | `client.snippets.create(**params)` | ✅ |
| POST | `/snippets/bulk-import` | `client.snippets.bulk_import(**params)` |  |
| POST | `/snippets/execute` | `client.snippets.execute(**params)` |  |
| GET | `/snippets/export` | `client.snippets.export()` |  |
| GET | `/snippets/folders` | `client.snippets.list_folders()` |  |
| POST | `/snippets/folders` | `client.snippets.create_folder(**params)` |  |
| PUT | `/snippets/folders/rename` | `client.snippets.rename_folder(**params)` |  |
| DELETE | `/snippets/folders/{name}` | `client.snippets.delete_folder(name)` |  |
| PUT | `/snippets/folders/{name}/metadata` | `client.snippets.update_folder_metadata(name, **params)` |  |
| PUT | `/snippets/reorder` | `client.snippets.reorder(**params)` |  |
| DELETE | `/snippets/{id}` | `client.snippets.delete(id)` | ✅ |
| GET | `/snippets/{id}` | `client.snippets.retrieve(id)` | ✅ |
| PUT | `/snippets/{id}` | `client.snippets.update(id, **params)` | ✅ |

</details>

<details>
<summary><code>client.sso</code> (6 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/users/ldap/login` | `client.sso.ldap_login(**params)` |  |
| GET | `/users/sso-providers` | `client.sso.list_providers()` |  |
| POST | `/users/sso-providers` | `client.sso.create_provider(**params)` |  |
| GET | `/users/sso-providers/admin` | `client.sso.list_providers_admin()` |  |
| DELETE | `/users/sso-providers/{id}` | `client.sso.delete_provider(id)` |  |
| PUT | `/users/sso-providers/{id}` | `client.sso.update_provider(id, **params)` |  |

</details>

<details>
<summary><code>client.sync</code> (4 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/sync/tombstones` | `client.sync.push_tombstones(**params)` |  |
| GET | `/sync/{entityType}` | `client.sync.pull(entity_type, **params)` |  |
| POST | `/sync/{entityType}` | `client.sync.push(entity_type, **params)` |  |
| GET | `/sync/{entityType}/tombstones` | `client.sync.pull_tombstones(entity_type, **params)` |  |

</details>

<details>
<summary><code>client.system</code> (3 operations, 2 live-tested)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/health` | `client.system.health()` | ✅ |
| GET | `/releases/rss` | `client.system.list_releases(**params)` |  |
| GET | `/version` | `client.system.version(**params)` | ✅ |

</details>

<details>
<summary><code>client.tailscale</code> (1 operation)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/tailscale/devices` | `client.tailscale.list_devices()` |  |

</details>

<details>
<summary><code>client.terminal</code> (7 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/terminal/command_history` | `client.terminal.log_command(**params)` |  |
| POST | `/terminal/command_history/delete` | `client.terminal.delete_command_history_entries(**params)` |  |
| DELETE | `/terminal/command_history/{hostId}` | `client.terminal.clear_command_history(host_id)` |  |
| GET | `/terminal/command_history/{hostId}` | `client.terminal.list_command_history(host_id)` |  |
| POST | `/terminal/image-upload` | `client.terminal.image_upload(**params)` |  |
| GET | `/terminal/session_settings` | `client.terminal.get_session_settings()` |  |
| POST | `/terminal/session_settings` | `client.terminal.set_session_settings(**params)` |  |

</details>

<details>
<summary><code>client.termix_id</code> (18 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| DELETE | `/termix-id` | `client.termix_id.delete()` |  |
| POST | `/termix-id` | `client.termix_id.create(**params)` |  |
| PUT | `/termix-id` | `client.termix_id.update(**params)` |  |
| DELETE | `/termix-id/ca` | `client.termix_id.delete_ca()` |  |
| GET | `/termix-id/ca` | `client.termix_id.get_ca()` |  |
| POST | `/termix-id/ca` | `client.termix_id.create_ca(**params)` |  |
| POST | `/termix-id/ca/rotate` | `client.termix_id.rotate_ca(**params)` |  |
| GET | `/termix-id/check/{handle}` | `client.termix_id.check_handle(handle)` |  |
| POST | `/termix-id/keys` | `client.termix_id.create_key(**params)` |  |
| POST | `/termix-id/keys/generate` | `client.termix_id.generate_key(**params)` |  |
| DELETE | `/termix-id/keys/{id}` | `client.termix_id.delete_key(id)` |  |
| PATCH | `/termix-id/keys/{id}` | `client.termix_id.update_key(id, **params)` |  |
| POST | `/termix-id/keys/{id}/certificate` | `client.termix_id.issue_certificate(id, **params)` |  |
| GET | `/termix-id/linked-credentials` | `client.termix_id.list_linked_credentials()` |  |
| GET | `/termix-id/me` | `client.termix_id.get_me()` |  |
| GET | `/termix-id/u/{handle}` | `client.termix_id.get_public_identity(handle)` |  |
| GET | `/termix-id/u/{handle}/ca` | `client.termix_id.get_public_ca(handle)` |  |
| GET | `/termix-id/u/{handle}/{algo}` | `client.termix_id.get_public_key(handle, algo)` |  |

</details>

<details>
<summary><code>client.tmux</code> (12 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/tmux_monitor/{hostId}/focus` | `client.tmux.focus(host_id, **params)` |  |
| POST | `/tmux_monitor/{hostId}/kill` | `client.tmux.kill(host_id, **params)` |  |
| POST | `/tmux_monitor/{hostId}/kill-pane` | `client.tmux.kill_pane(host_id, **params)` |  |
| POST | `/tmux_monitor/{hostId}/kill-window` | `client.tmux.kill_window(host_id, **params)` |  |
| GET | `/tmux_monitor/{hostId}/metrics` | `client.tmux.metrics(host_id)` |  |
| GET | `/tmux_monitor/{hostId}/overview` | `client.tmux.get_overview(host_id)` |  |
| POST | `/tmux_monitor/{hostId}/rename` | `client.tmux.rename(host_id, **params)` |  |
| GET | `/tmux_monitor/{hostId}/search` | `client.tmux.search(host_id, **params)` |  |
| POST | `/tmux_monitor/{hostId}/sessions` | `client.tmux.list_sessions(host_id, **params)` |  |
| POST | `/tmux_monitor/{hostId}/split` | `client.tmux.split(host_id, **params)` |  |
| PUT | `/tmux_monitor/{hostId}/tags` | `client.tmux.set_tags(host_id, **params)` |  |
| POST | `/tmux_monitor/{hostId}/windows` | `client.tmux.list_windows(host_id, **params)` |  |

</details>

<details>
<summary><code>client.tunnel</code> (7 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/ssh/tunnel/cancel` | `client.tunnel.cancel(**params)` |  |
| POST | `/ssh/tunnel/connect` | `client.tunnel.connect(**params)` |  |
| POST | `/ssh/tunnel/disconnect` | `client.tunnel.disconnect(**params)` |  |
| GET | `/ssh/tunnel/status` | `client.tunnel.get_status()` |  |
| GET | `/ssh/tunnel/status/stream` | `client.tunnel.watch_status()` |  |
| GET | `/ssh/tunnel/status/{tunnelName}` | `client.tunnel.get_status_by_name(tunnel_name)` |  |
| POST | `/ssh/tunnel/web-endpoint/open` | `client.tunnel.open_web_endpoint(**params)` |  |

</details>

<details>
<summary><code>client.tunnel_presets</code> (4 operations, 4 live-tested)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/c2s-tunnel-presets` | `client.tunnel_presets.list()` | ✅ |
| POST | `/c2s-tunnel-presets` | `client.tunnel_presets.create(**params)` | ✅ |
| DELETE | `/c2s-tunnel-presets/{id}` | `client.tunnel_presets.delete(id)` | ✅ |
| PUT | `/c2s-tunnel-presets/{id}` | `client.tunnel_presets.update(id, **params)` | ✅ |

</details>

<details>
<summary><code>client.user_admin</code> (10 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/users/admin-create` | `client.user_admin.create_user(**params)` |  |
| GET | `/users/admin/export/{userId}` | `client.user_admin.export_user(user_id)` |  |
| POST | `/users/admin/reset-password` | `client.user_admin.reset_user_password(**params)` |  |
| POST | `/users/admin/totp/disable` | `client.user_admin.disable_user_totp(**params)` |  |
| GET | `/users/count` | `client.user_admin.count()` |  |
| GET | `/users/db-health` | `client.user_admin.get_db_health()` |  |
| DELETE | `/users/delete-user` | `client.user_admin.delete_user()` |  |
| GET | `/users/list` | `client.user_admin.list()` |  |
| POST | `/users/make-admin` | `client.user_admin.make_admin(**params)` |  |
| POST | `/users/remove-admin` | `client.user_admin.remove_admin(**params)` |  |

</details>

<details>
<summary><code>client.users</code> (25 operations, 1 live-tested)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/users/change-password` | `client.users.change_password(**params)` |  |
| POST | `/users/complete-reset` | `client.users.complete_reset(**params)` |  |
| POST | `/users/create` | `client.users.register(**params)` |  |
| GET | `/users/data-status` | `client.users.get_data_status()` |  |
| DELETE | `/users/delete-account` | `client.users.delete_account()` |  |
| POST | `/users/initiate-reset` | `client.users.initiate_reset(**params)` |  |
| POST | `/users/link-oidc-to-password` | `client.users.link_oidc_to_password(**params)` |  |
| POST | `/users/logout` | `client.users.logout()` |  |
| GET | `/users/me` | `client.users.get_me()` | ✅ |
| POST | `/users/me/dismiss-donation-modal` | `client.users.dismiss_donation_modal()` |  |
| GET | `/users/me/token` | `client.users.get_token()` |  |
| POST | `/users/proxy-login` | `client.users.proxy_login()` |  |
| GET | `/users/sessions` | `client.users.list_sessions()` |  |
| POST | `/users/sessions/revoke-all` | `client.users.revoke_all_sessions(**params)` |  |
| DELETE | `/users/sessions/{sessionId}` | `client.users.revoke_session(session_id)` |  |
| GET | `/users/terminal-image-storage-settings` | `client.users.get_terminal_image_storage_settings()` |  |
| PATCH | `/users/terminal-image-storage-settings` | `client.users.update_terminal_image_storage_settings(**params)` |  |
| POST | `/users/terminal-image-storage-settings/test` | `client.users.test_terminal_image_storage_settings(**params)` |  |
| POST | `/users/totp/backup-codes` | `client.users.get_totp_backup_codes(**params)` |  |
| POST | `/users/totp/disable` | `client.users.disable_totp(**params)` |  |
| POST | `/users/totp/enable` | `client.users.enable_totp(**params)` |  |
| POST | `/users/totp/setup` | `client.users.setup_totp(**params)` |  |
| POST | `/users/unlink-oidc-from-password` | `client.users.unlink_oidc_from_password(**params)` |  |
| POST | `/users/unlock-data` | `client.users.unlock_data(**params)` |  |
| POST | `/users/verify-reset-code` | `client.users.verify_reset_code(**params)` |  |

</details>

<details>
<summary><code>client.vault</code> (4 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/vault/profiles` | `client.vault.list_profiles()` |  |
| POST | `/vault/profiles` | `client.vault.create_profile(**params)` |  |
| DELETE | `/vault/profiles/{id}` | `client.vault.delete_profile(id)` |  |
| PUT | `/vault/profiles/{id}` | `client.vault.update_profile(id, **params)` |  |

</details>

<details>
<summary><code>client.webauthn</code> (6 operations)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| POST | `/users/webauthn/authenticate/options` | `client.webauthn.authenticate_options(**params)` |  |
| POST | `/users/webauthn/authenticate/verify` | `client.webauthn.authenticate_verify(**params)` |  |
| GET | `/users/webauthn/credentials` | `client.webauthn.list_credentials()` |  |
| DELETE | `/users/webauthn/credentials/{credentialId}` | `client.webauthn.delete_credential(credential_id)` |  |
| POST | `/users/webauthn/register/options` | `client.webauthn.register_options(**params)` |  |
| POST | `/users/webauthn/register/verify` | `client.webauthn.register_verify(**params)` |  |

</details>

<details>
<summary><code>client.workspaces</code> (11 operations, 11 live-tested)</summary>

| Method | Path | SDK call | Live-tested |
|---|---|---|---|
| GET | `/workspaces` | `client.workspaces.list()` | ✅ |
| POST | `/workspaces` | `client.workspaces.create(**params)` | ✅ |
| GET | `/workspaces/last-session` | `client.workspaces.get_last_session()` | ✅ |
| PUT | `/workspaces/last-session` | `client.workspaces.save_last_session(**params)` | ✅ |
| DELETE | `/workspaces/{id}` | `client.workspaces.delete(id)` | ✅ |
| PATCH | `/workspaces/{id}` | `client.workspaces.update(id, **params)` | ✅ |
| POST | `/workspaces/{id}/apply` | `client.workspaces.apply(id)` | ✅ |
| PUT | `/workspaces/{id}/content` | `client.workspaces.set_content(id, **params)` | ✅ |
| POST | `/workspaces/{id}/duplicate` | `client.workspaces.duplicate(id, **params)` | ✅ |
| POST | `/workspaces/{id}/set-default` | `client.workspaces.set_default(id)` | ✅ |
| POST | `/workspaces/{id}/unset-default` | `client.workspaces.unset_default(id)` | ✅ |

</details>
<!-- routes-table end -->

## What's generated vs. hand-written

`src/termix_sdk/resources/`, `models/`, and `types/` are generated by
`tools/sdk-gen/generate.py` from `spec/termix-openapi.json` and
`tools/sdk-gen/config/resource-map.json` — don't hand-edit them, changes
will be overwritten on the next run. Everything else (`_client.py`,
`_error.py`, `_object.py`, `_session.py`, `_sse.py`, ...) is hand-written
core, adapted from [stripe/stripe-python](https://github.com/stripe/stripe-python)
where noted — see [NOTICE](NOTICE) for the MIT attribution this carries.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how the spec/generator/tests
fit together and how to regenerate the SDK after a Termix release.

## Documentation

- [Routes covered](#routes-covered): every endpoint the SDK implements, next to the SDK call for it.
- [Generating our own Termix API spec](tools/spec-gen/docs/spec-generation-strategy.md): why the SDK does not rely on the official `openapi.json`, and how the spec is derived from the Termix backend source (route discovery, auth, typed request bodies, every response per status code, Drizzle schema, test examples).
- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## License

MIT — see [LICENSE](LICENSE). Portions adapted from stripe-python are
also MIT; see [NOTICE](NOTICE).
