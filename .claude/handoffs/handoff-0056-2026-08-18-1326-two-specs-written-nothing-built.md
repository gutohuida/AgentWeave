# Handoff: two specs authored, three fixes landed, and the loop is still running

**Date:** 2026-08-18T13:26:46+01:00 · **Branch:** `autonomous/2026-08-18-loops-and-side-panels` · **HEAD:** `c453d6f`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive — alongside a Windows Scheduled Task driver firing every 15 min)
**Previous handoff:** `.claude/handoffs/handoff-0055-2026-08-18-0936-night-run-landed-and-the-corpus-got-its-first-merge.md`
**Status:** chunk complete. **The autonomous run is still armed and firing until 17:00.** Nothing blocked.

## Goal

Give AgentWeave a real loop — work an agent can set running and leave — and a side-panel framework
that makes what it is doing visible. The operator's framing, which governs every design call:

> "We need to follow the agentweave philosophy of governance and visibility."

The *why*: the operator wants to spec a feature, or sleep, while work proceeds — *"I don't need to be
here driving everything"* — without the single-session context rot that makes long agent runs
degrade, and with checkpoints and stages they can inspect.

**This run was narrowed twice by the operator and implements neither feature.** It ships measured
fixes and produces designs. That is deliberate, recorded as `decisions_for_user.DEC-run-narrowed`.

## Current state

**The autonomous run's queue is 8 of 9 done.** `Q1` CI fixes, `Q2` merge-500, `Q3` false provenance,
`Q4` false `ui_stale`, `Q5` loop exploration, `Q6` loop spec, `Q7` panel exploration, `Q8` panel spec.
Only `Q9` (runway) is pending.

**Merged to `master` today:** PR #2 — the parent branch's ~70 commits, with **the first green CI this
work has ever had**, and master's own CI green afterwards. That closes `known_debts.ci-never-ran`.

**Implemented and on this branch, not merged** — 174 lines vs `origin/master`, all verified:

| File | What |
|---|---|
| `hub/hub/api/v1/spec.py` (+15), `hub/hub/spec_service.py` (+10) | The gated-merge 500. `merge_document()` now returns `SaveResult \| ProposeResult` and short-circuits before writing provenance when `save_document` proposed instead of wrote; the route builds its response by `isinstance` **before** `session.commit()`. Finished. |
| `hub/tests/test_spec_merge.py` (+102) | The `rigor` cases that file never had. Finished. |
| `hub/hub/main.py` (+42) | `ui_source_fingerprint()` now content-hashes each enumerated file's working-tree bytes instead of combining git blob ids with a `status --porcelain` diff. Content hashing is stage-invariant, so stamping before a commit can no longer desync from it. Finished. |
| `hub/tests/test_ui_build_stamp.py` (+24) | Reproduces the false `ui_stale` first — failed before the fix. Finished. |

**Specced, nothing built.** Two openspec changes, **105 open tasks, 0 done, 28 requirements**:

- `openspec/changes/2026-08-18-a-loop-writes-its-own-queue/` — 64 tasks, 14 requirements.
- `openspec/changes/2026-08-18-one-shell-three-panels/` — 41 tasks, 14 requirements.

`npx openspec validate --changes --strict` passes, 10 items.

**The driver is currently standing down because this interactive session's `last_heartbeat` is
fresh.** It will resume within 15 minutes of that going stale. See Next steps 1.

## Files touched

**Committed this session** (`ab7e5fe`, `effd4f6`, `b7fbf90`, `b4144e9`, `9c31059`, `a1c1eb1`,
`c453d6f`, plus firing commits interleaved):

- `openspec/explorations/2026-08-18-loops-as-an-agent-tool.md` — **written, then rewritten**, then
  extended twice (§5a creator/controller, §5b editing). The design input for the loop change.
- `openspec/changes/2026-08-18-a-loop-writes-its-own-queue/{proposal,design,tasks}.md` and
  `specs/agent-loops/spec.md` — authored by firings 12:32–12:38, then **merged with a duplicate**
  this session: design gained an addendum `D10–D15`, tasks gained `A1–A7`, the spec gained five
  requirements. Finished and validating.
- `openspec/changes/2026-08-18-a-loop-writes-its-own-queue/specs/task-lifecycle-governance/spec.md` —
  **new**, carried over from the deleted duplicate. Finished.
- `openspec/changes/2026-08-18-one-shell-three-panels/**` — authored by a firing 13:00–13:04. **Not
  reviewed by the operator or by this session.**
- `openspec/explorations/2026-08-18-the-side-panel-family.md` — by a firing. Not reviewed.
- `hub/hub/{api/v1/spec.py,spec_service.py,main.py}`, `hub/tests/{test_spec_merge,test_ui_build_stamp}.py`,
  `hub/hub/static/ui/ui-build-stamp.json` — the fixes above. Written by a firing, **verified and
  committed by this session** (`b4144e9`).
- `.claude/autonomous/STATE.json` — 9 queue items, 15 limits, 11 `decisions_for_user`, 8
  `known_debts`, `standing_checks`, `time_guard`.
- `.claude/autonomous/2026-08-18-loops-and-side-panels-log.md` — entries 0–6.
- `src/agentweave/cli.py`, `tests/test_packaging.py`, `tests/test_cli.py` — CI fixes. **Already in
  `master`** via PR #2.

**Deleted this session:** `openspec/changes/2026-08-18-loops-that-remember/` — a duplicate loop
change this session authored without checking. See Dead ends.

**Untracked and deliberate** (leave alone): `spec/` (real fixture content, `CLAUDE.md` forbids
committing it at the root), `hub/seed_taste_doc.py`, `testbed/scratch/**` (gitignored — includes
`t3ref/`, 30 T3 Code source files, and `extract_t3ref.py`, `seed_state.py`, `repoint_state.py`,
`add_spec_stages.py`).

## Key decisions

1. **A loop is "a job that ends and owns a backlog"** — not "an agent on a schedule", because a bare
   `AIJob` already is exactly that. *Rejected:* retiring the concept, which the operator initially
   suspected was right.
2. **Continuity is re-derived from durable state, not a resumed conversation.** Settled by the
   operator's purpose — a loop exists partly for *"context management since it's not a single
   unstopped session with more and more polluted context"* — so fixing `session_mode="resume"` would
   rebuild the problem loops exist to escape. *Rejected:* fixing `last_session_id`; and inventing a
   `next_action` field, which would have been a worse duplicate of checkpoints (which already
   implement "blind resume" **with a probe grading the result**).
3. **The queue's author is not its executor.** Creator authors; the attributed executor cannot add
   and may only ask by message — which already starts the creator's turn (`messages.py:257-259`).
   This is what makes termination safe: an executor that can file its own tasks controls its own stop
   condition. *Rejected:* executor-adds-with-audit (auditing does not stop non-termination);
   routing via `ask_user` (it blocks, burning an unattended firing).
4. **Creator and controller are separate.** Controller defaults to the operator, delegable to the
   creator agent and back. Follows `Agent.default_permission_mode` (`models.py:196`): nullable, NULL
   means *the current default*, never a stored copy. *Rejected:* a single "owner"; a boolean.
5. **An edit is always accepted and applied at the next firing.** *Rejected:* refusing during a run
   (a long firing locks the operator out of their own loop); applying immediately (a firing that
   re-reads its queue would see a world it was never briefed on).
6. **A late task is refused with its reason and offered as a successor's seed.** *Rejected:*
   reviving a stopped loop; discarding the task; suspending termination during an edit.
7. **Terminate on an empty queue even with a request outstanding — and measure the exception.**
   Operator: *"We can track this kind of information and improve the loops."* Telemetry instead of a
   third state.
8. **A "stage" is task-lifecycle position**, derived from statuses. *Rejected:* named phases
   (implement → test → review) — real structure, but a new concept to model and not needed.
9. **openspec for both changes, full depth** — operator's explicit choice, asked because `CLAUDE.md`
   forbids picking silently. *Rejected:* the trial Hub's own flow, which is the migration's goal and
   would have produced dogfooding findings, but depends on the Hub staying healthy unattended and has
   two known live defects.
10. **The duplicate was merged into the firings' change, not the reverse** — theirs was first and
    deeper on mechanics. The later decisions went in as a **marked addendum** rather than edited into
    place, so the order decisions were taken in stays legible.

## Constraints and user directives (verbatim)

> *"Full auto, but only on green CI"* — standing. **Never merge or release on red or unfinished CI.**

> *"Let's ship the fixes and what is ready and deterministic and let's run a explore on the loop and
> the side panel"* — the first narrowing, ~10:52.

> *"let's run a explore on the loop then and prepare the spec then we run a explore and spec on the
> side panel"* — the second, ~11:00. **Specs yes, implementation no.**

> *"The problem is that autonomous-prep is a local skill used to develop agentweave. What we're
> looking at is an autonomous loop within agentweave. That is usable by agentweave. I think you are
> veering off the true objective."* — **the most important correction of the session.**

> *"Loops can have their own tasks. A spec is one source. Loops can be attributed to other agents. If
> a loops is created by the architect and attributed to the developer only the creator can create new
> tasks… Agent can create loops for themselves but once the loop is defined only with user approval
> then can add more tasks."*

> *"The operator will never create loops by himself. He will do it with an agent. So we have two
> subjects there. The one who created and the one who controls it… But the operator can leave the
> control to the agent that can decide for himself."*

> *"But we need enforcements not to break the loop. If I'm editing a loop it only goes after no run is
> active."*

> *"It should terminate. The architect can create another one. We can track this kind of information
> and improve the loops."*

> *"I strongly recommend you to look at T3 code for this."* — done; `testbed/scratch/t3ref/`.
> **Design reference only — study the patterns, do not copy the code, do not commit it.**

> **Live agent turns:** *"a few short cheap-model turns."* **Never used this session.**

> **Do not touch `aw-loop10`** (`proj-ff695d96`). The dev Hub on `:8000` holds unrelated real
> operator work — read only.

From `CLAUDE.md`, still binding: never create `.agentweave/` or `agentweave.yml` at the repo root;
`spec/` at the root is deliberate and untracked; use `openspec`, never the `aw-*` skills; stage paths
explicitly; commit `hub/ui/src` and `hub/hub/static/ui` together; always `py -3.11`.

## Dead ends

- **I wrote a duplicate openspec change.** Firings had already authored the loop spec at 12:32–12:38;
  I wrote a second one at ~13:20 without checking `openspec/changes/`. Cause: I let `last_heartbeat`
  go stale for **67 minutes** while talking to the operator, so firings correctly took the branch.
  **Check `openspec/changes/` and `git log` before authoring anything the queue says is done.**
- **The branch claim is only as good as its refresh rate, and it has failed twice.** (a) A firing
  already running **never re-checks the heartbeat** — one started at 11:11:59 and I claimed the branch
  at 11:17, so we shared a tree for twenty minutes. (b) An interactive session that stops *writing*
  stops holding the branch even while alive. Nothing was lost either time, and both times the reason
  was **staging paths explicitly instead of `git add -A`**.
- **A firing ended with a dirty tree**, saying it would wait for a background suite then commit — the
  iteration ended first, leaving Q2–Q4 complete but uncommitted. **If you find uncommitted work you
  did not write, run its tests before committing it.** I did: 25 passed, 1 skipped.
- **I mined `.claude/autonomous/` as a design reference and it was wrong.** It is Claude Code
  scaffolding for developing this repo; designing from it imports constraints AgentWeave's users do
  not have. It was about to produce a `next_action` field duplicating checkpoints.
- **I ran the explore skill without holding its stance** — invoked it, then went and wrote a document
  without asking the operator anything, which is the one thing it forbids. Had to rewrite.
- **My claim that `8898155` shipped UI source without rebuilding the bundle was wrong.** It did
  rebuild. The stamp was stale for a different reason (fixed in `main.py` this session).
- **`openspec` CLI 1.4.1 has no `new`/`status --change`/`instructions` subcommands.** The
  `openspec-propose` skill describes a newer CLI this repo does not have. Follow `CLAUDE.md`'s layout
  and validate with `npx openspec validate --changes --strict`.
- **Complex `python -c` with nested quotes breaks or hangs.** Write a script into `testbed/scratch/`.

## Verification

**Ran and passed, by me, this session:**
- `py -3.11 -m pytest hub/tests/test_spec_merge.py hub/tests/test_ui_build_stamp.py hub/tests/test_ui_staleness.py -q` → **25 passed, 1 skipped** (13.6s). This is what justified committing `b4144e9`.
- `npx openspec validate --changes --strict` → **10 passed, 0 failed**, after the merge and the deletion of the duplicate.
- `gh pr checks 2` → all 9 green before merging; master's own CI run green after.

**NOT tested:**
- **No live agent turn was driven, again.** The working indicator, "Worked for Xs" and scroll pinning
  have still never been watched against a real run — carried unresolved from handoff 0055.
- **Neither spec has been implemented or reviewed by the operator.**
- **`one-shell-three-panels` and `2026-08-18-the-side-panel-family.md` were written entirely by
  firings and have been read by nobody** — not the operator, not this session.
- **The full `hub/tests/` suite was not run this session** — only the three files above.
- **`tests/` (CLI suite) was not run this session.**
- **Overlapping loop firings** remain unverified — flagged in both the exploration and design D14.
- A firing reports fixing `_batch_loop_summaries` (a missing `"assigned"` status); **I did not verify
  that independently.**

## Git state

- **Branch:** `autonomous/2026-08-18-loops-and-side-panels`, **HEAD:** `c453d6f`, **no unpushed commits.**
- **Dirty:** two untracked paths only — `spec/`, `hub/seed_taste_doc.py`. Both deliberate.
- **90 commits ahead of the stale local `master` ref; 6 files / 174 lines ahead of `origin/master`.**
  Local `master` is stale — always compare against `origin/master`.
- **`origin/master` = `10c5ee6`**, the PR #2 merge, CI green.
- **Duplicate commits across branches:** the packaging and CI fixes exist on both this branch and the
  parent under different SHAs. **Rebase, do not merge, when landing this branch** — rebase matches
  patch-ids and drops them; merge will not.
- **Driver `AgentWeaveAutonomousSession`: REGISTERED and firing every 15 min until 17:00**, then it
  unregisters itself.

## Next steps

1. **Decide whether the loop keeps running, and release or stop it.** It is standing down *only*
   because this session's `last_heartbeat` (`2026-08-18T13:18:52+01:00`) is fresh. To let it continue
   with `Q9`, back-date the heartbeat ~40 minutes:
   `py -3.11 -c "import json,pathlib;from datetime import datetime,timedelta;p=pathlib.Path('.claude/autonomous/STATE.json');s=json.loads(p.read_text(encoding='utf-8-sig'));s['last_heartbeat']=(datetime.now().astimezone()-timedelta(minutes=40)).isoformat(timespec='seconds');p.write_text(json.dumps(s,indent=2,ensure_ascii=False),encoding='utf-8')"`
   then commit and push. To stop it instead:
   `Unregister-ScheduledTask -TaskName 'AgentWeaveAutonomousSession' -Confirm:$false`.
2. **Read `openspec/changes/2026-08-18-one-shell-three-panels/`.** Nobody has. It is 41 tasks and 14
   requirements of UI design written unattended, and the operator has strong opinions about this
   surface.
3. **Review the merged loop change**, specifically that design `D10` genuinely generalises `D7`
   rather than contradicting it — task `A1.4` exists to prove it, and this session asserted it.
4. **Decide whether to implement either change**, and if so which first. `DEC-run-narrowed` currently
   forbids it.
5. **Drive one short cheap-model agent turn** on the trial Hub (`:8010`), still never done across two
   handoffs.

## Open questions for the user

- **Does the loop keep running until 17:00, and doing what?** `Q9` runway is the names exploration
  (recommend nothing), the capability-validation-rule exploration, and the factual `CLAUDE.md`
  corrections. Implementing a spec is the alternative and is currently forbidden.
- **When does this branch land, and onto what?** 174 lines of verified fixes plus two specs sit
  unmerged. Rebase, do not merge.
- **`D5` capability-validation rule, `D6` rigor coupling, `D2` taste-pass live turns, `D3` retro-cover
  1.0.1, `D4` the `agentweave-hub` pin** — all still open from handoff 0055.
- **`N3`: `CLAUDE.md`'s Specifications section is factually wrong** — it says AgentWeave has "no
  archive phase and no concept of a current-behaviour specification", but five phases shipped
  2026-08-16. Correction drafted in
  `openspec/explorations/2026-08-18-claude-md-trial-hub-section-is-stale.md`, still not applied.
- **The name-reuse hole** (`D15`): a new agent taking an archived agent's name inherits its creator
  privilege. Recorded, not fixed. Should close before control delegation is relied on.

## Read on resume

- `.claude/autonomous/STATE.json` — position, 15 limits, 11 decisions, 8 debts, the time guard. Read first.
- `.claude/autonomous/2026-08-18-loops-and-side-panels-log.md` — entries 0–6, oldest first; entries 5
  and 6 record the two coordination failures.
- `openspec/explorations/2026-08-18-loops-as-an-agent-tool.md` — the design input; §2 the two
  read-with-no-write findings, §3 the passive-requirement lesson, §5a/§5b the operator's decisions.
- `openspec/changes/2026-08-18-a-loop-writes-its-own-queue/design.md` — `D1–D9` by firings, `D10–D15`
  the addendum. The `D7`/`D10` relationship is the thing most likely to be got wrong.
- `openspec/changes/2026-08-18-one-shell-three-panels/proposal.md` — unread by anyone.
- `hub/hub/scheduler.py:296` (`_do_fire_job`) and `:83-102` (`_loop_stop_reason`) — where the loop
  change lands.
