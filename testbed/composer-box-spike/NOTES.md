# Composer box spike (RSSC-1, FR-3 a-box-is-one-unit)

Throwaway. `index.html` is a contenteditable field with an inline box
(`<span class="box" contenteditable="false" data-ref=…>`), in three modes (`?mode=`):

- `native`: the browser handles every key.
- `guarded`: my own keydown handlers for Backspace, Delete, ArrowLeft and ArrowRight, plus the two hybrid handlers.
- `hybrid`: native keys, plus a `selectionchange` guard that moves a caret found inside a box to just after it, plus a plain-text paste handler.

Run `py -3.11 drive.py`: Playwright Chromium 151 with real CDP key presses, 18 scenarios per mode;
the exit code reflects hybrid only. `probes.py` and `ime_cancel_probe.py` cover copying a box, IME and auto-growth.
Last output: `drive-output.txt`.

## What held: hybrid (18/18)

- In Chromium (the app's pywebview runs on WebView2, which is Chromium), `contenteditable=false` already
  makes a box one character. Backspace after it or Delete before it removes the whole box. ArrowLeft and
  ArrowRight cross it in one press. A click cannot leave the caret inside it. Shift-selecting across it
  and deleting works, and so does undo.
- The real build needs **no key handlers** for FR-3. It does need two pieces:
  1. A **`selectionchange` guard**. Cancelling an IME composition right after a box leaves the caret
     *inside* the box (anchor = the box's text node, offset 6), and then the **next typed key is
     silently dropped** in native mode. The guard moves the caret just after the box, and typing works again
     (`ime_cancel_probe.py`).
  2. A **plain-text paste handler** (`execCommand('insertText', text/plain)`). Native paste of rich
     HTML inserts a `<b>` into the field. `insertText` keeps undo working.

## What failed

- `guarded` (my own Backspace/Delete handlers): removing the box with `box.remove()` bypasses the undo
  stack, so Ctrl+Z then replayed a stale step (`see nownow`). Switching to "select the box, then
  `execCommand('delete')`" restores the box, but leaves it selected instead of putting the caret back. Native is
  strictly better, so do not intercept these keys.
- One harness bug, fixed: `load()` lost the caret position when it merged text nodes.

## Pitfalls the real build must handle

- **Copying a box**: with the plain-text paste handler, copying a box and pasting it back gives
  the plain text `SPEC-1`, not a box. Native paste kept the box, because the HTML round-trips.
  Fix: on `copy`/`cut`, write our own payload too (a custom MIME, or `data-ref` in text/html), and on
  paste turn only *our* boxes back into boxes; everything else is plain text.
- **IME**: composing next to a box works (`你好` lands after the box). A cancelled composition needs the
  selectionchange guard above. Any keydown logic added later must skip `e.isComposing`.
- **Undo**: any change made to the DOM directly (inserting a box from the `@` menu or the side panel)
  bypasses the native undo stack. Insert boxes with `execCommand('insertHTML', …)` or keep our own history.
  `insertBox()` in the spike uses `range.insertNode`, which has this problem.
- **Selection across a box**: works natively. When you serialise, a box is one token (`[[id]]`),
  and the caret offset must count it as one.
- **Auto-growth**: the div grows with content (34 → 74 px over three lines). Cap it with `max-height` +
  `overflow-y:auto`; the textarea's `scrollHeight` resize code is not needed. Shift+Enter inserts `\n`
  under `white-space: pre-wrap`; make sure Enter still sends.
- **`@` trigger**: reading the text before the caret in the current text node works both after a space and
  directly after a box (a box is a text-node boundary, so `^@` matches). Decide whether `SPEC-1@x`
  (`@` straight after a box with no space) should open the menu: it does here.
- A trailing box needs no zero-width filler in Chromium: ArrowRight and typing after a final box both work. This
  was not checked in Firefox or WebKit (only Chromium is installed), where it has historically failed.
