# Test guide — a document says how it will be built, and approval starts it

## Agent-verifiable

1. **Proposing needs an answer, and old documents are unharmed.** Tasks 1.1-1.3.
2. **Approval starts the declared flow on the next tick, as the operator.** Task 1.4.
3. **A flow that cannot be made never blocks approval, and the operator can replace a stale agent.**
   Tasks 1.5, 1.6.
4. **A board that fails is reported, not hidden, and cannot undo approval.** Task 1.7, with its
   mutation.
5. **The report and the stale flag are read, not written.** Tasks 1.8, 1.9.
6. **The agent is told to ask, and can name an agent.** Tasks 1.11, 1.12.

## Human-only

1. Explore a small change with a real agent. Before it proposes, it asks how the work will be built
   and recommends a flow. Answer "a flow, dev, stop when the queue empties".
2. The proposed page shows the Delivery section. Archive dev in another tab and reload: the page
   says the delivery is stale, beside Approve.
3. Approve, choosing another agent. The document is approved, the report lists the tasks and the
   flow, and the flow has not fired yet. It fires on the next 5-minute boundary.
4. Approve another document whose delivery says no flow. The board appears, and the report offers
   **Start a flow…**.
