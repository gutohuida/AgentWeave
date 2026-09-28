# Proposal — the Codex models offered are the ones its CLI lists

Findings: **F267 (B)** and **F174 (B, changed shape)**. Bundle B7 (models and budget), R1,
2026-09-24. Built on the recommended answer to **D2's first question** (*"read the CLI's cache at
runtime, or regenerate the literal at release?"*): **read it at runtime, and keep the literal as
the fallback.**

## Why

`model_catalog.py`'s docstring names its Codex source of truth: *"read directly from
`~/.codex/models_cache.json`, the CLI's own server-synced catalog … Only entries with
`"visibility": "list"` are included"* (`hub/hub/model_catalog.py:36-41`). But the Codex half is a
literal (`:236-247`), and nothing in the product reads that file. Every door that sets a model
refuses anything the literal does not declare (F267's four doors; `runners.py:40`, `agents.py:695`,
`validate_overrides`, `worker.py:165`). So a drift is fixed only by a Python edit and a release.

**F174 has changed shape, and the new shape is the argument.** F174's drift (`gpt-5.6-sol` as the
default, and `gpt-5.4`, both gone upstream) was repaired by hand in `b661766` and `b8d30f2` on
2026-09-23. The same edits declared `gpt-6-luna` and `gpt-6-sol`, *"from the changelog alone"*,
because CLI 0.156.1 is sent them and 0.146.0 is not (`model_catalog.py:42-53`). Measured today:

```
$ py -3.11 scripts/check_model_catalog.py
cache:   ~/.codex/models_cache.json (fetched_at=2026-09-23T10:10:51Z client_version=0.146.0, 3 listed)
2 drift(s):
  [declared but gone] 'gpt-6-luna' is offered by the catalog and not listed upstream
  [declared but gone] 'gpt-6-sol' is offered by the catalog and not listed upstream
EXIT 1
```

The server sends a different list to each client version (the docstring's own words: *"The catalog
the server sends depends on the client's version"*). So **no literal can be right for two installed
CLIs at once.** Today's literal is right for 0.156.1 and offers this machine's 0.146.0 two models
its CLI has never been told about. Before 2026-09-23 the literal was wrong for the installed CLI too (F174). The one list that is right
for the CLI the Hub will actually spawn is the cache that CLI wrote.

`R-3.4` (decided 2026-09-08) built `scripts/check_model_catalog.py` so the drift could be seen.
F267 records that this made staleness *visible*, not *fixable without a release*. This change makes
it fixable, because there is nothing left to fix by hand.

## What changes

- **The Codex models are read from the installed CLI's cache at runtime.** The cache path is
  `$CODEX_HOME/models_cache.json`, else `~/.codex/models_cache.json`, which is the same resolution
  `read_codex_rollout_accounting` uses (`runner_parsing.py:677`). The models are the entries with
  `visibility: "list"`, in the cache's `priority` order. Each takes the cache's `display_name` as
  its label and its `context_window` as its window. The first becomes the default. The read is
  memoised on the file's modification time and size, only when it succeeds, so the Codex CLI
  refreshing its cache reaches the Hub without a restart and a failed read is retried. A run on a
  model the cache no longer lists keeps the built-in list's context window for it.
- **The literal stays, as the fallback.** It is used when the cache is absent, unreadable,
  malformed, or lists no model. That covers CI, a machine without Codex, and a Docker Hub whose
  container has no Codex home. `scripts/check_model_catalog.py` keeps its job of telling whoever
  edits the fallback that it has drifted.
- **The catalog says where its list came from.** `GET /model-catalog` gives each provider a
  `source`: `cli_cache` with `fetched_at` and `client_version`, or `built_in` with the reason the
  cache was not used. The runner form shows it in one line under the Codex model select.
- **The controls stay literal.** The effort control's values are still the declared intersection
  (`model_catalog.py:55-62`). Deriving them from the cache per model is the docstring's recorded
  follow-up, and it stays one.

## What this does not claim

**Codex is undrivable on this machine** (operator decision, 2026-08-29). This change reads a file
and validates against it. It does not, and cannot here, show that a Codex *run* on a cache-listed
model succeeds. The claim is narrower and fully checkable: the Hub offers and accepts exactly what
the installed CLI lists, and offers nothing it does not.

## Capabilities

- **model-catalog**: ADDED, a provider that publishes its own catalog is described from it.

## Impact

- `hub/hub/model_catalog.py`: an effective catalog in place of direct `CATALOG` reads in
  `providers()`, `get_provider()`, `context_window_for_model()` and `permission_mode_values()`.
  All other callers already go through `get_provider` (grep: `agents.py:694`, `runners.py:39`,
  `schemas/runners.py:54`, `worker.py:164`).
- `hub/hub/schemas/model_catalog.py`: `source` on the provider response.
- `hub/tests/conftest.py`: an autouse fixture that pins the suite to the literal. Without it, this
  machine's real cache would change what ten test files assert (`gpt-6-sol` and similar appear
  in `test_worker.py`, `test_model_catalog.py`, `test_agent_trigger_overrides.py`, and others).
- `hub/ui/src/components/runners/RunnersPage.tsx`: the source line, so the UI bundle is refreshed.
- No migration. An existing runner on a model the cache does not list is kept and marked
  unrecognised, as `runner-registry` already requires (*"Existing runners keep working"*).
