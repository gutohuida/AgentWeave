# Test guide — a pending proposal can be withdrawn

## Agent-verifiable

1. **A repeat stacks nothing** (F213). Task 1.1 fails before and passes after, on F213's own staging.
2. **A revision supersedes; another proposer's does not.** Tasks 1.2–1.4.
3. **Withdraw records no judgement, and only the operator can.** Tasks 1.5–1.6.
4. **Deciding refreshes every view.** Tasks 1.7 and 1.11 — 1.11 uses a real query client, which is
   how the defect escaped the mocked panel test.
5. **Twins are marked in the route's order, and by digest.** Tasks 1.10, 1.10b and 1.10c.
5a. **A take-back is superseded** (review). Tasks 1.14 and 1.15 fail before and pass after.
5b. **A decided proposal is not decided again** (review). Task 1.16 fails before; 1.17 guards the
   supersede and accept paths.
6. **Nothing else moved.** Control 1.8 and the full-suite count.
7. **Drive** (3.1), with screenshots.

## Human-only

1. On a `gate` document with pending proposals, is the difference between **Reject** and
   **Withdraw** clear from the buttons and tooltips? Reject says the edit is wrong; Withdraw says it
   should not be considered.
2. If you have duplicate proposals from before this change, does *"same as the one above"* make it
   obvious which to withdraw?
