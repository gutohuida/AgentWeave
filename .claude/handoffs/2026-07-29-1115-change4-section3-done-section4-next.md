# Handoff: Change 4 (add-agent-stream-kinds) — section 3 complete (16/16); section 4 (invocation lifecycle) not started

**Date:** 2026-07-29T11:15:00+01:00 · **Branch:** `master` · **HEAD:** `5ad5c9f`
**Agent:** Claude (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-07-29-1015-change4-section3-3-of-4-collectors-done.md`
**Status:** chunk complete (section 3 fully done, 16/16); section 4 (13 tasks) not started

## Goal

Implement Change 4 (`add-agent-stream-kinds`, folded with former Change 6), a 94-task plan at
`openspec/changes/add-agent-stream-kinds/tasks.md`. Sections 1 (canonical contracts) and 2
(stdout adapters) were done before the previous session. Section 3 (`Auxiliary context
collectors`, 16 tasks) is now fully done as of this session — the last two tasks (OpenCode
model-limit resolution, 3.15-3.16) were completed and committed this session. Section 4
(`Invocation lifecycle and canonical context delivery`, 13 tasks) is the next chunk: this is
where the four collectors/limit-resolvers built in section 3 (Codex, Copilot, Kimi, OpenCode)
actually get wired into the live invocation loop, replacing legacy context-writer call sites.

## Current state

**Section 3 is 16/16 complete** (previous session did 3.1-3.14 across three commits; this
session did 3.15-3.16 in one commit, `5ad5c9f`).

This session's work — OpenCode model-limit resolution (tasks 3.15-3.16):

- Confirmed via design.md decision 5 and a live-verified exploration-doc quote ("The runner's
  own model catalog supplies `limit.input` and `limit.context`; a hard-coded AgentWeave model
  table should not be the primary source") that OpenCode does **not** need a
  `RunnerUsageCollector` subclass — its usage already comes from stdout (section 2, task 2.7,
  `_opencode_usage_sample`). Only the *limit* half needed new code.
- Live-probed installed OpenCode CLI 1.18.5: confirmed `step_finish` events carry no
  provider/model identity at all (raw captured event has only `sessionID`/`messageID`, no
  `providerID`/`modelID` — see Verification below for the exact captured JSON). So the model
  string must come from outside the stream — it's the same `provider/model` string AgentWeave
  already resolves via `session.get_runner_config(agent).get("model")` and passes as
  `--model` when building the `opencode run` command (`watchdog.py` ~line 2157-2161) — no new
  resolution needed for *that* half, it already exists.
- Found and read `~/.cache/opencode/models.json` (confirmed via `opencode debug paths`
  live-checked as the CLI's own `cache` dir, and confirmed via the compiled `opencode.exe`
  binary containing the literal string `XDG_CACHE_HOME`, which it honors as an override). This
  file is the exact same data `opencode models --verbose` renders (cross-checked one entry,
  `minimax-coding-plan/MiniMax-M2`, byte-for-byte matching `limit` object) but is valid JSON on
  its own — the CLI's own `--verbose` output is NOT valid JSON as a whole (it's
  `"provider/id\n{json}\n"` repeated), so reading the cache file directly avoids fragile
  text-stream parsing.
- Implemented three new pure functions in `watchdog.py`, placed immediately before
  `_opencode_usage_sample`:
  - `_opencode_cache_dir()` — `$XDG_CACHE_HOME/opencode`, else `~/.cache/opencode`.
  - `_opencode_models_catalog(cache_dir=None)` — reads `models.json`, returns `Optional[Dict]`,
    `None` on any failure (missing file / malformed JSON / non-dict top level).
  - `_opencode_model_context_limit(catalog, model)` — takes `"providerID/modelID"` (splits on
    the *first* `/` only — confirmed live that some model IDs themselves contain `/`, e.g. the
    `anyapi` provider's `google/gemini-2.5-flash`), prefers `limit.input`, falls back to
    `limit.context`, rejects non-positive values.
- Extended `_opencode_usage_sample`'s signature with two new optional keyword params,
  `model: Optional[str] = None` and `limit_tokens: Optional[int] = None`, both passed straight
  through to the returned `ContextUsageSample`. The existing call site
  (`_parse_opencode_stdout_line`, ~line 4321) was **not** changed — it still calls
  `_opencode_usage_sample(tokens, source="opencode")` with neither param, so no live behavior
  changed this session. Wiring an actual resolved model/limit into that call site is section
  4's job (see Next steps), matching the same "collector built and tested in isolation, not
  yet wired into `_do_run_agent_subprocess`" pattern the previous session used for
  Codex/Copilot/Kimi.
- Added 17 new tests in `tests/test_watchdog.py`: `TestOpencodeModelsCatalog` (4),
  `TestOpencodeModelContextLimit` (11), `TestOpencodeUsageSampleWithLimit` (2). Inserted
  immediately before `TestPopenUsesUtf8Encoding`, matching where every other section-3 test
  class this week was inserted.

## Files touched

- `src/agentweave/watchdog.py` — added `_opencode_cache_dir`, `_opencode_models_catalog`,
  `_opencode_model_context_limit` (new, ~65 lines) immediately before `_opencode_usage_sample`;
  extended `_opencode_usage_sample`'s signature with `model`/`limit_tokens` optional params
  (backward compatible, existing call site unchanged). No other functions touched. File is
  ~4600 → ~4665 lines.
- `tests/test_watchdog.py` — added `_opencode_model_context_limit`, `_opencode_models_catalog`,
  `_opencode_usage_sample` to the top import block; added `TestOpencodeModelsCatalog`,
  `TestOpencodeModelContextLimit`, `TestOpencodeUsageSampleWithLimit` (17 tests total) directly
  before `TestPopenUsesUtf8Encoding`.
- `openspec/changes/add-agent-stream-kinds/tasks.md` — checked off 3.15 and 3.16 (section 3 is
  now fully `[x]`, 16/16).
- `.claude/handoffs/LATEST.md` — about to be rewritten by this handoff.

Nothing else changed. No design.md/spec.md edits. No Hub, CLI (`src/agentweave/cli.py`), or
other source files touched.

## Key decisions

- **OpenCode does not get a `RunnerUsageCollector` subclass**, unlike Codex/Copilot/Kimi.
  Design.md decision 5 states OpenCode stays "stdout-native" for usage; only the *limit* needed
  external resolution, and that's a plain value (a `provider/model` string AgentWeave already
  knows before spawn) fed through a pure lookup function — there's no per-invocation state to
  manage across `setup`/`bind`/`observe`/`close` the way Copilot's OTel file or Kimi's Wire
  path resolution needed. Confirmed against the previous handoff's own open question ("worth
  confirming against the spec before assuming one is required") — the spec confirms no
  collector needed.
- **Read `~/.cache/opencode/models.json` directly instead of shelling out to `opencode models
  --verbose`.** The CLI's `--verbose` text output is not valid JSON as a whole document (each
  model is `"provider/id\n{json}\n"`, concatenated — would need fragile line-splitting to
  parse), whereas the cache file it's rendered from is a single valid JSON document, confirmed
  byte-identical in content for at least one cross-checked model entry. This also has no
  subprocess-call overhead unlike Kimi's `kimi provider list --json` (which needed a subprocess
  because Kimi's raw source is TOML, not JSON — not the case here).
- **`_opencode_model_context_limit` splits `model` on the first `/` only, not all occurrences.**
  Confirmed live in the real catalog that model IDs can themselves contain `/` (`anyapi`
  provider's `google/gemini-2.5-flash`, `mistralai/devstral-2512`, etc. — 11+ such entries
  found). Splitting on all `/` would silently misroute the provider/model lookup for any
  AgentWeave user configured against one of those providers.
- **`_opencode_usage_sample` gained optional `model`/`limit_tokens` params rather than doing
  the catalog lookup internally.** Consistent with keeping it a pure, single-purpose token-math
  function (like Codex's `_codex_rollout_usage_sample` takes already-resolved data); the catalog
  read is comparatively expensive (3.2MB JSON file) and invocation-scoped, not
  per-`step_finish`-line scoped, so a future section-4 caller should read/resolve the limit
  once per invocation and pass the same `limit_tokens` int to every `step_finish` sample, not
  re-read the catalog file on every stdout line.

## Constraints and user directives (verbatim)

Nothing new said by the user this session (autonomous continuation from `/resume` off the
previous handoff, per that handoff's Next steps §1-3). All constraints carried forward from
the previous handoff chain remain binding:

- Kimi's session-status service (task 3.10) is intentionally **not implemented** —
  investigated live and skipped with explicit user sign-off in the previous session
  ("If there is no alternative we can skip it."). Do not silently implement it.
- New commits, not amends — this repo's default; the one prior amend was an explicit
  one-off exception, not a pattern.
- Zero new runtime dependencies (stdlib only) — this session's OpenCode work is
  `json`/`os`/`pathlib` only, no new imports beyond what was already in `watchdog.py`.
- Never commit `.agentweave/*`; use template loading not hardcoded template strings; lock
  task mutations; preserve unrelated dirty work; target Kimi v0.29.x only.
- Live CLI probes must run in isolated scratch directories outside the repo, cleaned up
  after — done this session (`opencode run` probe in the session's scratchpad dir, deleted
  after capturing the raw JSONL).
- Pushing the now-12 unpushed commits has never been asked for in this chain — still open.

## Dead ends

- None new this session. (Considered shelling out to `opencode models --verbose` and parsing
  its `"provider/id\n{json}\n"` text stream instead of reading `models.json` directly —
  rejected before writing any code once the cache file was found to be valid JSON on its own;
  not implemented, so not really a "tried and failed" dead end, just a path not taken.)

## Verification

- `.venv\Scripts\python.exe -m pytest tests\ -q`: **935 passed, 4 skipped** (918 → 935, +17,
  matching the 17 new tests added). Ran once before black reformatting and once after; both
  935 passed.
- `.venv\Scripts\python.exe -m ruff check src\ tests\` — clean, no issues.
- `.venv\Scripts\python.exe -m black --check src\ tests\` — initially flagged
  `tests\test_watchdog.py` (two multi-line `assert` statements collapsible to one line); ran
  `black src\ tests\` to auto-fix, then re-verified `--check` clean.
- `.venv\Scripts\python.exe -m mypy src\` — success, only the pre-existing
  Python-3.8-unsupported pyproject warning (unrelated, noted in every prior handoff).
- Live CLI probes, in an isolated scratch directory
  (`<scratchpad>/opencode_probe`, deleted after use, confirmed via `git status --short`
  showing no leftover):
  - `opencode --version` → `1.18.5`; `opencode models --verbose` inspected for real `limit`
    shapes (`opencode/big-pickle` has `limit.input`; `minimax-coding-plan/MiniMax-M2` has only
    `limit.context`).
  - `opencode debug paths` → confirmed `cache` dir is `C:\Users\huida\.cache\opencode` even on
    Windows (not an OS-specific convention).
  - Ran `opencode run "Reply with exactly the word: pong" --model minimax-coding-plan/MiniMax-M2
    --format json` against a real configured MiniMax provider, captured the raw 3-line JSONL
    stream (`step_start`, `text`, `step_finish`) — confirmed `step_finish.part` has no
    `providerID`/`modelID` field, only `sessionID`/`messageID`.
  - Compared `~/.cache/opencode/models.json`'s `minimax-coding-plan.models["MiniMax-M2"]` entry
    against the CLI's own `--verbose` rendering for the same model — identical `limit` object.
  - Grepped the compiled `opencode.exe` binary (`strings`-style via `grep -a`) for env-var
    names, confirming `XDG_CACHE_HOME` is a real string the binary checks.
- Committed as `5ad5c9f`.
- `openspec status --change add-agent-stream-kinds --json` was **not** re-run this session
  (tasks.md checkbox count — now 46/94 — tracked manually in the file).

Not run:

- Hub backend/UI test suites (`hub\tests`, `hub\ui`) — untouched (sections 5-8).
- Any `mkdocs build` — MkDocs not installed in this environment (noted every prior handoff).
- Section 4 integration code — deliberately out of scope this session (see Next steps).

## Git state

- Branch: `master`
- HEAD: `5ad5c9f` (message: "Resolve OpenCode context limits from its own model catalog")
- Upstream: `origin` → `https://github.com/gutohuida/AgentWeave.git`. **12 commits ahead of
  `origin/master`**, none pushed this session (11 inherited + 1 new). Oldest first:
  `97bc0c4`, `d619dbb`, `ca8abd2`, `99df59d`, `960782e`, `d70f2f0`, `76266a1`, `7b957ca`,
  `d834cb6`, `1c6970d`, `399f6c2`, `5ad5c9f` (this session's).
- Working tree: clean except `.claude/handoffs/LATEST.md` (pointer update, about to be
  rewritten by this handoff) and the six pre-existing untracked handoff files from earlier
  sessions (unrelated, already untracked before this session started).
- Not asked to push this session.

## Next steps

1. **Read `openspec/changes/add-agent-stream-kinds/design.md` decisions 1, 6, and 7 in full**
   before starting section 4 — only decisions 1 and 5 have been read across this and the
   previous session. Decision 1 ("Coordinate two producers at the invocation boundary") is
   referenced by `RunnerUsageCollector`'s own docstring (`watchdog.py` ~line 53) but its full
   text in design.md has not been re-read recently; decisions 6 ("Separate run identity from
   session identity") and 7 ("Normalize storage and transport once") are directly relevant to
   tasks 4.1-4.2 and have not been read at all yet this chain.
2. **Read section 4's 13 tasks in full**
   (`openspec/changes/add-agent-stream-kinds/tasks.md` lines 95-120): 4.1 (fresh `run_id` per
   invocation), 4.2 (strictly increasing stream sequence values), 4.3 (canonical lifecycle
   events), 4.4 (update the runner loop to deliver events + collector samples), 4.5 (bind
   collectors to active agent/run/session, reject mismatched/stale samples), 4.6 (reset new
   session's context to `unavailable`), 4.7 (reconstruct session binding after watchdog
   restart), 4.8 (replace legacy context writers with one atomic canonical snapshot — this is
   where `CodexRolloutCollector`/`CopilotOtelCollector`/`KimiWireCollector`/the new OpenCode
   limit functions actually get called), 4.9-4.10 (legacy reader compatibility), 4.11-4.12
   (transport), 4.13 (watchdog tests).
3. **Find the current legacy call sites to replace**, referenced in the previous handoff as
   `_write_context_usage`/`_write_codex_context_usage`/`_write_context_usage_from_wire` around
   `watchdog.py` lines ~3430-3465 as of two sessions ago — re-grep, line numbers have shifted
   twice since (file is now ~4665 lines, was ~3946 at the start of the previous session).
4. This is a substantially bigger, more structural chunk than section 3 was (touches the
   invocation loop itself, `run_id` generation, sequence numbering, session-restart handling —
   not just new leaf functions). Consider proposing a sub-chunking plan to the user before
   diving in (e.g. "4.1-4.3 first as the event/lifecycle plumbing, then 4.4-4.8 as the actual
   collector wiring, then 4.9-4.13 as compatibility/tests") rather than attempting all 13 in
   one sitting the way section 3's collectors were done one-per-commit.

## Open questions for the user

- Whether to push the now-12 unpushed commits to `origin/master` — not asked this session,
  carried forward as open from every previous handoff in this chain.
- Whether to sub-chunk section 4 (see Next steps §4) or attempt it as previous sessions did
  section 3 (one task-group per commit, continuing until natural stopping points) — not yet
  asked; worth raising at the start of the next session before committing to an approach.

## Read on resume

- `openspec/changes/add-agent-stream-kinds/tasks.md` — sections 1-3 now fully `[x]`
  (94-task plan, 46/94 done); section 4 (lines 95-120) is the next unchecked block.
- `openspec/changes/add-agent-stream-kinds/design.md` — decisions 1, 6, 7 specifically (not
  yet read this chain; directly relevant to run_id/sequencing/storage-normalization work in
  section 4), plus decision 5 (already read, describes the OpenCode/Kimi/Codex/Copilot
  collector-binding rules this session's work extends).
- `src/agentweave/watchdog.py` — specifically the legacy context-writer functions (grep for
  `_write_context_usage`, `_write_codex_context_usage`, `_write_context_usage_from_wire`) that
  section 4 task 4.8 replaces, and the main invocation loop in `_do_run_agent_subprocess` where
  `RunnerUsageCollector` instances need to actually get constructed/bound/polled for the first
  time — currently `CodexRolloutCollector`/`CopilotOtelCollector`/`KimiWireCollector` are fully
  implemented and tested but never instantiated outside tests.
- `tests/test_watchdog.py` — the four section-3 test blocks
  (`TestCodexRolloutCollector`, `TestCopilotOtelCollector`, `TestKimiWireCollector`,
  `TestOpencodeModelsCatalog`/`TestOpencodeModelContextLimit`/`TestOpencodeUsageSampleWithLimit`)
  as the established per-runner test pattern; section 4's tests will look different since
  they test the invocation loop itself, not isolated pure functions.
</content>
