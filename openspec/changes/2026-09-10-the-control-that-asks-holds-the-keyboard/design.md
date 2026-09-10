# Design — the control that asks holds the keyboard

## D1. The arbitration signal is `event.defaultPrevented`, and nothing else

`useDialogFocus`'s Escape branch gains one condition: **if the event is already `defaultPrevented`,
do nothing.** Not "close anyway but later", not "close unless a popper is open" — return.

The reason this is the right signal rather than a clever one is ordering, and the ordering was read
out of the installed dependencies rather than remembered:

| who | where it binds | phase | when it runs relative to the hook |
|---|---|---|---|
| Radix `DismissableLayer` | `document` | **capture** | before the target, so before the hook |
| a nested React `onKeyDown` | root container (React 18 delegation) | bubble | at the root container, so before the hook |
| `useDialogFocus` | `document` | bubble | **last** |

The hook is structurally the last listener to see the key. That is not an accident of this codebase —
it follows from binding on `document` in the bubble phase, which is the outermost position there is.
So "has anything nearer already dealt with this" is answerable at the exact moment the hook needs to
answer it, and the DOM already has a word for it.

Radix supplies that word for free: `DismissableLayer` calls `event.preventDefault()` *before*
`onDismiss()` (`@radix-ui/react-dismissable-layer/dist/index.mjs:63-65`), for the highest layer only.
So the status-menu half of `F310` is repaired by the hook's one added condition, with no change to
`RowMenu` and no knowledge of Radix anywhere in our code.

**That branch is conditional, so it was checked rather than assumed.** The `preventDefault()` sits
inside `if (!event.defaultPrevented && onDismiss)` — a layer with no `onDismiss` would dismiss
nothing and mark nothing. `@radix-ui/react-menu/dist/index.mjs` supplies one at both content roots
(`:145` and `:160`, `onDismiss: () => context.onOpenChange(false)`), which is what a `DropdownMenu`
renders. If that were not so, this whole decision would be wrong while every fact around it stayed
true, which is the failure the round discipline exists to catch — so a later round should re-read
those two lines rather than re-read this paragraph.

The converse case is also safe: `useEscapeKeydown` lives *inside* `DismissableLayer`, so with no
layer mounted there is no handler, nothing marks the key, and a panel with nothing open inside it
dismisses exactly as it does today.

## D2. A nested owner declares ownership by preventing the default

The other half needs the nested handler to say the same thing. `TaskDetailDrawer.tsx:413-415`
currently cancels the reason and stays silent; it gains `e.preventDefault()`.

This is a contract, not a patch, and it is stated as a requirement precisely so the next nested
control does not have to rediscover it: **a control that handles Escape marks the event handled.**
Two consequences worth writing down.

- `DirectoryPicker.tsx:57-62` already does exactly this — `event.preventDefault()` then `onClose()` —
  which is why the third instance in `proposal.md` is repaired without being edited. That it was
  already correct, by an author who was not thinking about this hook, is the argument that the
  contract is the natural one rather than one invented for this change.
- The remaining Escape owners in the UI (`Composer.tsx:242`, `ModelPicker.tsx:109`,
  `ConversationRow.tsx:183`, `FilesIndexTab.tsx:42`, `SpecDocumentBrowser.tsx:92`) are **not** inside
  a `useDialogFocus` panel, so nothing about their behaviour changes and none of them is edited.
  They are listed here so a later round does not have to re-derive the boundary; the boundary is
  "mounted inside a panel whose `useDialogFocus` is active", and it is two components today.

## D3. The hook keeps its `document` binding

The obvious-looking alternative — bind `keydown` on the panel instead of on `document`, so Escape
only reaches the hook when focus is inside the panel — would fix the menu half of `F310` for free
and is rejected, because **focus is frequently not inside the panel at all.** That is `F307`,
measured: the hook never moves focus in when it activates, so after a confirm dialog opens the
active element is still the trigger that opened it, outside the panel. A panel-bound listener would
therefore make Escape stop dismissing those dialogs entirely — trading a double-dismissal for a
dead key, on five screens that this change is not otherwise touching.

That option becomes available only once `F307` is fixed, and `F307` is deliberately not in scope
(`proposal.md`). If a later change does fix `F307` and wants to move the binding, the arbitration
requirement in this change survives it unchanged: it constrains *who answers*, not *where the
listener lives*.

## D4. The menu stands aside per item, not per menu

`RowMenuItem` gains an optional flag meaning *"choosing this opens a control that will take focus;
do not take it back"*. `RowMenu` remembers whether the item last chosen carried it, and prevents
Radix's close-auto-focus in that case only.

Per item, not per menu, because the same menu carries both kinds. `TaskDetailDrawer`'s status menu
offers every legal transition: **Move to blocked** opens the reason panel, and every other move
fires a mutation and leaves nothing on screen to hold focus. Preventing the restore for all of them
would drop focus on `document.body` after an ordinary move — a keyboard operator loses their place
entirely, which is a worse defect than the one being fixed and would reach four other `RowMenu` call
sites that have no focus-moving item at all.

The flag must be cleared on every close, however the menu closed — selection, Escape, or a click
outside — so a dismissal that follows a focus-moving selection does not inherit it. Radix runs
close-auto-focus on every close, which is the one place that reset belongs.

Rejected: exposing `onCloseAutoFocus` on `RowMenu` as a passthrough. It works, and it puts a Radix
concept in front of five call sites that should not have to know what Radix is. The item-level flag
states the intent (*this action opens something that takes focus*) and leaves the mechanism in the
one component that already owns it.

## D5. The reason panel takes focus explicitly, and `autoFocus` is removed

`autoFocus` on the input (`TaskDetailDrawer.tsx:410`) is replaced by a ref and an effect that focuses
the input when the panel becomes visible — not on every keystroke, so the effect is keyed on
*whether* a reason is being collected, not on its value.

This is not belt-and-braces on top of `autoFocus`; it **replaces** it, so there is exactly one
mechanism taking focus and one place to look when it does not. It also disposes of the one link
`proposal.md` admits was not measured: whether `autoFocus` fires and is overridden, or never fires,
stops mattering, because neither answer is load-bearing any more.

It is not a race with Radix either. Radix has been told to stand aside for this item (D4), so after
this change nothing else is trying to move focus during that transition — which is the difference
between this and the rejected shape below.

Rejected: focusing the input from a `setTimeout` or `requestAnimationFrame` scheduled to land after
Radix's restore. It is a timing guess dressed as a fix; it would pass a drive on one machine and be
one slow frame away from failing on another, and the failure mode is the silent one this finding is
already about.

## D6. Where the requirements live

The two new requirements go to `hub-interaction-feedback`, whose stated purpose is *"How the Hub
answers a pointer and a keyboard … Stating it once keeps every surface from inventing its own
answer."* That is this change in one sentence: three components disagreed about who answers a
keystroke, and the disagreement was invisible until someone drove it.

The third delta modifies `task-lifecycle-governance`'s *"A waiting task names what it is waiting
for"* rather than adding a requirement beside it. The scenario that says a control offering the
waiting status must collect the statement is already there and is already obeyed; what it does not
say is that the collection has to be reachable. Adding a second, nearly identical requirement in a
different capability is how a corpus ends up with two rules about one control that can drift apart.

**Open for the review rounds.** The generic requirement in `hub-interaction-feedback` already covers
`F309` mechanically. Whether the `task-lifecycle-governance` modification earns its place — or is
the same rule restated in a second voice — is a fair challenge, and R2 or R3 should either defend it
or delete it. The case for keeping it: it is the only one of the three that names what the operator
actually loses, on a path the Hub makes mandatory.

## D7. Alternatives rejected

- **A LIFO stack of Escape owners.** Every dialog registers on activation; only the topmost
  responds. More durable in the abstract, and rejected as strictly additive: Radix's layers would
  not be in our stack, so the `defaultPrevented` rule would still be needed for the menu half, and
  the stack would then be machinery that changes nothing measurable. It also has to survive
  `React.StrictMode`'s double-invoked effects (`main.tsx:18`), which is a new failure mode bought for
  a case that does not exist. **The case it guards against was checked, not assumed:** no
  `useDialogFocus` panel is mounted inside another today — all six mount at page or `App` level
  (`App.tsx:610`, `App.tsx:620`, `ProjectSettingsPanel.tsx:321`, `InstructionsPage.tsx:155`,
  `SpecPhaseBar.tsx:217`, and the drawer from the task board). If two are ever simultaneously active,
  `defaultPrevented` resolves them by registration order, which means the **outer** one wins — the
  wrong answer. That is the residual risk of this decision, it is stated here rather than discovered
  later, and the tasks carry a check that keeps the invariant honest.
- **`stopPropagation()` in the nested handlers.** Fixes the reason-input half and cannot touch the
  menu half: Radix's listener is a capture-phase listener on `document` that has already run by the
  time any nested handler is reached. One rule that covers both beats two rules that cover one each.
- **Sniffing the DOM for an open Radix popper** (`[data-radix-popper-content-wrapper]`). Works today,
  couples our hook to a dependency's internal attribute names, and would fail silently on a Radix
  upgrade — silently being the operative word for a finding of this kind.
- **`modal={false}` on `RowMenu`'s content**, to stop the page going inert. Treats a symptom: the
  inert page is a consequence of focus sitting on the trigger and disappears when `F309` is fixed
  (legs `P1`-`P4` show Radix's own cleanup is correct). It would also change dismissal and scroll
  behaviour at all five `RowMenu` call sites to fix a defect at one.

## D8. What this change does not do

- It does not fix `F307` — the Tab branch and initial focus placement. `proposal.md` states the three
  reasons and the one dependency that runs the other way.
- It does not change what `TaskDetailDrawer` sends, when it sends it, or what the Hub accepts. No
  route, schema, migration or API shape is touched. Leg `C3` counted zero task writes across the
  whole failing sequence, and there should still be zero after this change until the operator
  confirms.
- It does not add a unit test that *reproduces* either defect. Both depend on real focus and real
  event phases; jsdom's answer to either would be evidence about jsdom. The acceptance evidence is
  the two browser harnesses going green.
