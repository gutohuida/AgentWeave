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
fallback)` rendered into a `role="alert"` block — and `AgentCreateDialog.tsx` already uses both
halves of what this change needs: a `<Select>` populated from `useModelCatalog()` (line 222) and a
mutation-error alert (line 235). `RunnersPage` is the outlier, not the frontier.

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
- `flags` is already effectively clearable. `agent_trigger.py:976` reads `list(runner_row.flags or
  [])`, so `[]` and `None` are the same state at spawn, and `PATCH {"flags": []}` reaches it. The
  asymmetry is real but costs nothing today; `model` is the only field whose empty spelling the
  Hub refuses.

`""` stays refused. The UI never sends it, and a caller that does is asking for a model named the
empty string.

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
is changeable and the model choice must reset with it — `AgentCreateDialog.tsx:180` already does
exactly this and is the pattern to copy.

**Not the `ModelPicker` component.** `components/agents/ModelPicker.tsx` is a composer control: it
positions itself `absolute … bottom-full` (opens upward, correct above a composer, wrong inside a
centred modal), styles itself with `composerControlClassName`, and has no way to express "no model"
— `current` falls back to the provider's default descriptor, so unset and default-selected render
identically. A plain `<Select>`, which this dialog already uses for CLI, is both the smaller change
and the correct control.

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
