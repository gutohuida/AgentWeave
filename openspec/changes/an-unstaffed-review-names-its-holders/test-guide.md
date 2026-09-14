# Test guide — an unstaffed review names its holders

## Agent-verifiable (run by IMPL and DRIVE)

| # | check | how |
|---|---|---|
| A1 | The unstaffed reason names every agent and what it holds | Tasks 2.6–2.8; the drive's `review_unstaffed` event |
| A2 | The history route survives a long reason | Task 2.9; `GET /api/v1/projects/<p>/jobs/<job>/history` → 200 on the drive Hub |
| A3 | Two stuck reviews are recorded once each | Tasks 3.2–3.3; the drive's event count after two firings |
| A4 | The refusals name Land it, never "clear the assignee" | Tasks 4.3–4.7 |
| A5 | An agent is told it cannot change who holds a task | Task 4.4; one real Haiku turn in the drive |
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
   without an agent review? Or should the product also offer a way to hand the review to a
   specific agent (F336)?
3. **Is the sentence too long?** With four or more agents it runs to several hundred characters.
   *Judge:* is naming every agent worth the length, or should it name only those holding work
   outside the flow? That second shape depends on the OPERATOR QUESTION in `proposal.md`.

## Not covered by this change

- **Which agents count as free.** That is the OPERATOR QUESTION in `proposal.md`, and F352 stays
  open for it.
- **An agent reassigning a task over HTTP** (F366). Noted, not changed.
