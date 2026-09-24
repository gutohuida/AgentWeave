# Proposal — a model alias is a model choice

Finding: **F221 (D)**, changed shape. Bundle B7 (models and budget), R1, 2026-09-24. Built on the
recommended answer to **D2's second question** (*"Are aliases accepted?"*): **yes, and a runner
keeps the alias as written.**

## Why

The catalog declares aliases for every Claude model it offers as current: `opus`, `sonnet`,
`haiku` and `fable` (`hub/hub/model_catalog.py:168-192`). `GET /model-catalog` serves them
(`schemas/model_catalog.py:52`). The `model-catalog` spec says a model entry carries *"any shorthand
aliases the provider accepts"*. And `claude --help` documents `--model` as taking *"an alias for
the latest model … or a model's full name"* (quoted in F267).

Every door that sets a model still refuses them. `ProviderDescriptor.model()` matches `m.id` only
(`model_catalog.py:128-132`). Its callers are the runner create and edit routes
(`api/v1/runners.py:40`), the Add-agent find-or-create (`api/v1/agents.py:695`), per-run overrides
(`validate_overrides`, `model_catalog.py:373`, used at `api/v1/agent_trigger.py:1559`), the worker
gate (`worker.py:157-165`), and the `model_unrecognised` flag (`schemas/runners.py:55`).

**What changed since F221 was filed.** Commit `568f868` (2026-09-23, Round 4b) made the refusal
truthful. It no longer says an alias *"is not a model 'claude' declares"*. It says *"'opus' is the
alias 'claude' publishes for 'claude-opus-5-5'; a runner stores the model id, so use
'claude-opus-5-5'"* (`undeclared_model_reason`, `model_catalog.py:287-305`). So F221's stated
defect, a sentence that was untrue, is fixed. What remains is D2's question: should the alias be
refused at all?

**Why accepting it matters (F267).** The Claude half of the catalog has no machine-readable
upstream. `claude --help` lists no models, and `scripts/check_model_catalog.py` covers Codex only
(`PROVIDER = "codex"`). So the only thing that keeps a Claude runner on the provider's latest model
without a catalog edit and a release is the alias, which the CLI resolves at spawn. This is also
the mechanism that already moved under the catalog once: on 2026-09-23 the `opus` alias moved from
`claude-opus-5` to `claude-opus-5-5` (`b661766`). A runner stored as `opus` would have followed it.
A runner stored as `claude-opus-5` did not.

## What changes

- An alias the catalog declares for a provider is accepted **wherever that provider's model id
  is**: runner create and edit, Add agent, per-run overrides, and workers. It is also recognised
  wherever a model is flagged unrecognised.
- **A runner keeps the alias as written.** `opus` is stored as `opus` and passed to the CLI as
  `--model opus`, so the runner follows the provider's latest Opus. Choosing `claude-opus-5-5`
  still pins that model. These are two different choices, and both are offered.
- Runner management and Add agent offer each alias as its own choice, labelled
  `opus — latest (now Opus 5.5)`. The label is taken from the alias's current target in the
  catalog, and states it as the catalog's reading, not a promise.
- `undeclared_model_reason` loses its alias branch, since aliases are no longer refused. Its list
  of what would be accepted names the aliases too.

## Out of scope

- Changing the Add-agent default from `claude-sonnet-5` to `sonnet`. That is a product call about
  what a new agent should get, and it is left for the operator.
- Codex aliases. The Codex cache declares none.

## Capabilities

- **model-catalog**: ADDED, a declared alias is accepted wherever a model is, and is kept as
  written.
- **runner-registry**: ADDED, runner management offers each declared alias as a choice of its own.

## Impact

- `hub/hub/model_catalog.py` (alias resolution in `model()`, `undeclared_model_reason`),
  `hub/hub/worker.py` docstring. The UI pickers are `RunnersPage.tsx` (the `RunnerForm` model
  select), `AgentCreateDialog.tsx:222`, the checkpoint-model select
  (`ProjectSettingsPanel.tsx:290-297`) and the composer's `ModelPicker.tsx:55` (R2), plus `runnerOptionLabel` if
  `a-runner-choice-names-its-model` shipped first.
- One existing test inverts: `test_a_published_alias_is_refused_naming_the_id_it_stands_for`
  (`hub/tests/test_a_refusal_says_what_would_work.py:56`).
- No migration. A runner already storing an id is unchanged.
