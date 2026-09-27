# Test guide — a document says how it will be built, and approval starts it

## Agent-verifiable

1. **Proposing needs an answer, and old documents are unharmed.** Tasks 1.1-1.3.
2. **Approval starts the declared flow on the next tick, as the operator, and announces it only
   after its commit.** Task 1.4, and `test_an_event_is_announced_after_commit.py` unchanged.
3. **A flow that cannot be made never blocks approval, the operator can replace a stale agent, and
   a re-approval does not make a second flow, nor calls an ended one working, nor silently drops a
   replacement agent.** Tasks 1.5, 1.6 (the claim race and the failure after adoption, both of which
   must answer 200, not 500, and publish no `job_created` frame).
3a. **An approval that gives the flow no tasks starts no flow**, whether the board failed or every
   declared task was already served. Task 1.6c, with its mutation.
4. **A board that fails is reported, not hidden, cannot undo approval, and leaves no half board.**
   Task 1.7, with its mutation.
5. **The report and the stale flag are read, not written, and approval agrees with the flag.**
   Tasks 1.8 (with a frozen clock, the second of two approvals is the one returned), 1.9.
6. **`POST /jobs` no longer leaves a job without its loop, and a claim race answers 409.** Task 1.10.
6a. **A document saved with no delivery keeps its bytes, and an unchanged resubmission to a `contract`
   document written before the upgrade files no proposal.** Task 1.1.
7. **The agent is told to ask (change documents only), and can name an agent.** Tasks 1.11, 1.12.

## Human-only

1. Explore a small change with a real agent. Before it proposes, it asks how the work will be built
   and recommends a flow. Answer "a flow, dev, stop when the queue empties".
2. The proposed page shows the Delivery section. Archive dev in another tab. Without reloading, the
   page says the delivery is stale, beside Approve.
3. Approve, choosing another agent. The document is approved, the report lists the tasks and the
   flow, and the phase bar shows the flow rather than **Start a flow…**. The flow has not fired
   yet; it fires on the next 5-minute boundary.
4. Approve another document whose delivery says no flow. The board appears, the report says no
   flow was started and points to **Start a flow…** above it, and the page shows that button once,
   in the phase bar. Start one: the button and the pointer disappear, and the report still says no
   flow was created at approval.
