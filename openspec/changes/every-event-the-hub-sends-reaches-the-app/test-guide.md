# Test guide — every event the Hub sends reaches the app

## Agent-verifiable

1. **The vocabulary is declared once and kept true.** 1.1-1.3 fail before and pass after. 1.2's
   injected `job_deleted` proves the dead-name check can fail.
2. **Nothing is dropped by name.** 1.5 (every admitted kind reaches a listener and invalidates what
   D4 says) and 1.6 (an unknown kind is dispatched; `connected` is not).
3. **The code already written for these kinds now runs.** 1.7 (`useCheckpoints`), 1.8 (the rail).
4. **A handler for a kind the Hub never sends fails the build.** 1.10, recorded once.
5. **F335 is not re-exposed.** 0.4 is checked before group 2; 3.2 on a live Hub.
6. **In the served bundle** (3.1): archiving a job and renaming a conversation update the screen
   without reload.

## Human-only

1. With a project's Activity tab open on a trial Hub, let an agent run long enough to cross its
   checkpoint threshold under `offered`. The checkpoint offer appears in the agent panel without a
   reload. Judge whether the newly visible feed lines (`checkpoint_due`, `agent_requested`,
   `worktree_released`, …) read as useful or as noise; any that read as noise is a new finding
   about its sentence, not a reason to drop the kind.
