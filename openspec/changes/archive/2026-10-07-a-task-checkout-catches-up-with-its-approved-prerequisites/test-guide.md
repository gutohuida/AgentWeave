# Test guide — a task checkout catches up with its approved prerequisites

## Agent-verifiable

1. **An early checkout gets its prerequisite's work once the prerequisite is approved** (F158 shape
   1). Task 1.1: an ancestry check, before and after.
2. **A prerequisite declared later reaches the checkout** (shape 2). Task 1.2.
3. **Catching up never damages a checkout.** Tasks 1.3 and 1.4 hash the branch tip and the tree.
4. **Unapproved work does not chase a started task; new checkouts are seeded as before.** Task 1.5.
5. **No cost for a task with no prerequisites.** Task 1.6.

## Human-only

1. On a trial Hub, two tasks where B depends on A. Message B's agent about B (naming the task) while
   A is still in progress, so B's checkout exists. Approve A with its work left off the main branch
   (for example with the operator's checkout dirty, so integration skips). Message B's agent again
   about B, and ask it to run `git log --oneline` in its checkout: A's commit is there.
