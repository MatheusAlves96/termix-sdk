# termix-sdk spec-gen report

Generated from tag `release-2.7.1-tag` (commit `76fd9eedbf0f7e853d5ffe40717cac126ffe6a98`) on 2026-09-18T21:23:15.389Z.

## Route counts

- Total route registrations: **494** (3 of which are `X.use()` method catch-alls, listed under `x-any-method-routes` instead of `paths`)
- Unresolved routes (origin never reached an express() app): **0**

| Service | Port | Routes | Global auth |
|---|---|---|---|
| database | 30001 | 343 | no (per-route) |
| tunnel | 30003 | 6 | no (per-route) |
| file-manager | 30004 | 40 | yes (from line 133) |
| metrics | 30005 | 58 | yes (from line 1047) |
| dashboard | 30006 | 8 | yes (from line 38) |
| docker | 30007 | 17 | yes (from line 36) |
| tmux | 30010 | 12 | yes (from line 339) |
| homepage | 30012 | 10 | yes (from line 26) |

## Drizzle schema

- Tables: **72**
- Columns: **726**

## Handler analysis coverage

- Routes with a resolvable handler: **494/494**
- Opaque handlers (could not be statically resolved): **0**
- Routes with no documented 2xx/3xx response: **1**
- Routes whose every response is `x-confidence: unknown`: **0**

### Request body field confidence

| Confidence | Count |
|---|---|
| inferred | 374 |
| unknown | 971 |

### Response field confidence

| Confidence | Count |
|---|---|
| repository-type | 1861 |
| handler-literal | 3544 |
| inferred | 664 |
| unknown | 331 |

### Routes with no documented success response

- POST /database/export — `src/backend/database/database.ts:669`

## Test suite examples (Phase 6)

- Examples mined: **90**, covering **29** route(s) from **7** test file(s).

## Frontend client cross-check (Phase 7)

- Frontend calls matched to a route: **380**, covering **354** route(s).
- Responses where the frontend's return type filled a gap the backend analysis left `unknown`: **6**
- Frontend/backend request-body field mismatches worth a look: **3**
  - PUT /host-sidebar/preferences (`src/ui/api/host-sidebar-preferences-api.ts:24`, saveHostSidebarPreferences) — frontend body type has 3 field(s) not seen in the backend's own destructuring: version, groupKey, openFolders
  - PUT /user-preferences (`src/ui/api/open-tabs-api.ts:156`, saveUserPreferences) — frontend body type has 5 field(s) not seen in the backend's own destructuring: showHostTags, hostTrayOnClick, foldersCollapsed, compactHostView, statusColorScheme
  - POST /ssh/tunnel/connect (`src/ui/api/tunnel-api.ts:171`, connectTunnel) — frontend body type has 28 field(s) not seen in the backend's own destructuring: scope, mode, tunnelType, bindHost, targetHost, hostName, sourceIP, sourceSSHPort

## Existing @openapi text reuse (Phase 8)

- `@openapi` JSDoc blocks parsed: **425**. Their `summary`/`description`/`tags`/parameter descriptions are reused verbatim when present; `requestBody`/`responses` from them are never used as a schema source.

## Diff against the official spec (Phase 10, criterion 4)

Official spec regenerated with `npm run generate:openapi` (Termix's own release process) rather than scraped from the docs site — see `official-diff.ts` for why.

- Official operations: **413**
- Our operations: **512**
- Matched: **410**
- Only in the official spec (we should have these too — worth investigating each one): **3**
  - DELETE /host/opkssh/token/{hostId}
  - GET /automations/runs
  - GET /host/opkssh/token/{hostId}
- Only in ours (the known coverage gap — real endpoints the official spec never documented): **102**

## OpenAPI lint (@redocly/cli)

- Errors: **0**
- Warnings: **723**
- Ignored: **0**

Spec is structurally valid OpenAPI 3.1.
