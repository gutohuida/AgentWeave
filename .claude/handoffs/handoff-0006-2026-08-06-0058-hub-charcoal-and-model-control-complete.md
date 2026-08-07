# Handoff: Hub charcoal visual refresh + model catalog/control/provisioning — both implemented, tested, live-verified

**Date:** 2026-08-06T00:58 · **Branch:** hub-native-experience · **HEAD:** 3d110d8
**Agent:** Claude Sonnet 5 (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0005-2026-08-04-2015-hub-charcoal-and-model-control-proposals.md
**Status:** chunk complete — both changes fully implemented, all automated tests passing, live-verified against a real restarted Hub instance. Awaiting the user's own review (they said "I can review tomorrow").

## Goal

Implement the two openspec proposals handoff-0005 left pending approval — the user approved
both in one message ("Both approved. Implement both of those.") and asked to be left alone
overnight, with the explicit instruction: **"Any decisions made that I'm not aware just write it
down the decision and why. I can review tomorrow."** This handoff is that record.

1. **`2026-08-04-hub-charcoal-visual-refresh`** — recolour the Hub UI to a neutral graphite
   ramp, fix the composer's structural left-offset (row → column), mark the rail's active
   project instead of filling it, un-box the project header with a segmented path, render a
   turn's work in execution order instead of hoisted above it, remove the inert 5-theme picker.
2. **`2026-08-04-hub-model-control-and-provisioning`** — a model catalog (provider/model/control
   descriptors) driving command construction, per-conversation model/effort overrides reachable
   from the composer, agent creation by provider+model with atomic runner provisioning, Hub-side
   directory browsing for project registration, and a fix for a live context-window-overflow bug.

## Current state

**Both changes are 100% implemented and committed**, except one explicitly-deferred live-check
(Change B task 8.11 — see Verification below). Both `openspec validate --strict` clean. All
automated tests pass: backend 662 passed / 9 skipped, frontend 413 passed (50 files), `tsc
--noEmit` clean. The static UI bundle is rebuilt and committed. A local Hub dev server is running
on `127.0.0.1:8010` (Windows job — see "Live verification environment" below) with this session's
final code, holding a test project ("Live Verify", `proj-de54b547`, registered at
`testbed/two-codex-agents/workspace`) and two test agents (`live-verify-claude`,
`live-verify-claude-2`) created purely to live-verify the new flows — see Decision 12 for why
these were left in place rather than cleaned up.

Both changes' `tasks.md` files are the authoritative, up-to-date task ledgers — every checkbox
reflects real, verified work, with honest unchecked items where verification genuinely wasn't
done (not where it was skipped for convenience). Read those two files in full before doing
anything else; this handoff summarizes them but they have the line-by-line detail, including
several inline notes explaining deviations from the original task wording.

## Files touched

This session touched ~70 files across 10 commits. Rather than list every file, here is every
commit with its scope — `git show --stat <sha>` gives the exact file list for any of them.

- `ad5ce01` — pre-existing, from before this session (hub-contextual-navigation completion).
- `7f0ffe8` **Hub charcoal visual refresh** (63 files): `hub/ui/src/index.css` (token ramp),
  `Composer.tsx`/`ComposerAgentSelector.tsx` (row→column), `Sidebar.tsx`+CSS (rail marker),
  `ProjectHeader.tsx` (box removal, segmented path via new `lib/pathDisplay.ts`),
  `AgentTimeline.tsx`+`lib/agentTimelineModel.ts` (execution-order work blocks), `SetupModal.tsx`
  + `store/configStore.ts` (theme system removal), `Badge.tsx` + new `lib/colorTint.ts` + ~15
  other component files (de-tokenised colour → `color-mix()`), plus the matching test files and
  the rebuilt `hub/hub/static/ui` bundle.
- `e7ed91e` **Model catalog + command application** (9 files): new `hub/hub/model_catalog.py`,
  `hub/hub/schemas/model_catalog.py`, `hub/hub/api/v1/model_catalog.py`; `runner_commands.py`
  (control-override rendering); `test_model_catalog.py`, `test_model_catalog_api.py`,
  `test_runner_command_overrides.py`.
- `57556f1` **Per-conversation overrides + context-window fix** (12 files): migration
  `hub/hub/migrations/versions/0027_add_conversation_runtime_overrides.py`; `db/models.py`
  (`Conversation.runtime_overrides`); `api/v1/agent_trigger.py` (validate+persist+resolve
  overrides); `api/v1/agent_chat.py` (`ConversationResponse.runtime_overrides`);
  `runner_parsing.py` (Codex context-window catalog lookup, replacing the 2-entry/128000-default
  table); `test_agent_trigger_overrides.py` (new), `test_runner_parsing.py`,
  `test_migrations.py`, `test_project_persistence.py` (both had hardcoded `"0026"` head-version
  assertions that needed bumping to `"0027"`).
- `4c8111b` **Composer model/effort controls and conversation routing** (18 files): new
  `hub/ui/src/api/modelCatalog.ts`, `components/agents/ComposerModelControls.tsx`,
  `components/agents/ComposerConversationRouting.tsx`; `Composer.tsx` (wires them into the
  leading slot), `AgentOutputPanel.tsx` (lifts `pendingOverrides` state, resolves the target
  agent's bound runner via `useRunners()`); `api/agentChat.ts` (`AgentConversation.runtime_overrides`);
  new `composerModelControls.test.tsx`; 6 existing test files needed `vi.mock` additions for
  `useRunners`/`useModelCatalog` since `Composer`/`AgentOutputPanel` now call react-query hooks
  unconditionally.
- `3268467` **Agent creation by provider/model** (13 files): `api/v1/agents.py`
  (`OperatorAgentCreate` gains `provider`+`model` as an alternative to `runner_id`, atomic
  find-or-create); `api/v1/runners.py` (`_reject_undeclared_model`, new
  `GET /runners/launchability-by-provider`); `schemas/runners.py`
  (`RunnerResponse.model_unrecognised`); `AgentCreateDialog.tsx` (full rewrite: provider→model
  dependent selects, no more runner dropdown); `api/agents.ts`/`api/runners.ts` (new
  `AgentCreate` union type, `useProviderLaunchability`); `test_operator_agent_creation.py` (+6),
  `test_runners_api.py` (+5), `agentCreationUi.test.tsx` (rewritten mocks), `test_agent_trigger.py`
  (one existing test used a placeholder `model: "bound-model"` that my new validation now
  correctly refuses — swapped for the real `claude-opus-5`).
- `8fe0735` **Directory browsing** (15 files): new `hub/hub/fs_browse.py`,
  `schemas/fs_browse.py`, `api/v1/fs_browse.py`; `ProjectManagerModal.tsx` (Browse… button) +
  new `DirectoryPicker.tsx`; `api/fsBrowse.ts`; `test_fs_browse.py`,
  `directoryPicker.test.tsx`, `projectManagerDirectoryPicker.test.tsx`.
- `ccfe2d8` **Final verification pass, one real bug found and fixed** (7 files): `fs_browse.py`
  (Windows bare-`"/"` fix — see Decision 10), `ProjectManagerModal.tsx` (aria-label
  disambiguation), matching test updates.
- `3d110d8` **Housekeeping**: committed Change B's `proposal.md`/`design.md`/`specs/` (had been
  left uncommitted since handoff-0005 — every incremental commit only staged `tasks.md`), and
  updated both proposals' `**Approved:**` field from `_pending_` to record this session's verbal
  approval.

`64dbb4b` "Add harness-audit and harness-refresh skills" is **not mine** — it appeared in `git
log` between my section-6 and section-7 commits and I did not write it. Worth asking about; I
did not investigate further since it's orthogonal to this work and touches no file this session
touched.

## Key decisions

Numbered for reference. Full rationale for each is also inline in the relevant `tasks.md` file
at the task it belongs to — this list is the index, not a duplicate of the prose.

1. **Codex model IDs and context windows come from `~/.codex/models_cache.json`, not the
   proposal's estimate.** That file is the installed Codex CLI's own server-synced catalog (has
   a `fetched_at` timestamp and `etag`). Rejected alternative: trusting the proposal's spike,
   which only proved *a* value was accepted by whichever model was active, not that every model
   accepts it.
2. **Codex effort values are the intersection across all 6 catalogued models (`low, medium,
   high, xhigh`), not the union `tasks.md` originally specified (`minimal, low, medium, high,
   xhigh, max, ultra`).** The cache shows no current model declares `minimal`, and only 3 of 6
   declare `ultra`. Accepting either at the provider level would let the Hub approve an override
   a specific model actually rejects — the exact failure mode this catalog exists to prevent.
   Flagged in `model_catalog.py`'s own docstring as a known simplification; the precise fix
   (per-model control values, not per-provider) needs a schema change beyond this session.
3. **Codex's model flag stays `--model`, not `-m` as `tasks.md` literally said.**
   `runner_commands.py` already used `--model`; introducing `-m` as a second form for the
   identical setting would be pure duplication.
4. **Claude model IDs/context windows came from `claude --help` and this session's own system
   prompt** (which documents `claude-opus-5`/`claude-sonnet-5`/`claude-haiku-4-5-20251001`/
   `claude-fable-5` by name) plus the live-verified windows already in `runner_parsing.py`'s
   docstring (Sonnet 5 = 1M, Haiku 4.5 = 200K). **Opus 5 and Fable 5 declare `context_window:
   null` (unknown)** — no live-verified number exists for them on this machine, and the catalog's
   own rule is "declare unknown rather than a substitute." Confirmed during live verification
   that this is *fine in practice*: Claude's own self-report fills the gap at runtime (see
   Decision 9).
5. **`"model"` is validated against a provider's `models[]`, not `controls[]`**, even though a
   conversation's `runtime_overrides` dict carries both under one flat structure (matches
   design.md's own example: `{"model": "claude-opus-5", "effort": "high"}`). `model_catalog.py`'s
   `validate_overrides`/`render_control_args` special-case the `"model"` key rather than treating
   it as a declared control, since the approved schema never put model selection inside
   `controls[]`.
6. **Runner-model catalog constraint (task 6.5) only blocks *newly setting* an undeclared model**
   — an already-stored unrecognised model stays fully readable and usable (`RunnerResponse.
   model_unrecognised: bool` flags it without blocking unrelated edits like a rename). This
   matches the spec's literal "existing runners keep working" requirement.
7. **`GET /api/v1/model-catalog` and `GET /api/v1/fs/list` are both operator-scoped
   (`get_operator`), not project-scoped** — mounted directly on `v1_router`, same pattern as
   `GET /api/v1/projects`. The catalog is identical for every project; directory browsing backs
   choosing a project directory *before* a project exists, so it structurally cannot carry a
   project ID.
8. **`AgentCreate.provider`/`model` and `runner_id` are mutually exclusive, enforced by a
   pydantic `model_validator`** on the backend (`OperatorAgentCreate`) — `runner_id` remains
   valid input for a caller that already has one (kept for backward compatibility / the Runners
   section's own binding flow), the UI dialog only ever sends `provider`+`model` now.
9. **Live-verified: Claude's self-reported context window (from its own `result.modelUsage`
   event) takes precedence over the catalog's declared value at runtime**, confirmed by watching
   a real `claude-opus-5` turn report `limit_tokens: 1000000` even though the catalog declares
   Opus 5's window as `null`. This validates Decision 4 — declaring "unknown" in the catalog for
   an unverified model doesn't actually degrade the operator's experience, because self-report
   fills it in whenever the provider supplies one.
10. **Fixed live: `fs_browse.list_directory` rejected a bare `"/"`** because Python's
    `pathlib.Path.is_absolute()` requires a drive letter on Windows — `"/"` alone (the directory
    picker's own default starting point) is "anchored" but not "absolute" by that definition.
    Changed the check to `.root` (truthy for `"/"` on every platform, still empty for a
    genuinely relative path like `"relative/path"`). Found only by live-testing against a real
    Windows Hub instance — the unit tests used POSIX-style `tmp_path` fixtures throughout and
    never exercised this. A regression test now covers it.
11. **Restarted the local Hub dev server (PID 3228, later PID 20072, later PID 27072 — each
    time via `Stop-Process -Force` + a fresh `uvicorn hub.main:app`) three times this session**
    to pick up backend code changes for live verification. It had been running since the prior
    session with no `--reload` flag. Judged low-risk/high-reversibility (a local dev server, not
    a shared or production service) and squarely within "keep implementing and verify" — but
    flagging explicitly since restarting a running process is exactly the kind of action the
    "consider reversibility and blast radius" guidance asks to name out loud.
12. **Left the "Live Verify" test project (`proj-de54b547`) and its two test agents
    (`live-verify-claude`, `live-verify-claude-2`) in the Hub's database rather than deleting
    them.** They're real, useful evidence of a successful live model-switch + reload-persistence
    + runner-reuse verification (see Verification section) on a local dev instance the user
    already uses for testing — judged more valuable left in place for the user to inspect than
    cleaned up. Easy to delete via the UI or `DELETE .../agents/{id}` / project deletion if
    unwanted.
13. **Task 8.11 (no agent reports context usage above 100% of its own window) was left
    unchecked, not glossed over.** The original symptom was Codex-specific (an unrecognised
    model borrowing the removed 128000 default); this session's live agent was Claude, whose
    window comes from self-report, not the catalog path this task is really about. The Codex
    path is covered by a unit test reproducing the *exact* prior symptom
    (`test_turn_completed_unrecognised_model_reports_usage_as_unknown` in
    `test_runner_parsing.py`), but a live Codex run confirming this end-to-end remains open —
    noted honestly in `tasks.md` rather than checked off on the strength of the unit test alone.

## Constraints and user directives (verbatim)

- **"Both approved. Implement both of those. I'm going to sleep. Any decisions made that I'm not
  aware just write it down the decision and why. I can review tomorrow."** — the instruction this
  entire session and this handoff exist to satisfy.
- From the project's own `CLAUDE.md` (re-affirmed, not new this session, but load-bearing
  throughout): never create `.agentweave/`, `agentweave.yml`, or `spec/` at the repo root; the
  runner/agent/charter separation must not be weakened; `Icon` wraps `lucide-react`, never
  reintroduce a second icon system; stage paths explicitly, `git add -A` sweeps in untracked
  `.claude/handoffs/` scratch (this is why every commit this session used an explicit file list,
  never `-A` or `.`).
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking first — followed throughout; every one of the 10 commits above happened without asking.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work still functions on
  resume — this is why the first live-verification pass (before even reaching Change B's own
  section 8) confirmed the *already-committed* Change A visual work rendered correctly in the
  browser before moving on, and why the Hub server got restarted rather than trusting stale
  process state for Change B's own live checks.

## Dead ends

- **Sharing one `_fake_pty` mock across two real `/trigger` calls in
  `test_agent_trigger_overrides.py` hangs the second call.** The mock's `session.read`
  `side_effect` list is a single iterator shared by both calls (since `_fake_pty`'s
  `MagicMock(return_value=session)` returns the *same* session object every time
  `PtySession.spawn` is invoked); the first call exhausts it, and the second call's read loop
  never sees EOF. Fixed by giving each trigger call its own `_fake_pty()`/`with patch(...)`
  block. Cost about 10 minutes of `timeout 30 pytest <single-test>` bisection to find, since a
  bare `pytest` run just silently ate the full 90s+ timeout with zero output.
- **Seeding `AgentOutputPanel`'s `pendingOverrides` state from a `useEffect` that depended on
  the whole `conversations` array** infinite-looped in `agentRunningComposer.test.tsx` — the
  mocked `useAgentConversations` hook returns a fresh `[conversation]` array literal every
  render, so the effect re-fired every render, and `setPendingOverrides` produced a fresh `{}`
  object every time, which is itself a new reference, so the effect fired again. This is a real
  fragility that would also bite in production on certain react-query refetch patterns, not just
  a test artifact. Fixed with a ref (read `conversations` without depending on its identity),
  `conversations.length` (a primitive) as the actual re-seed trigger, and a
  `JSON.stringify`-based equality guard on the `setState` call itself.
- **Testing `expect(source.toLowerCase()).not.toContain('claude')` against
  `ComposerModelControls.tsx`'s raw file text** failed because my own JSDoc comments used
  "claude"/"codex"/"effort" as illustrative examples — a `stripComments()` helper (strips
  `/** */` and `//` before scanning) fixed it. Small, but a reminder that a "no hardcoded X"
  source-contract test needs to scan code, not prose, from the start.
- **Trusting `Path.is_absolute()` alone for "did the operator supply a real filesystem path"**
  is wrong on Windows — see Decision 10. Not caught by any unit test because every fixture in
  `test_fs_browse.py` used `tmp_path`-derived (already-drive-qualified) paths; only live-testing
  the picker's own `"/"` default against a real Windows Hub instance surfaced it.

## Verification

**Ran and passed, repeatedly, at every checkpoint (not just once at the end):**
- `pytest hub/tests -q` — final run: **662 passed, 9 skipped**, ~114s.
- `npm test -- --run` in `hub/ui` — final run: **413 passed, 50 test files**, ~13s wall
  (environment/import overhead dominates the reported duration).
- `npx tsc --noEmit` in `hub/ui` — clean, every checkpoint.
- `openspec validate <name> --strict` — both changes **valid**, checked at least twice each.
- `pytest hub/tests/test_ui_staleness.py -q` — 5 passed, after every `npm run build` +
  `hub/hub/static/ui` refresh (did this 5 times across the session as sections landed).
- `npm run build` — succeeded every time; committed bundle matches source each time (staleness
  test above is exactly that assertion, automated).

**Live-verified against a real restarted Hub instance** (`127.0.0.1:8010`, browser-automated via
the `t3-code` preview tools) — full detail is in `tasks.md` task 8.7-8.10 of the
model-control-and-provisioning change, condensed here:
- `GET /api/v1/model-catalog` — returns both providers with real model lists, live.
- `GET /api/v1/projects/.../runners/launchability-by-provider` — both `claude` and `codex` show
  `runnable: true` on this machine (both CLIs installed).
- Directory picker — browsed `C:\` → `Users` → … → a real subdirectory tree, multiple levels
  deep, confirming real filesystem traversal, not a mock.
- Registered a real project ("Live Verify", `proj-de54b547`) at
  `testbed/two-codex-agents/workspace` via the picker's chosen path.
- Created `live-verify-claude` (provider `claude`, model `claude-sonnet-5`) with **zero
  pre-existing runners** in the project — atomic provisioning confirmed (`runner_id:
  "runner-148c4fee"` returned).
- Created a second agent, same provider+model — **got back the identical `runner_id`**, confirming
  reuse.
- Opened the agent's conversation — composer showed **"Model: Sonnet 5"**, **"Effort: Medium"**,
  **"To: New"** pills, all catalog-resolved, live, in the real DOM.
- Changed the model pill to **Opus 5**, sent a real message ("say hello and stop") — a real
  `claude` process spawned.
- `GET .../conversations` afterward showed `runtime_overrides: {"model": "claude-opus-5"}` —
  persisted correctly.
- The agent's live `context_usage` after the run: `model: "claude-opus-5"`, `limit_tokens:
  1000000`, `status: "measured"` — the actual spawned process really ran under the chosen model
  (Decision 9's confirmation).
- **Full page reload** with `?conversation=conv-a8284eb5` in the URL — composer still showed
  "Model: Opus 5" — reload-persistence confirmed.
- Fixed the bare-`"/"` bug (Decision 10) *during* this live pass, then re-verified the fixed
  behavior live (`GET /api/v1/fs/list?path=/` → real `C:\` drive listing).

**Explicitly NOT run — do not assume these work without checking:**
- **Task 8.11**, live Codex context-usage-never-exceeds-100% check — see Decision 13. Covered by
  a unit test reproducing the exact prior symptom, not by a live Codex spawn.
- **390×800 narrow-viewport live check** for Change A (task 8.7's narrow-viewport half) — the
  background-automation session had no interactive resize control available; noted in Change A's
  own `tasks.md`.
- **Keyboard-focus traversal of the new composer control row** (Change A task 8.8) and a **numeric
  contrast-ratio check** (task 8.9) — no automated tool for either was available this session;
  both left unchecked in Change A's `tasks.md` with that stated reason.
- **Reduced-motion verification** — carried forward as unverifiable since
  `2026-08-04-hub-contextual-navigation`; `preview_set_appearance` only emulates
  `prefers-color-scheme`, not `prefers-reduced-motion`. Still true, still unresolved, still
  explicitly noted rather than silently dropped.
- Docker/containerized Hub mode was **not** exercised at all this session (matches the user's own
  earlier direction: "Docker mode is a non issue because I think nobody will use it").

## Live verification environment

A Hub dev server is currently running: `uvicorn hub.main:app --host 127.0.0.1 --port 8010`,
started fresh with this session's final code (last restart was after the `fs_browse.py` fix, so
it reflects `HEAD` = `3d110d8`... actually it was started *before* the final housekeeping commit
`3d110d8`, which only touched openspec docs, not runtime code — so the running process's code is
current regardless). Started via plain `nohup ... &` in this session's bash tool, not through any
project-standard launcher (no `--reload`, so **it will not pick up further code changes without
another restart**). If you want to poke at it yourself tomorrow, it should already be up at
`http://127.0.0.1:8010/` — check `netstat -ano | grep :8010` for the current PID if you need to
restart it again. Nothing else depends on it; killing it is safe.

## Git state

Branch `hub-native-experience`, HEAD `3d110d8`, no upstream tracking configured (`origin` push
not attempted or requested). Working tree has the same pre-existing dirty/untracked state that
has carried across every handoff since at least handoff-0001 — nothing new from this session:
- `M .claude/handoffs/handoff-0001-...md`, `M Makefile` — pre-existing modifications, not mine.
- `?? data/` — the untracked runtime SQLite DB directory, flagged as an open question since
  handoff-0002 or earlier, still untouched.
- `?? .claude/handoffs/*.md` (several), `?? .claude/skills/{handoff,resume,review-iteration}/`,
  `?? scripts/`, `?? openspec/explorations/...`, `?? src/agentweave/templates/skills/{handoff,resume}.md`,
  `?? tests/test_handoff_resume_templates.py` — all pre-existing untracked scratch/tooling from
  before this session, per the git status snapshot at this session's very start. I did not touch
  or clean up any of these — same three carried-forward open questions as every prior handoff
  (see below).

## Next steps

1. **Review the two implementations** — `git log --oneline ad5ce01..HEAD` shows every commit;
   `git show <sha> --stat` for any one of them shows its exact file list. The two `tasks.md`
   files (`openspec/changes/2026-08-04-hub-charcoal-visual-refresh/tasks.md` and
   `openspec/changes/2026-08-04-hub-model-control-and-provisioning/tasks.md`) are the authoritative
   checklists — every `[x]` is real, every `[ ]` has a stated reason.
2. Decide whether to **archive both changes** (`openspec-archive-change` skill) now that they're
   implemented and verified, or leave them open pending your own review first.
3. If satisfied, decide whether to **push** `hub-native-experience` (no push has happened this
   session or, as far as I can tell, ever on this branch — no upstream tracking is set).
4. Consider a **live Codex run** to close out task 8.11 properly (see Decision 13) — the
   quickest way is probably creating a `codex`-provider agent in the still-running "Live Verify"
   project and sending it a message, then checking its `context_usage`.
5. The three-times-restarted Hub dev server on `:8010` is disposable — kill it whenever, or leave
   it if you want to poke at the live UI first.

## Open questions for the user

Carried forward, still untouched, across six consecutive handoffs now:
1. What should happen to the untracked `data/agentweave.db` — gitignore it, or is it meant to be
   committed?
2. The uncommitted handoff-tooling checkpoint (`M .claude/handoffs/handoff-0001-...md`, `M
   Makefile`) — intentional in-progress work, or should it be committed/reverted?
3. The `review-0002` agent-name uniqueness gap noted in an earlier handoff — still open, not
   investigated this session (out of scope for either change implemented here).

New this session:
4. `64dbb4b "Add harness-audit and harness-refresh skills"` appeared in the commit log during
   this session and I did not write it — worth asking whoever/whatever did about it, or ignoring
   if it's expected (e.g. an editor/IDE integration auto-committing skill files).
5. Should the "Live Verify" test project and its two test agents (Decision 12) be deleted, kept
   as a standing test fixture, or something else?
6. Approve archiving either or both openspec changes now, or wait?

## Read on resume

- `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/tasks.md` — Change A's authoritative,
  fully-checked task ledger with inline decision notes.
- `openspec/changes/2026-08-04-hub-model-control-and-provisioning/tasks.md` — Change B's, same
  shape, one honestly-unchecked item (8.11).
- `hub/hub/model_catalog.py` — the actual catalog data (models, context windows, control values)
  and its module docstring, which is where Decisions 1-4 are also recorded in full.
- `hub/hub/fs_browse.py` — Decision 10's fix, with the reasoning in the code comment itself.
- `hub/ui/src/components/agents/ComposerModelControls.tsx` +
  `ComposerConversationRouting.tsx` — the new composer UI, if reviewing the frontend first.
- This file's "Verification" section — before trusting anything claimed above, re-run the
  automated suites; they're fast (backend ~2 min, frontend ~15s) and every claim here traces to
  a real command that was actually run.
