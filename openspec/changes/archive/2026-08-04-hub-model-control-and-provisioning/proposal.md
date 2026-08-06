# Model catalog, per-turn model and effort control, and inline provisioning

## Why

The Hub can run Claude and Codex agents, but the operator cannot choose *what* they run with. Three
separate gaps share one missing concept.

**There is no model catalog, and the ad-hoc substitute is already producing wrong numbers.**
`Runner.model` is a free-text `String(256)` with no validation and no companion metadata.
Context-window limits live in `runner_parsing.py` as two partial tables:
`CODEX_MODEL_CONTEXT_LIMITS` holds two entries behind a `CODEX_DEFAULT_CONTEXT_LIMIT = 128000`, and
that module's own docstring records that the Claude table "is stale (has no entry for Sonnet 5's
actual 1M window and silently falls back to a wrong 200K default)". The damage is visible in the
running application: agent `codex-beta` reports **136,550 / 128,000 tokens — 100% estimated**, over
a limit that is merely the default for an unrecognised model. Context-usage pressure, which pauses
autonomous turns, is being computed against a fabricated denominator.

**Model and effort cannot be changed without editing a runner.** Both CLIs accept a model per
invocation and both accept an effort level, but neither is reachable from the conversation. To move
one turn to a stronger model the operator must leave the conversation, edit the runner record —
which is shared by every agent bound to it — and come back.

**Creating an agent cannot create its capability.** `AgentCreateDialog` offers only a dropdown of
runners that already exist, so an operator who wants a Codex agent on a model no runner uses must
first go to the Runners section and build one. The provider and model are the two things the
operator actually has in mind, and they are the two things the dialog does not ask for.

**A project's directory must be typed from memory.** `ProjectManagerModal` presents a bare text
input for an absolute path with no browsing affordance, so a typo is indistinguishable from a
missing directory until the registration fails.

### What the spike established

Model switching mid-conversation was the open risk. It is resolved, and the answer is that both
providers support it:

- **Claude** documents `--model` and `--effort` as applying to "the current session", and session
  transcripts confirm the behaviour empirically: a single continuous Claude Code session on this
  machine contains three model changes (`claude-opus-5` → `claude-sonnet-5` → `claude-opus-5`) with
  the model recorded per message. Model is not pinned at session creation.
- **Codex** documents `-c model="o3"` as an override example on `codex exec resume` itself, offers
  `-m/--model` on `exec`, and accepts `model_reasoning_effort` as a validated config key — a
  neighbouring unknown key is rejected under `--strict-config`, this one is not.

Two findings from the spike shape the requirements directly:

1. **The effort scales differ per provider.** Claude accepts `low, medium, high, xhigh, max`; Codex
   accepts `minimal, low, medium, high, xhigh, max, ultra`. A shared enum would be wrong for both.
2. **Provider validation is asymmetric and partly silent.** Claude rejects an unknown `--model`
   outright, but an unknown `--effort` only warns and *silently proceeds at the default*. The Hub
   therefore cannot delegate validation to the CLI without risking a run that quietly used settings
   the operator did not choose.

## What changes

- **A model catalog becomes a first-class capability.** Each supported provider declares its models
  — with the context window each one actually has — and its available controls. The catalog is
  served to the frontend and is the single authority the Hub validates against before spawning.
- **Controls are declared, not coded.** A control declares its identity, kind, permitted values,
  default, and how it maps onto the provider's command line. Adding a further control — Codex also
  exposes `model_verbosity`, `model_reasoning_summary`, and `plan_mode_reasoning_effort`; Claude
  exposes `--max-budget-usd` — is a catalog entry, not new UI code and not a new endpoint.
- **Context-window limits move into the catalog.** The partial tables in `runner_parsing.py` are
  replaced by catalog lookup, so usage percentages stop being computed against a default that does
  not describe the model in use. Self-reported windows from a provider still take precedence where
  the provider reports one.
- **The composer gains model and effort controls**, rendered from the catalog into the control row
  that `2026-08-04-hub-charcoal-visual-refresh` establishes. The operator changes either without
  leaving the conversation.
- **The choice is remembered per conversation.** A conversation carries its runtime overrides; a new
  conversation inherits its agent's runner defaults. Overrides are stored as one structured field
  keyed by control identity, so a new control needs no schema change.
- **The composer routes a message explicitly.** The operator chooses whether a message continues the
  current conversation or starts a new one, alongside the existing choice of target agent.
- **Agent creation asks for provider and model**, then finds or creates the matching runner. Runners
  remain the underlying capability record and the runner/agent/charter separation is preserved; the
  dialog provisions one rather than requiring the operator to have done it first.
- **The project directory can be browsed.** A directory-listing endpoint backs a picker in the
  project dialog. Browsers cannot supply an absolute path to a web page — `showDirectoryPicker()`
  deliberately withholds it — so the listing must come from the Hub process itself.

## Non-goals

- Adding providers. Claude and Codex are the two the Hub can spawn today
  (`runner_commands.SUPPORTED_RUNNERS`); the catalog is shaped to accept more, but this change adds
  none.
- Making the catalog operator-editable at runtime. It ships with the Hub and updates with it. The
  descriptor is designed so a file- or database-backed source can be layered later.
- Changing the runner/agent/charter separation, or letting an agent bind to more than one runner.
- Per-turn overrides for anything other than the controls the catalog declares.
- A general-purpose filesystem browser. The endpoint lists directories to choose a project root.
- Changing conversation semantics: queue handling, hop budget, handoff, autoscroll, and
  provider-identity confinement keep their current specified behaviour.

## Impact

- **Backend:** new `model_catalog` module and `GET` endpoint; `agent_trigger.py`
  (`TriggerAgentRequest` gains overrides, validated before spawn); `runner_commands.py` (apply
  overrides from descriptors); `runner_parsing.py` (context limits from the catalog);
  `conversations.py`; `api/v1/agents.py` (creation by provider and model); a directory-listing
  endpoint; migration `0027` adding `Conversation.runtime_overrides`.
- **Frontend:** `Composer.tsx` control row population, `ComposerAgentSelector.tsx` (conversation
  routing), new catalog-driven control component, `AgentCreateDialog.tsx`,
  `ProjectManagerModal.tsx`, and the API hooks for the catalog and directory listing.
- **Specifications:** adds `model-catalog`; modifies `agent-conversation-workspace`,
  `operator-agent-creation`, `runner-registry`, `agent-context-usage`, and
  `local-project-workspace`.

## Approval gate

Implementation MUST NOT begin until the user explicitly approves this proposal.

**Approved:** yes (2026-08-05, verbal: "Both approved. Implement both of those.")
