# Handoff: Phase 4 (identity, runner capability, and surface split) complete

**Date:** 2026-08-01T20:38:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `1963c64`
**Agent:** Claude (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-08-01-1938-phase3-audit-findings-closed.md`
**Status:** chunk complete

## Goal

Ship the `hub-native-experience` OpenSpec change
(`openspec/changes/2026-07-30-hub-native-experience/`). This session executed the whole of
**Phase 4 — "Identity, runner capability, and surface split"** (tasks 4.1–4.7) in one sitting,
per the user's instruction: *"Execute full phase 4. Only stop if there is actually a blocking
issue... don't need to be conservative on the changes... if there is genuinely a best approach
you can scrap anything that already exists. Also apply these new rules when creating handoffs.
Do a little bit less handoffs then previously but still do them."* No blocking issue arose, so
the whole phase shipped in this single session with one handoff at the end (not one per task, as
prior sessions in this chain did).

## Current state

**Phase 4 is fully closed** — all 7 tasks (4.1–4.7) checked off in `tasks.md` with detailed
implementation notes on each (read those before re-deriving anything below from memory; they are
more complete than this summary). In one sentence: **agent identity is now established once, at
spawn, via a new `AW_AGENT_IDENTITY` env var — never asserted by a tool-call parameter or a CLI
flag — and the "which access path should I use" question the watchdog used to silently assume is
now actually probed.**

Concretely, three mechanisms now exist that didn't before:

1. **Identity binding.** `AW_AGENT_IDENTITY=<agent>` is set by whichever process spawns an
   agent's CLI: `agent_trigger.py`'s native-runtime spawn (also stamps `AW_RUN_ID`),
   `watchdog.py`'s ping-spawned local/git processes, `agentweave switch` (exports it for the
   claude_proxy eval path; prints a tip for other runners), and `agentweave run`. Since
   `agentweave-mcp` (the one live CLI-side MCP server — see "Important context" below) is a stdio
   subprocess spawned by the agent's own CLI, it inherits this env var automatically. The
   `send_message`/`create_task`/`ask_user`/`update_task` MCP tools and the `quick`/`msg send`/
   `delegate`/`task create`/`question ask` CLI subcommands no longer accept *any* caller-supplied
   identity parameter or flag — they read `tool_surface.bound_identity()` and refuse (return an
   error dict / exit 1) if it's unset, rather than the old `args.from_agent or "unknown"`/`"user"`
   fallback.
2. **Access-path probing.** `hub_client` in session.json is now purely an operator override
   (`"cli"`/`"mcp"`; `"auto"` is treated as unset). When unset, `tool_surface.resolve_access_path()`
   (CLI/watchdog side) and `hub.launchability.resolve_access_path()` (Hub side, independent mirror
   — see that module's existing docstring on why it never imports from the `agentweave-ai`
   package) shell out to `<cli> mcp list` for claude/claude_proxy/native/codex and check for
   `"agentweave"` in the output, cached 5 minutes per CLI binary. This closes a real, previously
   undetected defect: the old `hub_client_mode == "auto"` branch in `watchdog.py` never probed
   anything — it unconditionally assumed MCP was registered. Runners not yet probeable (kimi,
   opencode, copilot, manual) default to `"cli"` (the guaranteed-available path) rather than
   assuming an unverified server; Copilot is explicitly deferred per task 4.3's own wording.
3. **Turn-start notice.** `tool_surface.access_path_notice()` / `hub.launchability.access_path_notice()`
   produce one line telling the agent which path is in use. Prepended to every Hub-triggered run's
   initial prompt and every watchdog ping prompt — the only two places a turn currently starts.

## Files touched

- `src/agentweave/tool_surface.py` — **new file.** `bound_identity()`/`UnboundIdentityError`,
  `probe_mcp_registered()`/`resolve_access_path()`/`access_path_notice()`. Finished.
- `hub/hub/launchability.py` — added the same three access-path functions as an independent
  mirror (`PROBEABLE_RUNNERS`, `probe_mcp_registered`, `resolve_access_path`,
  `access_path_notice`); `get_agent_config()` now falls back to session.json's top-level
  `hub_client` when an agent has no per-agent override, mirroring the CLI's
  `Session.get_agent_hub_client`. Finished.
- `hub/hub/api/v1/agent_trigger.py` — `trigger_agent_directly` now resolves the access path,
  prepends `access_path_notice(...)` to the prompt *before* `build_command` is called, and injects
  `AW_AGENT_IDENTITY`/`AW_RUN_ID` into the spawn env (preserving inherited env when
  `resolve_agent_env` returned `None`, not replacing it — this was a real bug I caught and fixed
  during implementation, not a delivered defect). Finished.
- `src/agentweave/watchdog.py` — two changes: (1) `_run_cmd`'s spawn always sets
  `AW_AGENT_IDENTITY` in `proc_env`, forcing a real dict even when `_prepare_runner_env` returned
  `None`; (2) the ping-callback's prompt-selection branch (previously keyed on the literal
  `hub_client_mode == "cli"` string) now calls `resolve_access_path`/`access_path_notice`, and the
  codex/codex_mcp branch (which inlines message content instead of instructing a tool call) got
  the notice appended too, for whatever the agent does *next*. Finished.
- `src/agentweave/mcp/server.py` — `send_message`, `create_task`, `ask_user`, `update_task` lost
  their `from_agent`/`assigner`/`agent` identity parameters; each now calls `bound_identity()` and
  returns an error dict on `UnboundIdentityError`. `save_checkpoint`'s `agent` param was
  deliberately **not** touched — design.md flags its disposition as an open question for task 7.3
  (collapsing the two MCP servers), not this phase's scope. Finished.
- `src/agentweave/cli.py` — new `_require_bound_identity()` helper; `cmd_quick`, `cmd_msg_send`,
  `cmd_task_create`, `cmd_question_ask` now use it instead of a `--from-agent`/`--assigner`/`--from`
  flag (all three removed from their argparse subparsers, along with `delegate_parser`'s
  `--from-agent`); `cmd_delegate` no longer passes `from_agent` through to `cmd_quick`. `cmd_switch`
  prints `export AW_AGENT_IDENTITY=<agent>` in the claude_proxy eval branch and a one-line tip in
  every other runner branch (opencode/copilot/codex/other); `cmd_run` adds `AW_AGENT_IDENTITY` to
  the subprocess env it builds. Finished.
- `tests/test_mcp_server.py` — updated the two existing `create_task` tests that used
  `assigner=` to set `AW_AGENT_IDENTITY` via `monkeypatch.setenv` instead; added
  `test_create_task_refuses_without_bound_identity` and a new `TestBoundIdentity` class covering
  `send_message`/`ask_user`/`update_task` (attribution + refusal), plus
  `test_send_message_signature_has_no_from_agent_parameter` (proves impersonation is structurally
  impossible via `inspect.signature`, not just discouraged by docs). Finished.
- `tests/test_watchdog_session.py` — updated the codex ping test to expect the access-path notice
  appended and to monkeypatch `tool_surface.probe_mcp_registered` (avoids a real subprocess call);
  replaced the "non-codex uses inbox prompt" test with
  `test_agent_message_to_non_probeable_runner_uses_cli_prompt` — kimi is unprobeable, so it now
  correctly gets the CLI-command prompt instead of the old (buggy) unconditional
  `get_inbox()`-call prompt. Finished.
- `hub/tests/conftest.py` — new autouse fixture `_no_real_mcp_probe` that monkeypatches
  `hub.launchability.probe_mcp_registered` to `False` for every Hub test by default (deterministic,
  no real subprocess spawn of `claude`/`codex` during the suite). Finished.
- `hub/tests/test_launchability.py` — new `TestAccessPath` class (override precedence, unprobeable
  defaults to cli, "auto" treated as unset, probe result drives outcome, `probe_mcp_registered`'s
  own behavior including cache-hit correctness and exception swallowing) plus
  `test_get_agent_config_falls_back_to_session_wide_hub_client`. Finished.
- `hub/tests/test_agent_trigger.py` — two new tests:
  `test_trigger_injects_identity_env_and_tells_agent_the_access_path` (env keys + notice text in
  the actual `build_command` prompt kwarg) and
  `test_trigger_respects_explicit_mcp_override_without_probing` (override skips the probe
  entirely, not just outvotes it — asserted via a probe stub that raises if called). Finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — tasks 4.1–4.7 checked off with
  the implementation notes summarized above (more detail there than here). Finished.
- `docs/reference/mcp-tools.md`, `README.md` — updated the `send_message`/`create_task`/
  `ask_user` signatures shown in both docs to drop the removed identity parameters, with a note
  that attribution is automatic. Finished. Deliberately did **not** rewrite this doc's framing of
  "one unified MCP tool surface" — see "Important context not to lose" below; that's a separate,
  larger doc problem this session didn't cause and didn't have scope to fix.

All committed in `1963c64 Phase 4: identity binding and access-path resolution
(hub-native-experience)`.

## Key decisions

1. **Env var over a per-run Hub-issued bearer token.** Considered minting a `Run.token` /
   `aw_run_...` credential and a new REST auth dependency so the Hub REST layer itself could
   verify identity server-side. Rejected: the actual attack surface this closes is a
   prompt-injected *LLM* supplying a spoofed identity via a tool-call parameter — removing the
   parameter from the tool signature entirely (so it's structurally not accepted) closes that
   regardless of what happens one layer down at the HTTP boundary. A second credential system
   would have added a new DB column, a new auth dependency, token lifecycle/expiry rules, and
   duplicated trust machinery that already exists at the project-API-key layer, for no additional
   protection against the actual threat model in play.
2. **`AW_AGENT_IDENTITY` is honored by trusting the process environment, not re-verified per
   call.** Consistent with Decision 9's framing ("the Hub pushes state in") and with how
   `agentweave-mcp` already works (one stdio subprocess per agent CLI session, spawned by that
   CLI, inheriting its env) — "the connection" in "bind identity to the connection" *is* this
   process's env for its whole lifetime, so there's no separate connection-level handshake to add.
3. **Did not fork a second CLI binary for the "agent verb set"** (task 4.4's literal phrasing:
   "split the agent surface from the operator CLI"). **Scope decision, annotated as requested:**
   the existing `quick`/`msg send`/`delegate`/`task create`/`question ask` subcommands now refuse
   without a bound identity, which is what actually matters behaviorally — a second console script
   would duplicate argparse wiring for the same commands with no capability difference, since the
   operator's diagnostic/management verbs (`hub start`, `roles`, `doctor`, …) need no identity and
   were already unaffected. Revisit only if a concrete need appears (e.g. hiding operator verbs
   from an agent's own `--help` output).
4. **`hub/hub/mcp_server.py` was left completely untouched.** See "Important context" below — it's
   dead code, not a live attack surface, and its cleanup is explicitly task 7.3.
5. **`save_checkpoint`'s `agent` param was left as-is.** design.md itself flags this tool's fate as
   an open question for task 7.3 ("collapsing the two MCP servers... `save_checkpoint` exists only
   on the CLI side and needs a decision"). Fixing its identity parameter now would be solving a
   problem whose answer might be "delete this tool entirely" three tasks from now.
6. **Hub-side probing shells out on the Hub host, not per-agent-machine.** Native runtime always
   spawns agents on the Hub host itself (Decision 1), so `<cli> mcp list` run from the Hub process
   checks the exact CLI installation about to be launched — no remote-probe problem exists here.
7. **Probe cache is a 5-minute in-process TTL dict, not persisted.** Matches this session's actual
   need (repeated watchdog pings within one running process) without adding a DB table or
   cross-restart persistence for a value that's cheap to recompute once every 5 minutes and stale
   if persisted across a Hub restart with a changed CLI config anyway.

## Constraints and user directives (verbatim)

- **This session's directive, in full:** *"Execute full phase 4. Only stop if there is actually a
  blocking issue. If any decisions were taken that were out of scope annotate them. Don't need to
  be conservative on the changes trying to keep things. If there is genuinely a best approach you
  can scrap anything that already exists. Also apply these new rules when creating handoffs. Don't
  need to be conservative... Do a little bit less handoffs then previously but still do them."** —
  followed: no blocking issue arose so the whole phase shipped in one session; out-of-scope
  decisions are annotated above (items 3–5 in particular); this is a single handoff for the whole
  phase rather than one per task, per the explicit "less handoffs" instruction.
- "Yeah and always commit the changes." (prior session, still binding, reconfirmed by
  `[[always-commit-checkpoints]]` memory) — committed without asking.
- "After every threshold of implementation you must run the skill `/handoff`" (prior session,
  still binding) — this file, at the phase boundary (task 4.7 is itself a `/handoff` checkpoint in
  the plan).
- Repository rule: never commit runtime `.agentweave/` state; stage explicitly rather than
  `git add -A`. Followed — staged the 14 changed/new files by exact path.
- `tasks.md`'s own working protocol: re-read `proposal.md`/`design.md`/touched `specs/*/spec.md`
  before starting a phase. Done this session — read `design.md` in full (Decisions 1–12,
  especially Decision 9 on MCP inversion and the tool-fate table) and both
  `specs/agent-tool-surface/spec.md` and `specs/agent-identity-and-skills/spec.md` before writing
  any code, which is what surfaced the decision that identity-and-skills (charters, personas,
  roster, agent budget) is Phase 13's scope, not Phase 4's — confirmed by grepping `tasks.md` for
  "charter"/"persona"/"roster" before starting, not assumed.

## Dead ends

- **Initially designed a full per-run Hub-issued bearer-token system** (new `Run.token` column, a
  `get_agent_identity` FastAPI auth dependency, token revocation on run completion) before
  realizing the actual live attack surface is the MCP tool-call parameter, not the HTTP layer
  beneath it — see Key decision 1. Caught during design, before any code was written; no wasted
  implementation, just wasted analysis time.
- **First env-injection edit for the Hub trigger path had a real bug**: `env = dict(env) if env is
  not None else {}` — when `resolve_agent_env` returns `None` (meaning "inherit the Hub's own
  environment unchanged"), defaulting to `{}` instead of `dict(os.environ)` would have **replaced**
  the spawned process's entire environment with just the two new keys, losing `PATH` and
  everything else. Caught by re-reading `resolve_agent_env`'s own docstring immediately after
  writing the line, before running any test. Fixed to `dict(os.environ)`.
- **First test run of the new `TestAccessPath.test_probe_mcp_registered_reads_mcp_list_output`
  failed** because `probe_mcp_registered`'s 5-minute cache was shared across tests within the same
  file — an earlier test had already cached `("claude", False)`, so this test's fake
  `subprocess.run` never got called. Fixed with an autouse per-test fixture that clears
  `hub.launchability._probe_cache` before and after each test in that class.
- **First full Hub suite run after adding the identity/notice code would have started shelling out
  real `claude mcp list`/`codex mcp list` subprocess calls** across dozens of pre-existing trigger
  tests (since `resolve_access_path` is now called unconditionally on every trigger, and several
  existing tests patch `shutil.which` to pretend a CLI is present). Caught by reasoning through it
  *before* running the suite, not by a hang/failure — added the `hub/tests/conftest.py` autouse
  fixture pre-emptively.

## Verification

Ran and passed, this session:

- `py -m pytest tests/ -q` (full CLI suite, from repo root) — **987 passed, 4 skipped** (no change
  in skip count from the previous handoff's 983... actually matches the pre-session baseline; net
  +new tests from `test_mcp_server.py`/`test_watchdog_session.py` additions/rewrites).
- `cd hub && py -m pytest -q` (full Hub suite) — **357 passed, 4 skipped** (up from 345 before this
  session — 12 new tests: `TestAccessPath` (7) + `test_access_path_notice_names_...` (1) +
  `test_get_agent_config_falls_back_...` (1) in `test_launchability.py`, plus 2 new tests in
  `test_agent_trigger.py`, plus a net +1 from splitting/renaming in that file — exact split not
  re-verified line-by-line, but the pass count and zero-failure result are what matters).
- `py -m ruff check` on every touched Python file (both CLI and Hub sides, listed individually) —
  clean.
- `py -m black --check --fast` on every touched Python file — clean (after one `--fast` reformat
  pass on `tool_surface.py`, `hub/hub/launchability.py`, and `hub/tests/test_agent_trigger.py` —
  re-ran the full test suites afterward, still green).
- `py -m mypy src/agentweave/tool_surface.py` — clean, no issues. (Did not run mypy across the rest
  of the touched files — the Phase 3 handoff already established mypy is not a clean/enforced gate
  in this repo, with 108 pre-existing errors across 18 files; not attempting to fix pre-existing
  debt, same as last session.)
- **Manual end-to-end CLI smoke test** in a scratch project (`agentweave init` → `msg send`/
  `task create`/`quick` each tested with and without `AW_AGENT_IDENTITY` set, confirming refusal
  without it and correct attribution with it; confirmed `--from-agent`/`--assigner`/`--from` are
  gone from `--help` output on all four affected subcommands; confirmed `agentweave switch claude`
  prints the `AW_AGENT_IDENTITY` tip for a non-proxy runner).

Not tested this session:

- No live Hub-triggered run against a real installed `claude`/`codex` CLI with the MCP server
  actually registered (i.e., no live verification that `resolve_access_path` returns `"mcp"` in a
  real environment where `claude mcp list` genuinely lists `agentweave` — only the parsing/logic
  around a mocked `subprocess.run` result was verified). Worth doing if this session's next
  reader has a machine with Claude Code MCP already configured for this project.
- No live watchdog run with a real second agent process — the ping-callback change was verified
  via `test_watchdog_session.py`'s unit-level harness (fakes `_run_agent_subprocess` entirely), not
  an actual spawned CLI receiving and acting on the new notice text.
- Did not exercise `cmd_switch`'s claude_proxy branch live (needs a configured minimax/glm agent
  with a real or fake API key var) — confirmed the code path logically and via the non-proxy
  branch instead; the proxy branch's added `print(f"export AW_AGENT_IDENTITY={agent}")` line is a
  one-line, low-risk addition to an already-tested loop, but wasn't independently re-run live.
- Hub UI: no changes were made to `hub/ui/` this session (phase 4 is backend-only per its task
  list), so no UI build/test/manual-browser verification was performed or needed.

## Git state

- Branch: `hub-native-experience`.
- HEAD: `1963c64 Phase 4: identity binding and access-path resolution (hub-native-experience)`.
- Working tree: clean except the same pre-existing untracked paths noted in every prior handoff in
  this chain (six older handoff files plus `.claude/skills/aw-spec-reindex/`) — none of this
  session's business, left alone.
- No upstream configured; all commits local and unpushed (matches every prior handoff's git state).

## Next steps

1. Re-read `openspec/changes/2026-07-30-hub-native-experience/design.md` (Decision 7) and
   `openspec/changes/2026-07-30-hub-native-experience/specs/hub-native-runtime/spec.md`'s isolation
   scenarios before starting Phase 5 — the working protocol at the top of `tasks.md` requires this
   before starting a phase, and it was **not** done yet for Phase 5 specifically (this session's
   re-reads covered Phase 4's specs only).
2. Start Phase 5 — "Workspace isolation"
   (`openspec/changes/2026-07-30-hub-native-experience/tasks.md`, starts right after Phase 4's
   entries, 6 tasks: 5.1–5.6). First task: 5.1, provision a git worktree per writing agent, on its
   own branch, sharing the object database, prepared before the agent's first turn. This phase was
   deliberately moved ahead of the queue phase (same "Ordering revision" rationale noted for Phase
   4 in the previous handoff) — the scheduler is what causes concurrent turns, and isolation must
   exist before concurrency does.
3. Task 5.1 will need a spawn-time hook point — likely the same two places this session just
   touched for identity injection (`agent_trigger.py`'s `trigger_agent_directly`/`_execute_run` and
   `watchdog.py`'s `_do_run_agent_subprocess`/`_run_cmd`) are where a worktree's path would need to
   become the process's `cwd` instead of (or in addition to) the existing `work_dir`/`cwd` handling
   already in both of those functions — worth reading both functions in full again before design,
   since this session already has fresh, accurate context on their exact current shape.
4. Run `/handoff` again after Phase 5 completes (task 5.6 is explicitly a `/handoff` checkpoint in
   the plan itself, same pattern as 4.7).

## Open questions for the user

None currently blocking. One thing worth surfacing next time there's a natural pause: this
session found that `hub/hub/mcp_server.py` (a second, 24-tool MCP server implementation) is
**entirely dead code** — not mounted in `hub/hub/main.py`, no console-script entry point, not
imported anywhere except its own test file. It duplicates the exact identity-assertion pattern
(`from_agent`, `assigner` as tool parameters) that this session just closed in the live
`src/agentweave/mcp/server.py`, but since nothing can currently reach it, it's not a live
vulnerability — just dead weight and a footgun for a future contributor who wires it up without
knowing it predates this fix. Its cleanup is already correctly scoped to task 7.3 ("collapse
`src/agentweave/mcp/server.py` and `hub/hub/mcp_server.py` into one surface"); flagging here only
so it isn't mistaken for something this session missed.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — authoritative phase ledger; Phase
  4 fully closed with detailed per-task notes, Phase 5 starts immediately after.
- `openspec/changes/2026-07-30-hub-native-experience/design.md` — Decision 7 (git worktree per
  writing agent) is the one Phase 5 implements; required reading per the working protocol.
- `src/agentweave/tool_surface.py` — the new identity/access-path module Phase 5 should *not* need
  to touch, but is useful context for how spawn-time injection is currently done in both the Hub
  and CLI/watchdog paths (the pattern Phase 5's worktree assignment will likely follow).
- `hub/hub/api/v1/agent_trigger.py` — `trigger_agent_directly`/`_execute_run`, this session's most
  heavily edited Hub file; Phase 5's worktree `cwd` injection almost certainly lands here too.
- `src/agentweave/watchdog.py` — `_do_run_agent_subprocess`/`_run_cmd`, the local/git-transport
  equivalent spawn path; same reasoning as above.
