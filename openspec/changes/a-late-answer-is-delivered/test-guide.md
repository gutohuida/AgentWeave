# Test guide — a late answer is delivered

## Agent-verifiable

| What | How | Task |
|---|---|---|
| An answer after the wait ended, while the run lives, is queued | route test with `wait_ended_at` set and a `running` run | 1.2 |
| An answer in the tool's grace window is not queued twice | route test with `wait_expires_at` passed and `wait_ended_at` NULL | 1.3 |
| A decline that completes a late batch delivers it | route test | 1.4 |
| List and detail agree that nobody is waiting | the agreement test, with the new row | 1.5 |
| The expiry report delivers answers the tool never received, once per batch | report test, 4-question batch | 2.2 |
| Completeness is judged on committed state | the sibling answered mid-request | 2.3 |
| A queued answer waits behind the live run | scheduler test | 2.5 |
| Repeated reports and lone late declines queue nothing more | report tests | 2.6, 2.7 |
| Either order of answer and report delivers exactly once | both orders | 3.1, 3.2 |
| An answer or decline landing between the report's load and its write: the answer is delivered, the decline is not stamped | a second session commits mid-report (Round 2) | 2.8, 2.9 |
| A decline landing mid-sweep at the run's end is not stamped | a second session commits after the sweep's load (Round 3) | 2.10 |
| The real tool, the real wait and a real agent | drive 5.2–5.4 on a drive Hub | 5.x |

## Human-only

1. **The question card after the wait.** Ask a question from an agent whose question timeout is
   short, and let the wait run out while the agent keeps working. The card should switch to its
   *nobody waiting* look while the run is still working, not only once the run ends.
2. **The answer arrives.** Answer it then. When the agent's current turn ends, a new turn should
   start that carries your answer. Judge whether the agent's use of it reads as sensible, given
   that it had already gone on without it. That judgement is D6's open question about wording.
3. **Nothing twice.** Answer a question promptly, inside the wait. The agent should get it once, as
   its tool result, and no second turn should follow.

## Known and accepted

- **A decline given after the tool's last poll is not delivered as a decline** where the rest of
  its batch was already returned (design D3). The agent reads that question as unanswered, not as
  declined. It is accepted, because delivering it would mean either recording a decline as silence
  or sending the agent answers it already has.
- **A lost report, then an answer inside the run's remaining life** (design D5, the proposal's
  *Residual*). Still lost. Nothing in the Hub can tell it apart from an answer the tool received.
- **(Round 2) A timeout lengthened while a run is live** leads to the same outcome by a second
  route. The tool gives up at the old deadline, and its report is refused against the new one
  (design, *Context*). A later answer inside the run's life is lost. Round 2 names a no-migration
  way to deliver both at the run's end, left to a follow-on change (design D5).
- **(Round 3) An answer given inside the wait, then the run dies before the tool's next poll**
  (up to 2 s). The answer is lost. This is pre-existing. Neither this change nor the no-migration
  option reaches it; only a receipt stamp would (design D5, the route table).
