# Test guide — a document's rigor history and retired requirements are on screen

## Agent-verifiable

1. **The payload orders are pinned** at the routes (1.1), and the UI tests use them (1.2, 1.6).
2. **History newest first**, from an ascending payload. Task 1.2 fails before and passes after.
3. **A demotion carries a reason; a promotion may not.** Tasks 1.3–1.5.
4. **Retired requirements and their work are reachable.** Tasks 1.6–1.7.
5. **A failed read says so.** Task 1.8.
6. **Bundle matches source** (`AW_CHECK_UI_BUNDLE=1`, `test_ui_build_stamp.py`).
7. **Drive** (3.1), with screenshots.

## Human-only

1. Open a document and change its Enforcement. Does the confirm row read clearly? When lowering it,
   is the reason prompt's wording right — does it explain why a reason is asked?
2. Open *History*. Is it clear who changed what, and why?
3. On a document that dropped a requirement, open *retired requirements*. Would you know from it
   that work still points at a requirement the document no longer states?
