# Design — an unread editor cannot overwrite

## The condition to gate on, and why it is not `isError`

The obvious repair is to read `isError` alongside `isLoading` and add a branch. It is not the
cleanest one, because `isError` is a *reason*, and what the textarea needs is a *fact*: has this
project's stored content arrived?

React Query gives four combinations at this call site, and only one of them has content to show.
(R2 re-read the table out of the **installed** package rather than the declared range: `package.json`
says `^5.62.16`, `node_modules/@tanstack/react-query` is 5.90.21, and it is the installed copy the
bundle is built from.)

| query state | `isPending` | `isFetching` | `isLoading` | `isError` | `data` | current page renders |
|---|---|---|---|---|---|---|
| loading | true | true | **true** | false | undefined | skeleton — correct |
| success | false | false | false | false | present | editor with the stored text — correct |
| error, retries exhausted | false | false | **false** | true | undefined | **empty editor, Save enabled** |
| disabled (`enabled: false`) | true | false | **false** | false | undefined | **empty editor, Save enabled** |

`isLoading = isPending && isFetching` is the derivation
(`hub/ui/node_modules/@tanstack/query-core/build/modern/queryObserver.js:310`), and it is why the
last two rows fall through to the editor: both are "not fetching right now", and neither is
"loading".

`data === undefined` is true for exactly the three rows that have nothing truthful to show and false
for the one that does. So the render becomes:

```
data present            -> the editor, as today
isError                 -> the failure block, with a retry
otherwise (no data yet) -> the skeleton
```

Three branches, one of them new, and the ordering matters: `data` first, so a refetch that fails
after a successful load keeps the operator's editor rather than snatching it away mid-edit. That is
a deliberate choice and it is stated as a scenario, because the naive `isError`-first ordering gets
it wrong — a background refetch failure would replace a screen the operator is typing into.

**R2: the library agrees, and says so in its own vocabulary.** R1 argued that ordering from first
principles. The same observer that computes `isLoading` also computes
`isLoadingError = isError && !hasData` and `isRefetchError = isError && hasData`
(`queryObserver.js:331` and `:335`) — which is exactly the `data`-before-`isError` split, shipped as
two named flags. `data present -> editor; isError -> failure` is therefore equivalent to
`isLoadingError -> failure`, and an implementation may use either. This is corroboration, not a
correction: it makes the ordering the library's own distinction rather than this change's taste.

**The fourth row is derived, not driven — and R2 sharpened the derivation without changing the
verdict.** `useInstructions` is `enabled: isConfigured && !!projectId`
(`hub/ui/src/api/instructions.ts:14`), and `App.tsx:484` renders `<InstructionsPage />` from a
branch that carries `destination.projectId`, while the hook reads `selectedProjectId` from
`useConfigStore` — a second source. R1 left "whether those two can disagree while the page is
mounted" open. They can, and the mechanism is nameable: the two sources are reconciled in an
**effect** (`App.tsx:152-157`, `setSelectedProject(destinationProjectId)` guarded by
`destinationProjectId !== projectId`), which runs *after* the render it corrects. The store's
initial value is `loadSelectedProject()` from `localStorage` and `isConfigured` is `!!initial.apiKey`
read synchronously from `sessionStorage` (`configStore.ts:129-131`), while the destination is
resolved from `window.location` in a `useState` initialiser (`useWorkspaceNavigation.ts:25-27`). So
a first paint in which the destination names project A and the store still says `null` — or says
project B — is a committed render, not a hypothetical.

What is still **not** established is that any such window lasts longer than the frame before the
effect commits, and no drive has put an operator in one. So the verdict is unchanged: the gate above
covers it either way, no scenario asserts the state is reachable, and none should until someone
drives it.

**R3: the disabled row misinforms, but it cannot destroy — and neither earlier round asked.** The
two rounds before this one argued about whether the row is *reachable*. Neither asked what a Save
click in it actually does, and the answer narrows the row. `enabled` is
`isConfigured && !!projectId`, and each way of failing that test also breaks the write, because
`useSaveInstructions` builds its URL and its credential from the same two values:

- `!projectId` — the PUT goes to `/api/v1/projects/null/project/instructions` (a template literal of
  `null`), and `get_project` looks the path parameter up with `session.get(Project, "null")` and
  **404s** (`hub/hub/auth.py:156-158`).
- `!isConfigured` — `isConfigured` is `!!apiKey` (`configStore.ts:131`), so there is no bearer token
  to send (`client.ts:11,17`) and `get_project` **401s** (`hub/hub/auth.py:144-148`).

So of the three states that render an empty editor over unread content, **two are one-click
destruction paths and the third is not**: the disabled row shows the operator a lie, and the write
it invites is refused by the route. That changes no requirement — the gate is `data` present, which
covers all three, and "no textarea" is owed for a misinformation path as much as for a destructive
one — but it is the difference between three live destruction paths and two, and the proposal should
not claim the larger number.

**The adjacent risk is out of scope and recorded here rather than filed.** In the `projectId = B,
destination = A` variant the page is A's while the hook — read *and* write — is B's, which is a
second identity source disagreeing with the one the operator is looking at. That is not this
change's defect and it has not been driven; it is a drive candidate, not a claim.

## What the failure block owes the operator

Three things, and the third is the one that is easy to leave out:

1. **It says a load failed** — in the section, not only in the console. Announced, so it is not
   purely a colour: `role="alert"`, matching `ProjectSettingsPanel.tsx:319` and
   `AgentCreateDialog.tsx:235`.
2. **It offers a retry in place.** The query's own `refetch()`. Without it the only way out is a
   full page reload, which on a settings surface reads as "the app is broken", and the operator's
   next move after a Hub restart is exactly this button.
3. **A usable sentence when there is no `ApiError` to read.** `readableApiError`
   (`hub/ui/src/api/client.ts:74`) returns its fallback for anything that is not an `ApiError`, and
   `fetchWithAuth` (`:24-27`) constructs one only from a *response* — a dropped connection rejects
   in `fetch` with a `TypeError` and never reaches it. The aborted-GET column of `F271`'s table is
   that case. So the fallback string is not decoration: it is what the operator reads in one of the
   two driven failure modes. It must name the thing that failed and say that nothing was lost.

## Save, stated as an outcome rather than as an attribute

The requirement says no PUT can be issued while the stored content has not been read — not that a
button carries `disabled`. Two reasons.

`disabled` on the existing `Button` is already `saveMutation.isPending` alone
(`InstructionsPage.tsx:39`); a requirement written about that attribute would be satisfied by
`disabled={saveMutation.isPending || isError}` while a `data === undefined` route stayed open. The
outcome form is satisfied only by the gate actually holding.

It also survives the obvious implementation, which is not to render Save at all when there is no
editor to save. Both shapes pass; the requirement does not pick one.

### R2: Save is not where the branch is, and the loading state is unguarded today

R1 wrote the gate as a rewrite of the render at `:45` and assumed Save came with it. It does not.
The button is handed to `SettingsSection` as `actions` (`InstructionsPage.tsx:36-43`) and
`SettingsSection` renders `{actions}` in the heading (`SettingsSection.tsx:58`), a sibling of
`{children}` (`:60`) where the `isLoading` ternary lives. Three consequences:

1. The three-branch rewrite reaches the textarea and not the button. Gating Save has to be a
   separate, explicit act — either the control moves inside the gated region or `actions` is made
   conditional on the same `data` test. `tasks.md` 1.4 said "not rendering Save in the failure block
   is an acceptable implementation of this", which is not implementable as written: there is no
   failure block that contains Save. R2 corrected the task.
2. **The loading state is already a destruction path**, not merely a correct skeleton. While the
   skeleton renders, Save is on screen and enabled, and `content` is `''`. This is the *third* state
   the current page cannot distinguish from an empty project, and unlike the other two it is on
   every visit. It is short when the request fails fast (`retry: 1` plus a backoff) and unbounded
   when the request hangs, since `isPending && isFetching` stays true.
3. The requirement as written already forbids it — "for a project whose stored instructions have not
   been read successfully" covers in-flight as much as failed — so no requirement text changed. What
   was missing was a scenario, a unit test and a drive column, and R2 added all three.

The severity does not change: the driven case is still the one that took stored content away. But
R1's table describes the loading row as "correct", and it is only correct about the editor.

## Scope: a page, not a family — and the capability-wide requirement is rejected

`F271`'s 2026-09-03 sweep (`scripts/drive/d6_seed_writeback_sweep.py`) counted, over 153 query call
sites reachable from `main.tsx`: 7 where a query's data seeds component state, 5 of those where the
seeded state is what a write sends back, and **2** of those unguarded. They are
`InstructionsPage.tsx:9` — this one, driven — and `AgentOutputPanel.tsx:207`, still a static read
and still undriven.

So the tempting move is to write the general requirement into `project-environment-settings`, beside
its existing *Saving reports its outcome*: "a configuration section whose settings failed to load
says so rather than presenting them as editable". **Rejected for this change**, on the ground that
it is a promise about eight pages (`quality`, `instructions`, `runners`, `charters`, `worktrees`,
`diagnostics`, `budgets`, `settings` — `App.tsx:483-490`) and only one of them has been measured.
Shipping a requirement seven unmeasured pages may already breach makes the corpus describe something
that is not true, which is worse than a narrow requirement that is.

It is a good candidate for its own change, after a sweep that measures the other seven. Recorded
here so that the next person does not have to rediscover that it was considered.

**R2 attacked this call rather than inheriting it, and part of the sweep it asks for is now done —
but R2 got the count wrong, and R3 corrects it.** R2 reported **zero of eight** from a `grep` for
`isError`/`isLoadingError`, which returns hits in exactly two files — `AccountingPanel.tsx:137,147`
(`updateBudget.isError`) and `ProjectSettingsPanel.tsx:84` (`update.error ?? relocate.error`) — both
*mutation* errors, the save-side reporting `project-environment-settings` already requires.

That grep missed a page, because a component can bind a read error without ever writing the string
`isError`. **`WorktreesPanel` does exactly that**: `const { data, isLoading, error } =
useWorktrees()` (`WorktreesPanel.tsx:21`), passed down and rendered as
`if (error) { … role="alert" "Could not read this project's checkouts." }` (`:44-50`). The honest
count is **one of eight**, not zero.

The rejection is unaffected — a capability-wide requirement would still promise seven pages that
have not been measured against it, and one conforming page does not make it true of the other seven.
What changes is that the follow-up candidate now has a *model* inside the codebase rather than only a
gap, which is worth more to whoever writes it than the count was.

That measurement points both ways and it is worth being precise about which way it decides.

- It **confirms the rejection**: a capability-wide "a section whose settings failed to load says so"
  would be breached by seven pages the day it shipped, which is exactly the corpus-lying failure R1
  named. Writing it now would be describing an intention, not the product.
- It **strengthens the candidate**: this is no longer "someone should look" but a counted, named
  gap. What remains unmeasured is the part that decides severity — whether any of the seven seeds a
  write from the read it does not check. `F271`'s own 153-site sweep says only two sites in the
  whole application do, and one of them is this page, so the other seven are very likely
  *misinforming* rather than *destroying*. That belongs in the follow-up change's Why, not here.

## R3: the shape proposed here is already shipped one page over

`WorktreesPanel` is not merely a counterexample to a count. It is the same `SettingsSection` family,
in the same `environment` tab, and it renders the three-branch structure this change proposes —
error first, then a not-yet-answered gate, then content (`WorktreesPanel.tsx:44`, `:56`, `:64`). Two
things follow, and both are worth more than the correction that surfaced them.

**The disabled row was already decided, in a comment, by whoever wrote that page.** R1 derived the
fourth row from `queryObserver.js` and labelled it "derived, not driven"; R2 spent its open question
on whether the row is reachable. `WorktreesPanel.tsx:52-55` had answered the question the product
actually has to answer:

> `!data` covers more than the fetch in flight: with no project selected the query is disabled and
> never resolves, so there is no answer rather than an empty one. Both are "nothing to say yet", and
> neither is a failure — reporting either as an error would be the same lie in the other direction.

That is this change's gate, arrived at independently, including its treatment of the disabled query
and including the reason: an unanswered read is not a failed one. The `data`-present test is
therefore not this change's invention and not a matter of taste — it is the convention the codebase
already holds, and `InstructionsPage` is the page that departs from it.

**Where this change diverges, it diverges deliberately, and the reason is the textarea.**
`WorktreesPanel` checks `error` **first**; this change checks `data` **first** (see the ordering
argument above). Both are right for their page. A worktrees list is read-only, so replacing it on a
background refetch failure costs the operator nothing but a re-read; an instructions textarea is
something the operator *types into*, so taking it away mid-edit destroys unsaved work — a second
data-loss path, opened by the fix for the first. Stating the divergence and its reason is what keeps
the two pages from looking inconsistent to whoever reads them next.

**Consequence for the corpus, not just for this change.** Neither page's behaviour is required by
anything shipped: no requirement in `openspec/specs/` states what a settings section owes on a
failed read (checked across all 30 documents). So `WorktreesPanel` is *unspecced code precedent* —
it can regress without breaching anything — which is a further argument for the capability-wide
follow-up, and a note that the follow-up should codify the existing shape rather than invent one.

The rejection therefore stands, on evidence rather than on caution.

`AgentOutputPanel.tsx:207` is likewise out of scope: it is composer/override seeding, not a settings
editor, it belongs to a different capability, and it has never been driven. The drive that would
settle it is unchanged and unqueued.

## Rejected alternatives

**Seed `content` from `data?.content ?? ''` on every render instead of in an effect.** Removes the
stale-project variant, but not the defect: on a failed load it still produces an empty textarea that
is indistinguishable from an empty project, and Save is still enabled. It repairs the mechanism the
finding *describes* while leaving the behaviour the finding *measured*.

**Make Save refuse a PUT that would replace non-empty stored content with the empty string.** This
is the operator's product decision, not a bug fix — the empty string is a value the route accepts on
purpose and "clear my instructions" is legitimate. `F271` says so explicitly. Carried to the review
page as a question. Note that it is also *not sufficient* on its own: it does nothing about the
misleading empty editor, and a client that cannot tell "not loaded" from "empty" would still be
lying to the operator with the confirmation dialog on the screen.

**R2 residual, recorded and not specced: the seeding lag on a *successful* project switch.** The
gate is `data` present, and the effect that copies `data.content` into `content` runs after the
render in which `data` arrived. So when the selected project changes and the new project's read
*succeeds*, there is a render where the editor is shown (`data` present, for the new project) while
`content` still holds the previous project's text. The failure variant is covered by a scenario; this
success variant is not, because it is a frame, not a state, and no drive has produced it. The cheap
remedy if implementation wants it is to key the editor by project id so `content` cannot survive the
switch — noted in `tasks.md` 1.2 as an option, deliberately not made a requirement.

**Track the loaded state in a `useState` beside `content`.** A second source of truth for something
the query already answers, and one that has to be reset by hand on every project change. The bug
being fixed is a component that kept state the query had invalidated.

**Give the query `placeholderData` or `retry: Infinity` for this endpoint.** Hides the failure
rather than stating it, and makes the empty editor arrive more slowly instead of not at all.

## Verification

`scripts/drive/t_d4_instructions_failed_load.py` currently **asserts the defect**: its 19 assertions
pass today because the page is broken.

**R2 checked what could be checked here without a Hub, and says plainly what it did not.** The
harness asserts through a `check(ok, label)` helper (`:60`), and the assertions that carry the claim
are readable in the source: `:196` *"the skeleton is gone — the page is no longer 'loading'"*, `:197`
*"and an EMPTY textarea is what the operator sees"*, `:198` *"with Save ENABLED over a failed load"*,
and the read-back pair at `:217`/`:226`. So "it asserts the defect" is verified from the file, and
task 4.1's instruction to invert exactly those is correct — including that the baseline column
(`:172-173`) survives inversion untouched, since it asserts the success path. What is **not**
re-verified is that they all still pass: that is `F271`'s 2026-09-02 run, and neither R1 nor R2
started a Hub. The harness also has **no in-flight column at all** — every `check` sits in the
success, aborted or 500 case — which is how the loading-state write path went unmeasured; `tasks.md`
4.1b adds it. It is the regression drive for this change and its
expectations invert — the empty-editor and Save-enabled assertions become "no editor, no Save, a
stated failure", and the end-to-end read-back stops being a destruction check and becomes a
preservation check (stored content unchanged after the operator's click). Its baseline column must
keep passing unchanged; that is what shows the fix did not cost the working path.

Unit coverage goes in `hub/ui/src/__tests__/`, which is where every other component test in this
repository lives. A test that only mounts the error state and asserts a string is weak — it passes
against a page that renders the error text *and* the textarea. The assertion that carries the
requirement is that no PUT is issued: assert on the mutation, not on the markup.

The bundle at `hub/hub/static/ui` is a committed build artefact and the drive runs against the
**served** bundle. `npm run build` then `python scripts/refresh_ui_bundle.py`, committed with
`hub/ui/src`, or the drive re-measures the old page and reports success.

## R3: reading the two specs in full found a requirement this component already breaches

R3's brief required reading `project-instructions` and `project-environment-settings` end to end
rather than grepping them, because on 2026-08-28 round 3 caught rounds 1 and 2 both breaching a
requirement that had shipped four days earlier. It happened again, in the milder form: nothing in
this delta contradicts either document, but the component the delta edits does not satisfy one of
them, and had not for as long as it has existed.

`project-environment-settings` — *Saving reports its outcome*: "Changing a configuration section's
settings SHALL report whether the change was saved, and a failure SHALL state why in the section
rather than only in a log."

`InstructionsPage` reports one half. `saveMutation.isError` and `saveMutation.error` are never read;
`:20-26` binds `isSuccess` alone and drives a "Saved" badge from it. A rejected PUT therefore
re-enables the button, renders nothing, and leaves an operator who watched the button return to
"Save" with no way to tell a refusal from a success. That is a shipped requirement breached today.

Three reasons it is folded into this change (task 1.6) rather than filed:

1. It is **measured, on one page** — the same standard on which R1 rejected the capability-wide
   requirement for promising seven pages nobody had looked at. This one was looked at.
2. It is the **same defect class in the same component**: the page telling the operator something
   about its own state that is not true. Fixing the read side and shipping the save side unchanged
   leaves a page that announces failures it did not cause and hides the ones it did.
3. It needs **no delta**. The requirement already binds; nothing is added to the corpus. What was
   missing was an implementation and a test, which is what 1.6 and 2.8 are.

The other direction was also checked and is clean. *A configuration section states what it governs*
survives the new failure state, because `SettingsSection` renders the title and description in the
heading (`:45-57`), outside the `{children}` the branch replaces — but only if the implementation
replaces the branch rather than the section, which is now stated as task 1.5 because it is an easy
and invisible way to breach it. Nothing in `project-instructions` is contradicted: its two
server-side requirements are untouched, the route is untouched, and the MODIFIED requirement is the
only client-side one.
