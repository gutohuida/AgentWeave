# Tasks

Implementation MUST NOT begin until the proposal is approved.

Ordering is deliberate: the catalog and its descriptors land first because command building,
validation, context accounting, and every piece of UI in this change read from them. The composer
work assumes the control row from `2026-08-04-hub-charcoal-visual-refresh`; if that change has not
landed, do section 5 after it.

The mid-conversation model-switch spike is already resolved — see `proposal.md` — so no
investigation task precedes implementation.

## 1. The catalog

- [x] 1.1 Add `hub/hub/model_catalog.py` defining the provider, model, control, and application
      descriptor shapes from `design.md`.
- [x] 1.2 Populate the Claude entry: models with their context windows, the `model` control applied
      as `--model {value}`, and the `effort` control applied as `--effort {value}` with values
      `low, medium, high, xhigh, max`. Model/context-window values live-verified against
      `claude --help` and `runner_parsing.py`'s docstring, not authored from memory — see
      `model_catalog.py`'s own module docstring.
- [x] 1.3 Populate the Codex entry, **with two deviations from this task's literal text, found
      during implementation and decided in favour of live evidence over the proposal's estimate**:
      1. **Model flag is `--model {value}`, not `-m {value}`.** `runner_commands.py`'s existing
         `_build_codex_command` already used `--model` before this change (verified by reading it);
         `-m` is that flag's short alias. Introducing a second flag form for the same setting would
         be pure duplication for no behavioural difference.
      2. **Effort values are `low, medium, high, xhigh` — `minimal` and `ultra` are dropped.**
         Read directly from `~/.codex/models_cache.json`, the installed Codex CLI's own
         server-synced model catalog (has a `fetched_at` timestamp and `etag` — this is live,
         current data, not a guess). Its 6 listed models' `supported_reasoning_levels` show `low/
         medium/high/xhigh` on every one, `ultra` on 3 of 6, and `minimal` on none. The task's
         claimed 7-value scale came from the proposal's spike, which manually probed
         `--strict-config` against whichever model happened to be active — sufficient to prove
         *a* value is accepted, not that *every* model accepts it. Accepting `minimal`/`ultra` at
         the provider level would let the Hub approve an override that a specific selected model
         actually rejects or silently discards — exactly the failure mode this whole change exists
         to prevent (see proposal.md's "What the spike established"). Precise per-model control
         values would be the more accurate fix but needs a schema change (scoping a control's
         values by model, not just by provider) beyond this session — flagged as a follow-up, not
         done here.
      Models themselves are the 6 with `"visibility": "list"` in that same cache file (excludes
      `codex-auto-review`, `visibility: "hide"`), with that file's own `context_window` per model.
- [x] 1.4 Declare a context window per model, using unknown rather than a substitute where the true
      window is not known. (Claude's Opus 5 and Fable 5 — no live-verified window on this machine.)
- [x] 1.5 Add `GET /api/v1/model-catalog` returning the descriptors. Not project-scoped — the
      catalog is static and identical for every project. (Operator-authenticated via `get_operator`,
      same as `GET /api/v1/projects`.)
- [x] 1.6 Add a validation helper resolving an override set against a provider entry, returning
      either the accepted values or a stated reason. (`validate_overrides` in `model_catalog.py`.)
- [x] 1.7 Tests: every declared provider is spawnable; no unspawnable provider is declared; an
      effort value valid for one provider is refused for the other. (`test_model_catalog.py`,
      `test_model_catalog_api.py` — 19 tests.)

## 2. Applying overrides to invocations

- [x] 2.1 Teach `runner_commands.build_command` to render an application specification into argv,
      handling both the flag form and the configuration-override form. (New `control_overrides`
      param, rendered via `model_catalog.render_control_args`; `model` stays its own dedicated
      param — model selection was never part of `controls[]` in the approved schema, only
      `ModelDescriptor`.)
- [x] 2.2 Apply resolved overrides for Claude, confirming `--model` and `--effort` are placed where
      the CLI expects them.
- [x] 2.3 Apply resolved overrides for Codex, keeping exec-level flags before the `resume`
      subcommand — the ordering already required for `--sandbox`.
- [x] 2.4 Tests, table-driven from the descriptors: each control renders the documented argv; a
      resumed Codex invocation keeps its flags before `resume`. (`test_runner_command_overrides.py`
      — 6 tests, plus the 1 pre-existing `test_runner_command_env.py` test still passing.)

## 3. Per-conversation overrides

- [ ] 3.1 Migration `0027`: add `Conversation.runtime_overrides` as a nullable JSON column.
- [ ] 3.2 Resolve a turn's effective settings as conversation overrides, then the agent's runner,
      then the catalog's control defaults.
- [ ] 3.3 Extend `TriggerAgentRequest` to accept overrides, validate them against the catalog before
      spawning, and refuse with a stated reason on failure.
- [ ] 3.4 Persist accepted overrides onto the conversation.
- [ ] 3.5 Expose a conversation's current overrides on the endpoints the composer reads.
- [ ] 3.6 Tests: overrides persist across turns and reload; a new conversation inherits runner and
      catalog defaults; changing one conversation leaves the agent and its other conversations
      unchanged; an invalid override refuses the turn and starts no process.

## 4. Context windows from the catalog

- [ ] 4.1 Replace `CODEX_MODEL_CONTEXT_LIMITS` and `CODEX_DEFAULT_CONTEXT_LIMIT` in
      `runner_parsing.py` with catalog lookup.
- [ ] 4.2 Remove the stale Claude substring table described in that module's own docstring.
- [ ] 4.3 Implement the resolution order: provider self-report, then catalog, then unknown.
- [ ] 4.4 Report unknown usage as unknown — no proportion, no pressure state, no budget pause.
- [ ] 4.5 Attribute usage to the model that ran each turn so a conversation whose model changed is
      measured correctly.
- [ ] 4.6 Tests at all three branches, plus: reported usage never exceeds its own window. Confirm
      the live symptom is gone — an agent must not report over 100% of a default window.

## 5. Composer controls and routing

- [ ] 5.1 Add a React Query hook for the catalog.
- [ ] 5.2 Build a control component that renders any declared control by kind, with no hardcoded
      provider knowledge.
- [ ] 5.3 Place the model and control selectors in the composer control row's leading slot.
- [ ] 5.4 Present the current model and control values at rest, without opening a menu.
- [ ] 5.5 Re-derive the presented controls when the target agent's provider changes.
- [ ] 5.6 Add conversation routing — continue the current conversation or begin a new one — and make
      the destination visible before sending.
- [ ] 5.7 Tests: controls follow the provider; a message routes to the stated conversation; the
      interface hardcodes no provider models or control values.

## 6. Agent creation by provider and model

- [ ] 6.1 Replace the runner dropdown in `AgentCreateDialog.tsx` with provider and model selection
      driven by the catalog.
- [ ] 6.2 Probe and present launchability per provider, keeping an unlaunchable provider visible
      with its reason.
- [ ] 6.3 Implement find-or-create of the matching runner, creating runner and agent in one
      transaction.
- [ ] 6.4 Keep server-side launchability revalidation on submit.
- [ ] 6.5 Constrain runner management to catalog models, keeping existing unrecognised models
      readable and reporting them as unrecognised on edit.
- [ ] 6.6 Tests: a second agent on the same provider and model reuses the runner; a failed creation
      leaves no runner; a provisioned runner appears in runner management.

## 7. Directory browsing

- [ ] 7.1 Add `GET /api/v1/fs/list`, returning subdirectories with the listed path and its parent.
- [ ] 7.2 Require the standard API key; never return file names or contents; do not traverse
      symbolic links out of the listed directory.
- [ ] 7.3 Where a workspace root is configured, bound listings to it and refuse anything outside
      with a stated reason.
- [ ] 7.4 Return an unreadable directory as an empty listing with a reason rather than an error that
      ends browsing.
- [ ] 7.5 Add the picker to `ProjectManagerModal.tsx`, keeping the text input for a known path.
- [ ] 7.6 Tests: unauthenticated refusal; directories only; symlink not traversed; workspace-root
      bound enforced; unreadable directory reports a reason.

## 8. Verification

- [ ] 8.1 `pytest hub/tests -q`.
- [ ] 8.2 `npm test` in `hub/ui`.
- [ ] 8.3 `npx tsc --noEmit` in `hub/ui`.
- [ ] 8.4 Migration check: `0027` applies to an existing database and existing conversations load
      with no overrides.
- [ ] 8.5 `npm run build`, then refresh and commit `hub/hub/static/ui`.
- [ ] 8.6 `pytest hub/tests/test_ui_staleness.py -q`.
- [ ] 8.7 `openspec validate 2026-08-04-hub-model-control-and-provisioning --strict`.
- [ ] 8.8 Live: change model and effort mid-conversation against a real agent and confirm the turn
      runs under the chosen values and that the values survive reload.
- [ ] 8.9 Live: create an agent by provider and model with no pre-existing runner; confirm a second
      such agent reuses the runner.
- [ ] 8.10 Live: browse to a project directory and register a project with the chosen path.
- [ ] 8.11 Live: confirm no agent reports context usage above 100% of its own window.
