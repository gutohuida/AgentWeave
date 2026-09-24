# Design — the Codex models offered are the ones its CLI lists

**Built on the recommended answer to D2 (first question): read the CLI's cache at runtime, with
the literal as the fallback.** If the operator answers *"regenerate the literal at release"*
instead, withdraw this change and open a smaller one. It would add a `--write` mode to
`scripts/check_model_catalog.py` that rewrites the Codex tuple from the cache, plus a release-
checklist step that runs it. F174's current shape (a literal that is wrong for one of two client
versions) would then stay open by design and be recorded as accepted.

## The options for D2 (source), with evidence

| Option | What it releases | What it breaks or costs |
|---|---|---|
| **A. Literal + check script (today, R-3.4)** | Nothing to build | Wrong for at least one client version at any time (proposal's measurement). Every fix is an edit plus a release. The check is red today *by design*, because the catalog deliberately declares ahead of the installed CLI, so a red check no longer tells anyone to act |
| **B. Regenerate the literal at release** | CI stays independent of the machine | Correct only for the client version on the machine that ran the release. It needs someone to run the Codex CLI first to refresh the cache, and **Codex is undrivable here** (2026-08-29), so the cache refreshes only when someone runs `codex debug models` by hand. It freezes between releases, and the operator's `:8000` runs this checkout, so its "release" is whatever was last committed |
| **C. Read at runtime, literal as fallback (recommended)** | Correct for exactly the CLI the Hub spawns, which is the cache's owner. No maintenance for a provider nobody here drives. The docstring's stated source finally becomes the actual one | The list becomes per-machine, so the test suite must pin it (D4). A stale cache is only as stale as the last CLI run, but that is the CLI's own view, which is what it will accept. Docker without a Codex home falls back (D2) |

**Why Codex being undrivable argues for C, not against it.** Under A and B, someone must notice a
drift and act on it. On this machine nobody will ever notice, because nobody runs Codex. Under C,
the Hub follows the CLI with no human in the loop. And the part C needs verified (read a file,
offer its list, refuse the rest) is checkable without spawning Codex at all.

## D1 — the effective Codex descriptor

`model_catalog._codex_models_from_cache() -> Optional[CacheReading]`:

1. Path: `Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "models_cache.json"`,
   through a module-level `_codex_cache_path()` so tests can pin it.
2. Memoised on `(path, st_mtime_ns)`. A changed file is re-read on the next call. An absent file
   costs one `stat`.
3. Read with `encoding="utf-8"` **explicitly**. The real cache on this machine contains bytes that
   the Windows default codec cannot decode. Measured while writing this change: `json.load(open(p))`
   raised `UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d in position 11902`. A reader
   using the default encoding would *always* fall back on this machine and look correct in CI.
4. Keep `models[*]` whose `visibility == "list"` and whose `slug` is a non-empty string. Sort by
   `priority` ascending (a missing priority sorts last, and ties keep file order).
   `ModelDescriptor(id=slug, label=display_name or slug, context_window=int(context_window) or None,
   default=(first))`.
5. Any exception, a non-object document, a missing `models` list, or zero listed models gives
   `None` plus a reason string. It **never raises**.

`_effective_catalog()` returns `CATALOG` with the `codex` entry's `models` replaced when a reading
exists, and with `controls` untouched. `providers()`, `get_provider()`, `context_window_for_model()`
and `permission_mode_values()` read it instead of `CATALOG`. `CATALOG` stays importable as the
fallback, and `scripts/check_model_catalog.py` keeps loading it by path.

## D2 — `source`

`ProviderDescriptorResponse.source: {kind: "cli_cache" | "built_in", fetched_at?: str,
client_version?: str, reason?: str}`. Claude is always `built_in` with no reason. Codex is
`cli_cache` with the cache's own `fetched_at` and `client_version`, or `built_in` with the reason
(`no Codex model cache at <path>`, `Codex model cache unreadable: <exception class>`, or
`Codex model cache lists no models`).

The runner form shows it under the Codex model select, in one line: *"As listed by your installed
Codex CLI (0.146.0, fetched 23 Sep)"*, or *"Built-in list: no Codex model cache at …"*.

## D3 — what does not move

- Controls, including the effort values. See the proposal.
- `check_model_catalog.py`'s exit codes. Its docstring gains one paragraph saying the literal is
  now the fallback, so a drift means *"the fallback is stale"*, not *"the Hub offers the wrong
  list"*.
- Stored runners. A runner on `gpt-6-sol` on a 0.146.0 machine is kept, readable, and marked
  unrecognised (`runner-registry`, *"Existing runners keep working"*).

## D3a — whose cache it is (R2)

- **Docker.** The image is `python:3.11-slim` with only the Hub installed (`hub/Dockerfile`); it
  ships no Codex CLI, and `docker-compose.yml` mounts no Codex home and sets no `CODEX_HOME`. So a
  Docker Hub reads `/root/.codex/models_cache.json`, finds nothing, and answers `built_in` with
  *"no Codex model cache at /root/.codex/models_cache.json"*. That is the right answer there: no
  Codex CLI in the container means no list the Hub could follow. An operator who mounts a Codex home
  and sets `CODEX_HOME` gets the runtime read with no further change.
- **An agent's own `CODEX_HOME`.** An agent's `config.env_vars` is merged into its spawn
  environment (`launchability.resolve_agent_env`, `launchability.py:143-175`), and the rollout
  reader already honours a per-run `CODEX_HOME` (`agent_trigger.py:2380`). The catalog is per Hub,
  not per agent: it reads the Hub process's `CODEX_HOME`. An agent pointed at another Codex home
  may be offered a list its CLI was not sent. This is a known limit, stated in the docstring
  rewrite (task 2.1), not a reason to make the catalog per agent.

## D4 — the test suite must not read the developer's cache

An autouse fixture in `hub/tests/conftest.py` monkeypatches `model_catalog._codex_cache_path` to a
path under `tmp_path` that does not exist, so every test sees the literal unless it writes a cache
of its own. **This is the same trap as the `claude`-on-PATH memory** (the local suite green for a
machine-specific reason): without the fixture, the suite on this machine would assert against a
0.146.0 cache and in CI against the literal.

## What each route returns when what it calls raises

- `GET /model-catalog`: the reader never raises (D1.5), so the route answers 200 with `built_in` and
  a reason. A test pins this with a cache file that is a JSON array.
- `POST/PATCH /runners`, `POST /agents`, `POST /agent/trigger` overrides: they reach the reader
  through `get_provider`, so they get the same guarantee. A malformed cache means literal
  validation, never a 500.
- `stat` raising `PermissionError` is inside the same guard.

## Tests that can fail

New file `hub/tests/test_codex_models_from_the_cli_cache.py`. Build caches with the shape
`tests/test_model_catalog_drift.py:74-94` writes, plus `priority`.

1. A cache listing `m-b` (priority 2), `m-a` (priority 1) and a hidden `m-h` (priority 0, the
   lowest, as `gpt-reserve` is in the real cache) gives
   `get_provider("codex").models` ids `["m-a", "m-b"]`, `m-a` as the default, and the cache's labels
   and windows. **Fails today** (the literal). **Fails if the sort is dropped**, because the file
   order is `m-b` first.
2. No cache gives exactly the literal's ids, and `source.kind == "built_in"` with a reason naming the
   path.
3. A cache whose `description` field contains `”` (U+201D, UTF-8 `E2 80 9D`) is read. This is the
   reading this machine's real cache needs. On Windows it fails if the reader opens without
   `encoding="utf-8"`. On Linux CI the default is UTF-8, so the assertion is recorded as
   Windows-meaningful in the test's docstring.
4. A JSON array, `{}`, and a cache with zero listed models each fall back, each with its own
   reason.
5. Rewrite the cache (a new mtime) and the next `get_provider` reflects it with no reload.
6. Through the route: with a cache listing only `m-a`, `POST /runners {"cli":"codex","model":"m-a"}`
   is 201, and `{"model":"gpt-6-sol"}` (literal-only) is 400. **Both fail today.**
7. `GET /model-catalog` gives `providers[1].source.kind == "cli_cache"`, with `client_version`
   echoed. Models are in priority order, which the route returns unchanged (the test asserts the
   list, so reversing the sort fails it).
8. The conftest guard: with no per-test cache, `[m.id for m in get_provider("codex").models] ==
   [m.id for m in CATALOG["codex"].models]`. On this machine this fails if the fixture is removed.
9. UI: the runner form test with `GET /model-catalog` carrying each `source` kind renders the right
   line.

## Round log

- R1 (2026-09-24): written.
- R2 (2026-09-24): re-measured the real cache, `mode` read-only, `encoding="utf-8"`: a dict with
  `fetched_at` (2026-09-23T10:10:51Z), `etag`, `client_version` 0.146.0 and five `models`; three
  have `visibility: "list"` (`gpt-5.6-terra` p7, `gpt-5.6-luna` p8, `gpt-5.5` p12), two `hide`
  (`gpt-reserve` p3, `codex-auto-review` p43). So the priority sort must run *after* the
  visibility filter, or a hidden p3 model would be first and become the default; test 1 already
  includes a hidden model and now gives it the lowest priority to pin this. `CATALOG` has exactly
  the four readers D1 names (`model_catalog.py:280, 284, 330, 358`); `:296` uses it only for
  provider names. Added D3a (Docker ships no Codex CLI; the catalog is per Hub, not per agent).
