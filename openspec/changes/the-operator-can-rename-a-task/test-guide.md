# Test guide — the operator can rename a task

## Agent-verifiable

1. **Renaming works and is not a transition.** Task 1.1.
2. **Blank, null and agent renames are refused.** Tasks 1.2, 1.2a, 1.3; 1.3a proves the agent
   refusal comes before any write.
3. **The drawer edits in place, and a blocked task can be renamed.** Tasks 1.4, 1.4a: the rename
   sends only `{title}` (operator review 2026-09-24).

## Human-only

1. In a browser on a trial Hub, rename a task from its drawer: the board card and the drawer header
   update together, and Escape abandons an edit cleanly. Rename a `blocked` task too.
2. Know the skew (design D5): until the operator restarts `:8000` on the new code, a rename from
   `:8000`'s reloaded page answers with an error and changes nothing.
