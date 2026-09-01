## How wide is this change?

The state note that queued this round pointed at something real: *"a refused create or edit reaches
nothing, and that absence is systemic rather than local to runners."* Round 1 measured how systemic,
because the answer decides the shape of the change.

**Measured** — every `.tsx` under `hub/ui/src` containing `.mutate(`, checked for any of
`readableApiError`, a rendered `.error`, an `errorDetail` helper, or an `onError` callback:

```
55 mutate call sites
 6 files with a mutation and no error surface at all:
     agents/AgentSettingsControls.tsx      agents/ConversationView.tsx
     instructions/InstructionsPage.tsx     messages/MessageCard.tsx
     spec/SpecPhaseBar.tsx                 tasks/TaskIntegrationNote.tsx
12 files already using readableApiError
```

So the absence is **not** the app lacking an idiom. The app has one — `readableApiError(err,
fallback)` rendered into a `role="alert"` block — used by twelve files. `RunnersPage` is the
outlier, not the frontier.

**Round 2 correction — the exemplar is only half an exemplar.** Round 1 named
`AgentCreateDialog.tsx` as using "both halves of what this change needs". Opened and read, one half
holds and one does not:

- The model half is genuine: `useModelCatalog()` at line 149, `catalog?.providers ?? []` at 168,
  and a `<select aria-label="Model">` over that provider's models at 222. Copy it.
- The error half is **not** `readableApiError`. Line 235 renders `errorDetail(createAgent.error)`,
  and `errorDetail` is a private helper at lines 10-18 — a near-identical twin of the
  `extractErrorDetail` this change deletes from `RunnersPage.tsx:19-30`. Both parse
  `{ detail?: string }`; both discard the Pydantic array body; neither reaches
  `readableApiError`.

That sharpens the case rather than weakening it: the same bespoke helper has already been written
twice, which is what a shared idiom exists to stop. It also means task 3.2 must copy
`AgentCreateDialog`'s *placement and tokens* and explicitly not its helper.

**Rejected: a global `MutationCache.onError` toast in `main.tsx`.** It would add a second, competing
error surface on top of twelve existing local ones, so the twelve would double-report; and it puts
the sentence somewhere other than beside the control that failed, which is the one place the
operator is looking. `readableApiError`'s own docstring already draws this distinction for its two
variants.

**Rejected: generalising the shipped requirement instead of adding a local one.**
`agent-conversation-workspace:2051` — *"The operator reads why a submission was refused"* — is the
general rule this change is an instance of, scoped to conversation submissions. Hoisting it to cover
every write surface is the cleaner end state and should happen. It does not happen here: the six
surfaces above have never been driven, so a general requirement would ship as prose the code
breaches on the day it lands, which is exactly the spec/code drift this corpus exists to prevent.
**Follow-up, named not done:** drive those six, then hoist the requirement.

So the change stays inside runner management, and adds the one API repair a picker forces.

## Why the API repair is in scope and not deferred

A free-text box let the operator believe they had cleared the model. They had not: an emptied field
became `model: undefined` in `RunnerFormValues`, which `JSON.stringify` omits, so the PATCH carried
no `model` at all and the old one stayed. The screen was wrong in a way the operator could not see.

A select cannot hide that. It must name the unset choice — "Provider default" — and a choice the
product offers has to work. Measured, it does not: `PATCH {"model": null}` answers **200** with the
old model still in the response body, because `update_runner` gates every field on `is not None`
(`runners.py:136-141`) and Pydantic gives an explicit `null` and an absent key the same value. The
one spelling that *does* reach the operator, `""`, is refused by the catalog check.

Splitting this out would ship a picker whose unset choice silently does nothing — the same class of
defect the change exists to retire, in a new place.

**The fix distinguishes absent from explicit-null**, on `model_fields_set` (or an equivalent
sentinel), for `model` only. It deliberately does not extend to the sibling fields:

- `name` has no meaningful null — a runner without a name is F176, a separate open finding.
- `flags` is already effectively clearable. Round 1 read this off `agent_trigger.py:976`
  (`list(runner_row.flags or [])`, so `[]` and `None` are the same state at spawn) without driving
  it. **Round 2 measured it** (`t_r2_runner_update_semantics.py`, Q3): `PATCH {"flags": ["--verbose"]}`
  then `PATCH {"flags": []}` leaves `flags == []`, and `PATCH {"flags": null}` is a **no-op** — the
  same null-is-absent shape as `model`. So `flags` carries the identical defect and it costs nothing
  only because `[]` is a reachable spelling that means the same thing at spawn. `model` has no such
  spelling: `""` is refused. That asymmetry is the whole reason `model` is fixed here and `flags` is
  not.

`""` stays refused. The UI never sends it, and a caller that does is asking for a model named the
empty string.

## The constraint round 1 missed: a legacy runner cannot be saved unchanged

`_reject_undeclared_model(cli, model)` takes a provider and a model string. **It cannot see the
runner's stored model**, so it cannot tell a newly typed undeclared model from the one the runner
already carries. Its own docstring claims otherwise —

> a model is refused only when it is being newly *set* — an already-stored, unrecognised model
> (from before this catalog existed, or a future CLI release) is left alone

— and that claim is true today only by accident. It holds because the free-text box sends
`model: model || undefined`, which `JSON.stringify` drops, so an untouched model field reaches the
Hub as an absent key. **A picker cannot do that.** The picker's selected value *is* the stored
model, and task 2.3 requires the edit path to keep sending `model` explicitly — so every save of a
legacy runner would carry its unrecognised model into `_reject_undeclared_model`.

Measured, on a fixture runner whose row was set to an undeclared model directly
(`t_r2_runner_update_semantics.py`, Q5, 18 passed / 1 failed — the one red being exactly this):

```
GET  /runners/{id}                                   -> model_unrecognised: true
PATCH {"name": "renamed"}                            -> 200, legacy model survives
PATCH {"name": "renamed", "model": "claude-3-legacy-9"}
      (the runner's own stored model, re-submitted)  -> 400
      'claude-3-legacy-9' is not a model 'claude' declares
```

So the change as round 1 wrote it would ship a screen on which a legacy runner **cannot be saved at
all** — not renamed, not re-bound, nothing — which breaches the shipped `runner-registry` scenario
"Existing runners keep working" that this change is otherwise strengthening. Round 1's own task 4.4
asserts the opposite of what the code does.

**The repair is one clause in `update_runner`:** a model identical to the one the runner already
records is not "being newly set", so it is not refused. That makes the docstring true rather than
accidentally true, and it is the minimum that lets the picker's third option state (design below)
round-trip. It deliberately does **not** relax the refusal for create, or for changing a legacy
runner to a *different* undeclared model — both of those are genuinely new settings.

## The picker's three states

The select carries exactly three kinds of option, and the third is what makes the shipped
"Existing runners keep working" scenario true rather than merely asserted:

1. **Provider default** — value unset. Sends `model: null` on edit, omits `model` on create.
   Selected when the runner has no model, which is what both seeded default runners have
   (measured: `Claude (default)` and `Codex (default)` both `model: null`).
2. **Each model the catalog declares for this runner's CLI** — 4 for `claude`, 6 for `codex`,
   measured from `GET /model-catalog` on the running Hub.
3. **The runner's own stored model, when the catalog does not declare it** — present, selected,
   and marked. Without it, opening the edit dialog on a legacy runner would silently re-point it at
   whatever option happened to be first, and pressing Save would destroy a working configuration.
   This is the requirement's own third scenario, and it is why the change reads
   `model_unrecognised` rather than recomputing recognition in the browser.

The CLI select is already `disabled` when editing (`RunnersPage.tsx:217`), so a runner never changes
provider and the option list never has to migrate under an existing selection. On **create**, the CLI
is changeable and the model choice must reset with it.

**Round 2 correction: `AgentCreateDialog.tsx:176-181` is the wrong thing to copy here.** Its
`handleProviderChange` resets to `entry?.models.find((m) => m.default)?.id ?? entry?.models[0]?.id`
— an explicit model id — because an agent must have one (`canSubmit` requires `!!model`, line 172).
A runner must reset to the **unset** "Provider default" option instead: unset is a valid runner
state, and silently choosing a model for the operator when they change CLI is the same class of
mistake as silently re-pointing a legacy runner. Copy the *shape* (reset on provider change), not
the value it resets to.

**Not the `ModelPicker` component.** `components/agents/ModelPicker.tsx` is a composer control: it
positions itself `absolute … bottom-full` (opens upward, correct above a composer, wrong inside a
centred modal), and styles itself with `composerControlClassName`. It also has no way to express
"no model", for two independent reasons, both re-derived: `current` is
`provider.models.find((m) => m.id === effectiveModel) ?? provider.models.find((m) => m.default)`
(line 55), so `effectiveModel === null` renders identically to the default being selected; and its
callback is typed `onChangeModel: (modelId: string) => void` (line 44), which has no spelling for
"unset" to emit even if the display could show one. A plain `<Select>`, which this dialog already
uses for CLI, is both the smaller change and the correct control.

## The error surface must be reset, not only rendered

`useCreateRunner()` and `useUpdateRunner()` are called in `RunnersPage`, not in `RunnerForm`
(`RunnersPage.tsx:36-38`). The mutation objects therefore outlive the dialog: `RunnerForm` unmounts
when `showForm` goes false, and `createRunner.error` is still set. React Query holds a mutation's
last result until the next `mutate` or an explicit `reset()`, so **"New Runner" reopened after a
refusal renders the previous refusal before the operator has submitted anything** — an alert about
a runner they are no longer creating.

`AgentCreateDialog` has exactly this shape and no reset, so copying it copies the defect. The dialog
must `reset()` the relevant mutation when it opens and when it is cancelled. *(Derived from React
Query's documented mutation-state lifetime and the call sites above, not driven — the assertion in
task 4.6 is what proves it.)*

## What round 2 checked and did not change

Recording these because a round that only reports what it changed makes the next round look cheaper
than it is. All measured by `scripts/drive/t_r2_runner_update_semantics.py` against the `:8011` Hub
in a fixture project, created and deleted; **18 passed / 1 failed**, the single red being the legacy
runner above.

- **What does the route leave behind when it raises?** `update_runner` assigns `runner.name` at
  line 133 and `_reject_undeclared_model` can raise at line 137, so a refused PATCH could plausibly
  commit half of itself. It does not: `get_session` yields inside `async with async_session_factory()`
  and never commits on the exception path, so the assignment is discarded when the session closes.
  Driven twice with two different undeclared models — the name was unchanged both times. Round 1
  never asked this; the answer is clean, and this change does not need to touch it.
- **A refused create leaves no row** — runner count unchanged across a 400.
- **`useDeleteRunner` throws `ApiError`.** Its `mutationFn` calls `fetchWithAuth` directly rather
  than a `*Json` helper, and `readableApiError` returns its *fallback* for anything that is not an
  `ApiError` — so task 3.4's swap could have silently replaced the delete refusal's sentence (which
  names the agents to unbind) with a generic one. Checked: `fetchWithAuth` throws
  `new ApiError(res.status, text)` on `!res.ok` (`client.ts:24-27`). The swap is safe.
- **`model_fields_set` is the right mechanism.** Verified against the real `RequestModel`
  configuration (`extra="forbid"`): an explicit `{"model": null}` yields `{'model'}`, an absent key
  yields `set()`, and `{"name": "x"}` yields `{'name'}`. Task 1.1 stands as written.

## What round 3 changed: the carve-out falsified a scenario that was left standing

Round 2 was right that a legacy runner must be saveable, and right about the clause that does it.
What it did not do is carry the consequence back through the requirement it was editing. The delta
was left holding two scenarios in the same requirement whose conditions overlap and whose outcomes
are opposite:

> **An undeclared model is refused** — WHEN a runner is submitted with a model its provider does not
> declare, THEN the request is refused with a stated reason.

> **A legacy runner can still be saved** — WHEN the operator ... saves it with that model still
> selected, THEN the save is accepted.

The second is an instance of the first's `WHEN`. An implementer who reads the requirement top to
bottom implements the first and breaks the second; one who reads it bottom to top does the reverse.
The normative paragraph four paragraphs down (*"refused where it is newly set, and only there"*)
resolves it, but a scenario is what gets turned into a test, and this pair cannot both be turned
into a passing one.

Two edits, both narrowing rather than adding:

- The requirement's bare absolute — *"The Hub SHALL refuse a runner carrying a model its provider
  does not declare"* — now says **a request that sets** a runner's model. A runner that already
  carries the model is not having it set. The sentence and the carve-out now agree at every reading
  depth instead of only at the fourth paragraph.
- The scenario gains `AND the runner does not already record that model`.

This is the whole of the round's headline. The change's argument survives it; its spec text did not.

## The second correction: a scenario with no test, and a test with no scenario

`A request that changes nothing is not reported as a change` was written for F219, before task 1.3
existed. Once task 1.3 lands, a `PATCH` carrying the runner's own stored model is *accepted*, `200`,
and the model is unchanged — which is that scenario's `WHEN` read literally, with the outcome the
change deliberately wants. So the scenario reads as forbidding what task 1.3 requires.

Meanwhile the requirement's own normative text — *"A request that carries no model at all leaves the
runner's model as it was; these are different requests and the Hub SHALL distinguish them"* — had no
scenario at all, while task 1.4 already tests exactly that.

So the scenario is replaced by the one the normative text asks for, and the guard it was carrying
(the response must not report the old model as though nothing had been asked) moves into the
clearing scenario as an `AND`, which is where it can actually be asserted. Net: the same behaviours
are covered, each by a scenario that can fail.

## The third: task 2.6 asked for something nothing required

`The runner list row marks a runner whose model_unrecognised is true` appeared in `tasks.md` and in
proposal.md's *What Changes*, and in no requirement — the shipped scenario says the operator is told
*when editing it*, and round 2's delta text scoped the marking to the offered choices.

Backed rather than dropped, and the reason is the requirement's own purpose. What makes a legacy
runner safe is that it is legible; the list is where runners are seen and the edit dialog is where
one already suspected is opened. The change is also already reading `model_unrecognised` in that
file for the picker, so the datum is in hand. One clause and one scenario `AND` now carry it.

## What round 3 checked and did not change

- **Both providers gate `--model` on the model being set.** Design above cited only
  `_build_claude_command` (`runner_commands.py:199-200`) for the claim that an unset model is a
  spawnable state. `_build_codex_command` does the same at `313-314` (`if model: cmd += ["--model",
  model]`). The claim holds for the whole catalog, not the half that was cited.
- **Every reader of `runner.flags` treats `[]` and `None` alike.** The asymmetry argument for fixing
  `model` and not `flags` rests on this, and round 1 cited one reader. There are exactly two:
  `agent_trigger.py:976` (`list(runner_row.flags or [])`) and `codex_appserver.uses_app_server`
  (`APP_SERVER_OPT_OUT_FLAG not in (flags or [])`, line 87), reached from `agents.py:226`. Both use
  `or []`. So clearing to `[]` genuinely restores the shipped *"A runner whose flags are unset SHALL
  receive the Hub's default transport"* state, and leaving `flags` alone breaches nothing.
- **`RunnersPage` is the only writer of runners in the app.** `useCreateRunner` / `useUpdateRunner`
  have one call site each (plus the test's mocks). So task 1.3's relaxation is reachable from the
  picker or from a direct API caller, and from nowhere else that could be surprised by it.
- **`useModelCatalog` is a `useQuery`**, so `isLoading` / `isError` are there for task 2.5 to read;
  `runnersUi.test.tsx:66` already mocks it with `{ data, isLoading: false }`.
- **The fixture measurements hold**: `modelCatalogFixture.ts` declares `models: []`, and `grep -rl`
  finds exactly 9 importers, all test files.
- **`t_r2_runner_update_semantics.py` re-run: 18 passed / 1 failed**, the same single red (the
  legacy runner's unchanged save). Nothing moved underneath the proposal.
- **`agent-conversation-workspace:1849` and `:2051` do not already govern this.** Both are scoped to
  *"a submission to an agent"* — conversation input, not runner CRUD — so the ADDED requirement is a
  sibling rather than a duplicate. `hub-interaction-feedback` is about pointer and focus states and
  says nothing about refusals. `hub-api-request-contract` governs *undeclared fields*, not refused
  values, and this change adds no field.

## Out of scope, and named: the refusal sentence is not strictly true

The catalog declares `opus` — as an *alias* of `claude-opus-5` (`model_catalog.py:154`) — but
`ProviderDescriptor.model()` matches `m.id` only (`model_catalog.py:113-117`), and nothing outside
the catalog module resolves aliases. So the Hub answers F173's exact reproduction with
`'opus' is not a model 'claude' declares` about a string the catalog lists and `claude --model opus`
accepts.

It is left alone here, deliberately: the picker submits ids, so after this change the sentence is
unreachable from the screen and the wart is API-only. Filed as **F221 (D)** rather than folded in,
because widening an A-severity repair to chase a D is how the repair stops shipping.

## What the catalog being empty means

`useModelCatalog` can be loading, or can fail. The dialog must not present an empty select as though
the provider declared no models — that reads as "this provider has none" rather than "we do not know
yet". While the catalog is unavailable the model control is disabled and says so, and Save stays
available: a runner with no model is a valid runner.

## Test fixture blast radius

`hub/ui/src/__tests__/support/modelCatalogFixture.ts` declares `models: []` for both providers and is
imported by **9** test files. `runnersUi.test.tsx` already mocks `useModelCatalog` with it (line 66),
even though `RunnersPage` does not read the catalog today — so the mock is in place and the fixture
is what has to change.

Extending the shared fixture with a small model list per provider is the right move: today every one
of those 9 tests renders a model picker against a provider that declares nothing, which is a state
the real Hub cannot produce. The task list requires the full vitest suite to be re-run after, and if
any test turns out to depend on the empty list, that test gets its own fixture rather than the shared
one being kept wrong.

## Open question for the operator

Whether to schedule the follow-up above — drive the six error-surface-less mutation sites, then hoist
`agent-conversation-workspace:2051` into a general requirement. It is a scope call, not a defect;
this change is complete without it.
