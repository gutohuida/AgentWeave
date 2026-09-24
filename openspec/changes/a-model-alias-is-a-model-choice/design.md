# Design — a model alias is a model choice

**Built on the recommended answer to D2 (second question): aliases are accepted and stored as
written.** If the operator answers *"accepted, but normalised to the id"*, D1 below changes. Every
door would store `m.id` instead of the submitted string, and the picker would offer no alias
choices (an alias typed over the API would simply resolve). The spec delta's second sentence would
become "is recorded as the model it stands for". If the operator answers *"refused"*, this change
is withdrawn: `568f868` already made the refusal truthful, and F221 closes as fixed by it.

## The options for D2 (aliases), with evidence

| Option | What it releases | What it breaks or costs |
|---|---|---|
| **A. Refuse (today)** | Nothing to build. The sentence is already true (`568f868`) | A Claude runner can only follow the provider's newest model through a catalog edit and a release (F267). The catalog publishes a vocabulary that no door accepts |
| **B. Accept, store the id** | The API accepts the CLI's shorthand | Nothing gained over A for F267: the stored id is as frozen as today's. The alias-to-id map (`opus → claude-opus-5-5`) becomes load-bearing and is a hand-maintained literal that has already moved once (`b661766`) |
| **C. Accept, store as written (recommended)** | A runner that follows the provider's latest model with no catalog edit, which is the one Claude-side answer to F267 | Two strings can now mean one model on a given day (`opus` and `claude-opus-5-5`). The context window for an alias is the target's, which could be stale if the alias moves to a model with a different window. See D3 |

## D1 — one resolution rule

`ProviderDescriptor.model(value)` returns the descriptor whose `id == value`, **or whose `aliases`
contain `value`**. Every door already goes through it, so every door agrees:

| Door | Call site | After |
|---|---|---|
| `POST/PATCH /runners` | `runners.py:40` | `opus` accepted, stored `opus` |
| `POST /agents` find-or-create | `agents.py:695-716` | accepted; matches an existing runner by `Runner.model == "opus"`, or creates one named `Claude Code — opus (latest)` |
| per-run override | `validate_overrides` (`model_catalog.py:395`) | accepted, passed through unchanged |
| worker gate | `worker.model_is_declared` (`worker.py:165`) | accepted. Its docstring's *"exact ids only, matching `_reject_undeclared_model`"* is rewritten, and the reason still holds (the two gates stay equal) |
| `RunnerResponse.model_unrecognised` | `schemas/runners.py:55` | `False` for an alias |

`context_window_for_model` already resolves aliases (`model_catalog.py:316-337`) and is unchanged.

**The runner name for an alias** in `agents.py:713` becomes `f"{provider.label} — {value} (latest)"`
rather than the target's label. A runner named `Claude Code — Opus 5.5` that runs whatever `opus`
means next month would be a new F268.

## D2 — what is offered

`RunnerForm` (`RunnersPage.tsx`, the model select built from `declaredModels`, `:203`) and
`AgentCreateDialog` (`:222`) render, for the chosen provider, the declared ids as today. After them
comes one group, `Latest`, with one option per alias. Its value is the alias, and its label is
`opus — latest (now Opus 5.5)`, where "now" is the target descriptor's `label`. The existing
`storedIsDeclared` check (`RunnersPage.tsx:209`) must count an alias as declared, or opening a
runner stored as `opus` would show it as unrecognised.

If `a-runner-choice-names-its-model` has shipped, `runnerOptionLabel` renders an alias-stored
runner's model part the same way.

**Two more readers of a stored model, found by R2** (grep `models.find` in `hub/ui/src`). Both
match `m.id === value` only, and both would misreport an alias-stored runner:

| Reader | Today on `opus` | After |
|---|---|---|
| The composer's `ModelPicker` (`ModelPicker.tsx:55`; fed `runner.model` by `AgentOutputPanel.tsx:1323` and `NewConversationSurface.tsx:211`) | `find` misses, so it falls back to the provider **default** and shows *Sonnet 5* for an agent running Opus. The same wrong-model display F268 is about | `current` also matches `m.aliases.includes(effectiveModel)`, and the button reads `opus — latest (now Opus 5.5)`. The list's active mark (`:197`, `model.id === (effectiveModel ?? current?.id)`) compares the raw value too, so an alias marks no row; it becomes `model.id === current?.id` (R3) |
| Project settings, checkpoint model (`ProjectSettingsPanel.tsx:290-297`, and the window lookup at `:91-93`) | offers ids only; a stored alias shows as a blank select, and the threshold preview has no window | offers the `Latest` group too; the window lookup resolves aliases |

One shared helper, `resolveCatalogModel(provider, value)` in `hub/ui/src/api/modelCatalog.ts`,
serves all five UI readers (the two pickers, `storedIsDeclared`, `ModelPicker`, the checkpoint
select), so the UI's rule is the Hub's D1 rule stated once.

**An unvalidated door, noted.** `PATCH /projects/{id}` accepts any `checkpoint_model` string
(`api/v1/projects.py:102`, `max_length` only); it is checked only at spawn, by the worker gate.
This change does not add validation there. With D1, an alias passes the worker gate, so the
checkpoint select's `Latest` group works end to end.

## D3 — the context window of an alias

The alias's window is its current target's (`context_window_for_model`). This is right today: every
alias targets a model whose window was re-verified on 2026-09-23. If the provider moves an alias to
a model with a different window, the meter uses the old window until the catalog is edited. That is
the same staleness the literal already has, not a new kind. The Claude context meter also reads
`result.modelUsage.<model>.contextWindow` from the CLI itself (`runner_parsing.py` docstring), so
the live meter follows the real model regardless.

## What each route returns when what it calls raises

`get_provider` and `ProviderDescriptor.model` do not raise (dictionary and tuple lookups). No route
gains a new failure path. `POST /runners` with an unknown string still answers 400 with
`undeclared_model_reason`.

## Tests that can fail

All in `hub/tests/test_a_model_alias_is_a_model_choice.py` (new) unless stated.

1. For each door (the three routes already parametrised in
   `test_a_refusal_says_what_would_work.py:29-35`, plus `validate_overrides` and
   `worker.model_is_declared`), `opus` is accepted. For the routes, the stored runner's `model` reads
   back `"opus"`. **Fails today** with 400. It **also fails if a later edit normalises to the id**
   (it asserts `"opus"`, not `claude-opus-5-5`).
2. `runner_commands.build_command(runner="claude", cli="claude", model="opus", …)` contains `["--model", "opus"]`.
   This pins "as written" at the argv, where it matters.
3. `GET /runners` for a runner stored as `opus` has `model_unrecognised == False`. **Fails today.**
4. An unknown model's refusal lists the aliases among what would be accepted.
5. `test_a_published_alias_is_refused_naming_the_id_it_stands_for`
   (`test_a_refusal_says_what_would_work.py:56`) is **deleted**, and its intent moves to test 1.
   Record this deliberately in the commit.
7. UI: `hub/ui/src/__tests__/composerModelControls.test.tsx` (extend): `ModelPicker` with
   `effectiveModel="opus"` shows the Opus label, not the provider default, and marks the Opus row
   active. **Fails today** (shows *Sonnet 5*, and marks no row).
6. UI: `hub/ui/src/__tests__/runnerForm*.test.tsx` (or the existing RunnersPage test) with
   `GET /model-catalog` served in catalog order. The `Latest` group lists `opus, sonnet, haiku,
   fable` in that order, each labelled with its current target. Opening a runner stored as `opus`
   selects the alias option and shows no `Unrecognised` chip. Fails today.

## Round log

- R1 (2026-09-24): written.
- R2 (2026-09-24): D1's backend door table confirmed complete (`ProviderDescriptor.model` has five
  callers: `runners.py:40`, `agents.py:695`, `schemas/runners.py:55`, `worker.py:165`,
  `model_catalog.py:312/394`; `model_context_window` resolves through it too). Added the composer
  `ModelPicker` and the checkpoint-model select, which would have shown the wrong model for an
  alias, and test 7. Noted `checkpoint_model` as an unvalidated door.
- R3 (2026-09-24): D1's five backend callers re-confirmed by grep; `context_window_for_model` already
  resolves aliases (`model_catalog.py:330-333`). One more UI comparison found: `ModelPicker.tsx:197`'s
  active mark compares `model.id` to the raw stored value; added to D2 and test 7. No collision with
  B8 (`a-checkpoint-is-handed-over-once-…` touches `cut_over`, `consider` and
  `checkpointOperationStore`, not the model selects) or B11 (`the-app-window-keeps-…` names
  `ModelPicker.tsx:29` only as a `localStorage` writer; it changes the window profile, not the
  picker). File overlap only, compatible: `the-permissions-pill-shows-the-posture-the-run-gets`
  edits Claude's control default in `model_catalog.py` and `AgentSettingsControls.tsx:199`;
  `a-runner-choice-names-its-model` edits `:253` and `ProjectSettingsPanel.tsx:171,279`, beside
  this change's checkpoint-model select (`:290-297`).
