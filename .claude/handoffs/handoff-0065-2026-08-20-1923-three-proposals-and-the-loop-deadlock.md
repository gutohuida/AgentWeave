# Handoff: three changes proposed, and dependencies deadlock the loop

**Date:** 2026-08-20T19:23:45+01:00 · **Branch:** `master` · **HEAD:** `706b481`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0064-2026-08-20-1723-four-items-were-one-problem-and-adoption-is-proposed.md`
**Status:** chunk complete. Working tree clean. **Everything pushed** — `origin/master` == `HEAD`.

## Goal

Work through the carve-up in `openspec/explorations/2026-08-20-the-row-is-the-spine.md` §9 — the
five changes the twelve backlog items collapsed into. Handoff 0064 left #1 (`document-adoption`)
proposed and #2–#5 untouched.

This session: pushed the 24-commit backlog, proposed #2 and #3, explored #4, then explored a
question the operator raised from #4 — how the loop fits once tasks have dependencies.

The *why* governing judgement calls is unchanged: this is the dogfooding migration CLAUDE.md
describes, so friction found while using the product is a **deliverable**, not a distraction.

## Current state

### The 24-commit backlog is pushed

Handoff 0064's most-repeated open question is closed. `git push origin master` ran at the start of
this session (`63ef94e..662ba1f`) and again after each commit. **`origin/master` is now `706b481`
and nothing is unpushed.** CI has finally seen the database-wipe fix.

### Four openspec changes are proposed. None is implemented.

| Change | Tasks | Validates |
|---|---|---|
| `document-adoption` | 38 | yes (from handoff 0064) |
| `corpus-aware-documents` | 55 | yes — **new this session** |
| `agent-created-documents` | 35 | yes — **new this session** |
| `task-dependencies` | 70 | yes — **new this session** |

`writable-spec-index` (29/29) and `operator-authored-documents` (21/21) are **complete with zero
open tasks and unarchived**. They are the predecessors that made `index.json` writable and let the
operator author documents. This is the oldest loose thread in the repo and was raised twice this
session without being acted on.

### Carve-up item #4 is explored and split, not fully proposed

`openspec/explorations/2026-08-20-what-the-spec-may-say-about-who-does-the-work.md` (616 lines,
revised three times during a live review with the operator).

- **4b + 4b′ → proposed** as `task-dependencies`.
- **4c** (complexity + tier table) and **4d** (auto-assignment) are **not** proposed. What blocks 4c
  is named: whether an agent may declare a task's complexity is the same shape as `decide_evidence`
  refusing an agent that judges its own evidence (`hub/hub/mcp_server.py:1127`).

### A loop deadlock was found, and a live bug is suspected

`openspec/explorations/2026-08-20-the-loop-under-dependencies.md` (306 lines). Two findings:

**1. `task-dependencies` deadlocks every loop.** `_loop_queue_order()` sorts non-pending above
pending; `CLAIMABLE_LOOP_TASK_STATUSES` includes `assigned`; a firing claims by moving
`pending → assigned` (`hub/hub/scheduler.py:815-816`), which the proposed dependency gate does *not*
block. So the loop claims an unstartable task, the agent is refused at `→ in_progress`, the task
stays `assigned` and sorts first forever. `scheduler.py:243-245` predicts this in a comment.

**2. Suspected live spin — NOT VERIFIED.** `completed` is not in `CLAIMABLE_LOOP_TASK_STATUSES`
(`hub/hub/scheduler.py:246`) but is also not in `TERMINAL_FOR_BINDING`
(`hub/hub/run_task_binding.py:272`, `("approved", "rejected")`). A loop whose tasks are all
`completed`-but-unapproved is therefore both un-claimable and not-empty: fires forever, claims
nothing, never stops. **This looks reachable today with no part of this session's work shipped.**
Verifying it is next step 1.

### Machine state

Nothing was started, stopped or registered this session. **No Hub was touched, no port was opened,
no code was run.** This session wrote markdown only. Handoff 0064's machine state is unverified and
should be re-checked rather than assumed:

| | |
|---|---|
| Port 8000 Hub | was running, one project `proj-adf8a200` "huida" → `C:\Users\huida` |
| Port 8010 | was running, untouched (standing prohibition) |
| This repo as a project | **NOT registered.** Operator said "Not yet" in the previous session and was not asked again |

## Files touched

All committed and pushed. `git status --short` is empty; `git diff --stat HEAD` is empty.

**`f8c67c3` — Propose corpus-aware documents** (5 files, +708)

- `openspec/changes/corpus-aware-documents/proposal.md` — new, finished
- `openspec/changes/corpus-aware-documents/design.md` — new, finished. D1–D8 plus 3 open questions
- `openspec/changes/corpus-aware-documents/specs/spec-corpus-map/spec.md` — new, 6 requirements
- `openspec/changes/corpus-aware-documents/specs/spec-document-authority/spec.md` — new, 2 ADDED
- `openspec/changes/corpus-aware-documents/tasks.md` — new, 9 groups / 55 tasks, split §7 agent-verifiable, §8 human-only, §9 test guide

**`d0d7c5f` — Propose agent-created documents** (6 files, +593)

- `openspec/changes/agent-created-documents/proposal.md` — new, finished
- `openspec/changes/agent-created-documents/design.md` — new, finished. D1–D7 plus 3 open questions
- `openspec/changes/agent-created-documents/specs/agent-document-creation/spec.md` — new, 5 requirements
- `openspec/changes/agent-created-documents/specs/spec-document-authority/spec.md` — new, 2 ADDED
- `openspec/changes/agent-created-documents/specs/agent-capability-plane/spec.md` — new, 2 ADDED
- `openspec/changes/agent-created-documents/tasks.md` — new, 7 groups / 35 tasks

**`17d02e7`, `26b7728`, `b3ece5d`, `170b3c9` — the #4 exploration, written then revised three times**

- `openspec/explorations/2026-08-20-what-the-spec-may-say-about-who-does-the-work.md` — new, then
  substantially rewritten as the operator reviewed it. **616 lines. Finished.** Sections 1–10.

**`ea5baf8` — Propose task dependencies** (7 files, +1063)

- `openspec/changes/task-dependencies/proposal.md` — new, finished
- `openspec/changes/task-dependencies/design.md` — new, finished. D1–D9 plus 4 open questions
- `openspec/changes/task-dependencies/specs/task-dependencies/spec.md` — new, 8 requirements
- `openspec/changes/task-dependencies/specs/task-dependency-board/spec.md` — new, 8 requirements
- `openspec/changes/task-dependencies/specs/task-lifecycle-governance/spec.md` — new, 3 ADDED
- `openspec/changes/task-dependencies/specs/spec-document-authority/spec.md` — new, 2 ADDED
- `openspec/changes/task-dependencies/tasks.md` — new, 11 groups / 70 tasks

**`706b481` — Explore the loop under dependencies** (1 file, +306)

- `openspec/explorations/2026-08-20-the-loop-under-dependencies.md` — new, finished. Sections 1–11.

**Untracked, left alone:** `.migration/` — and note it **is** gitignored (`.gitignore:153`),
correcting handoff 0064 which said it was "ignored by nothing" and would keep appearing in
`git status`. It does not.

## Key decisions

Operator decisions from this session, all recorded in the two exploration documents.

**On #2, corpus-aware documents**

1. **The hierarchy is derived by the agent and authored into `index.json`.** Operator: *"You can
   read them and generate it on your own. Those files were derived from openspec and the code."*
   `build_index` already preserves `parent` across rebuilds, so holding a hierarchy needs no code.
2. **The map renders into the file, not injected by the viewer** (D1). *Rejected:* view-time
   overlay — a corpus whose navigation only exists inside the app is absent exactly when a corpus is
   usually read (a diff, a code host, a browser with no Hub).
3. **Navigation is home + parent only; maps only where there are children** (D2). This is what makes
   D1 affordable: adding one document re-renders one other file instead of all 35. *Rejected:* full
   sibling lists — a corpus-wide diff for a one-document edit, forever.

**On #4, the big reversals**

4. **The max-concurrent-runs project setting is WITHDRAWN** — the operator's own earlier decision,
   reversed on review. *"I'm thinking of dropping this as a config and let the user control it."*
   Three grounds: `token_budget` already distinguishes operator turns from autonomous ones and a raw
   cap would ignore that; author/reviewer separation means a cap of 1 makes review structurally
   unreachable; and concurrency is a poor proxy for spend.
5. **Tiers are `high` / `medium` / `low`.** One axis. *Rejected:* two axes (effort + subtlety) until
   a real decomposition needs one — adding an axis later is easy, renaming one is not.
6. **A dependency is a precondition on an edge, not a property of a task.** Operator: *"A task won't
   be stopped by a dependency… it should never start if a dependency is not met."* Becomes a third
   guard in `task_transition_service`, beside `_guard_author_is_not_reviewer` and `requirement_gate`.
   *Rejected:* materialising dependents as `blocked` (illegal three ways), and a stored `ready`
   column (a denormalised join that goes stale).
7. **A dependency is met at `approved`, not `completed`.** Consequence accepted: every wave passes
   through review, so a chain needs ≥2 agents. Unplanned bonus: a chain cannot advance past
   unverified work, because `requirement_gate` guards the same edge.
8. **The document is the only writer of edges — the board draws, never authors.** The operator
   reversed their own earlier "operator can edit edges" decision: *"This would break protocol and the
   documentation."* Cost accepted: a hand-made task can never have a dependency.
9. **Cross-document dependencies work by importing the foreign task as an entry in this document.**
   The operator's idea, better than the derived off-board stub previously proposed: `depends_on`
   stays local keys, and the per-document board becomes *closed*.
10. **Imports name approved documents only** — turns a rename hazard into a rule, and guarantees the
    foreign task exists.
11. **Once approved, a path is frozen forever.** Found while checking #10: `rename_document` refuses
    on `phase == APPROVED` by equality, and `approved` has two exits, so an approved document's path
    can be changed today by archiving it first. **This is a latent bug independent of the feature.**
12. **Board: top-to-bottom**, because width is bounded by `agent_budget` and depth is not, and
    left-to-right would look identical to the kanban with columns meaning something else.
    **Per document**, with a picker and a standing "no document" board. **A finished layer collapses
    to one expandable row.** **A second view, toggled** — the 7-column board stays.
13. **A rejected dependency is surfaced, never resolved.** *Rejected:* propagating rejection
    (unseen cascade) and treating rejected as met (a dependent starts because its prerequisite was
    abandoned).

**On the loop**

14. **Improve the loop, do not rebuild it.** 24 requirements, three bugs found only by driving it
    live. Rebuilding re-derives all of it.
15. **No second agent bound to the loop.** Operator: *"Once the agent finishes the work it needs to
    send a message to a tester to continue the work. Any tester available."* `send_message`'s
    `message_type` vocabulary already includes `"review"`.
16. **Agent availability must be a TOOL, not a context section** — context is assembled once at turn
    start and availability changes during a turn.

## Constraints and user directives (verbatim)

From this session:

- *"You can read them and generate it on your own. Those files were derived from openspec and the
  code. So until it's all set and done and I'm using them we can edit them as we see fit."*
- *"Huum... Got it... So let's imagine this.. we set it to 1 but then I want to explore something
  else while it builds would I need to change the config to two? And what about testers? Will then
  enter in this math as well? I'm thinking of dropping this as a config and let then user control
  it. He can start the agents and tasks that he wants to start as he wants to start. But I think we
  would also need to have a different view on the tasks as well. Keeps the cards but connect them as
  a tree from top to bottom. They status must be in the card to visually know a which stage they
  are."*
- *"Let's make it per spec implementation and we should able to chose which spec board we want. As
  the project goes on and more things park in done it gets overpopulated. One board for each
  document I feel is the best approach."*
- *"Yeah I can't edit existing edges. Only if the document is changed those edges are changed. This
  would break protocol and the documentation. We can put in the document tasks from another document
  just linking that task there saying it's a dependence. Will that solve the problem? A task won't
  be stopped by a dependency.. it should never start if a dependency is not met."*
- *"We don't need to assign another agent I think. Once the agent finishes the work it needs to send
  a message to a tester to continue the work. Any tester available (Another think that we should do
  is a mcp to check available agents, because if there are 2 testers and one is testing we don't
  want to pile all the test on the same one right? But then an agents should identify a tester. If
  it can't e.g. names and charter are not explanatory, it should ask the user who should test his
  code, and there should also be a way to bind a tester to a task.. easy tasks can be reviewed by
  weaker agents)"*
- *"for number [4] you need to run openspec explore so I can review the exploration"*
- Chosen via AskUserQuestion: **"Push to origin/master now"**, **"explore 2, 3 and 4"**,
  **"Propose #2 and #3, explore #4"**, **high/medium/low**, **"A second view, toggled"**,
  **"A standing 'no document' board"**, **at approved**, **surface rejected deps**, **collapse done
  layers**, **once approved always frozen**, **"Explore the loop question properly"**.

Standing, carried forward from CLAUDE.md and handoff 0064 — **all still in force:**

- Never touch the Hub on **port 8010**. Stage paths explicitly; never `git add -A`.
- Never mark a task complete on the strength of a plan existing.
- `hub/hub/static/ui` is a committed build artefact — after `cd hub/ui && npm run build`, run
  `python scripts/refresh_ui_bundle.py` (`make` is not on PATH in Git Bash here).
- Keep the two `spec_manifest.py` twins (`hub/hub/` and `src/agentweave/`) in sync by hand.
- `hub/hub/mcp_server.py` may import **only** stdlib + fastmcp.
- `approve_tool_call` has **no return annotation** — do not add one.
- From memory: commit each completed checkpoint without asking first; specs must carry test guides
  split into agent-verifiable and human-only.

## Dead ends

- **`openspec status` has no bare form** — it is `openspec status --change <name>`, or `openspec
  list` for the overview. `openspec validate <name>` (no `--change`) is correct, as handoff 0064
  recorded.
- **Handoff 0064's claim that `.migration/` is "ignored by nothing" is wrong** — it matches
  `.gitignore:153` and does not appear in `git status`.
- **`grep -rn "depends_on"` over `hub/` is dominated by Alembic boilerplate** — every migration file
  declares `depends_on = None`. Filter it out or the search reads as "prior art exists" when there is
  none.
- **I initially framed dependency-readiness as a stored/displayed property of a task and worried
  about a task being "stopped for two reasons".** That was wrong and the operator corrected it. A
  task cannot be both `blocked` and dependency-unmet, because `blocked` is reachable only from
  `in_progress` and an unmet dependency prevents reaching it.
- **I proposed a derived off-board stub for cross-document dependencies.** Superseded by the
  operator's declared-import idea, which is better — do not re-propose the derived version.
- **I named the concurrency-cap slice "4a" without explaining it** and the operator did not
  understand; it was then withdrawn entirely. There is no 4a.

## Verification

**Ran, and passed:**

- `git push origin master` — twice, plus per-commit pushes. `origin/master` == `HEAD` == `706b481`,
  confirmed by `git log origin/master..HEAD` returning empty.
- `openspec validate corpus-aware-documents` → **valid**.
- `openspec validate agent-created-documents` → **valid**.
- `openspec validate task-dependencies` → **valid**.
- `openspec list` → 4 proposed changes, 2 complete.
- Every `file:line` citation in the two explorations and three change directories was read before
  being cited.
- `spec/index.json` parsed and summarised directly: **33 indexed documents, 35 `.html` on disk**,
  every `parent` is `null`, `order` unique 10–330, the two unindexed files are
  `spec/capabilities/project-instructions/spec.html` and `spec/capabilities/quiet-hours/spec.html`.
- Payload title+summary extracted from all 35 documents — **8 have no usable summary** (6 empty, 2
  still reading `TBD - created by syncing change …`).

**NOT tested — do not claim otherwise:**

- **No code was written or run this session.** Zero lines of Python, TypeScript or SQL. All four
  proposals are unimplemented.
- **No test suite was run.** `hub/tests/` and `tests/` have not been executed since handoff 0064
  reported 2508 passed / 404 passed on `4314567`. HEAD has moved 8 commits, all markdown.
- **No Hub was started and no browser was opened.** The five UI fixes from handoff 0063 remain
  jsdom-only and **still have not been seen working by a human.**
- **The suspected loop spin (§3 of the loop exploration) is UNVERIFIED.** It is reasoning from
  `CLAIMABLE_LOOP_TASK_STATUSES` and `TERMINAL_FOR_BINDING`, not an observed failure.
- **The claimed loop deadlock under dependencies is also unverified by execution** — it follows from
  reading `_loop_queue_order`, the claimable set, and the proposed gate, and `scheduler.py:243`
  describes the same mechanism, but nothing was run.
- **CI results for the pushed commits were not checked.** The push happened; whether `ci.yml` passed
  is unknown.

## Git state

- **Branch:** `master`. **HEAD:** `706b481`. **Working tree clean.**
- **Nothing unpushed.** `origin/master` == `HEAD`. This closes handoff 0064's repeated open question.
- This session added **eight commits**: `f8c67c3`, `d0d7c5f`, `17d02e7`, `26b7728`, `b3ece5d`,
  `170b3c9`, `ea5baf8`, `706b481`.
- `loop/2026-08-20-spec-corpus-migration` still exists and is fully merged.
- Untracked and gitignored: `.migration/`.

## Next steps

1. **Verify the suspected loop spin.** Create a loop over a document, drive its tasks to `completed`
   without approving them, and observe whether the loop keeps firing while claiming nothing. The
   prediction is in `openspec/explorations/2026-08-20-the-loop-under-dependencies.md` §3; the code is
   `hub/hub/scheduler.py:246` — `CLAIMABLE_LOOP_TASK_STATUSES` excludes `completed` — plus
   `hub/hub/run_task_binding.py:272`, where `TERMINAL_FOR_BINDING` is `("approved", "rejected")`,
   and the stop check at `hub/hub/scheduler.py:88-92`.
   **If it reproduces it is a live bug and should be fixed independently of everything else here.**
2. **Or implement one of the four proposals.** `/openspec-apply-change <name>`. All four validate and
   all four have an immediately executable task 1.1. Dependency order: `document-adoption` first
   (#2's two orphan documents need it), then the rest are independent.
3. **Or archive `writable-spec-index` and `operator-authored-documents`** — both complete, 0 open
   tasks, unarchived. `/openspec-archive-change`. Raised twice this session, not acted on.
4. **Or explore 4c's governance question** — whether an agent may declare a task's complexity. The
   precedent to reason from is `decide_evidence` refusing an agent that judges evidence it produced
   (`hub/hub/mcp_server.py:1127`). This is the only thing blocking 4c.
5. **Or explore #5** — the model catalog, the last untouched carve-up item.
6. **Run the test suites.** Not run since `4314567`; HEAD has moved 8 markdown-only commits, so the
   risk is low but the claim is stale.
7. **Browser-verify the five UI fixes** from handoff 0063 — still jsdom-only after three sessions.

## Open questions for the user

- **Which of next-steps 1–5?** Not asked; the session ended on a handoff request.
- **Register this repo as a project?** Answered "Not yet" in the previous session, not re-asked.
  `document-adoption`'s §8 human verification and `corpus-aware-documents`' task 6.1 both need it.
- **Retire `openspec/specs/`?** Open since handoff 0062.
- **Delete `proj-adf8a200`?** (the operator's home directory registered as a project.) Open since
  handoff 0063.
- **Who guarantees the review handoff** — the agent alone, the loop alone, or both? §7 of the loop
  exploration lays out the fork and recommends both, but it is undecided.
- **Does a task carry two complexity tiers (implementation and review), or is the review tier
  derived?** Raised by *"easy tasks can be reviewed by weaker agents"*, which the tier design did not
  anticipate.

## Read on resume

- `openspec/explorations/2026-08-20-the-loop-under-dependencies.md` — **first if doing next-step 1.**
  §3 is the suspected live bug, §2 the deadlock, §10 the L0–L5 split.
- `openspec/explorations/2026-08-20-what-the-spec-may-say-about-who-does-the-work.md` — every #4
  decision with its reason and its rejected alternatives. 616 lines; §8 is the carve-up, §9 what is
  still open.
- `openspec/explorations/2026-08-20-the-row-is-the-spine.md` — the parent carve-up (§9) that all five
  items come from. Still current.
- `hub/hub/scheduler.py:200-265` — `_loop_queue_order`, `CLAIMABLE_LOOP_TASK_STATUSES` and
  `_claim_loop_task`. The three facts both loop findings rest on.
- `hub/hub/task_transition_service.py:195-225` — where the third guard goes, and the comment
  explaining why that placement is load-bearing.
- `openspec/changes/task-dependencies/design.md` — D1–D9, if implementing rather than exploring.
