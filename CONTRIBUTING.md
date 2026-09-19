# Contributing

## Setup

```bash
git clone https://github.com/MatheusAlves96/termix-sdk.git
cd termix-sdk
python -m venv .venv
. .venv/Scripts/activate   # or: source .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest              # tests/ (unit) + tests/contract/ (generated)
ruff check .
ruff format --check .
mypy
```

All four run in CI on every push/PR (`.github/workflows/ci.yml`), across
Python 3.10–3.13.

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
4. Run `pytest`, `mypy`, `ruff check .` — same as CI.
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
unattended in CI. If you want to exercise the SDK against a real
instance, do so manually — there's no `tests/live/` yet.
