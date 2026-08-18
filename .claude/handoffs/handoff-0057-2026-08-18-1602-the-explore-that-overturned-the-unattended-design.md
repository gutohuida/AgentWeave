# Handoff: the explore that overturned the unattended design, and PR #3 green

**Date:** 2026-08-18T16:02:54+01:00 · **Branch:** `autonomous/2026-08-18-loops-and-side-panels` · **HEAD:** `18ad6a6`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0056-2026-08-18-1326-two-specs-written-nothing-built.md`
**Status:** chunk complete. Nothing blocked. **PR #3 is open, 9/9 CI green, and deliberately not merged.**

> The operator's PC restarted between this handoff being requested and being written. Every fact
> below was re-verified against the live repo *after* the restart, not recalled.

## Goal

Run a proper openspec explore on the side panel — with the operator present — because the existing
exploration and change were both written by unattended firings and had been read by nobody. Then
reconcile what the conversation settled into the two openspec changes, and get the branch landable.

The *why*: handoff 0056 flagged that `2026-08-18-one-shell-three-panels` was "41 tasks and 14
requirements of UI design written unattended, and the operator has strong opinions about this
surface." That turned out to be exactly right — **six of its decisions were overturned.**

## Current state

**The explore is complete.** Every thread opened was settled with the operator present. Three
documents written, two openspec changes reconciled, branch pushed, CI green, branches cleaned.

**PR #3** — https://github.com/gutohuida/AgentWeave/pull/3 — `autonomous/2026-08-18-loops-and-side-panels`
→ `master`. State `OPEN`, `MERGEABLE`, **all 9 checks SUCCESS** (build, hub-test, ui-test, and the
6-way OS/Python matrix). **Not merged** — the operator has reviewed none of the ~5,900 lines in it,
and merging is the one outward-facing step never authorised.

**Master is still `10c5ee6`** and contains none of this work.

**Still zero implementation.** Both changes are specs. The branch's only executable content is the
three fixes verified in the previous session plus one formatting fix. Task counts are now ~146 open
across the two changes, 0 done.

## Files touched

**Committed this session** (`8716dbe`, `68a3961`, `33c8d75`, `85570b4`, `18ad6a6`):

- `openspec/explorations/2026-08-18-the-side-panel-with-the-operator.md` — **new, 318 lines.**
  Records the whole conversation. §0 is a table of the six overturned recommendations. Finished.
- `openspec/explorations/2026-08-18-the-side-panel-family.md` — added a superseded banner at the top
  naming which six recommendations were overturned and stating its *research* is still sound.
  Finished.
- `openspec/changes/2026-08-18-a-loop-writes-its-own-queue/design.md` — appended **Addendum 2
  (D16–D21)**; also marked two stale cross-references in place (around former lines 205 and 278)
  that still pointed at the panel change for the loop view. Finished.
- `openspec/changes/2026-08-18-a-loop-writes-its-own-queue/specs/agent-loops/spec.md` — five new
  requirements: archivable-never-deletable, cannot-archive-a-running-loop, ending-state-as-a-value,
  claimed-task-is-current, project-wide-loops-listing. Finished.
- `openspec/changes/2026-08-18-a-loop-writes-its-own-queue/proposal.md` — new "What Changes" bullets
  for D16–D21; the false `**UI** — none in this change` line rewritten; the "Not building the side
  panel" Non-Goal replaced with "Not building the panel shell"; Migration updated for the new
  columns. Finished.
- `openspec/changes/2026-08-18-a-loop-writes-its-own-queue/tasks.md` — appended **Addendum 2 tasks
  B1–B8** (migration, archival, `archive_job`, summary fixes, loops index tab, loop drill-down tab,
  human-only checks, test-guide additions). Finished.
- `openspec/changes/2026-08-18-one-shell-three-panels/` — **all five files rewritten**:
  `proposal.md`, `design.md` (D1–D12), `specs/conversation-side-panel/spec.md` (13 requirements),
  `specs/spec-chat-session/spec.md`, `tasks.md` (sections 1–8). Finished.
- `spec/capabilities/project-instructions/spec.html`, `spec/capabilities/quiet-hours/spec.html`,
  `spec/changes/quiet-hours-for-agent-notifications/spec.html` — **now tracked.** Were untracked.
- `hub/tests/test_ui_build_stamp.py` — black reformat of two multi-line asserts. This is what was
  breaking CI. Finished.

**Untracked and left alone deliberately:** `hub/seed_taste_doc.py` — see Open questions.

## Key decisions

Full reasoning with rejected alternatives is in the new exploration and in Addendum 2. Condensed:

1. **The loop surface is project-wide with a loop picker, not conversation-scoped.** Grounded, not
   assumed: `Conversation` (`models.py:369-405`) has no `job_id`; the only link is
   `JobRun.conversation_id` (`:1194`); and `scheduler.py:337-343` creates a **fresh conversation per
   firing** when `session_mode="new"`, which the loop change's own D4 guarantees is always for a
   loop. *Rejected:* the unattended design's conversation-scoped tab, which would be empty in every
   conversation the operator sits in and duplicated across every firing conversation.
2. **The tab strip holds only open tabs; the plus adds one that is not open; one visible at a time.**
   *Rejected:* the unattended spec's fixed strip of three **plus** a menu specced to offer every
   panel and hide none — those are the same three items, so one affordance did nothing.
3. **Index tab → keyed detail tabs**, T3's shape (`rightPanelStore.ts:27-47`). Reopening a keyed tab
   refocuses and re-reveals (T3's `revealRequestId`, `:295`). *Rejected:* `singleton: true` on
   everything, which foreclosed the drill-down the operator asked for.
4. **Key by durable id where one exists** — `loop:<loop_id>`, `spec:<document_id>`, but
   `file:<path>`. Reason: `rename_spec_document` is agent-callable, so a `spec:<path>` tab would
   dangle on a live document. *Rejected:* path-keying everything for symmetry with T3, which
   path-keys files only because a file has no other identity.
5. **Tab configuration persists per project**, versioned, with a migration and reconciliation.
   *Rejected:* per-conversation destination state (the unattended D4/D5).
6. **Opening a file replaces the tree tab** (T3's `openFile` filters `kind === "files"`,
   `:284-286`); **the loops index deliberately does not** — a tree is a launcher, an index is a
   governance glance. The asymmetry is stated in both changes so neither is later "corrected".
7. **Nothing is deletable — loops and jobs archive.** `Loop.job_id` is `ondelete="CASCADE"`
   (`models.py:1208-1210`), `DELETE /jobs/{id}` exists (`jobs.py:482`), `delete_job` is
   agent-callable (`mcp_server.py:533`). The loop change's own **D14** already argued this principle
   while protecting only the task side of it. *Rejected:* keeping delete for bare jobs — the
   operator refused it, and it would make `delete_job`'s legality depend on a property its signature
   does not expose.
8. **Complete and archived are two different axes.** Lifecycle (running → complete | stopped) versus
   visibility (archived, operator-only, hides nothing destroys nothing). **A running loop cannot be
   archived.** `complete` becomes a real value because `stop_reason` is `Text` and `scheduler.py:102`
   writes the English string `"loop queue is empty"`, which cannot be counted or filtered.
   *Rejected:* one lifecycle with `archived` terminal — it would make an archived loop unable to say
   whether it succeeded.
9. **`delete_job` → `archive_job`, and it always produces an operator approval card regardless of
   permission posture.** `_require_agent_job_allowance` (`jobs.py:21-40`) gates on
   `project.allow_agent_jobs`, a *standing project boolean* — capability, not per-action direction.
   First MCP tool with an always-confirm rule, set deliberately.
10. **Panel-change D6 withdrawn; loop-change D13 wins.** D13 (`design.md:366-374`) had **already
    rejected by name** the exact join panel-D6 chose 20 minutes later. D13's own words: *"It should
    be one helper both callers use, not two joins."*
11. **Scope split, on the operator's instruction ("2 and 4 can be this spec"):** the panel change is
    shell + specs + files; the loop change absorbs archival + the loops index + loop drill-down.
    **The dependency inverts** — the panel change's shell now comes first.
12. **The panel change was rewritten, not amended** — its descriptor model, persistence, D6 and four
    Non-Goals were contradicted, not thinned.

## Constraints and user directives (verbatim)

> *"Loops should never be deleted. We need the information is tracking. Don't forget about the
> philosophy. Governance and traceability. We shouldn't lose information."*

> *"The job with no loop is not deletable. It's archivable"* · *"Archiving a loop is operator only"*
> · *"But the loop can be marked as complete the archivability is just to clean the UI"*

> *"Agent can archive only with the explicit direction from the user. So the mcp endpoint becomes
> archive."* · *"Complete gets a real state value"*

> *"It's a project wide interest. The loop tab I can chose which loop I want to see."*

> *"We shouldn't show all of them at all times. We add with the plus sign like t3... On the side
> panel we have only one tab active is just like a tab from a browser so to speak."*

> *"Each project we might want to have different tabs configurations."*

> *"One per loop. Tree tab plus per file tab we can apply the same for the loop. One tab with all the
> loops that exist and clicking into one opens a new tab drilling down on that loop"*

> *"The closing of a spec tab doesn't detach the document"* · *"it would be nice to navigate other
> specs while we have one spec attached"*

> *"Opening files behave like t3, loops behave like we described."*

> *"2 and 4 can be this spec"* — the scope split.

> *"do this and the do a cleanup on the branches yourself I'll tell my other agent to step down"*

Still binding from earlier sessions and `CLAUDE.md`: **"Full auto, but only on green CI"** — never
merge or release on red or unfinished CI. Never create `.agentweave/` or `agentweave.yml` at the repo
root. Use openspec, never the `aw-*` skills. Stage paths explicitly, never `git add -A`. Always
`py -3.11`. T3 source in `testbed/scratch/t3ref/` is **design reference only — study patterns, do not
copy code, do not commit it.** **Do not touch `aw-loop10`** (`proj-ff695d96`) on the dev Hub.

## Dead ends

- **A firing was running while I worked, and I nearly missed it.** The scheduled task was
  unregistered at 14:44:55, but a firing had already started at **14:42:00** (PID 10880) and — per
  the known flaw that a running firing never re-checks the heartbeat — had taken the branch on a
  49-minute-stale heartbeat. Killed at 14:45:53; it had written nothing and left no git locks.
  **Unregistering the task does not stop a firing already in flight — check for a `claude` process
  with a `-p "Continue the autonomous work session..."` command line.**
- **Two other `claude` processes exist and must NOT be killed.** `10340` and `32476` (pre-restart
  PIDs) both carried `--permission-prompt-tool` — they are **Hub-spawned agent runs**, not the
  driver's. Identify by command line via `Get-CimInstance Win32_Process`, never by name or age.
- **`git branch -d` refused `audit/2026-q2-hardening`** because it was 1 commit ahead of its *own
  upstream*, even though fully merged to master. Verified `git log origin/master..audit/...` returned
  **0** before force-deleting. Git's safety check compares against upstream, not master.
- **A bash heredoc (`cat >> file <<'EOF'`) failed** with "unexpected EOF while looking for matching
  quote" on long markdown. Used the `Edit` tool instead. Consistent with the previous handoff's note
  that complex quoting in shell breaks here.
- **My first branch-cleanup instinct — commit `hub/seed_taste_doc.py`** — would have **broken CI.**
  `ruff check src/ hub/ tests/` flags `I001` on it (`hub/seed_taste_doc.py:18`). It is invisible to
  CI only because it is untracked.
- **The handoff 0056 claim that "`CLAUDE.md` forbids committing `spec/` at the root" is false.**
  `CLAUDE.md` says the opposite twice: *"These are work product, not test output. Track and commit
  them"* (line 26) and *"`spec/` is tracked"* (Critical Rules). The files had been left untracked on
  that false basis. Now committed.

## Verification

**Ran and passed, this session:**

- `py -3.11 -m pytest hub/tests/ -q` → **2340 passed, 11 skipped, 1 xpassed** (634.93s). Baseline in
  `openspec/explorations/2026-08-17-the-hub-suite-has-never-run-clean.md` was 2130/11; the suite grew,
  nothing failed. The 1 xpassed is the pre-existing non-strict xfail at
  `hub/tests/test_agent_trigger_overrides.py:258`, untouched.
- `py -3.11 -m pytest tests/ -q` → **385 passed, 3 skipped** (19.09s).
- `py -3.11 -m pytest hub/tests/test_spec_merge.py hub/tests/test_ui_build_stamp.py hub/tests/test_ui_staleness.py hub/tests/test_migrations.py -q` → **76 passed, 2 skipped** (181.67s), run right after the rebase.
- `py -3.11 -m pytest hub/tests/test_ui_build_stamp.py -q` → **10 passed, 1 skipped**, after the black reformat.
- `npx openspec validate --changes --strict` → **10 passed, 0 failed**. Run three times: after
  writing, after the rebase, after the cross-reference fixes.
- `py -3.11 -m black --check src/ hub/hub/ hub/tests/ tests/` → **396 files unchanged** after the fix.
- `py -3.11 -m ruff check src/ hub/ tests/` → 1 error, **only** in untracked `hub/seed_taste_doc.py`.
- **GitHub Actions on PR #3 → 9/9 SUCCESS**, re-confirmed after the restart via
  `gh pr view 3 --json statusCheckRollup`. `hub-test` 7m21s, `ui-test` 1m44s, `build` 12s, plus the
  6-way matrix.

**NOT tested / not done:**

- **Nothing driven live. Again — third consecutive session.** No panel shell exists; every design
  decision is reasoned from code and from T3's recovered source, never watched in a browser.
- **Neither change is implemented.** ~146 open tasks, 0 done.
- **The operator has not reviewed the rewritten panel change or Addendum 2.**
- **No live agent turn on the trial Hub (`:8010`)** — carried unresolved from handoffs 0055 and 0056.
- **`mypy` was not run** this session (CI does not gate on it in `ci.yml`'s checked steps).
- The claim in handoff 0056 that a firing fixed `_batch_loop_summaries`' missing `"assigned"` was
  **not** verified; D21 now specs the fix regardless.

## Git state

- **Branch:** `autonomous/2026-08-18-loops-and-side-panels`, **HEAD `18ad6a6`**, **pushed** — no
  unpushed commits.
- **Dirty:** one untracked path only — `hub/seed_taste_doc.py`. Deliberate.
- **27 commits ahead of `origin/master`**; 0 behind. 28 files, +5892 / −292.
- **`origin/master` = `10c5ee6`**, unchanged.
- **The branch was rebased and force-pushed** (`--force-with-lease`). The rebase dropped two
  duplicate commits by patch-id (`05b460c`, `a8554d6` — the CI and packaging fixes already in
  master). **The pre-rebase remote history at `bffc13a` no longer exists** — it was overwritten.
- **Branch cleanup done: 16 deleted** (8 local + 8 remote), each verified merged into `origin/master`
  first: `audit/2026-q2-hardening`, `autonomous/2026-08-15-spec-flow-hardening`,
  `autonomous/2026-08-16-app-and-test-reform`, `autonomous/2026-08-16-spec-corpus-and-jobs`,
  `autonomous/2026-08-17-archive-and-hub-app`, `autonomous/2026-08-17-one-version-one-product`,
  `autonomous/2026-08-18-the-app-feels-alive`, `hub-native-experience`.
- **Local `master` fast-forwarded** from `1e0d08e` (74 behind) to `10c5ee6`.
- **Remaining: 4 local** (`agentweave-1-0`, `agentweave/q2verify`, this branch, `master`),
  **2 remote** (this branch, `master`).
- **Driver `AgentWeaveAutonomousSession`: UNREGISTERED.** Confirmed still unregistered after the PC
  restart. `Q9-runway`'s last item — the capability-validation-rule exploration — is unstarted and
  was knowingly forfeited.

## Next steps

1. **Merge PR #3** — https://github.com/gutohuida/AgentWeave/pull/3. State `OPEN`, `MERGEABLE`, 9/9
   green. Nothing blocks it but the operator's review. `gh pr merge 3 --squash` or via the web UI.
   After merging, delete the remote branch and fast-forward local `master`.
2. **Decide `agentweave-1-0`** — 4 unmerged commits, **local only, no remote, no other copy in
   existence**, last touched 2026-07-27. Holds the AgentWeave 1.0 target-state specification drafts
   (revs 6, 8, 9). Keep or `git branch -D agentweave-1-0`.
3. **Decide `hub/seed_taste_doc.py`** — leave untracked, or `git mv` it to `testbed/scratch/`.
   Do **not** commit it where it is: `ruff` fails on it and CI would go red.
4. **Start implementing, and start with the panel change's shell** — `tasks.md` sections 1 → 2 → 3,
   in that order, which the file states explicitly. Section 1.1 is the first executable step: create
   the per-project tab store (which tabs are open, their order, which is visible, whether the shell
   is open), keyed by project id, persisted to `localStorage` under a versioned key. The loop
   change's B5/B6 depend on this landing first.
5. **Drive one short cheap-model agent turn on the trial Hub (`:8010`)** — never done across three
   handoffs, and tasks 5.5 and 6.1 of the panel change are explicitly blocked on a real shell.

## Open questions for the user

- **Should an agent be able to archive a bare job at all**, even with an approval card? D18 settles
  that the path always asks and that loops are never agent-archivable; it deliberately does not
  settle whether that path should exist. Recorded as open in both the change and the exploration.
- **`agentweave-1-0`** and **`hub/seed_taste_doc.py`** — next steps 2 and 3.
- **The name-reuse hole (loop D15)** — a new agent taking an archived agent's name inherits its
  creator privilege. Still open from handoff 0056, should close before control delegation is relied
  on.
- **Two things the panel change refuses to invent:** the `files` tab's minimum width, and tab-strip
  overflow behaviour. Both need measuring against a running shell (tasks 5.5, 6.1).

## Read on resume

- `openspec/explorations/2026-08-18-the-side-panel-with-the-operator.md` — **read first.** The whole
  design conversation; §0 is the overturned-recommendations table.
- `openspec/changes/2026-08-18-a-loop-writes-its-own-queue/design.md` — D1–D9 by firings, Addendum 1
  D10–D15, **Addendum 2 D16–D21** from this session. The D7/D10 and D13/D19 relationships are the
  ones most likely to be got wrong.
- `openspec/changes/2026-08-18-one-shell-three-panels/tasks.md` — where implementation starts; the
  1 → 2 → 3 ordering is load-bearing and the file says why.
- `openspec/changes/2026-08-18-one-shell-three-panels/design.md` — D1–D12; D6 is a withdrawal notice,
  not a decision.
- `testbed/scratch/t3ref/src/rightPanelStore.ts` — the reference the tab model is built on:
  the surface union (`:27-47`), `openFile` replacing the tree (`:284-286`), the migration rules
  (`:237-248`). **Reference only, never copy, never commit.**
- `hub/ui/src/components/agents/ConversationView.tsx` — `:34-38` the derived breakpoint, `:150-291`
  the hosting block that becomes the shell.
