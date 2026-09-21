# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- `TermixClient.login()`, `AsyncTermixClient.login()` and
  `PendingTOTP.verify()` returned a client with no resource attributes:
  `client.users`, `client.hosts` and every other resource raised
  `AttributeError`, so a JWT-authenticated client could only be used
  through the low-level `request()` escape hatch. Found by the new live
  smoke suite against a real Termix instance.

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
