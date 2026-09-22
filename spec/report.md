# termix-sdk spec-gen report

Generated from tag `release-2.8.0-tag` (commit `fef8a5f28a5a6023ff10832acb65cbdfea81b777`) on 2026-09-22T07:51:18.551Z.

## Route counts

- Total route registrations: **535** (4 of which are `X.use()` method catch-alls, listed under `x-any-method-routes` instead of `paths`)
- Unresolved routes (origin never reached an express() app): **0**

| Service | Port | Routes | Global auth |
|---|---|---|---|
| database | 30001 | 383 | no (per-route) |
| tunnel | 30003 | 7 | no (per-route) |
| file-manager | 30004 | 40 | yes (from line 129) |
| metrics | 30005 | 58 | yes (from line 1112) |
| dashboard | 30006 | 8 | yes (from line 40) |
| docker | 30007 | 17 | yes (from line 31) |
| tmux | 30010 | 12 | yes (from line 341) |
| homepage | 30012 | 10 | yes (from line 29) |

## Drizzle schema

- Tables: **82**
- Columns: **817**

## Handler analysis coverage

- Routes with a resolvable handler: **535/535**
- Opaque handlers (could not be statically resolved): **0**
- Routes with no documented 2xx/3xx response: **0**
- Routes whose every response is `x-confidence: unknown`: **0**

### Request body completeness (docs/spec-generation-strategy-v2.md)

- POST/PUT/PATCH routes: **284**, of which **198** (70%) have an `application/json` body with every top-level field typed
- Routes where no body field was found at all: **41**
- Routes with a body but no `application/json` variant (e.g. streamed uploads): **3**
- Top-level `application/json` fields still `unknown`: **89**

### Request body field confidence (all nodes, all content types — includes nested fields)

| Confidence | Count |
|---|---|
| repository-type | 12 |
| handler-literal | 78 |
| frontend-type | 346 |
| matched-type | 444 |
| inferred | 711 |
| unknown | 100 |

### Response field confidence

| Confidence | Count |
|---|---|
| repository-type | 1978 |
| handler-literal | 3840 |
| inferred | 720 |
| unknown | 349 |

## Test suite examples (Phase 6)

- Examples mined: **101**, covering **31** route(s) from **8** test file(s).
- Statuses a test proved but static analysis missed: **2** (added to the OpenAPI output with `x-confidence: test`)
  - PATCH /users/branding → 401, from `src/backend/tests/database/routes/branding-routes.test.ts` ("rejects an unauthenticated request and persists nothing")
  - PATCH /users/branding → 403, from `src/backend/tests/database/routes/branding-routes.test.ts` ("rejects a non-admin request and persists nothing")

## Frontend client cross-check (Phase 7)

- Frontend calls matched to a route: **415**, covering **389** route(s).
- Responses where the frontend's return type filled a gap the backend analysis left `unknown`: **6**
- Frontend/backend request-body field mismatches worth a look: **3**
  - PUT /host-sidebar/preferences (`src/ui/api/host-sidebar-preferences-api.ts:24`, saveHostSidebarPreferences) — frontend body type has 3 field(s) not seen in the backend's own destructuring: version, groupKey, openFolders
  - PUT /user-preferences (`src/ui/api/open-tabs-api.ts:164`, saveUserPreferences) — frontend body type has 5 field(s) not seen in the backend's own destructuring: showHostTags, hostTrayOnClick, foldersCollapsed, compactHostView, statusColorScheme
  - POST /ssh/tunnel/connect (`src/ui/api/tunnel-api.ts:172`, connectTunnel) — frontend body type has 32 field(s) not seen in the backend's own destructuring: scope, mode, tunnelType, localAddress, remoteAddress, bindHost, targetHost, sourceHostSyncId

## Existing @openapi text reuse (Phase 8)

- `@openapi` JSDoc blocks parsed: **466**. Their `summary`/`description`/`tags`/parameter descriptions are reused verbatim when present; `requestBody`/`responses` from them are never used as a schema source.

## Golden route regression check (docs/spec-generation-strategy-v2.md, Passo 0)

No regressions: every field that already had a concrete type from an explicit validator (or other pre-plan signal) still has that exact type.

## Diff against the official spec (Phase 10, criterion 4)

Official spec regenerated with `npm run generate:openapi` (Termix's own release process) rather than scraped from the docs site — see `official-diff.ts` for why.

- Official operations: **454**
- Our operations: **559**
- Matched: **444**
- Only in the official spec (we should have these too — worth investigating each one): **10**
  - DELETE /host/opkssh/token/{hostId}
  - GET /automations/runs
  - GET /host/opkssh/token/{hostId}
  - GET /plugin-api/{pluginId}/{path}
  - GET /users/notification-private-endpoints
  - GET /users/secret-source-private-endpoints
  - GET /users/step-ca-private-endpoints
  - PATCH /users/notification-private-endpoints
  - PATCH /users/secret-source-private-endpoints
  - PATCH /users/step-ca-private-endpoints
- Only in ours (the known coverage gap — real endpoints the official spec never documented): **115**

## OpenAPI lint (@redocly/cli)

- Errors: **0**
- Warnings: **831**
- Ignored: **0**

Spec is structurally valid OpenAPI 3.1.
