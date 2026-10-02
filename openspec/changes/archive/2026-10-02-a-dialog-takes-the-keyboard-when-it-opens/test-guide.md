# Test guide — a dialog takes the keyboard when it opens

## Agent-verifiable

1. **Focus moves in, to the mark.** Tasks 1.1–1.3: the marked control, not DOM order, receives focus;
   an unmarked dialog focuses its first control. All fail today.
2. **Every confirmation opens on Cancel, and Enter cancels.** Task 1.5, per dialog.
3. **A dialog with nothing enabled still holds the keyboard.** Task 1.4.
4. **Closing returns the keyboard.** Task 1.6 measures today's behaviour first; 1.7 pins the fix.
5. **Nothing UI-1 fixed moves.** Task 1.8.
6. **The four dialogs outside the hook join it.** Tasks 1.9-1.12: the charter, runner and job forms
   and `SetupModal` focus their first field on open (the job form's, not its Close button), close on
   Escape, and return focus to the opener. Each fails today.
7. **A control disabled while pending does not drop the keyboard.** Task 1.13: `ArchiveConfirmDialog`
   and `JobForm` move focus to their panel.
8. **No modal dialog is left outside the hook.** Task 2.9's grep.
9. **In a real browser** (3.1, 3.2): the drive's leg E, press by press, and the four moved dialogs.

## Human-only

1. With a screen reader running, open "Clear instructions": the dialog's question is read on open.
2. Open, then close, each of the eleven dialogs (the seven hook users and the four moved onto it)
   with the keyboard alone, and confirm the keyboard is back on the control that opened it.
3. With a screen reader running, archive a document: while it says "Archiving…" the reader stays in
   the dialog (it does not announce the page behind it), and the browser's `document.activeElement`
   is the dialog panel, not `<body>`.
4. With the app connected, open Settings (the rail's setup control), press Escape: the dialog closes
   and the keyboard is back on that control. With the app not yet connected, Escape leaves it open.
