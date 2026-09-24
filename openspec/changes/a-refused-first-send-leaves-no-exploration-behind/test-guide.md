# Test guide — a refused first send leaves no exploration behind

## Agent-verifiable

1. **Refused before queueing leaves nothing.** Tasks 1.1 and 1.4 pass after commit A. 1.1b
   reproduces the orphan on today's two-request sequence.
2. **Refused by the dispatch archives, and deletes nothing.** Tasks 1.2 and 1.2b pass after
   commit A, and fail if the retire call is removed from the F108 branch or nested under the
   withdraw's `True`.
3. **Accepted keeps exactly one.** Tasks 1.3 and 1.4.
4. **The retire cannot touch a document someone used.** Task 1.7's mutation check.
5. **Creation failure refuses and loses nothing.** Tasks 1.5 and 1.6 at the route, and 1.9's
   vitest case at the composer.
5a. **Failures answer with a sentence and clean up fully.** Tasks 1.6 and 1.11: 503/409 with a
   code and a sentence, and neither the file nor the minted directory remains. Task 1.3: an accepted
   send broadcasts `spec_updated`.
5b. **A failed send cannot delete another send's document.** Tasks 1.10 and 1.12 (design D6).
6. **Live, on `:8010`.** Task 4.1.

## Human-only

1. After commit B reaches `:8000` (the operator's reload, after their restart), arm explore on a new
   conversation with an agent that will refuse (archive one first). Send, read the error, and check
   that the text is still in the box. Open the specification list: nothing was added.
2. Unarchive, send again, and check that the side panel opens the one new document.
