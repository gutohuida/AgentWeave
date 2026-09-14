# Test guide — an unstaffed review names its holders

**Stopped at REV, 2026-09-14, unbuilt** (proposal.md, top). This guide describes the change as it
would be built. The rung-3 rows (A1, A3's two-task shape as it reads rung 3, and human items 1
and 3) are re-derived once the OPERATOR QUESTION is answered.

## Agent-verifiable (run by IMPL and DRIVE)

| # | check | how |
|---|---|---|
| A1 | The unstaffed reason names every agent and what it holds, and names at least one even when held task ids are long | Tasks 2.6–2.8 and 2.9b; the drive's `review_unstaffed` event |
| A2 | The history route survives a long reason, whatever wrote it (F367) | Tasks 2.9–2.12; `GET /api/v1/projects/<p>/jobs/<job>/history` → 200 on the drive Hub, including a wedged review with a long title |
| A3 | Two stuck reviews are recorded once each | Tasks 3.2–3.3; the drive's event count after two firings |
| A4 | The refusals name a remedy that exists for the status: Land it or a review dispatch for `completed`, the three exits for `under_review`; never "clear the assignee", never "approves", never the assignee-and-status PATCH (REV: it queues no turn) | Tasks 4.3–4.9; the drive follows the operator's remedy and sees a review turn start |
| A5 | An agent is told none of the task tools it is offered reassigns a task, and is not told "no agent can" | Task 4.4; one real Haiku turn in the drive |
| A7 | The guard's operator sentence keeps its remedy at a 64-character id and a 32-character name (REV) | Task 2.13 |
| A6 | Who is free did not change | The existing ladder, width and busy-guard suites, unchanged and green |

## Human-only (for the operator, on their own Hub after a restart)

These need judgement, not an assertion.

1. **Does the stall line tell you what to do?** Open *Loops*. On a flow with a finished task and
   every other agent holding work, read the amber line, then hover it. *Expect:* the first words
   name agents and tasks. The hover shows the whole sentence, ending with an action you can take.
   *Judge:* could you have unblocked LoopEngine on 2026-09-13 from this sentence alone, without
   asking an agent?
2. **Is Land it the right thing to be told?** Open a completed task still held by its author, and
   choose `under_review` in the status menu. *Expect:* a refusal naming **Land it**, which sits in
   the same drawer. *Judge:* is "Land it" what you would want to be pointed at, knowing it approves
   without an agent review, or refuses and names the evidence still unjudged? Or should the product
   also offer a way to hand the review to a specific agent (F336)?
3. **Is the sentence too long?** With four or more agents it runs to several hundred characters.
   *Judge:* is naming every agent worth the length, or should it name only those holding work
   outside the flow? That second shape depends on the OPERATOR QUESTION in `proposal.md`.

## Not covered by this change

- **Which agents count as free.** That is the OPERATOR QUESTION in `proposal.md`, and F352 stays
  open for it.
- **An agent reassigning a task over HTTP** (F366). Noted, not changed. The agent's refusal is
  worded so it does not depend on the answer.
