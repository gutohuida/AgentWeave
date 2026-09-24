# Test guide — the coverage bar takes the evidence decision it asks for

## Agent-verifiable

1. **The decision is announced.** 1.1 fails today (no `spec_updated` after a decision) and passes after.
2. **Pieces render in the route's order, the most recently recorded marked *latest*.** 1.2 — a reversed fixture fails it.
3. **The two buttons send what they say.** 1.3, 1.4.
4. **Refusals are visible.** 1.5, 1.6.
5. **Rows without evidence are unchanged.** 1.7.
6. **Bundle.** `ui-build-stamp.json` updated by the script, not by hand.

## Human-only

1. Open a document whose coverage bar reads *awaiting review*. Open the bar and the requirement's
   **Evidence** toggle. You should see who recorded each piece, what it says, and which commit and
   branch it names. Ask yourself: could you tell from this alone whether to accept it?
2. Accept one. The bar's counts change without reloading, and if a task was approved and waiting on
   that evidence, its drawer shows the merge.
3. Try Reject with no reason: the button stays disabled.
4. With a second browser tab on the same document, decide in the first; the second updates.
