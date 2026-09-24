# Test guide — the coverage bar takes the evidence decision it asks for

## Agent-verifiable

1. **The decision is announced.** 1.1 fails today (no `spec_updated` after a decision) and passes after.
2. **Pieces render in the route's order, the most recently recorded marked *latest*.** 1.2 — a reversed fixture fails it.
3. **The two buttons send what they say.** 1.3, 1.4.
4. **Refusals are visible.** 1.5, 1.6.
5. **Rows without evidence are unchanged.** 1.7.
5a. **Accept says it may merge into main.** 1.3a — only on a piece that names a commit.
5b. **A greyed row un-greys when its run ends.** 1.9 fails today; the broadcast is sent only after
    the run has left the liveness registry. 1.9a: other runs send nothing.
6. **Bundle.** `ui-build-stamp.json` updated by the script, not by hand.

## Human-only

1. Open a document whose coverage bar reads *awaiting review*. Open the bar and the requirement's
   **Evidence** toggle. You should see who recorded each piece, what it says, and which commit and
   branch it names. Ask yourself: could you tell from this alone whether to accept it?
2. Accept one. The bar's counts change without reloading, and if a task was approved and waiting on
   that evidence, its drawer shows the merge.
3. Try Reject with no reason: the button stays disabled.
3a. Before accepting, read the sentence beside Accept: it should tell you, before you click, that the
    commit may be merged into main.
3b. Open the Evidence row while the agent that recorded the evidence is still running. The row reads
    *still being recorded*. When the run ends, it becomes decidable without a reload.
4. With a second browser tab on the same document, decide in the first; the second updates.
