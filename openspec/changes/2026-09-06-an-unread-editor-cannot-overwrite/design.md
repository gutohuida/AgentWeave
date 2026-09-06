# Design — an unread editor cannot overwrite

## The condition to gate on, and why it is not `isError`

The obvious repair is to read `isError` alongside `isLoading` and add a branch. It is not the
cleanest one, because `isError` is a *reason*, and what the textarea needs is a *fact*: has this
project's stored content arrived?

React Query 5.62 gives four combinations at this call site, and only one of them has content to
show:

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

**The fourth row is derived, not driven.** `useInstructions` is
`enabled: isConfigured && !!projectId` (`hub/ui/src/api/instructions.ts:14`), and `App.tsx:484`
renders `<InstructionsPage />` from a `destination.kind === 'project'` branch that carries
`destination.projectId`, while the hook reads `selectedProjectId` from `useConfigStore` — a second
source. Whether those two can ever disagree while this page is mounted was **not** established. The
gate above covers it either way; no scenario in this change asserts the state is reachable, and none
should until someone drives it.

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

**Track the loaded state in a `useState` beside `content`.** A second source of truth for something
the query already answers, and one that has to be reset by hand on every project change. The bug
being fixed is a component that kept state the query had invalidated.

**Give the query `placeholderData` or `retry: Infinity` for this endpoint.** Hides the failure
rather than stating it, and makes the empty editor arrive more slowly instead of not at all.

## Verification

`scripts/drive/t_d4_instructions_failed_load.py` currently **asserts the defect**: its 19 assertions
pass today because the page is broken. It is the regression drive for this change and its
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
