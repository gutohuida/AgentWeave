# Tasks — Charter read view

## 1. The read affordance

- [ ] 1.1 `ChartersPage.tsx` — hold expansion as a set of charter IDs in component state, so rows
      toggle independently and all start collapsed (design D3). Not persisted, not in the URL, not in
      the query cache.
- [ ] 1.2 Add the disclosure control: a real `<button>` carrying `aria-expanded` and an accessible
      name that includes the charter's name, using the existing `Icon` component (D4). Nine of these
      must be distinguishable in a screen reader's control list.
- [ ] 1.3 Render the expanded region as text, not as a form — `white-space: pre-wrap`, the monospace
      face already used for charter content, no border, no input background, no cursor change. A
      read-only `<textarea>` is specifically rejected: it reintroduces the read/write ambiguity this
      change exists to remove (D4).
- [ ] 1.4 Keep the two-line clamp as the collapsed state (D3); it is a good summary and only its
      exclusivity was the defect.
- [ ] 1.5 Make the row's text region a toggle target, and confirm the edit/delete cluster is **not**
      inside it (D5). A click meant for the row must not be able to land on delete.
- [ ] 1.6 Leave `CharterForm` and every mutation untouched.

## 2. Handle the states the list can actually be in

- [ ] 2.1 A charter whose content is empty — the collapsed row already shows "No content"; confirm
      expanding one does not present a blank region with no explanation.
- [ ] 2.2 Confirm expansion state survives a background refetch of the charter list, since React
      Query will refetch and re-render rows underneath an open charter.
- [ ] 2.3 Confirm a charter deleted while expanded does not leave a dangling entry in the expansion
      set.

## 3. Tests — agent-verifiable

- [ ] 3.1 New `hub/ui/src/__tests__/charterReadView.test.tsx`: expanding a charter reveals its full
      content, and the content is not inside any editable element.
- [ ] 3.2 Two charters can be open at once — open one, open a second, assert the first is still open.
      This is the requirement a read-only modal would fail, so it is the test that pins design D1.
- [ ] 3.3 All rows start collapsed.
- [ ] 3.4 The disclosure exposes `aria-expanded` and toggles it, and its accessible name distinguishes
      it from the other charters' controls.
- [ ] 3.5 Expanding does not fire any mutation — assert the update/delete hooks are not called.
- [ ] 3.6 `npx vitest run` green; record the count against the 767 baseline.
- [ ] 3.7 `npx tsc --noEmit` clean. (`npm run lint` does not work in this repo; tsc is the check.)
- [ ] 3.8 Rebuild `hub/ui` and copy `dist` over `hub/hub/static/ui`, confirming with `diff -rq`.

## 4. Verification — human-only (the operator runs these)

These cannot be delegated to the agent: they are judgments about legibility, and the agent cannot
assess whether text reads well on the operator's screen.

- [ ] 4.1 Is unrendered markdown good enough to judge a charter by, or do the `#` and `-` get in the
      way? This is the evidence design D2 defers the renderer decision on — answer it honestly, since
      "fine" and "annoying" lead to different follow-ups.
- [ ] 4.2 With two charters open, can you actually compare them, or does the page get too long?
- [ ] 4.3 Does the expanded region read as a document rather than as a field you might be editing?

## 5. User test guide

**Setup.** Any project with charters. The fresh project created for
`2026-08-11-charter-set-reshape` is the useful one, because reading its nine charters is the task
this change exists to unblock.

1. **Reading no longer means editing.** Open the Charters screen and expand a charter.
   *Expect:* the full text appears in place, with nothing to save or cancel.
   *Failure looks like:* a dialog opens, or the text appears in a box that looks typeable.

2. **Two at once.** Expand a second charter without collapsing the first.
   *Expect:* both stay open.
   *Failure looks like:* opening the second closes the first.

3. **The list is still a list.** Reload the page.
   *Expect:* everything collapsed, all nine names visible as a scannable list.
   *Failure looks like:* the page opens as a wall of text.

4. **Editing still works.** Click the pencil on a charter, change nothing, and cancel. Then edit one
   for real and save.
   *Expect:* unchanged behaviour from before this change.
   *Failure looks like:* the editor no longer opens, or an edit does not persist.

5. **Nothing is edited by accident.** Expand a charter, click around inside its text, and reload.
   *Expect:* the content is exactly as it was.
   *Failure looks like:* any change persisting — the defect this change exists to prevent.

6. **Now do the thing it was blocking.** Read all nine charters and answer
   `2026-08-11-charter-set-reshape` section 7: does nine read as a set you would pick from?
