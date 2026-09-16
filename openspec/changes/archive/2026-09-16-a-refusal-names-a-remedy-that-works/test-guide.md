# Test guide — a refusal names a remedy that works

Split from `an-unstaffed-review-names-its-holders` on 2026-09-15. Row ids kept from the parent's
guide where the check carried over, so a reader who knows that guide can find its own way here.

## Agent-verifiable (run by IMPL and DRIVE)

| # | check | how |
|---|---|---|
| A3 | Two stuck reviews are recorded once each | Tasks 3.2–3.3; the drive's event count after two firings |
| A4 | The refusals name a remedy that exists for the status: Land it or a review dispatch for `completed`, the three exits for `under_review`; never "clear the assignee", never "approves", never the assignee-and-status PATCH (it queues no turn) | Tasks 4.3–4.9; the drive follows the operator's remedy and sees a review turn start |
| A5 | An agent is told none of the task tools it is offered reassigns a task, and is not told "no agent can" | Task 4.4; one real Haiku turn in the drive |
| A7 | The guard's operator sentence keeps its remedy at a 64-character id and a 32-character name | Task 4.10 |
| A2' | The history route survives a write this change fits — the parent's A2 also covers rung-3-produced writes, not this change's business | Tasks 2.1–2.3; `GET /api/v1/projects/<p>/jobs/<job>/history` → 200 on the drive Hub after a wedged review with a long title |

## Human-only (for the operator, on their own Hub after a restart)

1. **Is Land it the right thing to be told?** Open a completed task still held by its author, and
   choose `under_review` in the status menu. *Expect:* a refusal naming **Land it**, which sits in
   the same drawer. *Judge:* is "Land it" what you would want to be pointed at, knowing it approves
   without an agent review, or refuses and names the evidence still unjudged? Or should the product
   also offer a way to hand the review to a specific agent (F336)?
2. **Is the dispatch refusal's new wording clear?** Dispatch a review of an `under_review` task to
   its own completer. *Expect:* a refusal naming approve/reject/revision_needed, not "Reassign".
   *Judge:* is "let the review in flight finish, or decide it yourself" clearer than the old
   "Reassign the task"?

## Not covered by this change

- **Which agents count as free, and what rung 3 says about them.** That is the sibling directory,
  `an-unstaffed-review-names-its-holders`, re-deriving against `F352-free` (decided (f),
  2026-09-15).
- **The board's stall-line hover.** Sibling directory's D6.
- **An agent reassigning a task over HTTP** (F366). Noted, not changed. The agent's refusal is
  worded so it does not depend on the answer.
