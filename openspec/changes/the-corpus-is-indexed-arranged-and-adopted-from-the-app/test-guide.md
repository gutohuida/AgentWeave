# Test guide — the corpus is indexed, arranged and adopted from the app

## Agent-verifiable

1. **Reindex announces itself.** Task 1.1 fails before and passes after.
2. **No route's behaviour moved.** Control 1.2.
3. **The home is asked for, not guessed.** Task 1.4, using the diagnostics in the order
   `build_index` emits them.
4. **Adopt and place show the Hub's own reasons.** Tasks 1.6–1.9.
5. **The bundle matches the source** (`AW_CHECK_UI_BUNDLE=1`, `test_ui_build_stamp.py`).
6. **Drive** (3.1), with screenshots.

## Human-only

1. Open the document browser (Ctrl+K). If your corpus has no index, the strip at the top says so.
   Is the sentence clear about what an index is *for* (home, hierarchy, order)?
2. Press **Rebuild index**. If it asks for a home, is it obvious which document you would call home?
3. Open a document and use **Place under…**. After placing it, does the rendered document's own
   navigation show where it now sits?
4. If you have files on disk the Hub does not track, do the **Adopt** buttons appear only on them?
