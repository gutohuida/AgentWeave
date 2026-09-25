# Test guide — a document says how it will be built, and approval starts it

## Agent-verifiable

1. **Proposing needs an answer, and old documents are unharmed.** Tasks 1.1-1.3.
2. **Approval starts the declared flow on the next tick, as the operator.** Task 1.4.
3. **A flow that cannot be made never blocks approval, the operator can replace a stale agent, and
   a re-approval does not make a second flow.** Tasks 1.5, 1.6 (including the race that must answer
   200, not 500).
4. **A board that fails is reported, not hidden, cannot undo approval, and leaves no half board.**
   Task 1.7, with its mutation.
5. **The report and the stale flag are read, not written, and approval agrees with the flag.**
   Tasks 1.8, 1.9.
6. **`POST /jobs` no longer leaves a job without its loop.** Task 1.10.
7. **The agent is told to ask (change documents only), and can name an agent.** Tasks 1.11, 1.12.

## Human-only

1. Explore a small change with a real agent. Before it proposes, it asks how the work will be built
   and recommends a flow. Answer "a flow, dev, stop when the queue empties".
2. The proposed page shows the Delivery section. Archive dev in another tab. Without reloading, the
   page says the delivery is stale, beside Approve.
3. Approve, choosing another agent. The document is approved, the report lists the tasks and the
   flow, and the phase bar shows the flow rather than **Start a flow…**. The flow has not fired
   yet; it fires on the next 5-minute boundary.
4. Approve another document whose delivery says no flow. The board appears, and the report offers
   **Start a flow…**. Start one: the offer disappears, and the report still says no flow was created
   at approval.
