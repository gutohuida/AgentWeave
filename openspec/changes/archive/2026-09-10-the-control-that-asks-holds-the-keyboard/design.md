# Design — the control that asks holds the keyboard

## D1. The arbitration signal is `event.defaultPrevented`, and nothing else

`useDialogFocus`'s Escape branch gains one condition: **if the event is already `defaultPrevented`,
do nothing.** Not "close anyway but later", not "close unless a popper is open" — return.

The reason this is the right signal rather than a clever one is ordering, and the ordering was read
out of the installed dependencies rather than remembered:

| who | where it binds | phase | when it runs relative to the hook |
|---|---|---|---|
| Radix `DismissableLayer` | `document` | **capture** | before the target, so before the hook |
| a nested React `onKeyDown` | root container (React 18 delegation) | bubble | at the root container, so before the hook — **but only if focus is inside its own subtree**; see D9 |
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

**R2 re-read all four files and every claim in the table above held**, at the exact lines: the
`{ capture: true }` registration on the owner document, `preventDefault()` at `:64` before
`onDismiss()` at `:65` inside the `if (!event.defaultPrevented && onDismiss)` at `:63`, and the two
`onDismiss` suppliers at `:145` and `:160`. It added the link R1 named but did not trace: it is
`MenuContentImpl` that hands that `onDismiss` down to `DismissableLayer` (`react-menu` `:264-272`),
so the chain from a `DropdownMenu` to the `preventDefault()` is complete rather than inferred.
`DismissableLayer` also answers only for the highest layer (`:60-61`), which is not a hazard here —
our panels are not Radix layers and are not in that stack at all — but it is the reason a *second*
open Radix layer could not silently take the marking away.

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
  and **R3 found that it is not enough on its own.** That handler is a React `onKeyDown` bound to the
  picker's own root `div` (`:85-91`, `tabIndex={-1}`), and **nothing ever focuses that root.** Opening
  the browser leaves focus on the `Browse…` button, which is a *sibling* of the picker
  (`ProjectManagerModal.tsx:153` and `:157-166`), so the synthetic event never travels through the
  picker's subtree, the handler does not run, `preventDefault()` is never called, and D1's condition
  is false. The third instance is therefore **not** repaired without an edit. See **D9**, which states
  the precondition this bullet assumed, and `tasks.md` §2.2, which now carries the edit that
  satisfies it. That an author could write a correct-looking Escape handler that cannot fire is the
  argument this contract needs a second half, not a weaker one.
- The remaining Escape owners in the UI (`Composer.tsx:242`, `ModelPicker.tsx:109`,
  `ConversationRow.tsx:183`, `FilesIndexTab.tsx:42`, `SpecDocumentBrowser.tsx:92`) are **not** inside
  a `useDialogFocus` panel, so nothing about their behaviour changes and none of them is edited.
  They are listed here so a later round does not have to re-derive the boundary; the boundary is
  "mounted inside a panel whose `useDialogFocus` is active", and it is two components today.

  **R2 re-derived the boundary from `grep` rather than from this list, and it held.** Seven Escape
  owners in `src/`, of which two are inside an active `useDialogFocus` panel (`TaskDetailDrawer:414`,
  `DirectoryPicker:58`) and five are not. The one that needed chasing rather than reading is
  `SpecDocumentBrowser`: it has two hosts (`SpecDocumentPicker.tsx:96`, `SpecIndexTab.tsx:31`) and
  the first has two of its own (`ConversationView.tsx:575`, `SpecPage.tsx:136`) — all page level, so
  it stays outside the boundary. `ModelPicker` was the other candidate worth checking, since a model
  choice inside `AgentCreateDialog` would have made a seventh instance; it reaches the tree only
  through `ComposerModelControls.tsx:183` inside `Composer`, which no dialog mounts.

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

**What `preventDefault()` on that event actually suppresses, read out of the dependency by R2.**
R1 described the restore loosely, as *"Radix returns focus to the trigger"*. There are two
mechanisms, not one, and both are suppressed by the same line — which is why this decision works,
and it is worth stating so an implementer does not go looking for a second lever:

1. `DropdownMenuContent` composes **its own** `onCloseAutoFocus`, which calls
   `context.triggerRef.current?.focus()` and then `event.preventDefault()`
   (`@radix-ui/react-dropdown-menu/dist/index.mjs:113-117`). It is composed with
   `composeEventHandlers(props.onCloseAutoFocus, …)`, and that helper defaults to
   `checkForDefaultPrevented: true` (`@radix-ui/primitive/dist/index.mjs`) — so a consumer handler
   that prevents the default stops Radix's own trigger focus from running at all.
2. `FocusScope` then does `if (!unmountEvent.defaultPrevented) focus(previouslyFocusedElement ?? document.body)`
   (`@radix-ui/react-focus-scope/dist/index.mjs:89-98`). Prevented, that is skipped too.

One line, both actors, no third one left. And note where that code sits: inside a
**`setTimeout(…, 0)`** in `FocusScope`'s cleanup. The steal is therefore strictly later than any
React commit, which is the precise reason `F309` is observable at all and the precise reason D5
forbids scheduling our own focus — the thing we would be racing runs in a macrotask we do not own.

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

**Settled by R2: kept, and narrowed.** The challenge R1 left open was whether the
`task-lifecycle-governance` modification is the same rule in a second voice. It is not. The generic
requirement says where the keyboard goes when *a menu action presents a control*; the lifecycle
requirement says that *this particular statement*, which the Hub refuses the transition without, has
to be enterable. Delete it and the corpus records that a mandatory field is unreachable nowhere at
all, because the interaction capability never mentions the waiting status and nobody reading the
lifecycle capability would find the rule that governs it.

**R2 did find the modification over-claiming, and cut it back.** As R1 wrote it, the scenario read
*"the operator moves a task to the waiting status **without using a pointer at any point**"* — and
that is not what this change delivers. The reachability half is `F307`, which D8 deliberately
excludes, and it was re-measured rather than reasoned about:

| step | what the code does | keyboard? |
|---|---|---|
| open the ticket | `TaskCard.tsx:213-214` is `role="button" tabIndex={0}` with an Enter/Space handler | yes |
| get into the panel | `useDialogFocus` moves focus nowhere on activation, and unlike three of the six dialogs `TaskDetailDrawer` autofocuses nothing at open — so the first Tab falls through to native order | **no** |
| reach the status menu | `TaskDetailDrawer` is rendered *after* the whole board (`TasksBoard.tsx:428`), so native order walks every remaining board control **behind the scrim** first | **no** |
| choose the move, type the reason | this change | yes |

So a scenario asserting a pointer-free path end to end would be archived into `openspec/specs/` as
current behaviour while the product did not have one. The scenario now starts where the change
starts — *"chooses the move to the waiting status from the keyboard"* — and the requirement says in
so many words that where focus starts when a panel opens is not settled here. When `F307` lands, the
change that fixes it is the one that gets to widen this.

## D7. Alternatives rejected

- **A LIFO stack of Escape owners.** Every dialog registers on activation; only the topmost
  responds. More durable in the abstract, and rejected as strictly additive: Radix's layers would
  not be in our stack, so the `defaultPrevented` rule would still be needed for the menu half, and
  the stack would then be machinery that changes nothing measurable. It also has to survive
  `React.StrictMode`'s double-invoked effects (`main.tsx:18`), which is a new failure mode bought for
  a case that does not exist. **The case it guards against was checked, not assumed:** no
  `useDialogFocus` panel is mounted inside another today — all six mount at page or `App` level
  (`App.tsx:610`, `App.tsx:620`, `ProjectSettingsPanel.tsx:321`, `InstructionsPage.tsx:155`,
  `SpecPhaseBar.tsx:217`, and the drawer — which R2 found mounts at **two** boards, `TasksBoard.tsx:428`
  and `DependencyBoard.tsx:534`, both at page level; same component, so same behaviour, but the drive
  exercises one of the two). If two are ever simultaneously active,
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
  reasons and the one dependency that runs the other way. **One carve-out, added by R3:** §2.2 does
  place initial focus, in `DirectoryPicker` and nowhere else, because without it a scenario in this
  change's own delta cannot be demonstrated on any surface (D9). That is one component chosen for a
  named reason, not the general rule `F307` asks for; §2.2b says so to the implementer.
- It does not change what `TaskDetailDrawer` sends, when it sends it, or what the Hub accepts. No
  route, schema, migration or API shape is touched. Leg `C3` counted zero task writes across the
  whole failing sequence, and there should still be zero after this change until the operator
  confirms.
- It does not add a unit test that *reproduces* either defect. Both depend on real focus and real
  event phases; jsdom's answer to either would be evidence about jsdom. The acceptance evidence is
  the two browser harnesses going green.

## D9. Arbitration presumes the nested owner holds the keyboard — added by R3

D1 says the hook stands down when something nearer has already answered. D2 says a nested owner
answers by preventing the default. **Neither says what has to be true for the nested owner's handler
to run at all**, and R3 found the change relying on the missing half in one of its three instances.

The precondition differs by mechanism, and the difference is not cosmetic:

| the nested owner | where its listener lives | runs when |
|---|---|---|
| Radix `DismissableLayer` (the menu) | `document`, capture phase | **always**, wherever focus is |
| a React `onKeyDown` (the reason input, the picker) | root container, dispatched along the React tree from the event target | **only when focus is inside that handler's own subtree** |

So a React `onKeyDown` is not a listener for Escape; it is a listener for *Escape pressed by someone
standing inside me*. The three instances land differently under that reading:

- **the menu** — capture on `document`, so focus is irrelevant. Works.
- **the reason input** — the handler is on the `<input>` itself (`TaskDetailDrawer.tsx:409-415`), and
  §4.1 puts focus in that input. Works, **because of §4.1**: the `F310` half of this change is
  therefore *dependent on* the `F309` half, not merely fixed alongside it. `tasks.md` §2.1 now says
  so, because an implementer landing §1.1 and §2.1 without §4.1 would see leg `C3` still fail and
  would have no reason to suspect the focus work.
- **the directory browser** — the handler is on a root `div` that nothing focuses, and focus after
  opening it is on the `Browse…` button outside it. **Does not work**, and §1.1 alone does not make
  it work.

This is the same fact D3 already argues in the opposite direction. D3 rejects binding the hook on the
panel because *"focus is frequently not inside the panel at all"* — `F307`, measured. That is exactly
why the picker's panel-scoped handler is dead. D2's bullet and D3's argument could not both be right;
D3 is the one that is.

**The repair is on-theme rather than a patch.** A browser the operator has just opened is a control
that asks — it exists to collect a directory — so it holds the keyboard, and the change's own title
is the rule that fixes it. The picker already carries `role="dialog"` and `tabIndex={-1}`, which is
the markup for a panel that intends to be focused and was never told to be. §2.2 focuses it on open
and returns focus to the trigger on close; nothing about D1's signal changes.

**Not generalised further, deliberately.** "Every panel focuses itself when it opens" is `F307`,
which D8 excludes with three reasons. This is the one panel that needs it to make a scenario in this
change's own delta true, and §2.2 is scoped to it.
