# Test guide — a refused first send leaves no exploration behind

## Agent-verifiable

1. **Refused before queueing leaves nothing.** Tasks 1.1 and 1.4 pass after commit A. 1.1b
   reproduces the orphan on today's two-request sequence.
2. **Refused by the dispatch leaves nothing.** Task 1.2 passes after commit A, and fails if the
   discard call is removed from the F108 branch.
3. **Accepted keeps exactly one.** Tasks 1.3 and 1.4.
4. **The discard cannot touch a document someone used.** Task 1.7's mutation check.
5. **Creation failure refuses and loses nothing.** Tasks 1.5 and 1.6 at the route, and 1.9's
   vitest case at the composer.
6. **Live, on `:8010`.** Task 4.1.

## Human-only

1. After commit B reaches `:8000` (the operator's reload, after their restart), arm explore on a new
   conversation with an agent that will refuse (archive one first). Send, read the error, and check
   that the text is still in the box. Open the specification list: nothing was added.
2. Unarchive, send again, and check that the side panel opens the one new document.
