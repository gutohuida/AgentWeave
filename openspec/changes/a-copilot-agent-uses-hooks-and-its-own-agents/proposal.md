# Proposal — a Copilot agent uses hooks and its own agents

**Depends on:** the `RunnerAdapter` of `each-runner-cli-is-one-adapter` (slice 1). The members this
change needs are `map_events`, `build_launch`, `decide_posture`, `launchability` and
`catalog_provider`. (R2: as slice 1 is written, `map_events` and `build_launch` are
stream-transport members and `catalog_provider` is one value per adapter, so this Copilot work lands
in slice 2's `copilot_acp` module and in `resolve_agent_env`/`guard_env` instead. See design,
*Required of slices 1–4*, rewritten in R3.) It also depends on `a-copilot-agent-runs-over-acp` (slice 2): its ACP client and
raw-event subscription, the Hub-owned `COPILOT_HOME` per agent written at agent creation, the
`--disable-builtin-mcps` spawn flag, and its `copilot` runner literal and migration. It uses the
shim of `a-run-reaches-the-hub-without-mcp` (slice 3) only in a design alternative the operator can
choose. It lands after the 2026-09-27 night queue (DECISIONS `ghcp-d5-order`).

R1, 2026-09-27. Slice 5 of `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`. This is
the "take full advantage of Copilot" slice. Parity with Claude and Codex is slices 1 to 4. Everything
here goes beyond parity.

## Why

The operator asked to *"take full advantage of ghcp"*. Copilot reports things that Claude Code and
Codex keep to themselves:

- when it compacts a conversation, and what the compaction removed;
- every error, with a category (`quota`, `rate_limit`, `authentication`, …) and a remediation;
- every subagent it starts, with its model, tokens and duration.

It also ships review agents (`code-review`, `security-review`, `rubber-duck`), can run on the
operator's own API key (BYOK), and has a built-in GitHub MCP server.

Today the Hub uses none of it. Most urgently, the checkpoint capability exists so that a conversation
never "continues on a compaction nobody authored" (`hub/hub/checkpoint_policy.py:24-26`). Copilot
compacts at about 80%, which is the Hub's default threshold (`checkpoint_policy.py:28`). So the loss
that capability prevents can happen on a Copilot run before any Hub reading crosses the threshold.
Nothing in the Hub would notice.

## What R1 found that changes the ask

The slice was named for **hooks**. R1 read the 1.0.88 package's own event schema
(`schemas/session-events.schema.json` in the Copilot package, **VERIFIED**). The raw session events
that slice 2 already subscribes to over ACP carry **more** than the hooks do, for every fact this
slice wants:

| Fact | Hook payload | Raw event payload |
|---|---|---|
| Compaction | `preCompact`: `trigger`, `customInstructions`, `transcriptPath`. Notification only; it cannot block. | `session.compaction_complete`: `success`, `preCompactionTokens`, `postCompactionTokens`, `tokenLimit`, `summaryContent`, `checkpointPath`, `trigger` |
| Error | `errorOccurred`: `error{message,name,stack}`, `errorContext`, `recoverable` | `session.error`: `errorType` (`quota`, `rate_limit`, `authentication`, …), `statusCode`, `remediation`, `message` |
| Subagent | `subagentStart`/`subagentStop`: name, response text | `subagent.started` / `completed` / `failed`: `toolCallId`, `model`, `totalTokens`, `durationMs`, `totalToolCalls`, `error` |

The raw events also have three other advantages over hooks:

- They arrive on the connection the Hub already reads, tied to the session.
- They need no second process and no run token written to disk.
- A company cannot switch them off with `allowManagedHooksOnly`. That matters on the work PC, which is the fire test.

So this change feeds those facts from the raw events. **It installs no Hub hook.** It also records,
as a requirement, which hooks the Hub must never install. The operator's decision D2 lists "hooks"
among the Copilot files the Hub writes. Whether any hook is still wanted is put back to the operator
(design D2).

## What changes: four task groups, each separately cuttable

The groups are ordered by value. **Each can be REJECTED on its own**: it has its own requirements,
its own tests and its own drive, and no group depends on another.

### Group A: Copilot's own lifecycle reaches the Hub (highest value)

- **Compaction counts as the threshold being crossed.** A successful `session.compaction_complete` is
  handled as though the conversation crossed its checkpoint threshold, under whatever checkpoint
  mode it already has:
  - `automatic` generates a checkpoint and hands over;
  - `offered` warns without spending;
  - `off` does nothing beyond recording the compaction.

  Every existing gate still applies (handed over, dismissed, nothing new since the last checkpoint).
  No notes are requested at that point, because it is too late for notes. A compaction arriving
  while a reading is being considered is considered afterwards, not dropped (R2).
- **Errors become error events** in the run's stream, keeping their category, status code and
  remediation, and recorded once even though Copilot also echoes them as text. (R2: an error, not a
  diagnostic, because diagnostics can be hidden and errors must stay visible. R3: Copilot sends the
  structured event before its echo, so the echo chunk is dropped on arrival and nothing is held.)
  A failed compaction is a diagnostic; a subagent's compaction is not the conversation's (R3).
  Recording one does not move any quota hold: holds are slice 4's.
- **Subagents appear in the run's timeline**: start, end and failure, paired by the parent's tool
  call.
- **No hook decides anything.** The Hub never installs `permissionRequest`, `preToolUse`, or a
  blocking `agentStop`/`subagentStop`, and never trusts the workspace folder on Copilot's behalf. The
  reasons:
  - a `permissionRequest` hook short-circuits ACP `session/request_permission` (**VERIFIED**), so it
    would move decisions out of `_decide`, out of the operator's cards and out of the decision record;
  - `preToolUse` fails **open** on timeout;
  - a blocking `agentStop` would be the backstop CLAUDE.md forbids;
  - a trusted folder would load this repository's own `.claude/settings.json` hooks into a Copilot run.

### Group C: BYOK, a Copilot runner on the operator's own API key

- A `copilot` runner can name a provider, `anthropic` (R2: `openai` deferred with Azure, because
  the Codex catalog is now a per-machine CLI cache, not a list of API ids), plus the **name** of a
  Hub environment variable that holds the API key. That is the same indirection `ANTHROPIC_API_KEY_VAR`
  already uses (`hub/hub/launchability.py:101-114,162-169`). The key is never stored.
- The runner's model is checked against that provider's catalog **ids** (an alias such as `haiku`
  is refused), at every place the Hub asks which models a runner may use; a single run cannot
  change it.
- Spawn sets `COPILOT_PROVIDER_*` and `COPILOT_MODEL`. When the runner has no provider, any ambient
  `COPILOT_PROVIDER_*` in the Hub's environment is stripped, just as an ambient
  `ANTHROPIC_BASE_URL` is stripped for Claude (`launchability.py:190`).
- **Review fixes, 2026-09-28** (Opus review: C was REVISE): every `COPILOT_PROVIDER_*` name is
  stripped from both the Hub's environment and the agent's `env_vars` before exactly four are set;
  the checkpoint, handover and title one-shot spawns get the same provider environment and model
  rule as runs; the key is scrubbed by its exact value from every recorded event, permission card
  and failure text of its run; the Runners page offers only the provider's model ids. The
  no-provider strip (and `COPILOT_ALLOW_ALL`'s) is asked of slice 2 and is not cut with C.
- **API keys only. A Claude Max subscription cannot back this** (DECISIONS `ghcp-d4`): Copilot's BYOK
  takes an API key, and a Max plan signs in by OAuth. Runner management says so.
- One nullable column on `runners` needs a migration.

### Group B: Copilot's review agents help a Copilot reviewer

- A per-agent setting names which of Copilot's built-in review agents (`code-review`,
  `security-review`, `rubber-duck`) a Copilot agent consults on its **review turns**.
- The review turn context names those agents, the commit range to hand them, and that the verdict
  stays the reviewer's to record with `update_task`.
- **A flow step does not name a Copilot agent.** Flows keep naming AgentWeave agents by the one
  reviewer resolution they already use (`agent-flows`, *"never a second one"*). The setting belongs
  to the reviewer.
- `research` and `/review` as a whole-turn slash prompt are excluded. `research` can only be started
  by a slash command, and a slash command must be the entire prompt, which conflicts with the Hub's
  turn notices.

### Group D (optional, lowest value): the GitHub MCP server, per agent

- Off by default: slice 2 already spawns with `--disable-builtin-mcps`.
- An operator toggle per Copilot agent omits the flag.
- Because that server acts on GitHub **as the operator**, a call to it under the `workspace` posture
  goes to the operator as an ask-me card. R2: `_decide` *would* auto-approve it (a GitHub call names
  no path and no command), so the rule is decided before `_decide` is consulted. A server that
  fails to start while enabled is reported in the run's stream. (Review fixes, 2026-09-28: while the
  toggle is on, a call to **any** reported server other than `agentweave` asks, under its own name;
  a call whose server Copilot did not report is refused by slice 2, DECIDED.)
- Group D is optional: it is the group the operator should cut first if something must go.

## Capabilities

- **agent-stream-events**: ADDED *A Copilot run's compaction, errors and subagents reach its stream* (A).
- **conversation-checkpoint**: ADDED *A compaction the runner performed counts as reaching the threshold* (A).
- **agent-run-sandboxing**: ADDED *No Copilot hook decides a call or a turn* (A).
- **runner-registry**: ADDED *A Copilot runner may reach its model with the operator's own API key* (C).
- **agent-flows**: ADDED *A Copilot reviewer may be told to consult Copilot's review agents* (B).
- **agent-configuration**: ADDED *Copilot's built-in GitHub server is off unless the operator enables it for that agent* (D).

## Impact

- **Group A:**
  - Hub backend only. `status_event` and `error_event` gain facts in `hub/hub/runner_events.py`, and
    slice 2's `diagnostic_event` is used with a `stream` (R3: slice 2's parameter names).
  - Copilot event mapping in slice 2's `copilot_acp.CopilotEventMapper` (R3: not an adapter
    `map_events`, which is a stream-transport member).
  - A new `consider_from_compaction` in `hub/hub/checkpoint_trigger.py`, reusing `consider`.
  - The checkpoint trigger stays `context_pressure`. `CHECKPOINT_TRIGGERS` is guarded by migration
    `0044` (`db/models.py:1646-1653`), and the UI's offer reads that value
    (`AgentOutputPanel.tsx:619`). So there is **no migration and no UI change**.
- **Group C:**
  - A migration adding `runners.provider_config`.
  - Changes to `schemas/runners.py`, `api/v1/runners.py`, `resolve_agent_env` / the Copilot
    `guard_env`, the adapter's `launchability`, every launchability call site, and the per-run model
    override check.
  - The Runners page (UI bundle refresh; it reaches `:8000` on reload).
- **Group B:** `api/v1/agents.py` (the review section of the context, `ROSTER_CONFIG_KEYS`),
  `review_turn.py` (`ReviewContext.base_sha`), and the agent Settings page (UI).
- **Group D:** slice 2's `copilot_acp.build_acp_argv` and `decide_permission`, its event mapper,
  `ROSTER_CONFIG_KEYS`, and the agent Settings page (UI).
- **No change is planned to `hub/hub/mcp_server.py`.** R2 confirmed slice 2 maps Copilot's
  `request_permission` onto `_decide` from `copilot_acp.decide_permission`, in the Hub process
  (design D9).
- **R2, 2026-09-28:** slices 1–4 are unbuilt at master `ef55e6f`, and only 5 of the night's 28
  changes have landed.
- **R3, 2026-09-28:** the same at `fc33ff9`. Design's *Required of slices 1–4* replaces R2's table:
  what this change needs from each slice, in that slice's names.
