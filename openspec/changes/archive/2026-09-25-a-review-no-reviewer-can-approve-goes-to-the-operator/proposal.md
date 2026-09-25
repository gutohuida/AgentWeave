# Proposal — a review no reviewer can approve goes to the operator

**Round 1, 2026-09-24** (bundle B1, decision D9). Finding: **F374 (B)**. Re-verified by reading on
HEAD `404c7d5`. **Nothing here is implemented yet.**

**D9 is already answered.** ROUNDS.md lists D9 (*"Is a gate-refused approval 'no verdict', and what
does the divergence reason say?"*, `spec-queue/ROUNDS.md:354`) as open, but the operator decided it
on 2026-09-19: `spec-queue/DECISIONS.md` **`F374-fix`** (`:985-991`) — *"A gate-refused approval is
not 'no verdict', and no operator-only refusal re-staffs. Any 409 naming a remedy only the operator
can apply ends the review and surfaces the gate's own sentence to the operator, rather than
re-staffing to a second reviewer who meets the identical refusal. Deliberately broader than F374
measured."* ROUNDS.md's row is stale. This change builds that verdict; nothing had built it
(`git log -S F374 -- hub/` finds nothing, and `_answer_failed_review` has no gate check,
`run_divergence.py:375-487`).

Ordered after `a-task-is-attended-only-by-a-turn-that-will-reach-it` (it adds a third sentence at
the F154 reason choice that change rewrites) and before `a-flow-stages-its-review-in-the-dispatch`
(which edits the same `_answer_failed_review` restaff).

## Why

A flow's reviewer that reaches no verdict is answered by `_answer_failed_review`
(`hub/hub/run_divergence.py:375-487`): a declared reviewer is surfaced, an availability-picked one is
replaced by resolving again (`:436-487`). Neither branch asks *why* there was no verdict. Where the
reason is the approval gate's `unaccepted` refusal (`requirement_gate._check_unaccepted`,
`:493-541`), whose remedy is *"accept the evidence, or grant an agent the capability to accept it —
both are the operator's"* (`ACCEPT_OR_GRANT`, `:77-80`), the second reviewer meets the identical 409.
F374 measured it live twice: `beta` refused three times, re-staffed to `gamma`, refused again.

**Shape since filing.**
- F374's point 2 (*"the surfaced reason is false"*, the rung-3 sentence claiming everyone was busy)
  is **fixed** by `an-unstaffed-review-names-its-holders` (archived 2026-09-23): `_answer_failed_review`
  now passes a per-agent exclusion reason (`:448-455`: *"reviewed this task and recorded no
  verdict"*), and `_rung_3_reason` names each agent with its own clause (`scheduler.py:1373-1420`).
- F357 (Round 5, 2026-09-23) now tells an ungranted reviewer, in its briefing, that approval can be
  refused and to `ask_user` the operator (`review_turn.verdict_evidence_sentence`,
  `review_turn.py:178-237`). A reviewer that does so keeps its turn live, and no divergence occurs.
  A reviewer that ends without asking, or whose question is declined or expires, still reaches
  `_answer_failed_review` — points 1 and 3 remain.

## What Changes

- **One predicate: is approval held for the operator?** (design D1)
  `requirement_gate.approval_held_for_operator(session, task, *, candidate)` evaluates the gate as a
  run would (`evaluate`, `:600`) and answers the gate's sentence when the refusal includes a
  category only the operator can remove for that candidate: `unaccepted`, or a `blocking` entry in
  `awaiting_review` (both are evidence decisions) where the candidate lacks `can_accept_evidence`;
  or `diagnostics` (a requirement that cannot hold evidence as written); or, whatever the candidate
  is granted, F424's "could not ask git" (operator, 2026-09-24, `spec-queue/tracks/reviews/B1-2026-09-24.md`
  §2). Any other exception is logged at warning and answers `None`. The evaluation runs in a
  savepoint, and its git spawns run off the event loop with a 5 s diagnostic timeout.
- **The restaff asks it** (design D2). In `_answer_failed_review`, after the resolution picks
  `choice.agent`, a held approval surfaces instead of restaffing. For a declared reviewer, the
  surfaced sentence is the gate's rather than *"asking this one again"*.
- **The flow's later surfacing asks it** (design D3). The F154 reason for the task (`decide_firing`,
  after change 1's D2) uses a gate-held sentence, remedy first, fitted to 500 characters.

No migration, no route shape, no UI.

## Capabilities

### Modified Capabilities

- `agent-flows` — *A flow resolves a reviewer by declaration, then by availability*: a review that
  gave no verdict is not re-resolved where approval waits on the operator and the selected agent
  cannot remove the reason.

### New Requirements

- `agent-flows` — *A review no reviewer can approve is handed to the operator*.

## Impact

- `hub/hub/requirement_gate.py`: one new public function.
- `hub/hub/run_divergence.py`: `_answer_failed_review` (`:375-487`).
- `hub/hub/scheduler.py`: the F154 reason choice in `decide_firing`, and one sentence function.
- `hub/tests/`: one new file.
