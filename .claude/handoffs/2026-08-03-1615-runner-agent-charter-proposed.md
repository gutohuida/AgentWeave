# Handoff: Runner/agent/charter separation proposed

**Date:** 2026-08-03T16:15:00+01:00 · **Branch:** hub-native-experience · **HEAD:** 9001204
**Agent:** Claude Sonnet 5 (Claude Code)
**Previous handoff:** .claude/handoffs/2026-08-03-1153-single-runtime-archived.md
**Status:** chunk complete — proposal only, no implementation started

## Goal

Complete the entire Hub-native-experience umbrella, one independently-proposed successor at a
time, per the slice table in
`openspec/changes/archive/2026-08-02-agent-conversation-workspace/design.md`.

## Current state

**Two things happened this session, in order:**

1. **A same-directory concurrent-write overlap, now explained and closed.** This session resumed
   from `.claude/handoffs/2026-08-03-0245-agent-capability-plane-closed.md` (which recommended
   "single-runtime" as next and said it was not yet started) and began redoing single-runtime's
   phase 3 (spec reconciliation) from scratch. Partway through, HEAD moved twice underneath this
   session — commits `a677935` ("single runtime phase 3: reconcile specifications") and `c31b3df`
   ("single runtime phase 4: verify and archive") landed while this session was still editing files,
   made by **a separate agent session** ("Codex gpt-5.6-sol", per its own handoff at
   `.claude/handoffs/2026-08-03-1153-single-runtime-archived.md`) operating in the **same working
   directory** on disk. **The user has since clarified they personally launched that Codex session
   to keep the work moving after this session ran out of context/tokens — it was a deliberate
   continuation, not an unexplained or automated spawn, and the user is in direct control of when
   further sessions are started.** This session's uncommitted edits to `openspec/specs/*.md` were
   apparently swept into Codex's `a677935` commit (the diff is nearly identical to what this session
   was independently producing from the same delta spec files) — git tree came back clean, 390 CLI
   tests passed, `openspec validate --all --strict` was 18/18. No data was lost. The one real
   takeaway to carry forward: two agent CLIs writing the same working tree at once can silently
   fold one session's uncommitted edits into another's commit — harmless here because the edits
   happened to converge, but worth confirming single-agent state before starting the next
   successor's *implementation* phase, since a collision there would be higher-stakes than a
   spec-sync redo. Confirmed before continuing: only one `claude` process running (this session,
   PID 20160), no `codex` process, no extra git worktrees, HEAD stable at `c31b3df` before this
   session's own commit.
2. **Proposed the next successor.** `single-runtime` was already fully done (implemented, tested,
   live-verified, spec-synced, archived at `openspec/changes/archive/2026-08-03-single-runtime/`,
   by the concurrent Codex session — not this one) by the time the incident above was resolved, so
   this session's own remaining contribution was to pick and propose the *next* umbrella successor:
   **runner/agent/charter separation**. Investigated the current role system first (see Key
   decisions), then ran `openspec new change` + wrote all four artifacts (proposal, design, specs,
   tasks) by hand, following the `openspec-propose` skill's per-artifact instructions. Committed as
   `9001204`. **No implementation has started** — tasks.md phase 0 (data model) is the first
   unchecked task.

The umbrella itself remains open (per its own closeout note, archives only once every phase 9–16
successor is complete). Per Codex's handoff, archived successors so far: conversation workspace,
accounting and budgets, agent capability plane, composer intelligence, single runtime. This
session added the proposal (not yet implementation) for runner/agent/charter separation.

## Files touched

- `openspec/changes/runner-agent-charter-separation/.openspec.yaml` — scaffold, via `openspec new
  change`.
- `openspec/changes/runner-agent-charter-separation/proposal.md` — why/what/capabilities/impact;
  finished.
- `openspec/changes/runner-agent-charter-separation/design.md` — Context/Goals-NonGoals/Decisions
  (Hub-DB-backed Runner+Charter tables, one-time seed from bundled role guides, one charter per
  agent, `context_builder.py` deleted not adapted)/Risks/Open Questions; finished.
- `openspec/changes/runner-agent-charter-separation/specs/runner-registry/spec.md` — new capability,
  4 ADDED requirements; finished.
- `openspec/changes/runner-agent-charter-separation/specs/agent-charter/spec.md` — new capability, 4
  ADDED requirements; finished.
- `openspec/changes/runner-agent-charter-separation/specs/agent-context-onboarding/spec.md` — 2
  MODIFIED requirements (role→charter terminology in "Layered project and role context" and "Role
  context lookup compatibility"); finished.
- `openspec/changes/runner-agent-charter-separation/tasks.md` — 6 phases (data model, runner
  registry, agent charter, spec reconciliation, delete legacy role system, regression+docs+archive);
  finished, all unchecked (`- [ ]`) — no implementation done.
- All 7 files above are committed in `9001204`.

**Not touched by this session** (left alone as pre-existing, unrelated untracked files present
before this session started — visible in every `git status --short` output above):
`src/agentweave/templates/skills/handoff.md`, `src/agentweave/templates/skills/resume.md`,
`tests/test_handoff_resume_templates.py`. If these matter, they belong to whatever session created
them, not this one — do not assume this handoff explains them.

## Key decisions

- **Investigated the current role system before proposing**, per the previous handoff's own
  "verify memories against current code before trusting them" instruction: confirmed
  `agentweave roles add/set/available` no longer exists in `cli.py` (deleted by single-runtime's
  phase 1+2), but `src/agentweave/roles.py`'s file-based assignment functions
  (`add_role_to_agent`/`set_agent_roles`/`load_roles_config`) still exist with zero surviving
  caller that writes `.agentweave/roles.json` — role *assignment* is permanently inert in the
  shipped product right now. Role *content* still partially works via
  `hub/hub/api/v1/agents.py::_load_role_content`'s bundled-template fallback tier
  (`hub/data/roles/*.md`), independent of the dead local-file tiers. Confirmed zero "charter"
  references anywhere in `.py` files despite `agent-tool-surface`'s shipped spec already promising
  an agent "its charter" at turn start.
- **Charter and Runner as Hub DB tables**, not hardcoded dicts or config files — mirrors the
  `project-instructions` precedent (moved from local file to Hub DB + UI editor in an earlier
  successor). See design.md's Decisions section for the alternative considered (hardcoded runner
  dict) and why it was rejected.
- **One-time seed of charters from the existing 21 bundled role guides** (`hub/data/roles/*.md`) on
  first boot after this change ships, so authored content isn't lost even though the mechanism
  changes. Not an ongoing fallback tier — the seed runs once, then the old files are deleted in
  tasks.md phase 4.
- **One charter per agent, no composition**, and **`context_builder.py` deleted entirely, not
  adapted** — both explicit Non-Goals/Decisions in design.md, with alternatives considered and
  rejection reasons recorded there (do not re-litigate without reading design.md first).
- **Did not create a delta spec for `agent-tool-surface`** despite the proposal initially listing it
  as a Modified Capability — on inspection its "Hub supplies state; the tool surface carries intent"
  requirement's wording about "charter" doesn't need to change (it's already correct), only the
  implementation catching up to it does. Fixed the proposal.md's Modified Capabilities section to
  reflect this before committing.

## Constraints and user directives (verbatim, still binding)

> "I want you to work on the entire umbrella project with the same parameters that we discussed
> previously"

> "Ignore the aw-spec skills. I'm using openspec only."

> "At the end of every implementation run handoff aaand spawn a new run with the skill resume."

> [this session, after the Codex overlap was found] "I launched it to continue on your work because
> I ran out of token. ... I'm in control right now" — the user personally launches follow-on
> sessions (Codex or otherwise) when a session runs out of context; it is not automated. Still worth
> confirming single-agent state before an implementation phase, but there is no unexplained spawn to
> chase down.

No root AgentWeave state; live product testing only in `testbed/`. Never mark a task done from a
plan alone — this session's runner-agent-charter-separation change is a **proposal only**; nothing
in it should be treated as implemented.

## Dead ends

- This session's own attempt to redo single-runtime's phase 3 (spec sync) was **wasted effort** —
  another session had already done it. If a `/resume` ever again finds HEAD has moved past what the
  loaded handoff describes, stop and re-diff before continuing; don't trust a handoff's "not yet
  started" claim without a fresh `git log` first. (This session did check, but only once, before
  starting — the second HEAD movement happened *during* the work and wasn't caught until a `git
  status`/`Edit` call surfaced a "file does not exist" error. Consider checking `git rev-parse HEAD`
  again immediately before any commit, not just at session start, in case the user has started a
  follow-on session elsewhere in the meantime.)

## Verification

- `openspec validate --all --strict` → 19/19 passed (18 pre-existing + the new
  `runner-agent-charter-separation` change), after this session's proposal was written.
- No implementation exists yet for this change, so no CLI/Hub/frontend tests were run against it —
  there is nothing to test. The 390-CLI-tests-passed / 18-openspec-passed numbers reported earlier
  in this session were verifying the *single-runtime* state left by the concurrent Codex session,
  not any work from this session.
- Confirmed only that no other agent process was running *at the moment checked* (one `claude`
  process, PID 20160, no `codex` process, single git worktree). The user controls when a follow-on
  session (Codex or otherwise) is launched, so this is a point-in-time fact to re-check at the start
  of each session, not a standing guarantee.

## Git state

Branch `hub-native-experience`, HEAD `9001204` ("Propose runner/agent/charter separation"). Tree
clean except the three pre-existing untracked files noted above (not part of this session's work).

## Next steps

1. **Before starting any implementation**, confirm again that no other agent session is active on
   this repo — repeat the process/worktree check from this session (`Get-Process | Where-Object {
   $_.ProcessName -match 'codex|claude' }`, `git worktree list`, `git status --short`, `git log -1`)
   immediately before writing any file. The user launches follow-on sessions manually when a prior
   one runs out of context, so this is a quick sanity check, not an investigation.
2. Start `openspec/changes/runner-agent-charter-separation/tasks.md` phase 0 (data model): write
   failing tests for the new `Runner`/`Charter` SQLAlchemy models and `Agent.runner_id`/`charter_id`
   columns in `hub/tests/`, per task 0.1, before touching `hub/hub/db/models.py`.
3. Work the successor's phases the same way as every prior one: tests precede implementation, commit
   and hand off every verified phase, verify against spec scenarios not intent.

## Open questions for the user

None.

## Read on resume

- openspec/changes/runner-agent-charter-separation/proposal.md (why + what + capability list)
- openspec/changes/runner-agent-charter-separation/design.md (the Hub-DB-table decision, seed-once
  decision, and the open question about carrying `RUNNER_CONFIGS` flags into seeded runners)
- openspec/changes/runner-agent-charter-separation/tasks.md (phase 0 is the first unchecked task)
- src/agentweave/roles.py (the module phase 4 deletes — re-grep its callers before deleting; the
  design doc's caller list may be stale by then)
- hub/hub/api/v1/agents.py (`_load_role_content` at line 622, `_render_hub_agent_context` at line
  737 — both get rewired in phase 2)
