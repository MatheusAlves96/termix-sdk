# Contributing

## Setup

```bash
git clone https://github.com/MatheusAlves96/termix-sdk.git
cd termix-sdk
uv sync --extra dev      # creates .venv from uv.lock (pinned tool versions)
```

Without [uv](https://docs.astral.sh/uv/): `python -m venv .venv`, activate
it, `pip install -e ".[dev]"`. You then get whatever `ruff`/`mypy`/`pytest`
versions resolve today rather than the locked ones CI uses, so a check may
pass locally and fail in CI (or the reverse) — the lockfile exists to avoid
exactly that.

## Running the checks

```bash
uv run pytest            # tests/ (unit) + tests/contract/ (generated)
uv run ruff check .
uv run ruff format --check .
uv run mypy              # src/ and examples/
```

`tests/live/` is skipped unless you opt in — see "Live smoke" below.

## What CI checks

`.github/workflows/ci.yml` runs on every push to `main` and every PR:

| Job | What it does |
|-----|--------------|
| `lint` | `ruff check`, `ruff format --check`, `mypy` (Python 3.13) |
| `test (3.10..3.13)` | `pytest` with coverage; the 3.13 run uploads to Codecov (informational, never blocks) |
| `generated-sync` | runs `tools/sdk-gen/generate.py` and fails if any committed file changes — hand-edits to `resources/`, `models/`, `types/` or `tests/contract/` are caught here |
| `spec-gen-typecheck` | `npm ci && npm run typecheck` in `tools/spec-gen` |
| `build` | `uv build`, `twine check`, installs the wheel into a clean venv, imports it and checks `py.typed` is shipped; uploads `dist/` |

`uv.lock` is enforced (`UV_LOCKED=1`): if you change `pyproject.toml`
dependencies, run `uv lock` and commit the lockfile, or CI fails at
`uv sync`.

`.github/workflows/live.yml` is the one workflow that never runs on a
PR — see "Live smoke" below.

`.github/workflows/zizmor.yml` lints the workflows themselves for
security issues (unpinned actions, template injection, leaked
credentials). Actions are pinned by commit SHA; Dependabot
(`.github/dependabot.yml`) opens weekly PRs to bump them, plus Python
and `tools/spec-gen` npm dependencies.

## Vulnerability scanning

`.github/workflows/osv-scanner.yml` runs [OSV-Scanner](https://google.github.io/osv-scanner/)
over `uv.lock` and `tools/spec-gen/package-lock.json` against the OSV
database (PyPA, GitHub and npm advisories in one place):

- on a PR it reports only vulnerabilities the PR introduces and fails
  if there are any;
- on push to `main` and weekly it does a full scan, fails on any known
  vulnerability and uploads the results to Security > Code scanning.

Dependabot alerts and security updates are enabled on the repository,
so a newly published advisory for a dependency shows up as an alert
and, when a fixed version exists, as a Dependabot PR. To check locally:

```bash
uvx osv-scanner -r .
```

## Releasing

Publishing is driven by a `vX.Y.Z` tag (`.github/workflows/release.yml`)
and goes to PyPI through Trusted Publishing — no API token lives in the
repo. The `pypi` GitHub environment requires a manual approval before
the publish step runs.

1. Bump `__version__` in `src/termix_sdk/_version.py`.
2. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`
   and add a fresh empty `## [Unreleased]` above it. The release notes on
   GitHub are that section, verbatim.
3. Open a PR with those two changes and merge it.
4. `git tag vX.Y.Z main && git push origin vX.Y.Z`.
5. The `preflight` job checks the tag matches `__version__` and that the
   CHANGELOG section exists, then the full CI runs again against the tag.
6. Approve the `pypi` environment deployment in the Actions UI. The
   workflow publishes to PyPI and creates the GitHub Release with
   `dist/` attached.

## How this repo is put together

Three layers, in dependency order:

1. **`tools/spec-gen/`** (TypeScript) — mines the Termix backend source
   for every route, its auth, its request/response shape, and the
   Drizzle schema, and emits `spec/termix-openapi.json`. See
   [its own strategy doc](tools/spec-gen/docs/spec-generation-strategy.md)
   for why this exists instead of trusting Termix's own `openapi.json`.
   Not something you normally need to touch or re-run — only when
   targeting a new Termix release (see below).

2. **`tools/sdk-gen/generate.py`** (Python) — reads `spec/termix-
   openapi.json` plus the curated `tools/sdk-gen/config/resource-map.json`
   (which operations exist, what Python method name and module each
   gets — the spec alone doesn't have good naming) and writes
   `src/termix_sdk/resources/*.py`, `models/*.py`, `types/*.py`, and
   `tests/contract/test_*.py`. **Never hand-edit any of those** — the
   next `python tools/sdk-gen/generate.py` run overwrites them.

3. **Hand-written core** (`src/termix_sdk/_*.py`) — the client,
   requestor, error hierarchy, object model, session helper, SSE/stream
   parsing. This is what the generated code in (2) is built on top of,
   and most of it is adapted from
   [stripe-python](https://github.com/stripe/stripe-python) (see
   [NOTICE](NOTICE)) rather than written from scratch.

## Adding or fixing a generated operation

1. Confirm the operation exists in `spec/termix-openapi.json` (search by
   path). If it's missing entirely, that's a `tools/spec-gen` gap, not
   an `sdk-gen` one.
2. Add (or fix) its entry in `tools/sdk-gen/config/resource-map.json`,
   under the right module. An empty `{}` takes the default name from
   `generate.py`'s `default_method_name()`; most operations need an
   explicit `"method"` override — the default rule only really fits
   plain CRUD on a bare `{id}`.
3. Run `python tools/sdk-gen/generate.py`. It also runs `ruff format` +
   `ruff check --fix` on everything it just wrote, and fails loudly (not
   silently) on:
   - a method name that collides with another in the same module
     (`ruff`'s `F811`, at the `ruff check --fix` step)
   - a method name that's a Python keyword (raised directly)
   - a `resource-map.json` entry naming an `operationId` the spec
     doesn't have (raised directly)
4. Run `uv run pytest`, `uv run mypy`, `uv run ruff check .` — same as CI.
   Commit the regenerated files: the `generated-sync` CI job regenerates
   and fails on any diff.
5. A field typed `Dict[str, Any]`/`List[...]` (or a list of a generated
   model) is, at runtime, wrapped as a nested `TermixObject`/list of
   `TermixObject` regardless of that static annotation — compare via
   `.to_dict()` in any test you hand-write against generated code, not
   field-by-field attribute equality against a plain dict/list literal.

`tools/sdk-gen/generate.py`'s own module docstring lists the known
simplifications this makes (every request-body field optional in the
generated `TypedDict` regardless of the spec's `required` list, no
per-operation `x-requires-admin`/`x-requires-data-access` docstring
callouts, etc.) — read it before making a structural change to the
generator itself.

## Regenerating against a new Termix release

```bash
cd tools/spec-gen
npm ci
npm run generate -- --tag <release-tag>   # or --tag latest
cd ../..
python tools/sdk-gen/generate.py
pytest
```

Diff the new `spec/termix-openapi.json` against the previous one for new
or removed operations before touching `resource-map.json` — `sdk-gen`
only processes what the map lists, so a brand-new endpoint won't appear
in the SDK until it's added there.

## Testing philosophy

`tests/` (hand-written) and `tests/contract/` (generated, one test per
operation) both run against a scripted fake transport
(`tests/http_client_mock.py`) — nothing here talks to a real Termix
instance. That's a deliberate scope decision, not an oversight: broad
live-instance coverage would need real SSH hosts, Docker containers, and
tmux sessions to test against, plus care around endpoints with real
side effects (`database/export`, `encryption/regenerate-jwt`,
`delete-account`, fleet actions across real hosts) that shouldn't run
unattended in CI.

`tests/live/` is the narrow exception: a smoke suite against a real
Termix instance, covering authentication, the central read/write
endpoints and the error mapping — not per-operation coverage.

## Live smoke

```bash
docker compose -f docker/live/compose.yml up -d --wait
```

```bash
TERMIX_LIVE=1 TERMIX_BASE_URL=http://localhost:8080 TERMIX_LIVE_PASSWORD='Live-Smoke-Aa1' uv run pytest tests/live -q
```

Without those three environment variables the whole directory is skipped
at collection, so a plain `uv run pytest` still runs only the mocked
suites (one reported skip, which is the gate).

What it covers, in sync and async: `health`; `version` (warns when the
instance is newer than the `SPEC_VERSION` the SDK was generated from);
`users.get_me()`; hosts create/retrieve/update/list/delete; snippets
create/retrieve/update/list/delete; the bootstrap API key showing up in
`api_keys.list()`; `NotFoundError` on an unknown id; `AuthenticationError`
on a bad API key; and that `login()` returns a client whose resources
actually work.

The suite registers its own `ci` user on the empty instance (the first
account created is the admin, which is what lets it mint an API key),
authenticates with that key, prefixes everything it creates with
`live-smoke-<hex>` and deletes it again on teardown.

`docker/live/compose.yml`'s own default is pinned to the release
`SPEC_VERSION` was generated from (`ghcr.io/lukegus/termix:2.7.1`, for
`release-2.7.1-tag`), not `:latest` — a floating tag would run the local
smoke against whatever Termix shipped most recently, silently testing a
release the spec doesn't describe. Bump it alongside `SPEC_VERSION` when
the spec is regenerated (`docs/sdk-plan.md` section 9). Override it with
`TERMIX_IMAGE=ghcr.io/lukegus/termix:<tag> docker compose -f
docker/live/compose.yml up -d --wait` to test a different release
locally.

`.github/workflows/live.yml` does not read that default: it sets
`TERMIX_IMAGE` itself and runs weekly and on `workflow_dispatch` against
`ghcr.io/lukegus/termix:latest` (or the tag a dispatch input names). That
one stays on `:latest` on purpose — it has no `pull_request` trigger, so
a Termix that is down, or an upstream release that changes a response
shape, can never block a merge, and the weekly run is what finds that
break before a user does. A failed scheduled run opens (or comments on)
an issue labelled `live-smoke`.
