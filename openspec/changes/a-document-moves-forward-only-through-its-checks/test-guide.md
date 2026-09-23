# Test guide — a document moves forward only through its checks

## Agent-verifiable

1. **The back door is shut.** 1.1: the phase route refuses to propose an empty document. It fails today.
2. **Approval re-checks.** 1.2: a proposed document edited into incompleteness cannot be approved,
   and no tasks are created. It fails today.
3. **One list.** 1.3/1.4: `propose` names the open exploration beside the other blockers.
4. **Illegal moves still read as illegal.** 1.5.
5. **The happy path is unchanged.** 1.6.
6. **F207's reproduction**, driven (3.1).

## Human-only

1. Open a proposed document in the app, have an agent (or the content editor) remove a task so a
   requirement is unserved, and press **Approve**. You should see the finding listed under the phase
   bar, in the same style as a blocked proposal, and the phase should still read `proposed`.
2. Fix it and press Approve again: it approves and the board gains the document's tasks.
