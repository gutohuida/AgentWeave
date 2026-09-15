# Test guide — an unstaffed review names its holders

**Stopped 2026-09-15 — see `proposal.md`'s top banner.** A3, A4, A5 and A7 moved with the split to
`a-refusal-names-a-remedy-that-works/test-guide.md`. What remains here (A1, A2's non-moved rows,
A6, and the rung-3 human items) needs re-deriving against `F352-free`'s decision (option (f)) —
this guide still describes option (e), which did not ship, and is kept as a starting point for
that round, not as current truth.

## Agent-verifiable (run by IMPL and DRIVE) — to be re-derived against (f)

| # | check | how |
|---|---|---|
| A1 | The unstaffed reason names every agent and what it holds, and names at least one even when held task ids are long | Tasks 2.6–2.8 and 2.9b; the drive's `review_unstaffed` event |
| A2 | The history route survives a long reason produced by rung-3's own clause construction | Tasks 2.9–2.11; `GET /api/v1/projects/<p>/jobs/<job>/history` → 200 on the drive Hub |
| A6 | Who is free did not change **by this directory's own tasks** — it changed by (f), shipped separately | The existing ladder, width and busy-guard suites, unchanged and green |

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
