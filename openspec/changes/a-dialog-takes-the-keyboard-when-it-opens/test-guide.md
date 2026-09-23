# Test guide — a dialog takes the keyboard when it opens

## Agent-verifiable

1. **Focus moves in, to the mark.** Tasks 1.1–1.3: the marked control, not DOM order, receives focus;
   an unmarked dialog focuses its first control. All fail today.
2. **Every confirmation opens on Cancel, and Enter cancels.** Task 1.5, per dialog.
3. **A dialog with nothing enabled still holds the keyboard.** Task 1.4.
4. **Closing returns the keyboard.** Task 1.6 measures today's behaviour first; 1.7 pins the fix.
5. **Nothing UI-1 fixed moves.** Task 1.8.
6. **In a real browser** (3.1): the drive's leg E, press by press.

## Human-only

1. With a screen reader running, open "Clear instructions": the dialog's question is read on open.
2. Open, then close, each of the seven dialogs with the keyboard alone, and confirm the keyboard is
   back on the control that opened it.
