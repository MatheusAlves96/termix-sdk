# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

Regenerated against Termix `release-2.8.0-tag` (`SPEC_VERSION` bumped
from `release-2.7.1-tag`). 531 operations in the spec, up from 491; none
were removed. 516 of them are now exposed, up from 477.

### Added

- Two new resource modules: `client.collab` (16 operations — rooms,
  members, the presenter stage, stage-control requests and the anonymous
  guest link) and `client.secret_sources` (5 — 1Password Connect sources).
- New operations on existing modules: `rbac.share_credential()`,
  `rbac.list_credential_access()`, `rbac.delete_credential_access()`,
  `rbac.share_snippet_folder()`, `rbac.list_folder_access()`,
  `rbac.delete_folder_access()`, `rbac.list_role_members()`;
  `instance_settings.{get,update}_branding()`,
  `instance_settings.{get,update}_audit_forwarding()`,
  `instance_settings.{get,update}_step_ca_settings()`;
  `hosts.update_terminal_config()`, `hosts.get_local_connection_auth()`;
  `ai.mark_proposal_run_in_terminal()`; `guacamole.get_connection()`;
  `tunnel.open_web_endpoint()`.
- New fields on existing shapes: `enableWebUi`, `enableAiAssistant` and
  `webUiConfig` across the host create/update/enroll/list/export
  operations; `autoTmux` on `instance_settings.update_host_defaults()`;
  `showPinAppRailButton` on `preferences.{get,update}()`; `reason` on
  `metrics.get_status()`.
- `tests/live/`: an opt-in smoke suite (`TERMIX_LIVE=1`) that runs the
  sync and async clients against a real Termix instance, plus
  `docker/live/compose.yml` to bring one up and a weekly
  `.github/workflows/live.yml` that runs it outside of PR checks.
  `docker/live/compose.yml`'s own default is pinned to the release
  `SPEC_VERSION` was generated from, not `:latest`, so a local run tests
  the release the spec documents; `live.yml` still tracks `:latest` on
  its own, so the weekly run keeps finding upstream breaks early (see
  the version-check fix below).

### Changed

Breaking, all of them following a 2.8.0 handler change:

- `users.setup_totp()` now takes a `credential` body field and returns
  the base `TermixObject` instead of `UsersSetupTotpResult`, which is
  gone: the route answers with one of two shapes in 2.8.0, so `qr_code`
  and `secret` are no longer statically typed attributes.
- `file_manager.create_folder()` returns `TermixObject` instead of
  `FileManagerCreateFolderResult`, which is gone, for the same reason.
- `guacamole.connect_host()` now returns `termixConnectId`, and its
  `guacamoleConnectionId` is `null` until the WebSocket handshake
  finishes — read it from the new `guacamole.get_connection()` instead.
- `hosts.quick_connect()`: `authType` is now a `Literal` union of the
  nine accepted values, and `password`, `keyPassword`, `keyType` and
  `overrideCredentialUsername` lost their `| None` (the 2.8.0 handler
  types them as non-nullable); `key` is now `Any`.
- `rbac.set_host_access_auth()`'s `credentialId` is now `Any` rather
  than `float`, and `sync.pull()`'s `rows` is `list[Any]` rather than
  `list[dict[str, Any]]` — in both cases 2.8.0 dropped the signal the
  spec generator was reading the type from.

### Fixed

- `snippets.update()` accepted no body fields, so a snippet could not
  actually be updated through the SDK. The spec generator only found a
  request body when the handler named its fields (destructuring or
  `req.body.x`); `PUT /snippets/{id}` assigns `req.body` to a variable
  and forwards it whole, so the operation reached the spec with no
  `requestBody`. The generator now also reads the type of the parameter
  the body is forwarded into, which gives the route its real fields
  (`name`, `content`, `description`, `folder`, `order`, `hostFilter`,
  `isNote`).
- `ai.update_provider()` gained the `providerType` field, from the same
  fix — it was previously typed from the frontend client, which does not
  send that field.
- `database.import_data()` now takes the SQLite file it exists to
  upload. A `multipart/form-data` route whose handler reads only
  `req.file` (no text field beside it) was being emitted with no request
  body at all, so the generated method sent an empty POST.
- `POST /users/oidc/backchannel-logout`'s `logout_token` field is now in
  the spec: a body read through a parenthesized cast
  (`(req.body as Record<string, unknown> | undefined)?.logout_token`) was
  invisible to the extractor.
- The live suite's version check read the `version` field of
  `GET /version`, which is the newest release *GitHub* knows about, not
  the instance's own. It therefore compared `SPEC_VERSION` against
  upstream's latest release instead of against the instance under test:
  it stayed quiet for an outdated instance and warned for an up-to-date
  one. It now reads `localVersion`.
- `tools/sdk-gen/generate.py` emitted an operation's `summary` as the
  first docstring line without wrapping it, so a summary long enough to
  push that line past 100 columns failed the generator's own
  `ruff check` step. 2.8.0's `PATCH /users/step-ca-settings` is the
  first one that does.
- `user_admin.delete_user()` accepted no parameters at all, so there was
  no way to tell it which user to delete. The generator only ever
  analyzed a request body for `POST`/`PUT`/`PATCH` handlers, on the
  (until now, unchallenged) assumption that `DELETE` never carries one —
  so every `DELETE` route reached the spec with no `requestBody`
  regardless of what its handler actually read off `req.body`. It now
  also analyzes `DELETE` handlers, which gives `delete_user()` its real
  `username` (required) and `successorUserId` fields and surfaces eight
  other previously-undocumented `DELETE` bodies: `alerts.clear_dismissed()`,
  `hosts.disable_autostart()`, `hosts.clear_command_history()`,
  `host_file_manager.{clear_recent,remove_pinned,remove_shortcut}()`,
  `users.delete_account()` and `file_manager.delete_item()`.
- `rbac.share_host()`, `rbac.share_credential()`, `rbac.share_folder()`
  and `rbac.share_snippet_folder()` were missing `targets`, the field
  that actually names who a share goes to — the real endpoint rejects a
  call without it (`targets must be a non-empty array of { type: 'user'
  |'role', id } entries`), so all four methods were unusable for their
  documented purpose. The backend handlers read it via a shared
  `parseShareTargets(req.body ?? {})` helper that plucks `body.targets`
  out from inside its own function body rather than the handler
  destructuring or `.`-accessing it directly, which the spec generator's
  request-body walk didn't follow into. It now also types a field from a
  forwarded-body helper's own return type when that helper reads exactly
  one property off its parameter, and a frontend-typed field the backend
  walk missed entirely (not just one it found as `unknown`) is now
  merged in from the frontend cross-check too — which is what caught the
  same bug in `fleets.share()`, fixed the same way here.
- `audit.export()`, `termix_id.get_public_ca()` and `database.export()`
  silently returned `None` instead of the real CSV/NDJSON, SSH-CA-key or
  SQLite bytes: `tools/spec-gen` had no way to record a response whose
  body comes from `res.write()`/`.end()` or `<stream>.pipe(res)` rather
  than a single `res.json()`/`res.send()` call, so these three operations
  reached the spec with either no response body documented at all, or
  (`get_public_ca`) the wrong content type (`text/html`, from a
  `.send()`-with-a-string-implies-HTML heuristic that didn't account for
  an explicit `res.setHeader("Content-Type", ...)` earlier in the same
  handler). `tools/sdk-gen/generate.py`'s `Operation.is_octet_stream` is
  now spec-driven — any 2xx response with a non-JSON content type routes
  to `_request_stream()`, not just a literal `application/octet-stream`
  match — so a future non-JSON operation is covered without another
  change here. Also fixed along the way: `POST /fleets/{id}/transfer/pull`
  now documents its real `application/zip` content type instead of a
  guessed `application/octet-stream`, and `GET /termix-id/u/{handle}`
  and `GET /termix-id/u/{handle}/{algo}` now correctly document
  `text/html`/`text/plain` instead of `application/octet-stream` (both
  were already generated as `TermixStreamResponse`, and still are — this
  only fixes what the spec says they send). Confirmed against a real
  Termix 2.8.0 instance; `tests/contract/` regenerated to match.

## [0.1.1] - 2026-09-21

### Fixed

- `TermixClient.login()`, `AsyncTermixClient.login()` and
  `PendingTOTP.verify()` returned a client with no resource attributes:
  `client.users`, `client.hosts` and every other resource raised
  `AttributeError`, so a JWT-authenticated client could only be used
  through the low-level `request()` escape hatch. Found while probing a
  real Termix instance for the live smoke suite.

## [0.1.0] - 2026-09-19

First release. Generated against Termix `release-2.7.1-tag`.

### Added

- `TermixClient` / `AsyncTermixClient`: connection options (`base_url`,
  per-service `service_urls` override, `api_key` or `jwt`, timeout,
  retries), a low-level `request()` escape hatch, and context-manager
  support.
- `TermixClient.login()` / `AsyncTermixClient.login()`: username/password
  login handling Termix's native-app-header requirement for getting a
  usable JWT back, including the TOTP second-factor flow
  (`PendingTOTP`/`AsyncPendingTOTP`).
- A typed exception hierarchy (`TermixError` and subclasses —
  `AuthenticationError`, `PermissionError`, `NotFoundError`,
  `RateLimitError` with `remaining_time`, `DataLockedError`,
  `TOTPRequiredError`, `SessionExpiredError`, `InvalidRequestError`,
  `ServerError`) mapped from Termix's actual error response shapes.
- `TermixObject`: dict-backed base model with attribute access,
  `to_dict()`, and secret redaction in `repr()`/logs.
- 477 of 491 real Termix endpoints, generated across 43 resource
  modules (`client.hosts`, `client.credentials`, `client.file_manager`,
  `client.metrics`, ... — see `tools/sdk-gen/config/resource-map.json`
  for the full list), each with a sync and an async client.
- `ssh_session()` / `async_ssh_session()`: connect/keepalive/disconnect
  lifecycle helper for the SSH-backed session pattern `file_manager` and
  `docker` share.
- SSE support (`iter_sse_events`/`aiter_sse_events`, `SSEEvent`) for the
  3 `text/event-stream` endpoints (tunnel status, Proxmox discovery, AI
  chat streaming).
- Real multipart file upload (`fleets.transfer_push`) where a field has
  no JSON equivalent.
- `tools/sdk-gen/generate.py`: the OpenAPI-spec-to-Python-client
  generator, plus `tests/contract/`, one generated test per operation.
- `py.typed` marker, so mypy/pyright pick up the package's inline types.

### Fixed

- `ssh_session()`/`async_ssh_session()` now type-check when passed a
  generated service (`client.file_manager`, `client.docker`): the
  session protocol accepted only `**params: Any` methods, which the
  generated `Unpack[TypedDict]` signatures don't satisfy.

### Known gaps

- 3 `file_manager` endpoints (`uploadFileStream`, `downloadFileStream`,
  `uploadFileChunk`) send/receive a raw body the spec has no documented
  schema for — not generated, to avoid inventing behavior the source
  doesn't support.
- 11 endpoints are out of scope by design: internal-auth-only routes,
  browser-redirect OIDC/opkssh flows, and `POST /users/login` /
  `POST /users/totp/verify-login` (handled by `TermixClient.login()`
  instead).
- No live-instance test suite yet (`tests/` and `tests/contract/` run
  against a scripted fake transport only) — see CONTRIBUTING.md's
  testing-philosophy section.
