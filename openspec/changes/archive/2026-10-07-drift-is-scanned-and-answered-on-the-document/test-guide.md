# Test guide — drift is scanned and answered on the document

## Agent-verifiable

1. **Filters, once-only answers, broadcasts, remedy.** Tasks 1.1–1.5 fail before and pass after.
2. **Coverage precedence did not move.** Control 1.6.
2a. ***Code corrected* asks again when the code did not go back (F436).** Task 1.13 fails before and
   passes after; control 1.14 shows the other two answers still silence the change.
2b. **The route's own order is pinned** (F190). Task 1.15, with a tie on `created_at`.
3. **The strip reads the route's order** (F190). Task 1.7's fixture is `created_at` ascending, as
   `list_drift` orders it; a component that re-sorts fails it.
4. **Buttons send the right enum; refusals are shown.** Tasks 1.8–1.11.
5. **Other tabs refresh.** Task 1.12, and the second-tab step of the drive.
6. **The bundle matches the source.** `AW_CHECK_UI_BUNDLE=1 py -3.11 -m pytest hub/tests/test_ui_build_stamp.py`.
7. **Drive** (3.1), with screenshots.

## Human-only

On the operator's own app, after the bundle reaches it:

1. Open a document that has accepted evidence. Beneath the coverage bar there is a *Drifting* strip
   (or, if nothing drifts, only the **Scan for drift** line). Read it: does each candidate say which
   requirement, which file, and which verified evidence it is about, in words you recognise?
2. Press **Scan for drift**. The sentence should say the scan covered the whole project.
3. Answer one candidate. Does the choice of three words say what you meant? If *Spec updated* reads
   as "I have already edited the spec" when you meant "the spec should change", say so — the
   resolution's meaning is the product's, and the label is the only place it is stated.
4. With the document open in two windows, answer in one; the other should stop showing it without a
   reload.
5. Press **Code corrected** on a candidate without changing the code, then **Scan for drift**. The
   candidate should come back. Does the tooltip make that outcome unsurprising?
