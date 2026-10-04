# Test guide — a secret split across two events is still scrubbed

## Agent-verifiable

1. **The split is caught in the order the runner emits it.** Tests 1.1-1.4, 1.7 and 1.8 fail before group 2 and
   pass after it. 1.2 and 1.3 drive the real `CopilotEventMapper`, so their fixture order is the
   mapper's. Check that no case builds its event list by hand.
2. **Mutations, one at a time, each restored afterwards:**
   - drop the carried tail (`joined = c`): every row of 1.2 fails;
   - drop the dangling-start rule: the "message → finish" and three-way rows fail, and so does
     1.2's thought→message row, because the thinking row keeps `plainproxy`;
   - set `m` to 1: the `explai` false-positive row of 1.1 fails;
   - drop the boundary-whitespace skip (`joined = tail + c`, tail not right-stripped): 1.1's two
     whitespace rows and 1.2's thought-ending-in-a-blank-line row fail;
   - move the call from the executors into `record_agent_output`: 1.5 fails. Check that 1.5's lock
     is raised at the real function's `commit`, not before the real function runs; otherwise this
     mutation passes;
   - call it at only one of the two executor sites: 1.2 (RPC) or 1.4 (`exec`) fails.
   - move the call after `_on_event`'s first `await`: 1.8 fails;
   - drop the scrub from the `session.error` log line (if folded in): 1.7 fails;
   - let a raise from that scrub propagate: 1.7's third case fails (the error card is lost).
3. **Nothing else moved.** The controls in 1.6 pass before and after. The full Hub and CLI suites
   pass with their counts on tasks 3.1 and 3.2, and the lint block is clean.
4. **Drive 3.4.** Zero occurrences of the key in rows, events, SSE frames, the timeline response and
   the Hub log, with the split forced at a thought→message boundary and at a message→tool→message
   boundary. Paste the stored rows into the round log.
5. **No delay.** In the drive's SSE capture, each `agent_output` frame arrives when the mapper
   emits it. A thought is not held until the next text: the thinking frame comes before the text
   block that completes the value has closed.

## Human-only

1. Open the driven run in the app. The thought reads `… <redacted>`, the reply reads
   `<redacted> …`, and the two rows together do not spell the key. The redaction markers read as
   deliberate, not as garbled text.
2. In an ordinary Copilot provider-runner run with no key in its output, the timeline looks exactly
   as before: no stray `<redacted>`, and no thought or tool card appearing late.
3. Decide open questions 1-3 in design.md (hold or not, and *m*; joining across tool cards; the
   `session.error` log line). These are judgments about acceptable exposure and delay, so they are
   the operator's.
