# Per-task worktrees: what F58 actually costs, and what option (c) actually asks for

**Date:** 2026-08-27 · **Status:** exploration. No code written, and **no proposal here** — the
propose round is `F58-R1`.
**Decision already taken:** option **(c), per-task worktrees**, by the operator on 2026-08-26
(`openspec/explorations/2026-08-26-what-is-still-unanswered.md`, "Decisions, 2026-08-26", item 1).
This document does **not** re-open that decision. It records why (a) and (b) were rejected, checks
the one objection that was raised against (c) *by line rather than by memory*, and writes down the
three things the decision left unanswered: migration, cost, and reaping.

Every line number below was opened and read on 2026-08-27 at branch
`autonomous/2026-08-27-the-rest-of-the-work` (`24b68af`). Every git behaviour claim was **measured**
in a throwaway repository, not reasoned about — the transcripts are in the "Measured" section and
the repositories are at `testbed/f58demo/` and `testbed/f58demo2/` (both gitignored).

## 1. The defect, stated once

`hub/hub/task_integration.py:10` opens the module's own docstring with the guarantee:

> **Merge a commit, never a branch.** `worktrees.branch_name` is per *agent*, so one builder's
> branch carries every task it ever worked on. Merging the branch when one task is approved would
> ship the others. The accepted evidence already names the commit the work was demonstrated at;
> that is what goes in, and anything committed after it stays out.

The first sentence is a real distinction and the last is true. **The middle is false.**
`integrate()` runs, at `hub/hub/task_integration.py:289-299`:

```python
result = _git(
    root, "-c", ..., "merge", "--no-ff",
    "-m", f"Integrate approved work {target.commit_sha[:12]}",
    target.commit_sha,
)
```

`git merge --no-ff <sha>` brings in **every ancestor of `<sha>` not already in the target** — the
commit's whole history back to the merge base. Naming a commit rather than a branch narrows *the
tip* and nothing else. Since `worktrees.branch_name` (`hub/hub/worktrees.py:144`) is
`agentweave/<agent>`, the first approval on *any* task an agent has worked ships everything that
agent has ever committed, including other tasks' unreviewed work and any scratch file
`snapshot_worktree` (`hub/hub/worktrees.py:448`) auto-committed at end of turn.

Measured live on 2026-08-26 against `ledger-stress`: one approval, 13 files and 16 commits, one of
them another task's test file for a task still sitting `assigned`. Full account in
`scripts/drive/FINDINGS.md:2579`.

**What is already fixed:** `commits_riding_along` (`task_integration.py:189`) records what came
along, `TaskIntegration.rode_along_commits` persists it (migration `0089`), and
`TaskIntegrationNote.tsx` renders it as an amber line. That makes the blast radius *visible*. It
does not make it smaller. The merge is byte-for-byte what it was.

## 2. Why the green test does not contradict any of this

This is the heart of the finding and the reason it survived so long, so it gets its own section.

`hub/tests/test_task_integration.py:296`,
`test_later_commits_on_the_branch_are_not_merged`, has this docstring:

> D1: what merges is the commit the evidence names, not the agent's branch. Branches are per agent,
> so the branch carries every task the builder ever touched. If this test fails, approving one task
> ships another task's unreviewed work — which is the failure the whole commit-not-branch decision
> exists to prevent.

It is green. It has always been green. **It would be green against every candidate implementation,
including the broken one, and that is a property of its fixture rather than of the code it tests.**

The fixture builds the agent branch like this (`:307`, `:311`):

```python
demonstrated = commit_on_branch(tmp_path, AGENT_BRANCH, "done.py", "ok\n")
await accept_evidence(app, auth_headers, builder)
# Work that happened after the evidence was accepted, on the same branch.
later = commit_on_branch(tmp_path, AGENT_BRANCH, "not-yet.py", "wip\n", create=False)
```

then asserts `later not in commits_on(main)`.

`later` is a **descendant** of `demonstrated`. No mechanism that integrates `demonstrated` can
include a descendant of it: not `merge --no-ff`, not a cherry-pick range, not a squashed patch, not
a per-task branch. The assertion is a restatement of git's ancestry ordering. It tests that the code
does not integrate the wrong commit — a real thing, worth a test — but it does **not** test the
sentence its own docstring says it tests, because the failure that sentence describes is an
*earlier* commit riding along, and no earlier commit exists in this fixture.

The proof that the suite knows this is in the same file, 33 lines down.
`test_rode_along_commits_names_what_actually_landed` (`:329`) builds the missing case (`:342`):

```python
earlier = commit_on_branch(tmp_path, AGENT_BRANCH, "unrelated.py", "wip\n")
demonstrated = commit_on_branch(tmp_path, AGENT_BRANCH, "done.py", "ok\n", create=False)
```

and asserts that `earlier` **still lands**. The suite currently contains a test that documents the
bug as expected behaviour and a test whose docstring says the bug cannot happen, and both pass.
When the fix lands, that second test's assertion has to be inverted, not deleted — the inversion is
the regression test.

This is the F43/F52 shape and the house failure mode named in `CLAUDE.md`: a test that passes
against both implementations it exists to tell apart. **`F58-R1`'s `tasks.md` must carry an explicit
task to invert `test_rode_along_commits_names_what_actually_landed`, and one to add to
`test_later_commits_on_the_branch_are_not_merged` the earlier-commit case that makes its docstring
true.**

## 3. Why (a) and (b) were rejected — measured, not argued

The exploration of record rejected both on reasoning. Both rejections hold when run, and one of them
is **worse than that document claimed**.

Setup (`testbed/f58demo2`): main at `base`; one per-agent branch carrying two tasks' commits
interleaved, `B1 · A1 · B2 · A2`, where `A*` is task A's work and `B*` is task B's unreviewed
work-in-progress. Task A's accepted evidence names `A2`, its tip. Files on `main` after integrating,
measured:

| mechanism | files that land on `main` | verdict |
|---|---|---|
| **today** — `merge --no-ff A2` | `A1 A2 B1 B2` | ships all of task B |
| **(a)** `cherry-pick base..A2` | `A1 A2 B1 B2` | identical to today |
| **(a)** `cherry-pick A1..A2`, i.e. from this branch's last integration point | `A2 B2` | ships `B2` **and drops `A1`** |
| **(b)** squashed diff of `A2` alone | `A2` | task A's own `A1` is missing |
| **(c)** task-A branch cut from `main`, merged at its tip | `A1 A2` | correct |

- **(a) cannot separate interleaved tasks.** F58's own text concedes this. What the measurement adds
  is that the *tighter* form of (a) — the one that sounded like the improvement — is strictly worse
  than the loose form: it still ships `B2`, and it now also **loses `A1`**, a commit of the approved
  task's own work. It ships partial work *and* somebody else's work in the same merge. That is a
  new detail; the exploration of record did not have it.
- **(b) breaks a multi-commit task.** The evidence names the tip, so a squashed tip-diff lands `A2`
  and not `A1`: partial work that has never been run in the form it lands in. Read the other way —
  squash the *tree* at `A2` rather than its diff — it re-includes `B1` and `B2`'s files and fixes
  nothing.

Both failures share one cause: **the branch does not correspond to the task**, so no query over the
branch can recover the task. (c) is not the cleanest of three fixes; it is the only one that makes
"the commit the evidence names" and "this task's work" denote the same thing.

## 4. The dependency objection, and where it genuinely survives

The one objection raised against (c): *a task that legitimately builds on another task's
not-yet-landed work would find a worktree forked from `main` missing it.*

The exploration of record dissolved it. **Re-verified here by opening the lines, and the citation it
used has drifted:**

| claim | verified at | verdict |
|---|---|---|
| A dependency is met only at `approved` | `hub/hub/dependency_gate.py:31` — `MET_STATUS = "approved"` | holds |
| The gate refuses the dependent's start | `hub/hub/task_transition_service.py:375-380` — `if to_status == "in_progress": ... raise DependencyUnmetError` | holds, **and is stronger than stated** |
| Approval integrates | `hub/hub/task_transition_service.py:434-435` — `if to_status == "approved": await integrate_task(...)` | holds |

Two corrections to the exploration of record, both worth carrying into `F58-R1`:

1. **Its citation `task_transition_service.py:375` no longer resolves to `integrate_task`.** Today
   line 375 is the *dependency gate's* own `if to_status == "in_progress":`; the `integrate_task`
   call is at 435.
   The claim is right and the line is stale. R2 and R3 should re-open every such citation rather
   than trusting the artifact, which is what those rounds are for.
2. **It never said which edge the dependency gate sits on, and that is the load-bearing part.** The
   gate is on `-> in_progress` **only** (`dependency_gate.py` module docstring, and
   `task_transition_service.py:375-380`, with its reasoning at `:368-374`) — not `-> assigned`, so
   a wave can be routed ahead of time.
   That is what makes the argument work: the dependent may not *begin* until its prerequisite is
   `approved`, and approval merges. A worktree cut from `main` at the moment work starts therefore
   contains every dependency the task is entitled to see, by construction.

### Where the objection survives, and (c) is a regression

**Integration is best-effort. Approval is not.** `integrate_task`
(`task_transition_service.py:466`) never blocks the transition — by design, stated in
`test_task_integration.py:14`: *"Nothing here may block an approval."* So a task can be `approved`
with its work **not** on `main`, through any of:

- `NO_MAIN_BRANCH` — no main branch chosen in project settings (`task_integration.py:52`)
- `NOT_A_REPOSITORY` — the project is not a git repo at all
- `NOTHING_TO_MERGE` — the accepted evidence has a `paths` footprint and no commit, which
  `integration_targets` (`:142`) documents as *"a supported project shape, not a degraded one"*
- `CHECKOUT_DIRTY` / `CHECKOUT_ELSEWHERE` — the operator's own checkout is mid-edit or parked
- `FAILED` — a real merge conflict; `integrate()` aborts and records it (`:305`)

In each case the prerequisite is `approved`, so the gate opens, and its work is not on `main`.

**Today that is survivable by accident.** If the same agent holds both tasks, the dependent's
worktree is the *same* worktree on the *same* branch, so the prerequisite's commits are simply
there. The bug that is F58 is the same mechanism that is quietly carrying dependent work.

**Under (c) it stops being survivable.** A fresh per-task worktree cut from `main` will genuinely
lack the prerequisite's work, and the agent will be told to build on something that is not in its
checkout. This is the one place per-task worktrees are strictly worse than what exists, and it is
not hypothetical: `NOTHING_TO_MERGE` fires for every `paths`-footprint project, which the product
supports on purpose.

**This is the question `F58-R1` has to answer, and it is a design decision, not a detail.** The
shapes available, none chosen here:

- Cut the task branch from `main` and additionally merge each approved prerequisite's evidence
  commit into it at provisioning — correct, and it makes provisioning able to conflict.
- Make the dependency gate require *integrated*, not merely `approved`, so the two facts cannot
  diverge — cleanest, and it means a project with no main branch can never advance a dependency
  chain, which is a real product change affecting non-repo projects.
- Cut from `main` regardless and state the gap in the turn context — cheapest, and it puts the
  problem on the agent.

## 5. Migration: the work already on per-agent branches

**Nobody has answered this, and it is the part that can damage a repository.** At the moment (c)
ships, every existing project has live per-agent branches with real, unmerged work on them — the
trial Hub has three of them on `ledger-stress` right now (measured: `agentweave/builder`,
`agentweave/critic`, `agentweave/relay`, plus two detached review checkouts).

The call sites that assume "one worktree per agent, found by agent name alone", all of which a
proposal has to name:

| site | what it assumes |
|---|---|
| `worktrees.branch_name` / `worktree_path` (`:144`, `:139`) | the key is an agent name; validated by `_AGENT_NAME_RE` |
| `ensure_worktree` (`:259`) | one path per agent; reuses an existing branch, and `--force`-resets it to `HEAD` when it is an ancestor |
| `existing_worktree` (`:232`) | answers "where is this agent's work?" with one path |
| `resolve_agent_workspace` (`:412`) | one workspace per agent per turn |
| `release_worktree` (`:516`) | releases *the* worktree for an agent |
| `requirement_evidence.footprint_root` (`:270`, `:285`) | reads the footprint from `existing_worktree(root, actor)` — **actor only, no task** |
| `checkpoints.py:373` | resolves a checkpoint's paths through `worktree_path(repo_root, agent)` |
| `api/v1/agents.py:1160` | tells the agent, in its turn context, *"This is an isolated git worktree on branch `agentweave/<agent>`"* |
| `api/v1/worktrees.py:56,95` | the REST surface is `GET /worktrees` and `GET /worktrees/{agent}` |
| `ui/src/components/environment/WorktreesPanel.tsx` | renders one row per agent |
| `session_sync.py:131` | the only reaper — releases on roster removal |

Migration questions with no answer today, for `F58-R1` to decide:

1. **An agent mid-task when this lands.** Its work is on `agentweave/<agent>`, uncommitted or
   snapshotted. Does provisioning adopt that branch as the task branch, leave it and start empty, or
   refuse the turn until an operator says?
2. **A per-agent branch carrying several tasks' work.** There is no record of which commit belongs
   to which task — that absence *is* F58 — so the work cannot be split automatically. Any migration
   that claims to split it is guessing.
3. **An already-approved task whose integration skipped.** Its work sits on a per-agent branch and
   `retry_integration` (`task_transition_service.py:440`) exists to land it later. If the branch is
   gone or renamed, that retry path breaks for exactly the tasks it was built for.
4. **`ensure_worktree`'s reuse-and-reset.** It `--force`-moves an existing branch to `HEAD` when the
   branch is an ancestor of `HEAD`. Applied to a task branch this is probably right and probably
   wrong for a *resumed* task; it needs stating either way.

My reading, offered as input to R1 rather than as a decision: the honest migration is **no
migration** — leave existing `agentweave/<agent>` branches exactly where they are, untouched and
un-reaped, so nothing is lost and `retry_integration` keeps working; provision per-task worktrees
only for work started after the change; and give the operator a read-only surface naming the legacy
branches that still carry unmerged commits. That trades a period of two coexisting schemes for never
guessing which commit belonged to which task.

## 6. Cost, and the reaper that does not exist

**Measured on 2026-08-27.**

`ledger-stress` (`C:\Users\huida\Documents\aw-stress`) has 3 agents and **19 tasks**. It carries 5
linked checkouts today (3 working, 2 review), totalling ~305 KB of working tree against a 602 KB
object store. Under (c) it would carry up to 19 working checkouts plus the 2 review ones.

Scale it to a repository that is not a toy. This repository has **2028 tracked files, 37.7 MiB** of
working tree. One checkout per task, at 19 tasks, is **~716 MiB** — and tasks accumulate forever
while agents do not. Per-agent worktrees are bounded by the roster (3–5). Per-task worktrees are
bounded by nothing.

**The precedent cited for the cost being acceptable points the other way, and this needs saying
plainly.** The decision text cites review checkouts — *"A review checkout is bounded and reused"*.
It is, and `ensure_review_checkout` (`worktrees.py:352`) says exactly why: *"Created on the first
review and **re-pointed** on every one after it, so the number of these directories is bounded by
the roster rather than by the number of reviews (design D3)."* That mechanism is unavailable to task
worktrees: re-pointing works for reviews because a review holds no state worth keeping, and a task
worktree holds in-flight work by definition. **The precedent is precedent for bounding by the
roster, which is the property (c) gives up.** That does not make (c) wrong — sections 3 and 4 stand
— but the cost argument has to be made on its own, not borrowed.

**And there is no reaper.** The only path that removes a working worktree today is
`session_sync.py:131`, when an agent leaves the roster. Nothing releases a worktree when work
*finishes*, because nothing has needed to: an agent's worktree is meant to outlive its tasks. Under
(c) the natural reaper is the task reaching a terminal state (`approved`, `rejected`), and
`release_worktree` (`:516`) already has the right refusal shape — it snapshots uncommitted changes,
never deletes the branch, and reports `unmerged_commits` rather than discarding them.

So `F58-R1` must carry a reaper as a first-class part of the change, with at least these decided:

- **When.** On the transition into `approved` after `integrate_task` returns `merged` — and
  explicitly *not* when it returns `skipped` or `failed`, or the retry path loses its checkout.
- **What survives.** The branch, always — same rule as `release_worktree` today. Disk is reclaimed
  by removing the checkout; history is never reclaimed.
- **`rejected`.** A rejected task's work is the thing an operator is most likely to want to look at.
  Probably keep the checkout and let roster removal or an explicit action reap it.
- **A backstop.** Some bound on total live task worktrees, or the first long-lived project fills a
  disk and the symptom will be a git failure in an unrelated turn.

## 7. Measured

Both repositories are under `testbed/` and gitignored.

**`testbed/f58demo` — F58 reproduced from first principles, no Hub involved.** Branch
`agentweave/builder` with `taskB_unreviewed.py` committed first, `taskA_done.py` second; merge
`--no-ff` of task A's tip into `main`:

```
--- after merge --no-ff TARGET, files on main:
README.md
taskA_done.py
taskB_unreviewed.py
--- earlier commit reachable from main?
YES - task B's unreviewed work landed
```

**`testbed/f58demo2` — the four mechanisms, same branch shape.** Transcript summarised in the table
in section 3; the branch is `B1 · A1 · B2 · A2` on `agentweave/builder`, and each mechanism was run
against a `git reset --hard` back to `base` so no run contaminated the next.

## 8. What this exploration deliberately did not do

- **No proposal.** `F58-R1` writes `proposal.md`, `design.md`, `tasks.md` and the spec deltas.
  Capabilities most likely touched: `run-task-binding`, `agent-flows`, `agent-run-sandboxing`,
  `agent-conversation-workspace`.
- **No re-opening of the option choice.** (c) stands. Nothing measured here weakens it; section 3
  strengthens it, since the tighter form of (a) turned out to be worse than recorded.
- **No live drive against the trial Hub.** The 8010 instance is running code from `7219090`, a
  distant ancestor. Every measurement above is either a file read at `24b68af` or a raw-git
  experiment, so none of it depends on that instance.

## 9. Open questions for R1 to close, in order of what they block

1. **The prerequisite-not-integrated gap** (section 4). Blocks the whole design — it decides what a
   task worktree is cut *from*.
2. **The workspace is chosen before the task is known.** `agent_trigger.py:535` calls
   `resolve_agent_workspace`; `resolve_bound_task` does not run until `:558`. Per-task worktrees
   need the binding first, and `resolve_bound_task` is documented as *"Reads only"*
   (`run_task_binding.py:247`), so moving the read earlier looks safe — **but it must be verified,
   not assumed, and it is the single largest structural obstacle in the change.**
3. **A turn with no bound task at all.** Ad-hoc composer turns and chat inherit a conversation
   binding or have none (`run_task_binding.py:284-289`). What workspace does a writing agent get
   when there is no task? Falling back to a per-agent worktree keeps both schemes alive forever;
   refusing the turn breaks ordinary chat.
4. **Migration** (section 5).
5. **Reaping and the disk backstop** (section 6).
6. **The two tests** (section 2). Not a design question, but it must be in `tasks.md` explicitly or
   the change will ship with a green suite that still cannot tell the implementations apart.
