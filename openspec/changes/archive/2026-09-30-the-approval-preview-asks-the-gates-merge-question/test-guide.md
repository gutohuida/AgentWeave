# Test guide — the approval preview asks the gate's merge question

## Agent-verifiable

1. **The conflict is known before approve.** 1.1 fails today.
2. **Preview and refusal agree.** 1.2.
3. **It is fresh.** 1.3: resolving and re-evidencing clears it with nothing persisted to clear.
4. **Where it cannot ask, it says so and does not fail.** 1.4, 1.5, 1.5a — and on the ungoverned
   path, 1.5b and 1.5c: a git failure answers 200 with "could not ask git", git is not asked twice,
   and the task is never said to have no branch.
5. **No branch, working tree or index is touched by asking.** 1.1's `git status` and `main` HEAD
   checks. (The test merge writes unreferenced objects; that is expected.)
6. **It never claims a merge that will not happen, and counts truthfully.** 1.7 (nothing to merge
   is not "merges cleanly"), 1.8 (two commits say two).
7. **Not covered here: F424.** Pressing Approve when git fails still answers a bare 500 until F424
   is fixed; this change fixes only the preview.

## Human-only

1. Open a task under review whose branch conflicts with the main branch. Before pressing Approve,
   the note beside it should say approval would be refused and name the file. Press Approve anyway:
   the refusal names the same file.
2. Resolve the conflict on the branch and have the evidence re-recorded and accepted. Reopen the
   drawer: the note says it merges cleanly.
3. Optional, if a slow or broken git can be arranged (e.g. `git` temporarily off PATH for the trial
   Hub, never `:8000`): open the drawer of a loop task with its own branch. The note says the Hub
   could not ask git — it does not say the task has no branch, and the drawer does not error.
