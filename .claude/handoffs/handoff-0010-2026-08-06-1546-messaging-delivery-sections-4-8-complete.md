# Handoff: messaging-delivery change closed out (sections 4-8) plus a new, separate permission-mode fix

**Date:** 2026-08-06T15:46 · **Branch:** hub-native-experience · **HEAD:** 671e9f3
**Agent:** Claude Sonnet 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0009-2026-08-06-1030-codex-appserver-wired-and-verified-claude-parity-checked.md
**Status:** chunk complete. Six commits. `2026-08-06-agent-messaging-delivery` sections 1-8 are now
all addressed (one item, §8.7, honestly flagged rather than claimed done). One new, separate openspec
change shipped in full. One significant new anomaly discovered and recorded, not resolved.

## Goal

Continue from handoff-0009: implement the two follow-on items it left open (the Claude
`--allowedTools` permission-mode fix, and section 4 of `2026-08-06-agent-messaging-delivery`), then
keep going through the rest of that change's sections. The operator explicitly picked both follow-ons
("A then B") at session start, then said "keep going" repeatedly as each section closed, driving
straight through sections 4, 5, 6, 7, and 8 of the messaging-delivery change in one session.

## Current state

**Task A — Claude non-yolo permission mode (commit `5d7c716`, its own openspec change
`2026-08-06-claude-non-yolo-permission-mode`, fully complete and separate from the messaging-delivery
change).** `hub/hub/runner_commands.py::_build_claude_command` now sets `--permission-mode manual`
for every non-yolo Claude run (previously set nothing, silently inheriting whatever
`~/.claude/settings.json` said on the machine the Hub happened to run on), and additionally sets
`--allowedTools "mcp__agentweave__*"` when an MCP command is configured and the run is non-yolo, so
the Hub's own tools stay usable under the now-real sandbox. Live-verified through the real Hub: an
unprompted built-in `Read` call was refused with the classic undifferentiated permission message, an
`mcp__agentweave__*` tool call succeeded, both in the same run.

**Task B — instance-scoped run credentials (commit `854946e`, §4 of messaging-delivery).** Each Hub
process now has a stable identity, minted once and persisted to a local marker file (deliberately NOT
a database row — see Key Decisions), stamped onto every new `Run.instance_id`, and checked at auth
time in `agent_auth.get_agent_actor`: a credential whose recorded `instance_id` doesn't match this
process's own is rejected with a distinct reason, separate from "expired"/"unknown". A run minted
before this feature (`instance_id=None`) is not treated as a mismatch. Found and fixed a real bug
along the way: the marker-file path fell back to the process's cwd for an in-memory sqlite DB (what
the test suite itself uses), which wrote a stray `instance_identity.json` into the source tree during
`test_lifespan_shutdown.py` — fixed before committing, with a regression test.

**§5 — make failures visible (commit `51d3c64`).** Found a real, previously-unknown gap while
implementing this: `send_message` to a nonexistent recipient had **zero existence validation** —
`create_message_for_actor` created a real `Message`/`InboundQueueEntry` addressed to any string and
returned 201, regardless of whether any agent by that name existed. Fixed:
`hub/hub/api/v1/messages.py`'s `create_message_for_actor` now checks the recipient against real
`Agent` rows in the project first; an unknown recipient gets a 404 naming it, and the rejection is
recorded on the *sender's* timeline (`persist_event(..., "agent_action_rejected", ...,
severity="warn")`) so the operator can see it through the same `/logs` API the UI already reads.
Also split `hub/hub/mcp_server.py`'s error types: `HubAPIError` ("the Hub was reached and rejected
this") now names the endpoint; new `HubUnreachableError` ("nothing answered at this HUB_URL at all")
is distinct from it, both by type and by wording. Live-verified organically: a real agent's own
onboarding charter led it to message "principal" — itself unregistered in that project, a real,
unplanned hit of exactly this scenario. Fixed 4 pre-existing tests that depended on the old permissive
behavior (each now registers its recipient first).

**§6 — collaboration readiness reporting (commit `1936206`).** Before extending anything, found and
fixed a prerequisite gap: `GET /agents/launchability` (`hub/hub/api/v1/agents.py`) probed a *legacy*
session-config-derived `runner`/`model` even for an agent bound to a real Hub `Runner`, diverging from
`trigger_agent_directly`'s own override of those two keys — the operator explicitly chose to fix this
first rather than build on top of it (see Key Decisions). On the corrected probe: new
`collaboration_ready`/`collaboration_reason` fields, computed only for a Runner-bound, already-
`runnable` agent (`None` means "not applicable", not "unready"). Checks callback-address agreement
(same condition `trigger_agent_directly` itself requires) and, for Codex specifically, whether the
Runner would hit this change's original silent-tool-denial defect (non-yolo classic `exec`, no
app-server opt-in) — Claude is always ready post-task-A. Surfaced in `ComposerAgentSelector.tsx`: a
runnable-but-not-collaboration-ready agent shows "Runnable — cannot collaborate" in amber instead of
plain green "Runnable". Live-verified against real, pre-existing dev-Hub data with zero synthetic
setup needed: two Runner-bound Claude agents report ready; a yolo Codex agent reports ready; a
non-yolo exec Codex agent reports not-ready with the exact reason text.

**§7 — runner name mojibake (commit `754e1a5`).** The design.md hypothesis going in ("double-encoding
somewhere in the write path") was **wrong**, and was disproven by inspecting raw bytes at every layer
(name construction, the stored DB column, the raw HTTP response bytes from a real running Hub via
`curl -o` — all correct UTF-8 everywhere). Root-caused instead as a missing `charset` on the JSON
`Content-Type` header, reproduced live through the actual client that plausibly produced the original
observation: Windows PowerShell 5.1's `Invoke-WebRequest` (this environment's own primary shell)
mis-decodes an unlabelled `application/json` body. Fixed with a small `UTF8JSONResponse` in
`hub/hub/main.py`, set as the app's `default_response_class`; confirmed live through the identical
PowerShell 5.1 request before (mojibake) and after (correct). `design.md`'s Decision 5 was rewritten,
not left pointing at a disproven hypothesis.

**§8 — end-to-end verification (commit `671e9f3`).** 8.1/8.2/8.8 clean (746 backend tests, 414
frontend tests, `tsc --noEmit` clean, openspec valid). 8.3-8.6 (codex-to-codex, claude-to-claude,
cross-provider codex-to-claude message delivery, all live through the real Hub) all confirmed —
**but not via the normal operator-facing `/agent/trigger` flow**, because that flow hit the new
anomaly below. Instead, confirmed by minting a run token directly
(`hub.agent_auth.mint_run_token`/inserting a `Run` row by hand) and calling
`POST /agent-actions/messages` directly, which bypasses needing an LLM to "comply" with an
instruction and isolates the Hub's own mechanics: message row correct, queue entry reaches
`state: delivered`, a real `Run` auto-starts for the recipient, and the recipient's actual transcript
contains the exact message content as an `inbound_peer` entry. The codex-to-codex exchange also
caught task 5's fix firing organically: the receiving agent's own `send_message` attempt got a real
422 in task 5's new format, self-corrected, and succeeded on retry. **8.7 (sandbox still holds) is
flagged `[~]`, not marked `[x]`** — a live re-confirmation attempt with the new agents ran into the
anomaly below and never delivered the intended breach-test instruction; relying instead on
already-established evidence (task A's live Claude test this session, and the prior session's Codex
app-server breach test from handoff-0009).

**New, unresolved finding — a queue-backlog / prompt-delivery anomaly.** Across six live
`/agent/trigger` attempts this session (three Claude, three Codex; `session_mode: "new"` used in most)
a triggered agent's *first response text* repeatedly did not correspond to the message actually sent
in that trigger call. Two read as generic non-engagement ("I'm ready to help, what would you like me
to do?"), suspiciously cheap (~$0.01-0.02, consistent with an almost-empty effective prompt). The
final attempt instead picked up unrelated content from earlier in the same conversation's history.
`hub/hub/api/v1/agent_trigger.py:328`'s prompt construction
(`f"{access_path_notice(access_path)}\n\n{message}"`) was read and looks correct — not traced further
than that. Appears correlated with rapid, closely-spaced trigger calls against the same
agent/conversation (this session's own live-testing cadence, not necessarily normal operator pacing).
**Not a blocker for closing the messaging-delivery change** — §8.3-8.6's mechanics were independently
confirmed by sidestepping this exact path. Full detail and the operator's explicit decision to stop
chasing it live are in `tasks.md` §8's own write-up.

## Files touched

**Task A (`5d7c716`):**
- `hub/hub/runner_commands.py` — `_build_claude_command`: `--permission-mode manual` for non-yolo
  (was: nothing); `--allowedTools "mcp__agentweave__*"` when `mcp_command` set and non-yolo.
- `hub/tests/test_runner_parsing.py` — updated 2 exact-argv tests, added 6 new (permission-mode
  present/absent by yolo, allowlist present/absent by mcp_command × yolo).
- `openspec/changes/2026-08-06-claude-non-yolo-permission-mode/` — new change: `proposal.md`,
  `design.md`, `tasks.md`, `specs/agent-run-sandboxing/spec.md` (new capability).

**Task B (`854946e`):**
- `hub/hub/instance_identity.py` — new module: `load_or_create()`/`get()`, marker-file-based, not a
  DB row.
- `hub/hub/agent_auth.py` — `get_agent_actor` rejects a recorded, differing `Run.instance_id`.
- `hub/hub/api/v1/agent_trigger.py` — stamps `instance_id=instance_identity.get()` on new `Run` rows.
- `hub/hub/db/models.py` — `Run.instance_id` column.
- `hub/hub/main.py` — `instance_identity.load_or_create()` called in `lifespan`.
- `hub/hub/migrations/versions/0028_add_run_instance_id.py` — new migration.
- `hub/tests/test_instance_identity.py` — new (4 tests, including the in-memory-DB regression test).
- `hub/tests/test_agent_capability_auth.py` — 3 new tests (mismatch rejected, match accepted, legacy
  row unaffected).
- `hub/tests/test_agent_trigger.py` — 1 new test (live-triggered run gets stamped correctly).
- `hub/tests/test_migrations.py`, `hub/tests/test_project_persistence.py` — bumped hardcoded
  "latest revision" assertions from `0027` to `0028`.

**§5 (`51d3c64`):**
- `hub/hub/api/v1/messages.py` — `create_message_for_actor`: recipient-existence check before any
  write; `persist_event(..., "agent_action_rejected", ...)` on rejection.
- `hub/hub/mcp_server.py` — `HubAPIError` gains `method`/`path`, renders `"Hub rejected {method}
  {path} ({status}): {detail}"`; new `HubUnreachableError` for `URLError`.
- `hub/tests/test_mcp_server.py` — 2 new tests (endpoint naming, unreachable-vs-rejected
  distinguishability).
- `hub/tests/test_agent_actions_coordination.py` — 1 new test (unknown recipient rejected + event
  recorded on sender's timeline).
- `hub/tests/test_messages.py`, `hub/tests/test_project_workspace_unavailable.py`,
  `hub/tests/test_agent_tool_surface_phase7.py` — fixed 4 tests that depended on the old permissive
  behavior (each now registers its recipient as a real `Agent` first).

**§6 (`1936206`):**
- `hub/hub/api/v1/agents.py` — `get_agents_launchability`: applies `Agent.runner_id -> Runner`
  override before probing (prerequisite fix); adds `collaboration_ready`/`collaboration_reason`.
- `hub/tests/test_launchability.py` — new `TestCollaborationReadiness` class, 7 tests.
- `hub/ui/src/api/agents.ts` — `AgentLaunchability` gains the two new optional fields.
- `hub/ui/src/components/agents/ComposerAgentSelector.tsx` — amber "cannot collaborate" label/color.
- `hub/ui/src/__tests__/composerAgentSelector.test.tsx` — 1 new test.

**§7 (`754e1a5`):**
- `hub/hub/main.py` — new `UTF8JSONResponse`, set as `default_response_class`; `/health`'s explicit
  `JSONResponse` call updated to use it too.
- `hub/tests/test_response_encoding.py` — new file, 3 tests.
- `openspec/changes/2026-08-06-agent-messaging-delivery/design.md` — Decision 5 rewritten.

**§8 (`671e9f3`):**
- `openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md` — §8 fully written up (see Current
  state above); no code changes, live-verification-only commit.

**All six commits also touched** `openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md`
(marking the relevant section's tasks done/flagged with implementation notes) — listed once here
rather than repeated per commit above.

**Pre-existing dirty files, not touched this session** (carried across every handoff since
handoff-0001): `M .claude/handoffs/handoff-0001-...md`, `M Makefile`.

## Key decisions

1. **Task A got its own openspec change (`2026-08-06-claude-non-yolo-permission-mode`), not folded
   into messaging-delivery.** It changes every non-yolo Claude run's command line, not just messaging
   — handoff-0009 had already flagged this as the likely right call; confirmed by going ahead with it.
   The `openspec new change`/`openspec status --change`/`openspec instructions` guided CLI workflow
   turned out to be broken for date-prefixed change names (a real CLI bug: `validateChangeName`
   rejects any name starting with a digit, even though every existing change in this repo IS
   date-prefixed) — worked around by writing `proposal.md`/`design.md`/`tasks.md`/the spec delta by
   hand, matching the existing changes' own convention exactly (none of them have a `.openspec.yaml`
   either, confirming they were authored the same way).
2. **Task B's instance identity is a local marker file, explicitly not a database row.** The exact
   scenario Decision 3 defends against is multiple Hub processes sharing one database — storing the
   identity *in* that shared database would mean every process reading the same row appears to be the
   same instance, defeating the entire point.
3. **§6's readiness endpoint got its data-source bug fixed first, at the operator's explicit choice**
   (`AskUserQuestion`, three options offered: extend-as-is, fix-first, or skip to §7 instead —
   "fix-first" chosen). Reasoning: extending a probe that already disagreed with the real trigger path
   would have meant `collaboration_ready: true` was itself unreliable for exactly the agents §6 cares
   about.
4. **§6's Codex collaboration-ready check requires yolo OR the app-server opt-in flag, not "any
   non-yolo Codex Runner".** A bare, zero-flag non-yolo Codex Runner is *not* collaboration-ready — it
   would hit the exact silent-tool-denial defect (`codex exec`, no approval channel) this whole change
   started from. This also shaped §8.3's live test setup: the two Codex agents used there were
   deliberately bound to an app-server-opted Runner, not a bare default one, since a bare one would
   have failed §8.3 by design, not by accident.
5. **§7's original "double-encoding" hypothesis was abandoned once raw bytes at every layer came back
   correct**, per its own task wording ("establish where before changing anything"). Root-caused
   instead by testing the actual client (PowerShell 5.1) that plausibly produced the original
   observation, live, before touching any code — confirmed by reproducing the mojibake, applying the
   fix, and reproducing correctness with the *same* client and the *same* request.
6. **§8.3-8.6 were confirmed by minting run tokens directly and calling `/agent-actions/messages`,
   not by relying on the normal `/agent/trigger` + "ask the agent nicely" flow**, once that flow's
   anomaly (see Current state) made it produce unreliable signal. This was an explicit pivot after the
   operator chose "stop investigating, treat as open question" when asked how to handle it — the
   mechanics-level proof still needed to exist for §8 to mean anything, so it was obtained a different
   way rather than either skipped or force-fixed live.
7. **§8.7 (sandbox still holds) was left flagged `[~]` rather than marked `[x]`**, per CLAUDE.md's
   "never mark a task complete on the strength of a plan existing — only verified implementation
   closes a task." A live re-confirmation attempt genuinely didn't complete due to the anomaly; citing
   older evidence as a substitute is reasonable, but claiming this session verified it would not be.

## Constraints and user directives (verbatim)

- **"A then B"** — session-opening instruction selecting both follow-on items from handoff-0009 in
  order (task A: Claude permission-mode fix; task B: §4 instance-scoped credentials), then **"Get to
  work"**.
- **"keep going"** — said repeatedly (after §5, after §6 implicitly via continuing, and explicitly
  after §6 and §7) authorizing continuation through the rest of messaging-delivery's sections without
  re-asking each time, until a genuine fork or a real blocker came up.
- Three `AskUserQuestion` checkpoints this session, each answered explicitly:
  1. **"Fix the endpoint to use Agent.runner_id -> Runner first (Recommended)"** — §6's readiness
     endpoint, over "extend as-is" or "skip to §7 instead".
  2. **"Stop here, treat as a new open question (Recommended)"** — the compliance/queue-backlog
     anomaly, over "keep investigating now" or "something else". This directly shaped §8.7 being
     flagged rather than closed, and the pivot to direct-token testing for §8.3-8.6.
  3. (Earlier, start of session) resume-flow confirmation of next steps — not a fork requiring a
     recorded decision, standard `/resume` flow.
- From `CLAUDE.md`, load-bearing throughout: never create `.agentweave/`, `agentweave.yml`, or
  `spec/` at the repo root; stage paths explicitly, never `git add -A`; use openspec, never aw-spec
  skills, when working on this repo itself; Icon is the only icon system (not touched — no new icons
  added, only color/text changes to an existing component).
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without asking.
  All six commits happened unprompted, each after its own test run and (for every section except §7's
  code-only portion) a live-Hub verification.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. Done at session
  start — re-ran the full `hub/tests/` suite (720 passed, 9 skipped, matching handoff-0009's claim
  exactly) before touching anything. **Repeating the directive here for the next session.**
- User's own communication-style request this session, worth carrying forward: **"Keep it simple. Be
  direct clear. ELI5 style"** — given specifically for a status/next-steps summary, not for technical
  writing generally, but worth remembering when the next session reports back to this operator.

## Dead ends

- **Two `AskUserQuestion`-adjacent live-testing dead ends, both now folded into the "queue-backlog
  anomaly" finding above, not separate bugs**: (a) three consecutive `/agent/trigger` calls to
  `live-verify-claude` with increasingly explicit "ignore your charter, this is a diagnostic test"
  framing all produced generic non-compliant responses; (b) redirecting to *work with* the agent's own
  charter behavior (asking it to send its "usual availability notice" to a specific peer instead of
  the default) also failed the same way. Neither framing was the actual problem — the pattern
  persisted regardless of instruction phrasing, which is why it was reclassified as a delivery-layer
  anomaly rather than a prompting problem, once it also reproduced with Codex.
- **A stray `hub/instance_identity.json` file was written into the source tree during the first
  combined test run of task B's new tests** — root cause: `_marker_path()`'s naive version fell back
  to `os.path.dirname(":memory:") or "."` for the test suite's in-memory sqlite DB, resolving to
  whatever the pytest process's cwd happened to be. Fixed before committing (`_marker_path()` returns
  `None` for `:memory:`, `load_or_create()` mints a process-lifetime-only id instead of touching disk
  in that case) — caught by `test_lifespan_shutdown.py`, which is the one test in the suite that runs
  the *real* ASGI lifespan (`TestClient`, not `ASGITransport`) and so was the only one that actually
  exercised `instance_identity.load_or_create()` at all. Regression test added
  (`test_in_memory_database_mints_an_id_without_writing_to_disk`).
- **My own `session/sync` call during §8 setup destroyed the pre-existing `live-verify-claude`/
  `live-verify-claude-2` Agent DB rows entirely**, not just their session-config view — `session/sync`
  treats its `agents` payload as authoritative and reconciles the roster to match it, so omitting an
  existing agent from a sync call deletes its Agent row (roster entry, `runner_id` binding — not its
  run/message history, which is separate). Recovered by re-syncing with all four agent names included
  and re-binding the two Claude agents' `runner_id`. **This is real, reproducible, destructive
  behavior worth an operator-facing warning or a merge-instead-of-replace semantics change** — not
  fixed this session (out of scope, not asked for), recorded as a new open question below.
- **Two live agent-run tokens I minted directly (bypassing the Hub's real spawn path) for §8's
  mechanics tests left their `Run` rows stuck in `status: "running"` forever**, since nothing ever
  transitions a manually-inserted row to `completed` the way a real spawned subprocess's exit does.
  This blocked a *later*, real `/agent/trigger` call to the same agent ("agent is already running").
  Fixed by manually setting those three rows to `completed` before retrying. If a future session uses
  this same direct-token technique (minting a token, inserting a `Run` row, calling
  `/agent-actions/*` directly to test Hub mechanics without spawning a real subprocess), **remember to
  close the Run row afterward** — it will not close itself.
- **A Bash-tool pipe artifact, not a real bug**: `curl ... | python -m json.tool` in Git Bash rendered
  a correctly-stored em-dash runner name as further-mangled mojibake, differently from both the raw
  stored bytes (confirmed correct via direct Python DB read) and the raw HTTP response bytes
  (confirmed correct via `curl -o file` + a separate Python read). Something in Git Bash's own pipe
  buffering does its own encoding conversion; writing to a file and reading it separately avoided the
  artifact. Worth remembering for any future live-verification in this environment: prefer `curl -o
  file` + a separate read step over piping curl's stdout through another tool for anything containing
  non-ASCII content.

## Verification

**Ran, with real output, this session:**
- Full `hub/tests/` suite, six times as work landed (once per commit): 720 (baseline, matches
  handoff-0009) → 725 (task A) → 732 (task B, before the stray-file fix) → 733 (task B, after) → 736
  (§5) → 743 (§6) → 746 (§7). §8 was a docs-only commit; final count re-confirmed at 746 passed, 9
  skipped, zero failures throughout.
- `hub/ui`: `npm test -- --run` (414 passed) and `npx tsc --noEmit` (clean) after §6's UI changes — no
  UI files changed since, so this result still holds through §8.
- `ruff check` on every modified `hub/`/`tests/` file after every commit — clean, except one
  pre-existing SIM117 finding in `test_agent_trigger.py` (confirmed pre-existing via `git show
  HEAD:...`  + re-lint, same finding, same code, before any of this session's edits).
- `openspec validate <change> --strict` — both changes, after every `tasks.md`/`design.md` edit.
- **Live, task A**: two runs through the real dev Hub (`live-verify-claude`, project `proj-de54b547`)
  — an unprompted `Read` call refused under `--permission-mode manual`; `mcp__agentweave__list_tasks`
  and `mcp__agentweave__send_message` both succeeded in the same runs.
- **Live, task B**: real dev-Hub restart applied migration `0028` cleanly; `instance_identity.json`
  created at `hub/data/instance_identity.json` with a real minted id; a live-triggered run's `Run` row
  confirmed stamped with that exact id, then confirmed `status: completed, exit_code: 0`.
- **Live, §5**: real breach-test-style trigger of `live-verify-claude`; its own charter-driven
  `send_message` to "principal" (itself unregistered) was rejected 404, `is_error: true`; separately
  confirmed via `GET /logs?event_type=agent_action_rejected` that the event is visible through the
  operator-facing API with the exact expected `data` shape.
- **Live, §6**: `GET /agents/launchability` against two real, pre-existing dev-Hub projects —
  `proj-de54b547`'s two Claude agents both `collaboration_ready: true`; `proj-d9b5ed67`'s
  `codex-mini-1` (yolo) `true`, `codex-mini-2` (non-yolo exec) `false` with the exact reason text.
- **Live, §7**: identical `GET /runners` request via Windows PowerShell 5.1's `Invoke-WebRequest`,
  before the fix (mojibake reproduced, `Content-Type: application/json`, no charset) and after (correct
  em dash, `Content-Type: application/json; charset=utf-8`).
- **Live, §8**: three direct-token `/agent-actions/messages` calls (codex-to-codex, codex-to-claude,
  claude-to-claude) against the real dev Hub, project `proj-de54b547`; each confirmed message row +
  `InboundQueueEntry.state == "delivered"` + a real auto-started `Run` for the recipient + the
  recipient's actual transcript containing the message as `inbound_peer`. Six additional live
  `/agent/trigger` attempts (three Claude, three Codex) produced the queue-backlog anomaly instead of
  clean signal — not counted as passing verification, recorded as the new open finding instead.

**Explicitly NOT run — do not assume:**
- **§8.7's sandbox-still-holds check was not independently re-confirmed with `codex-collab-1`/
  `codex-collab-2` or the restored `live-verify-claude` agents this session** — see Dead Ends and Key
  Decision 7. Relying on older, still-believed-valid evidence, not new evidence.
- **The queue-backlog/prompt-delivery anomaly was not root-caused** — the prompt-construction code
  was read and looks correct; the actual subprocess argv/stdin the Hub sends was never inspected
  directly (e.g. via strace-equivalent or Hub-side debug logging). This is real, unfinished
  investigative work, not a closed loop.
- **The `session/sync` destructive-replace behavior was not fixed or even filed as its own openspec
  item** — only discovered, worked around, and recorded as a new open question below.
- **Sections of `2026-08-06-hub-composer-and-chrome-refinement`** (the separate, independent UI
  change) remain fully untouched, as in every handoff since it was specced.
- **`2026-08-06-operator-in-the-loop-turns`** remains deliberately DEFERRED per its own document header
  — not touched, not reconsidered this session.
- The frontend suite was not re-run after §7 or §8 (no UI files changed in either) — the §6 result is
  cited, not re-verified, for those two commits.

## Git state

Branch `hub-native-experience`, HEAD `671e9f3`, **no upstream configured — nothing has ever been
pushed on this branch** (carried forward from every prior handoff).

Six commits this session: `5d7c716`, `854946e`, `51d3c64`, `1936206`, `754e1a5`, `671e9f3`.

Uncommitted, all pre-existing and none from this session (identical set to every handoff since
handoff-0001): `M .claude/handoffs/handoff-0001-...md`, `M Makefile`, plus the same set of untracked
scratch/legacy-handoff paths listed in every prior handoff's Git State section (`data/`, `scripts/`,
`.claude/skills/{handoff,resume,review-iteration}/`, older un-numbered handoffs, `openspec/
explorations/...`, `src/agentweave/templates/skills/{handoff,resume}.md`,
`tests/test_handoff_resume_templates.py`).

## Live environment

- **Hub dev server on `127.0.0.1:8010`** — restarted five times this session (uvicorn, from `hub/`
  directory, background, no `--reload`), currently running the full HEAD `671e9f3` code. Log at
  `/tmp/hub-dev-8010.log`. API key `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` (from `hub/.env`'s
  `AW_BOOTSTRAP_API_KEY`); `Authorization: Bearer <key>`. Disposable, kill any time.
- **`proj-de54b547` ("Live Verify")** now has **four** agents, up from two: `live-verify-claude` and
  `live-verify-claude-2` (both restored after the accidental deletion — see Dead Ends — Runner
  `runner-148c4fee`, `cli: claude`, non-yolo), plus new `codex-collab-1` and `codex-collab-2` (Runner
  `runner-f9a478b0`, `cli: codex`, `flags: ["--app-server"]`, non-yolo) added this session for §8's
  live tests. All four have real run/message history from this session's testing now.
- **Two `Run` rows manually inserted and then manually closed** this session for direct-token testing:
  `run-e2e-mech-check`, `run-e2e-cross-provider` (both `agent: codex-collab-1`), and
  `run-e2e-claude-to-claude` (`agent: live-verify-claude-2`) — all three now `status: completed`. Safe
  to ignore or query for their transcripts if useful.
- **`Two Codex Mini`** (`proj-d9b5ed67`) and the old **`Agentweave`**/breach-test project
  (`working_directory` bound to `testbed/scratch/appserver-breach-test/workspace`), unchanged from
  handoff-0009. `codex-mini-1` still `yolo: true`.
- **Port 8000** — not observed listening at end of session (previous handoffs noted an old Dockerised
  Hub there); may or may not still be running, not re-checked.
- `testbed/scratch/*.json` — several throwaway response captures from this session's live checks
  (`launchability_check.json`, `agents_check.json`, `runners_response.json`, `run1_check.json` through
  `run4_check.json`, `codex_collab2_check.json`, `cross_provider_check.json`,
  `claude_to_claude_check.json`, `breach_check.json`, `breach_check2.json`,
  `agents_status_check.json`). All gitignored (`testbed/.gitignore:3 = *`), safe to delete.

## Next steps

1. **If picking up the queue-backlog/prompt-delivery anomaly**: read `tasks.md` §8's full write-up
   first (the "New finding, not closed" block) for the complete evidence trail. Suggested first move
   is NOT another live trigger — inspect what the Hub actually sends to the CLI subprocess directly
   (e.g. temporary logging in `_execute_run`/`PtySession.spawn`'s `env`/argv construction, or a debug
   dump of the exact `-p` argument value right before `PtySession.spawn` is called) rather than
   inferring from model responses, which is what made the first six live attempts inconclusive.
2. **If picking up `2026-08-06-hub-composer-and-chrome-refinement`** (the independent UI change): it
   has had zero attention since it was specced (handoff-0007). Read its own `tasks.md`/`design.md`
   fresh — nothing from this session bears on it directly, though task A's Claude permission-mode
   change and §6's UI change (`ComposerAgentSelector.tsx`) both touch adjacent UI surface and are
   worth being aware of if this change also touches the composer.
3. **If considering archiving `2026-08-06-agent-messaging-delivery`**: sections 1-8 are now all
   addressed, but §8.7 is flagged not confirmed, and the queue-backlog anomaly is a live open
   question directly relevant to this change's own subject matter (message delivery). Whether that's
   enough to block archiving, or whether it should archive with those two items carried forward as
   separate follow-on work, is itself an open question for the user — see below.
4. **The `session/sync` destructive-replace behavior** (Dead Ends) has no scope yet — worth deciding
   whether it needs an openspec change of its own (e.g., "merge into the existing roster instead of
   replacing it" or "warn/refuse when a sync payload would drop an existing agent") before it costs
   an operator real state the way it cost this session's own test setup.
5. Everything else — sections 5-8 vs. handoff-0008's original framing (now fully superseded, since
   this session did exactly that work), the UI change, and the long-running open-questions backlog —
   is current as of the Open Questions section below.

## Open questions for the user

Carried forward from handoff-0009, still untouched:
1. What should happen to untracked `data/agentweave.db` — gitignore, or commit?
2. `M .claude/handoffs/handoff-0001-...md` and `M Makefile` — intentional WIP, or commit/revert?
3. The `review-0002` agent-name uniqueness gap — still open, still not investigated.
4. `64dbb4b "Add harness-audit and harness-refresh skills"` — still unexplained.
5. Should `Live Verify` (`proj-de54b547`) and its (now four, not two) agents be kept, or removed once
   deletion exists?
6. Should `hub-native-experience` be pushed? Still has no upstream, still never pushed.
7. Should the Hub gain project/agent deletion? Still not specced; test projects and now test agents
   keep accumulating.
8. `item/permissions/requestApproval`'s yolo-grant shape — still never actually observed live.

New this session:
9. **The queue-backlog/prompt-delivery anomaly** (Current state, Dead Ends, Verification) — is this
   worth a dedicated investigation now, or does it wait for the next natural touch of
   `agent_trigger.py`? Given it's directly in messaging-delivery's own subject matter, the operator
   may want it prioritized differently than the rest of the backlog.
10. **`session/sync`'s destructive-replace semantics** (Dead Ends) — worth fixing (merge instead of
    replace, or a warning), or is replace-semantics intentional/acceptable given `session/sync`'s role
    as "make the Hub's roster match the CLI's current config exactly"?
11. Should `2026-08-06-agent-messaging-delivery` be archived now, with §8.7 and the queue-backlog
    anomaly carried forward as separate tracked follow-ons? Or does archiving wait until both are
    resolved?
12. The Claude `--allowedTools` fix (from handoff-0009's own open question 10) is now done as its own
    archived-in-spirit change (`2026-08-06-claude-non-yolo-permission-mode`) — should that change
    itself be formally archived via `openspec-archive-change`, or left as-is?

## Read on resume

- `openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md` — §8's full write-up (the "New
  finding, not closed" block especially) before touching the queue-backlog anomaly or considering
  archiving; §1-8 are all now addressed, read whichever section's follow-on is being picked up.
- `openspec/changes/2026-08-06-claude-non-yolo-permission-mode/` — the whole change, small (4 files),
  if archiving it or extending the fix (e.g. to `claude_proxy`/`native` runners, which reuse the same
  `_build_claude_command` and already got the fix for free — confirm this if it matters).
- `hub/hub/api/v1/agent_trigger.py` — `trigger_agent_directly`, specifically the `prompt` construction
  around line 328, if picking up the queue-backlog anomaly.
- `hub/hub/api/v1/agents.py` — `_get_session_data`/session-sync's agent-reconciliation logic, if
  picking up the destructive-replace finding.
- `hub/hub/instance_identity.py` and `hub/hub/agent_auth.py` — task B's implementation, compact and
  self-contained, useful pattern reference if extending instance-scoping elsewhere.
