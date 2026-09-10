## Why

A ticket on the task board cannot be blocked from the keyboard, and one Escape dismisses two
things. Both were driven in a real browser on 2026-09-10 (`F309`, `F310`, day window `D-1`), against
the served bundle on a throwaway `:8013` Hub. Neither is a broken control: the mouse path works
perfectly in both cases. Both are the same failure of arbitration — **two mechanisms act on one
keystroke, and the one further from the operator wins.**

### `F309` — the reason a block requires cannot be typed

The Hub refuses a hand-set block without a statement of what the task is waiting for, so
`TaskDetailDrawer` asks for it rather than sending a status that would be refused
(`hub/ui/src/components/tasks/TaskDetailDrawer.tsx:296-299`, and the comment at `:143-145` says so
explicitly). Choosing **Move to blocked** mounts an input with `autoFocus`
(`TaskDetailDrawer.tsx:409-411`). Measured, leg `C2c`:

| | |
|---|---|
| `document.activeElement` after the input mounts | `BUTTON`, `data-testid="task-status-menu-<task-id>"` |
| the field's value after typing `the staging API key` | `''` |

Nineteen keystrokes, none of them in the field. `RowMenu` is a Radix `DropdownMenu`
(`hub/ui/src/components/layout/RowMenu.tsx:65`), and Radix returns focus to the trigger as the menu
closes — after React has mounted the input.

Then the second-order cost, which is why this is severity **A** and not B. The trigger is a
`<button>`, so a space is a click. Leg `P5`, one `Space` on the focused trigger:

```
before:  {"body": "auto", "poppers": 0, "menuItems": 0}
after:   {"body": "none", "poppers": 1, "menuItems": 3}
```

The menu re-opens, and Radix's `modal` default sets `pointer-events: none` on `document.body`.
*"the staging API key"* has three spaces. The operator types a sentence into nothing while the page
dims and un-dims under their hands, and the confirm button stays disabled with no explanation.

### `F310` — one Escape dismisses two things

`useDialogFocus` binds `keydown` on `document` (`hub/ui/src/hooks/useDialogFocus.ts:42`) and its
Escape branch (`:24-28`) closes unconditionally. It never asks whether something nearer the
keystroke already handled it. Measured, legs `C2` and `C3`:

| gesture | what the nested owner does | what the hook also does |
|---|---|---|
| Escape with the status menu open | Radix closes the menu | closes **the ticket** |
| Escape in the blocking-reason input | `TaskDetailDrawer.tsx:413-415` cancels the reason | closes **the ticket** |

```
C2   menu closed: True   ticket survived: False
C3   reason cancelled: True   drawer closed too: True
```

`TaskDetailDrawer.tsx:413-415` is the two-line handler `if (e.key === 'Escape') setBlockingReason(null)`
— a line written for no other purpose, which does its job and **has never once been observable**,
because the panel containing it is unmounted by the same keystroke.

### A third instance, never driven, found by this round

Grepping the UI for Escape owners returns nine. One of them is inside a panel whose
`useDialogFocus` is active: `DirectoryPicker.tsx:57-62` (`preventDefault()`, then `onClose()`),
mounted at `ProjectManagerModal.tsx:157-166` while that modal holds `useDialogFocus(!!mode, …)` at
`:73`. So Escape in the directory browser closes the browser **and the project modal behind it**, by
exactly the mechanism `F310` describes. Nobody has driven it. It is listed here because a fix
enumerated from `F310`'s two measured gestures would leave it standing, and because it is the
evidence that this is a hook-level defect rather than one screen's mistake.

## The mechanism — measured in the dependency's own source, not remembered

Both halves turn on *ordering*, so the ordering was read rather than assumed.

**Radix registers Escape on `document` in the capture phase, and marks the event handled.**
`@radix-ui/react-use-escape-keydown` (installed 2.1.16, `dist/index.mjs`) ends with
`addEventListener("keydown", handleKeyDown, { capture: true })` on the owner document.
`DismissableLayer` (`@radix-ui/react-dismissable-layer/dist/index.mjs:59-67`) runs it only for the
highest layer and then calls `event.preventDefault()` before `onDismiss()`. Capture on `document`
runs **before** the target, and therefore before every bubble-phase listener in the tree.

**React 18 delegates `onKeyDown` at the root container**, which is a descendant of `document`
(`react@18.3.1`; `main.tsx` mounts under `React.StrictMode`). A nested React handler therefore runs
during the bubble at the root container, **before** anything bound on `document`.

So `useDialogFocus`'s handler — a bubble-phase listener on `document` — is the **last** thing to see
an Escape that anything nearer has touched. At the moment it runs, `event.defaultPrevented` is
already `true` for the Radix case, and can be made `true` for the nested-React case by one line.
`defaultPrevented` is the platform's own answer to *"has anyone dealt with this"*, and it is
available here for free.

## What changes

**One.** `useDialogFocus` stands down on an Escape that is already `defaultPrevented`, and every
control that owns Escape inside a panel declares that it handled it. That is the whole of `F310`,
plus the `DirectoryPicker` instance, which already calls `preventDefault()` and so is repaired
without being touched.

**Two.** A menu item that opens a control expecting input says so, and `RowMenu` stops taking focus
back. Radix `DropdownMenu.Content` accepts `onCloseAutoFocus` (composed at
`@radix-ui/react-dropdown-menu/dist/index.mjs:113`); preventing that event is the supported way to
say *"I have moved focus deliberately, do not restore it"*. The drawer then takes focus **explicitly**
rather than relying on `autoFocus` — see the unmeasured link below. That is the whole of `F309`,
including the inert page, which is a consequence of focus sitting on the trigger and not a defect of
its own (legs `P1`-`P4` sampled `pointer-events` at 0/0.5/1/2/5/10 s after four different gestures
and `body` recovers at **+0 ms** every time; Radix cleans up correctly).

The two are one change because they are one gesture. The operator who cannot type the reason is the
operator whose Escape then throws the whole ticket away, and `F310`'s repair decides what `F309`'s
can be: if Escape is going to stay bound on `document`, the reason input must be able to declare
ownership of the key it already tries to handle.

## The one link this round did not measure

`F309`'s reading is that `autoFocus` fires and Radix's restore then overrides it. What was measured
is only the **end state** — `activeElement` is the trigger. If instead `autoFocus` never fires at
all, then preventing Radix's restore would leave focus on `document.body`, which is worse than
today. The change is therefore specified so that **the outcome does not depend on which of those two
is true**: the drawer focuses the input from a ref when the panel opens, in addition to Radix
standing aside. That is not a race, because the change removes the only actor that was competing.

A round that wants to settle the question can: it is one added reading in the existing harness. It
is worth settling, but it must not be a precondition for the fix, and the fix must not be written as
though the answer were already known.

## What this change does not do — `F307` is not subsumed

`F307` is the **Tab** branch of the same hook: `useDialogFocus` never moves focus into the panel when
it activates, so the first Tab in a confirm-only dialog escapes to whatever follows the trigger in
DOM order — measured landing in the instructions textarea *behind the scrim*, and driven all the way
to a wrong write on 2026-09-10. This change deliberately leaves it open, for three reasons.

1. **It is a different question.** `F307` asks *where focus starts*; this change asks *who answers a
   keystroke* and *who keeps focus after a menu closes*. Neither answer constrains the other.
2. **`F307`'s fix needs a decision that is not a window's to make.** Moving focus into the panel on
   activation means focusing the panel's first focusable, which in a destructive confirmation is
   **Cancel** — or its last, which is the destructive button itself. `F307` says so in its own words
   and declines to guess. That belongs on a review page, not inside this proposal.
3. **`F307` reaches five dialogs this drive never opened.** This change touches the sixth. Widening
   it would put a keyboard repair the operator hits on a mandatory path behind a design decision
   about five screens that are not broken in this way.

One dependency runs the other way and is stated so a later round does not trip on it: **if `F307` is
later fixed by binding Escape on the panel instead of on `document`, this change's arbitration rule
still holds** — it is about *who* answers, not about *where* focus is. And `F311` is the bookkeeping
finding that `F307`'s table of affected call sites lists five of six; the missing sixth is
`TaskDetailDrawer.tsx:167`, which is where both defects here live. It is ratcheted, not drained
(`DECISIONS.md` `f563815`: *"drain severity A and severity B; ratchet C, D and the unlabelled"*), and
a pointer was already added to `F307` in place.

## The shipped requirement this must not contradict

`task-lifecycle-governance` already requires, under *"A waiting task names what it is waiting for"*:

> **Scenario: A control offering the waiting status collects the statement**
> — **WHEN** an operator surface offers a move to the waiting status
> — **THEN** it obtains the statement before requesting the move

The product **is** obeying that today, and `F309` is not a breach of it: the drawer does ask, and the
confirm button stays disabled until something is typed, so nothing is requested without a statement.
What is broken is that the operator cannot supply one by keyboard. The delta therefore **modifies**
that requirement to say the control must accept the statement from the keyboard once the move has
been chosen, rather than adding a second requirement in a second voice that says nearly the same
thing. Grepping for the requirement before writing the delta is what turned this from an ADDED
into a MODIFIED, and it is exactly the check the round discipline exists to force.

**R2 cut that modification back.** R1 wrote the new scenario as *"without using a pointer at any
point"*, and that is more than this change delivers: reaching the drawer's status menu from the
keyboard means Tab-walking the board's remaining controls behind the scrim, which is `F307` and is
excluded below. The scenario now begins where the change begins — the move chosen from the keyboard —
and `design.md` D6 carries the measurement and the reasoning.

## Impact

- **Capabilities:** `hub-interaction-feedback` (two ADDED requirements — Escape arbitration, and
  focus after a menu selection), `task-lifecycle-governance` (one MODIFIED requirement).
- **Source:** `hub/ui/src/hooks/useDialogFocus.ts`, `hub/ui/src/components/layout/RowMenu.tsx`,
  `hub/ui/src/components/tasks/TaskDetailDrawer.tsx`. UI only — **no Python file changes**, so the
  committed bundle at `hub/hub/static/ui` must be rebuilt and the Python lint set is not required.
- **Behaviour changed for other call sites:** `ProjectManagerModal` + `DirectoryPicker` stops
  double-dismissing (a repair, and the third instance above). The other four `useDialogFocus`
  dialogs have no nested Escape owner, so their behaviour is unchanged. Every other `RowMenu` call
  site (`AgentTree:186`, `ConversationRow:284`, `PanelShell:184`, `TaskCard:260`) declares no
  focus-moving item, so Radix keeps restoring focus to the trigger there, unchanged.
- **Existing tests:** `hub/ui/src/__tests__/taskDetailDrawer.test.tsx:117` (*closes on Escape*) must
  keep passing unchanged — nothing nearer owns Escape in that gesture.
- **The guard is a drive, not a unit test.** `scripts/drive/t_d1_0910_escape_across_the_dialogs.py`
  (30 pass / 6 fail today) and `scripts/drive/t_d1_0910_rowmenu_leaves_the_page_inert.py`
  (18 pass / 1 fail today) both assert in the direction of the correct behaviour, so **both go green
  when this ships** and are the change's acceptance evidence. The counts are a floor rather than an
  equality: `tasks.md` adds legs to both files, and one existing leg skips silently rather than
  failing when its trigger is absent (`tasks.md` 7.2a).
