# Design — a Copilot agent uses hooks and its own agents

Slice 5 of `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`. It is written against
master `97b86ed` (2026-09-27), **before** the 28-change night queue and slices 1 to 4 land.

Every `file:line` below was read on 2026-09-27. Where an open change touches the same site, that
change is named and marked **re-verify in R2**.

## Context

Slices 1 to 4 give Copilot parity:

- **Slice 1:** the seam.
- **Slice 2:** Copilot over ACP. This includes the raw-event subscription
  `clientCapabilities._meta["github.com/copilot"].events` and the Hub-owned `COPILOT_HOME` per agent.
- **Slice 3:** the no-MCP shim.
- **Slice 4:** credits and holds.

This slice takes what Copilot offers beyond parity. It is split into four groups (A, C, B, D, in
order of value), each with its own requirements, tests and drive. The operator can reject any of
them independently. No group reads another group's state.

## What is known about Copilot, and how

| Claim | Tag | Source |
|---|---|---|
| Raw event types `session.compaction_start`, `session.compaction_complete`, `session.error`, `subagent.started`, `subagent.completed`, `subagent.failed`, `hook.start`, `hook.end` exist, with the field sets quoted in D1 | **VERIFIED** (schema file) | `%LOCALAPPDATA%\copilot\pkg\win32-x64\1.0.88\schemas\session-events.schema.json`, `definitions.CompactionCompleteData`, `ErrorData`, `Subagent*Data`, read 2026-09-27 |
| Those types are *delivered* over ACP `github.com/copilot/sessionEvent` when subscribed | **INFERRED**. Delivery was observed for `assistant.usage`, `session.usage_checkpoint`, `session.mcp_servers_loaded`, `hook.*` and `permission.*` (appendix A §A, `acp4.log`), not for these types | Task 1.1 captures real ones |
| A `permissionRequest` hook answering `allow` short-circuits ACP `session/request_permission` (`resolvedByHook:true`) | **VERIFIED** | appendix A §C, `acp4.log` |
| `preToolUse` command hooks fail **open** on timeout; `preCompact` is notification-only; `agentStop` `decision:"block"` forces another turn (cap 8) | **DOCUMENTED** | `hooks-reference` lines 237, 428, 659-674, 817 (scratch copy `ghcp/docs/hooks-reference.md`) |
| `http` hooks: `http://localhost` only with `COPILOT_HOOK_ALLOW_LOCALHOST=1`; `preToolUse`/`permissionRequest` must be `https`; `allowedEnvVars` header expansion forces `https` | **DOCUMENTED** | `hooks-reference` lines 167, 189, 194 |
| Repo hooks (`.github/hooks`, `.claude/settings.json`) load only in a trusted folder; `$COPILOT_HOME/hooks` loads everywhere; `COPILOT_ALLOW_ALL=true` trusts the cwd | **VERIFIED** (untrusted: "No hooks loaded") + **DOCUMENTED** | appendix A §C |
| Built-in agents `code-review`, `security-review`, `rubber-duck`, `explore` can be run by the main agent as subagents; `research` only by `/research` | **DOCUMENTED** | `about-custom-agents.md:61-75`; `ref.md:1186-1198` |
| A slash command over ACP must be the whole prompt ("a single text content block") | **DOCUMENTED** | `acp-server.md:184` |
| Built-in `code-review` does not receive repository instructions | **DOCUMENTED** | `ref.md:1244-1249` |
| BYOK: `COPILOT_PROVIDER_BASE_URL` activates it; `COPILOT_PROVIDER_TYPE` `openai`/`azure`/`anthropic`; `COPILOT_PROVIDER_API_KEY`; `COPILOT_MODEL` is required; no GitHub login needed | **DOCUMENTED** | `copilot help providers` (scratch `ghcp/help-providers.txt`) |
| BYOK works under ACP | **DOCUMENTED** (appendix A §H), not exercised | Task 6.3 |
| `--disable-builtin-mcps` is honoured under ACP (`github-mcp-server (disabled, builtin)`) | **VERIFIED** | appendix A §A spawn-flag table |
| The built-in GitHub server authenticates as the logged-in Copilot user | **INFERRED** | It is first-party and has no separate token; R2 checks `copilot help` |

## D1 — The facts come from raw events, not hooks

**Decision.** Compaction, errors and subagent lifecycle reach the Hub from the raw session events
that slice 2's ACP client subscribes to. This change adds six types to that subscription:
`session.compaction_complete`, `session.error`, `subagent.started`, `subagent.completed`,
`subagent.failed` and `session.compaction_start`. `session.compaction_start` is subscribed for the
drive's evidence only and maps to nothing.

**Why.** For each fact the raw event is a superset of the hook payload (proposal table, VERIFIED from
the schema):

- **Compaction.** `CompactionCompleteData` has `success`, `preCompactionTokens`,
  `postCompactionTokens`, `tokenLimit`, `trigger`, `summaryContent`, `checkpointPath`. `preCompact`
  has `trigger`, `customInstructions`, `transcriptPath`, and cannot block. The hook fires *before*
  compaction, so it also cannot tell a compaction that failed (`success:false`) from one that
  replaced the context. Only the `complete` event can.
- **Errors.** `ErrorData.errorType` names `quota`, `rate_limit` and `authentication`, and carries
  `statusCode` and `remediation`. `errorOccurred` has none of these.
- **Subagents.** `SubagentCompletedData` has `model`, `totalTokens`, `durationMs`, `totalToolCalls`.
  The hooks have the response text only.

Beyond the payloads:

- The events arrive on the connection the Hub already reads, stamped with `sessionId`. A hook's
  process would have to find the run itself.
- They need no second process per event, and no run token written into a hook file. Slice 2 writes
  hook files at agent **creation** (D2 of the operator), while run tokens are minted **per run**
  (`hub/hub/agent_auth.py`).
- On a company machine, `allowManagedHooksOnly` switches user hooks off. The raw events are part of
  ACP, which the fire test needs anyway.

**Cost.** Raw-event delivery is changelog-documented (`changelog.json` 1.0.81, *"raw event
subscriptions"*), not in the ACP docs page. Slice 2 already depends on it for usage. The limits are
256 in flight and 32 KB per event. `summaryContent` can exceed 32 KB and arrive as
`dataOmitted:"too-large"`, so the mapper never depends on it (D4).

## D2 — The Hub installs no hook; the transport question if the operator overrules

**Decision.** This change writes **no** hook file into the agent's `COPILOT_HOME/hooks/`. D1 leaves
no fact that a hook carries better. Of the hook capabilities that raw events lack, R1 found only
these, and each is excluded:

- `permissionRequest` / `preToolUse` decisions: excluded by D3.
- `agentStop` / `subagentStop` `block`: excluded by D3.
- `postToolUse.additionalContext` and `notification.additionalContext` inject text as a user message.
  That is a second input channel beside the durable inbound queue (`hub/hub/inbound_queue.py`), and
  input it carries would never be recorded as an inbound queue entry.
- `subagentStart.additionalContext` prepends to a subagent's prompt. That could carry group B's
  commit range, but the hook file is static and the range is per turn. The review context (D8)
  already hands the range to the main agent, which writes the subagent's prompt.

**Operator question (not answered by D1–D6).** `ghcp-d2-native-files` lists hooks among the Copilot
files the Hub writes. R1 recommends writing none, for the reasons above. The operator confirms, or
names the hook and what it is for.

**If the operator overrules:** use a `type:"command"` hook with `exec` = the Python the Hub runs
under, and `args` = [the pinned tool-server script (`hub/hub/tool_server.py`), its hook call mode,
the event name]. That is the shim call mode of `a-run-reaches-the-hub-without-mcp`. It reads
`AW_RUN_TOKEN` and `HUB_URL` from the environment it inherits from `copilot.exe` and posts to an
agent-actions route. **Not `type:"http"`**, for four reasons:

1. `http://localhost` needs `COPILOT_HOOK_ALLOW_LOCALHOST=1` in the CLI's environment.
2. The run token cannot reach the request. `allowedEnvVars` header expansion forces `https`, and a
   literal `Authorization` header would put a token on disk in a file written before the run exists.
3. `preToolUse`/`permissionRequest` http hooks must be `https` anyway.
4. An http failure is silent (fail-open, logged by the CLI only).

`exec` also sidesteps PowerShell quoting, since the shell tool on Windows is `powershell`
(appendix A §G).

## D3 — What no Hub hook may do, and no trusted folder

**Decision.** This is a requirement (`agent-run-sandboxing`), not only a design note, because each
item is a trap a later change could walk into.

- **No `permissionRequest` hook while the Hub answers approvals over ACP.** Its `allow`
  short-circuits `session/request_permission`: no request reaches the client (VERIFIED). A hook
  decision would bypass three things:
  - `_decide` and its shell/path judge (`hub/hub/mcp_server.py:1103-1592`);
  - the operator's ask-me cards (`hub/hub/api/v1/permissions.py`);
  - the decision record (`POST /permission-decisions`, `agent_actions.py:971`, which
    `a-run-records-that-its-calls-were-allowed` extends; **re-verify in R2**).

  A deny from a hook would also be invisible to the operator.
- **No `preToolUse` decision.** A command hook that times out fails **open** (documented). A control
  that lets a call through when it is slow is not a denial control. It would also duplicate
  `request_permission`.
- **No `agentStop` / `subagentStop` `block`.** Forcing another turn when the agent stopped is the
  backstop CLAUDE.md forbids: *"a turn that ends without calling it has ended … must not be
  reintroduced."*
- **No trusted folder.** The Hub must not set `COPILOT_ALLOW_ALL=true` in the run environment, nor
  write `trusted_folders` into the agent's `COPILOT_HOME` config.
  - A trusted cwd loads the repository's hooks, **including `.claude/settings.json` hooks**
    (appendix A §C).
  - In a repository like this one, those are Claude Code's hooks, written for Claude's payloads. They
    would run inside a Copilot run.
  - Folder trust also loads workspace `.mcp.json` servers.
  - Slice 2 maps full access onto the ACP `allow_all` config option, not onto this variable.
    Whether `allow_all` also trusts the folder is **INFERRED no**, and is R2 question 3.

## D4 — A compaction counts as the threshold being crossed

**Where it enters.** The funnel is `output_recording.record_agent_output`
(`hub/hub/output_recording.py:22-35`). It already resolves the conversation from `run_id` and then
`session_id` (`:36-54`). This mirrors how `record_context_usage` dispatches `consider_from_reading`
(`:233-238`). When a recorded event has `kind == "status"` and `payload.phase == "compacted"`,
`record_agent_output` dispatches a new `checkpoint_trigger.consider_from_compaction(project_id,
agent, conversation_id, payload)`.

- It is fire-and-forget, with the `_in_flight` / `_dispatched` discipline of
  `consider_from_reading` (`checkpoint_trigger.py:365-410`).
- The entry is runner-agnostic. Only Copilot emits the phase today. Claude's stream-json
  `compact_boundary` is R2 question 5.

**The event.** Copilot's `session.compaction_complete` with `success: true` maps to
`status_event("compacted", summary=…)`. Its payload carries:

- `pre_tokens` / `post_tokens` / `token_limit` (from `preCompactionTokens` / `postCompactionTokens` /
  `tokenLimit`);
- `trigger` (`auto` / `manual`);
- `percent = round(pre_tokens / token_limit * 100, 2)`, only when both are present.

`success: false` maps to a `diagnostic` event (D5), not to `compacted`, because the context was not
replaced. `summaryContent` is **not** copied: it can be `dataOmitted` (D1), and it is Copilot's
summary, which the Hub does not endorse by storing.

**What it drives.** `consider(..., compacted=True)` reuses every gate of `consider`
(`checkpoint_trigger.py:156-362`) except the threshold itself:

| Situation | Today's `consider` from a reading | With `compacted=True` |
|---|---|---|
| mode `off` (`resolve_policy`, `checkpoint_policy.py:79-108`) | declined | declined. The stream still shows the compaction |
| conversation missing or not open | declined | declined |
| `offered`, warning `dismissed`/`final` | final-warning backstop at ≥92% (`:192-234`) | **declined, no warning.** The final warning exists to come *before* the loss; after it, the stream event is the notice |
| already handed over (`:239-252`) | declined | declined |
| notes band (`should_request_notes`, `:254-268`) | notes requested | **skipped.** Notes written after compaction are written from Copilot's summary |
| below threshold (`should_checkpoint`, `:270-276`) | declined | **not consulted.** The threshold exists to act before the CLI compacts, and it has |
| nothing new since the last checkpoint (`:277-279`) | declined | declined |
| `offered` | warning `due`, no generation (`:281-309`) | the same. The `checkpoint_due` payload gains `"compacted": true`. **Warn before spend still holds** |
| `automatic` | generate (`trigger="context_pressure"`) and `cut_over` (`:311-362`) | the same |

**Why `context_pressure` and not a new trigger value.** `CHECKPOINT_TRIGGERS` is guarded by a check
constraint from migration `0044` (`db/models.py:1646-1653`). The UI offers a ready checkpoint only
when `trigger === 'context_pressure'` (`hub/ui/src/components/agents/AgentOutputPanel.tsx:618-620`).
A new value would cost a migration and would hide the offer. A compaction *is* context pressure.

**Why not only lower the threshold.** Slice 4 (`a-copilot-run-shows-its-credits`) gives Copilot
per-runner thresholds, so readings cross before Copilot's ~80%. That handles the common case. This
path is the backstop for the cases it cannot handle:

- a token-mode threshold set above the point where Copilot compacts;
- a manual `/compact`;
- an auto-compaction that lands between two `usage_update` readings.

The two do not collide. After a threshold-driven checkpoint, `_nothing_new_since_last_checkpoint`
declines the compaction's attempt until another run happens.

**Open change touching this site:** `every-event-the-hub-sends-reaches-the-app` changes SSE events
from this module (`checkpoint_due` delivery). **Re-verify in R2** that the added `compacted` field
survives.

## D5 — Errors become diagnostic events, recorded once

**The builder.** `runner_events.py` declares the `diagnostic` kind (`:10-11`,
`schemas/agents.py:19`) but has no builder: `status_event` is at `:221` and `error_event` at `:231`.
Add `diagnostic_event(*, code, message, severity, facts)`. Its payload is
`{version, code, message, severity, facts}`, bounded like `error_event`, with `facts` passed through
`redact_secrets`. The timeline already styles `diagnostic` output
(`hub/ui/src/components/agents/AgentTimeline.tsx:808`).

**The mapping.** `session.error` maps to `diagnostic_event(code="copilot." + errorType,
message=message, severity="error", facts={status_code, remediation, error_code})`. `stack`,
`providerCallId` and `serviceRequestId` are dropped.

- `errorType` `quota`/`rate_limit` is still recorded as a diagnostic. The allowance hold is slice 4's
  and is not duplicated here.
- `session.compaction_complete` with `success:false` maps to
  `diagnostic_event(code="copilot.compaction_failed", severity="warning")`.

**The echo.** Copilot also turns `session.error` into an ACP `agent_message_chunk` whose text starts
`Error:` (appendix A §A). Slice 2's mapper classifies those prefixes. **One fact, one record:**

- when the raw `session.error` arrives, the mapper suppresses an `Error:` text chunk with the same
  message text within the same prompt turn, **in either arrival order**;
- when no raw event arrives (the subscription was dropped), the text classification stands.

**Which order is real is unknown**, and CLAUDE.md requires the test to use the real one. Task 1.1
captures it, and task 1.3 tests both orders so that reversing them is caught.

**Open change:** `a-file-path-is-not-redacted-as-a-credential` edits `redact_secrets`
(`runner_events.py:53-82`). **Re-verify in R2.**

## D6 — Subagents in the timeline

`subagent.started` maps to `status_event("subagent_started", summary=f"{agentDisplayName} started")`.
`subagent.completed` and `subagent.failed` map to `status_event("subagent_completed" |
"subagent_failed")`.

- The payload carries `call_id` = `toolCallId`, `agent_name`, `model`, `total_tokens`,
  `duration_ms`, `total_tool_calls`, and `error` (redacted) for failures.
- `call_id` pairs them with the parent `task` tool call that slice 2's mapper already emits as
  `tool_use`.
- The built-in `general-purpose` agent emits no subagent events (hooks-reference line 526;
  **INFERRED** to hold for raw events too). A `task` call without a pair is therefore normal, and no
  test treats it as an error.

Token and cost accounting of subagents is slice 4's. These events are presentation and diagnosis
only.

## D7 — BYOK: the provider on the runner, the key in the Hub's environment

**Where it is stored.** A new nullable JSON column `runners.provider_config` holds
`{type, base_url, api_key_var}`.

- **Not `runners.flags`.** `flags` is `List[str]`, a list of CLI arguments (`schemas/runners.py:17,30,39`;
  consumed as argv at `api/v1/agent_trigger.py:1209`).
- **Not the agent's `config.env_vars`,** where `claude_proxy` keeps `ANTHROPIC_API_KEY_VAR`
  (`launchability.py:101-114`). A BYOK runner's model *is* the provider's model. Keeping the provider
  on the agent and the model on the runner would split one fact across two records, and two agents
  bound to one runner could reach its model through different providers.
- The migration follows `.claude/rules/db-migrations.md`: guard a missing table, and bump the heads in
  `test_migrations.py` and `test_project_persistence.py`. It comes **after** slice 2's migration,
  which widens `ck_runners_cli` (`db/models.py:340`).

**Validation** (`schemas/runners.py` and `api/v1/runners.py`):

- Only `cli == "copilot"` may carry `provider_config`.
- `type` must be `anthropic` or `openai`.
- `api_key_var` must match `^[A-Z_][A-Z0-9_]*$`. A value that is not an environment variable *name*
  is refused **before** it is stored, with a sentence saying to put the key in the Hub's environment
  and name the variable. This is what stops a pasted key from reaching the database.
- `base_url` defaults to `https://api.anthropic.com` / `https://api.openai.com/v1` and must be an
  `https://` URL or `http://localhost…`.
- The model must be set, since BYOK requires one. It is validated by the existing *"A runner's model
  is drawn from the catalog"* rule against the catalog provider the `type` names: `anthropic` → the
  `claude` catalog's model ids (`model_catalog.py:163-196`, real API ids such as
  `claude-haiku-4-5-20251001`); `openai` → the `codex` catalog's ids. That rule reads the adapter
  member `catalog_provider`.
- Open changes touching the catalog: `the-codex-models-offered-are-the-ones-its-cli-lists` and
  `a-model-alias-is-a-model-choice`. An alias (`haiku`) is not an API id and is refused for BYOK.
  **Re-verify in R2.**

**Azure is deferred.** An Azure model is a deployment name the catalog cannot declare
(`COPILOT_PROVIDER_WIRE_MODEL`), which conflicts with the catalog rule. This is an operator question.

**Spawn.** The adapter's `build_launch` for a runner with `provider_config` sets:

- `COPILOT_PROVIDER_TYPE` and `COPILOT_PROVIDER_BASE_URL`;
- `COPILOT_PROVIDER_API_KEY` = `os.environ[api_key_var]`, resolved at spawn as `resolve_agent_env`
  does (`launchability.py:162-169`);
- `COPILOT_MODEL` = `runner.model`.

For a `copilot` runner **without** `provider_config`, it **strips** every ambient `COPILOT_PROVIDER_*`,
`COPILOT_MODEL` and `COPILOT_OFFLINE` from the child environment. That mirrors the ambient
`ANTHROPIC_BASE_URL` strip (`launchability.py:190-194`): an operator's shell must not silently turn
a subscription runner into a BYOK one.

The key **must not** be forwarded into the MCP server's `env` in `--additional-mcp-config`, which
slice 2 builds as an explicit allow-list (compare Codex's list at `runner_commands.py:317-329`).
**Re-verify in R2** against slice 2.

**Launchability** (adapter member `launchability`): a BYOK runner is authorized iff `api_key_var` is
set and non-empty in the Hub's environment. The reason names the variable, not its value, following
`claude_proxy` (`launchability.py:108-114`). A GitHub login is not required.

**Where the key could leak, and why it does not:**

- It is in no database row.
- The runners API returns `api_key_var`, which is a name.
- `ROSTER_CONFIG_KEYS` (`api/v1/agents.py:651`) is agent config and unaffected.
- Stream text passes `redact_secrets` (`runner_events.py:53-56`). `sk-ant-…` and `sk-…` are caught by
  the `sk-` word-start rule; a 32-character hex Azure key by the high-entropy class.
- Stderr summaries are "secret-safe" per `runtime-diagnostics`.

A test asserts the key value appears in none of the runner response, the agent context file, or a
recorded run event.

**Plainly: a Claude Max subscription cannot back this.** Copilot's BYOK takes an API key. A Max plan
authenticates Claude Code and claude.ai by OAuth, and routing it through another harness is not a
supported use (DECISIONS `ghcp-d4`). Runner management states this beside the key field.

**Accounting note for slice 4.** Under BYOK the provider bills tokens, and Copilot's AI credits
probably read 0 (**INFERRED**). D3 already makes tokens the unit. Slice 4 should not present 0
credits as "free" (R2 question 6).

## D8 — A Copilot reviewer consults Copilot's review agents

**The setting.** Agent `config.copilot_review_agents` is a list drawn from `code-review`,
`security-review` and `rubber-duck`, empty by default. It is stored in `Agent.config` (an open JSON
object, `api/v1/agents.py:630-644` merge-patch), so no migration is needed. The PATCH route refuses
unknown names. The UI presents it only for an agent bound to a `copilot` runner (*"A setting with no
backing state is not presented"*).

**The effect.** In the review section of the rendered context (`api/v1/agents.py:1720-1785`), after
the verdict line, and only when `review is not None` and the agent's runner is `copilot` and the list
is non-empty, add one bullet:

> Before your verdict, run Copilot's `code-review` (and `security-review`) agent as a subagent on the
> changes from `<base>` to `<commit>`. Weigh what it reports and check it yourself. It does not see
> this repository's instructions, and its findings are not your verdict. The verdict is yours, and
> it is recorded only by `update_task`.

`<base>` is `git merge-base <commit> <the branch approval merges into>`, computed in
`prepare_review_turn` (`review_turn.py:240-293`) and carried on `ReviewContext`. When it cannot be
computed, the bullet names `<commit>` alone and says to review that commit's own changes.

`a-flow-stages-its-review-in-the-dispatch` and
`a-claude-run-is-told-its-agentweave-tools-by-their-full-names` both edit this module and this
section. **Re-verify in R2.**

**Why not a flow step naming a Copilot agent.** A flow's reviewer is an AgentWeave agent, resolved
*"by the same resolution the rest of the product already uses for a declared reviewer, never a second
one"* (`agent-flows`, *A flow resolves a reviewer by declaration, then by availability*).
`code-review` is not on the roster, cannot hold a run token and cannot call `update_task`. Making it
a reviewer would need a second resolution, and a verdict nobody could record. Built-ins are tools a
reviewer uses. They are not reviewers.

**Why not `/review` or `/research`.**

- A slash command over ACP must be the whole prompt (`acp-server.md:184`), and the Hub prepends turn
  notices to every prompt (`agent_trigger.py:1170-1193`).
- `/review` would also end with the code-review agent's report, not with an AgentWeave verdict.
- `research` cannot be started by the main agent at all (`about-custom-agents.md:71`).

**Cost.** Built-ins default to `claude-sonnet-4.6` (`ref.md:1190-1195`). On Free, subagents follow
Auto. Each consult is at least one extra model call, so the setting is off by default.

## D9 — The built-in GitHub MCP server as a per-agent toggle

- **The setting.** Agent `config.copilot_github_mcp` is a boolean, default false. It is read by the
  adapter's `build_launch`, which omits `--disable-builtin-mcps` when it is true (slice 2 adds that
  flag).
- **The decision.** A permission request for the `github-mcp-server` is an MCP-kind request. Under
  `workspace`, the Copilot approval mapping (slice 2, adapter `decide_posture` / the `_decide` call)
  answers it with the ask-me outcome, never `allow`.
  - The server acts on GitHub as the operator's login (**INFERRED**). That is outside the workspace
    `_decide` judges, so `_decide` has no ground to allow it.
  - Under full access (`allow_all`) it is allowed as everything else is.
  - Under `manual` it goes to the operator anyway.
  - Where slice 2 puts this mapping (inside `mcp_server.py`'s `_decide`, or in the adapter) decides
    whether `.claude/rules/mcp-server.md`'s import restriction applies. **R2 re-verifies against
    slice 2.**
- **BYOK interplay.** A BYOK agent has no GitHub login requirement. With the toggle on and no login,
  the server fails to start. The raw `session.mcp_servers_loaded` status then shows it failed, and
  slice 3's MCP status handling surfaces it. This change adds no second report.

## D10 — Independence of the groups

- **A** touches `runner_events.py`, `checkpoint_trigger.py`, `output_recording.py` and the Copilot
  mapper.
- **C** touches runners (schema, route, migration, UI) and the adapter's `build_launch` /
  `launchability`.
- **B** touches the context renderer, `review_turn.py`, and the agent Settings UI.
- **D** touches the adapter's `build_launch` / `decide_posture` and the agent Settings UI.

B and D share one UI section. Each adds its own control, so rejecting one leaves the other's control
standing. No group's test imports another group's code.

## Round log

- **R1, 2026-09-27** (Opus, one pass).
  - **Read:** the exploration and appendices A/B/C; DECISIONS `ghcp-d1`..`d6`;
    `the-approval-transport-is-not-the-tool-surface`; CLAUDE.md; `.claude/rules/{mcp-server,hub-ui,db-migrations}.md`;
    DEAD-ENDS 2026-09-27 entries.
  - **Code, at master `97b86ed`:** `checkpoint_policy.py` (all), `checkpoint_trigger.py` (all),
    `output_recording.py:22-60,150-238`, `runner_events.py:1-60,130-260`, `review_turn.py` (all),
    `api/v1/agents.py:640-700,900-930,1715-1800`, `launchability.py:90-196`,
    `db/models.py:314-342,1410-1425,1640-1660`, `schemas/runners.py` (grep), `model_catalog.py`
    (grep), `AgentOutputPanel.tsx:605-630`, `AgentTimeline.tsx:795-830`.
  - **Specs:** `runtime-diagnostics` (Structured diagnostic events; A runtime that dies…),
    `agent-flows` (review requirements), `conversation-checkpoint` (threshold and warning
    requirements), `runner-registry`.
  - **Copilot (no model call):** the 1.0.88 package's `schemas/session-events.schema.json`, parsed for
    the six event definitions; `app.js` grep for event names; scratch docs `hooks-reference.md`,
    `about-custom-agents.md`, `acp-server.md`, `ref.md`, `help-providers.txt`. No ACP probe was run;
    none was needed for what is claimed.
  - **Found:** raw events supersede hooks for every fact asked (D1), which reframes group A. Also a
    new trap: folder trust would load the repo's Claude hooks (D3).

## Open questions for R2/R3

1. **Slice 2 alignment.** What does slice 2's raw-event subscription list contain? Where does its
   mapper classify `Error:` chunks? Where does Copilot's `request_permission` meet `_decide`
   (D5, D9)?
2. **Delivery.** Are the six types actually delivered over ACP (**INFERRED**)? Task 1.1 settles it.
   If not, group A's source falls back to D2's hook transport, and the operator is told.
3. **Folder trust.** Does ACP `allow_all: on` trust the folder (and so load repo hooks)? Read
   `app.js` around `allow_all` and `trusted_folders` (D3).
4. **`ReviewContext` and the merge target.** Does `ReviewContext` already know the merge target?
   `task_integration` resolves "the branch approval merges into". Find the helper (D8).
5. **Claude compactions.** Claude's stream-json `compact_boundary`: should `runner_parsing.py` emit
   `status("compacted")` too, so Claude gets D4's backstop? It is out of scope here; file it if
   useful.
6. **BYOK credits.** Under BYOK, what does `session.usage_checkpoint.totalNanoAiu` read? This affects
   slice 4's display, not this change.
7. **Built-ins on a detached HEAD.** Does `code-review` accept an explicit `<base>..<commit>` range
   when HEAD is detached with a clean tree? This is documented as "branch diffs", so it is
   **INFERRED**. Drive task 7.2 checks it.
8. **Operator questions:**
   - D2: are any hooks still wanted?
   - D7: is Azure BYOK deferred?
   - D7: will the operator put an API key in the trial Hub's environment for the BYOK happy-path
     drive? It spends real money, a few cents on Haiku.
