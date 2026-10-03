# Design — a Copilot agent uses hooks and its own agents

Slice 5 of `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`. It is written against
master `97b86ed` (2026-09-27), **before** the 28-change night queue and slices 1 to 4 land.

Every `file:line` below was read on 2026-09-27. Where an open change touches the same site, that
change is named and marked **re-verify in R2**.

**R2 (2026-09-28) re-read every cited site at master `ef55e6f`.** Only 5 of the night's 28 changes
have landed, and **slices 1–4 are all unbuilt**. Of the files cited here, only `model_catalog.py`
(`63d9f34`, `3b3563a`) and `api/v1/agents.py` (+4 lines at `:707`) moved. Line numbers below are
`ef55e6f`'s where R2 corrected them. Every dependency on an unbuilt slice is marked **(rebase at
IMPL: <change> unbuilt at R2)**, and the section *Required of slices 1–4* (rewritten in R3) says,
in their own names, what this change needs from each.

**R3 (2026-09-28) re-derived every decision at master `fc33ff9`** (no product code moved since
`ef55e6f`; `fc33ff9` only edits the five slices' change folders). Slices 1–4 are still unbuilt.
R3's corrections are marked **R3** in place; the Round log lists them.

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
| Those types are *delivered* over ACP `github.com/copilot/sessionEvent` when subscribed | **INFERRED**. Delivery was observed for `assistant.usage`, `session.usage_checkpoint`, `session.mcp_servers_loaded`, `hook.*` and `permission.*` (appendix A §A, `acp4.log`), not for these types. R3: the forwarding is type-agnostic (next rows), so what remains open is only whether an ACP session *emits* them. Slice 3 measured no `session.mcp_servers_loaded` within a prompt-less window although it was subscribed (its D9) | Task 1.1 captures real ones |
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
| The built-in GitHub server authenticates as the logged-in Copilot user | **INFERRED** | It is first-party and has no separate token. R2 did not settle it (no process spawned); the drive's card (7.8) shows it |
| `ErrorData` requires `errorType` and `message`; also `errorCode`, `statusCode`, `remediation`, `eligibleForAutoSwitch`, `stack`, `providerCallId`, `serviceRequestId`, `url`. `errorType` is an **open string** ("e.g. authentication, authorization, quota, rate_limit, context_limit, query") | **VERIFIED** (schema, R2) | 1.0.88 `session-events.schema.json` |
| `CompactionCompleteData` requires only `success`; it also has `error`, `tokensRemoved`, `messagesRemoved`, `compactionTokensUsed`, `requestId`. `SubagentCompletedData` has `cancelled`; `SubagentFailedData` requires `error` | **VERIFIED** (schema, R2) | same file |
| Raw-event passthrough forwards every subscribed type the session emits (the only filter is the subscribed set, plus two `skill.context_delivered*` types). The envelope copies `agentId` when the event is a subagent's. When the serialized `data` exceeds 32 KB the **whole `data`** is replaced by `{omitted:"too-large", bytes, limit}` and the envelope gets `dataOmitted`, not only the long field. Beyond 256 notifications in flight, further ones are dropped | **VERIFIED-CODE** (R3) | 1.0.88 `app.js`: `bDn` (filter, `agentId` copy), `LDo` (whole-`data` omission, `Kre=32*1024`), `sendRawEventNotification` (in-flight drop) |
| For one session event, the raw notification is sent **before** its ACP `session/update`: `setupEventForwarding` calls `sendRawEventNotification` synchronously, then queues the update on `eventForwardingQueue` | **VERIFIED-CODE** (R3) | 1.0.88 `app.js`, `setupEventForwarding` |
| `session.error` becomes exactly one `agent_message_chunk` whose text is `` `Error: ${message}` `` | **VERIFIED-CODE** (R3) | 1.0.88 `app.js`, `mapEventToACPUpdate`, `case"session.error"` |
| Every event envelope in the schema has an optional `agentId`, *"absent for events from the root/main agent"*; a subagent's compaction emits `session.compaction_complete` with its `agentId` | **VERIFIED** (schema) + **VERIFIED-CODE** (R3) | `CompactionCompleteEvent.properties.agentId`; `app.js` passes `agentId` through for `session.compaction_complete` |
| `CompactionTrigger` is `threshold`, `context_limit_retry`, `manual`, `memory_pressure`, `model_switch` (not the hook's `auto`/`manual`). `CompactionStartData` carries `currentTokens` and `tokenLimit`, no summary. `RemediationAction` is a string enum (`sign_in`, `switch_account`, …). `McpServerStatus` is `connected`, `failed`, `needs-auth`, `pending`, `disabled`, `stopped`, `not_configured` | **VERIFIED** (schema, R3) | 1.0.88 `session-events.schema.json` |
| Under BYOK, ACP `session/new` needs no GitHub login: `hasSessionCredential(t){return t!==void 0\|\|this.options.providerContextId!==void 0}`, and the ACP server is constructed with `providerContextId` from the provider set-up | **VERIFIED-CODE** (R3; answers Open question 9) | 1.0.88 `app.js`, `newSession`, `hasSessionCredential`, the ACP server's constructor options |
| The ACP `allow_all` option does **not** trust the folder. It calls `session.permissions.setMode({mode:"allow-all"})` only. A session's workspace trust is `trustWorkingDirectory` (an SDK option the ACP path never sets) **or** `COPILOT_ALLOW_ALL==="true"` **or** `folderTrustIsTrusted(cwd, configDir)` | **VERIFIED-CODE** (R2) | 1.0.88 `app.js`: `async applyAllowAll(t,n)`, `resolveTrustDeclaration`, and the three `COPILOT_ALLOW_ALL==="true"\|\|await b.folderTrustIsTrusted(...)` sites that set `deferRepoHooks` |

## D1 — The facts come from raw events, not hooks

**Decision.** Compaction, errors and subagent lifecycle reach the Hub from the raw session events
that slice 2's ACP client subscribes to. This change needs six types in that subscription:
`session.compaction_complete`, `session.error`, `subagent.started`, `subagent.completed`,
`subagent.failed` and `session.compaction_start`. `session.compaction_start` emits no event of its own. **R3:** it is
the fallback for the counts when the `complete` event's `data` was omitted (D4, *Omitted data*).

**R2: most of the list is already someone else's.** Slice 2's D10 subscribes `session.error` itself
(for its `Error:` classification), and slice 4's D1 adds `session.compaction_complete` and
`session.error` for its usage ledger. So this change *ensures* the six are present, as a set union
onto slice 2's module constant, and genuinely adds only the three `subagent.*` types and
`session.compaction_start`. It never re-declares the list, so cutting slice 4 or this change leaves
the other's entries standing. **(IMPL pre-check, 2026-10-03: VERIFIED-CODE.
`COPILOT_RAW_EVENTS` (`copilot_acp.py:94-111`) already holds `session.error` and
`session.compaction_complete` from the now-archived slices 2 and 4.)**

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
- They need no second process per event, and no run token written into a hook file. A hook file
  would be written with the agent's `COPILOT_HOME`, at agent **creation** (operator decision
  `ghcp-d2`), while run tokens are minted **per run** (`hub/hub/agent_auth.py`). (R2: slice 2's D4
  as written writes only the agent file and `agentweave-mcp.json` into that home, and no hook
  file. R1's "slice 2 writes hook files" was wrong. Slice 1's D16 reserves a `hooks` member "for
  slice 5"; with D2 below, no slice adds it.)
- On a company machine, `allowManagedHooksOnly` switches user hooks off. The raw events are part of
  ACP, which the fire test needs anyway.

**Cost.** Raw-event delivery is changelog-documented (`changelog.json` 1.0.81, *"raw event
subscriptions"*), not in the ACP docs page. Slice 2 already depends on it for usage. The limits are
256 in flight and 32 KB per event. **R3: an oversized event loses its whole `data`, not one
field** (`LDo`, VERIFIED-CODE). A `session.compaction_complete` whose `summaryContent` pushes it past
32 KB therefore arrives with no `success` and no counts at all, which R1/R2's "never depend on
`summaryContent`" did not cover. D4 handles it.

**R3: only the root agent's events are the conversation's.** A subagent's compaction, error or
nested subagent carries `agentId` in the envelope (VERIFIED). A subagent compacting its own context
did not compact the conversation, so an event with `agentId` never maps to `compacted` (D4). The
mapper therefore needs the whole `sessionEvent` params (`agentId`, `dataOmitted`), not only
`{type, data}` (*Required of slices 1–4*).

## D2 — The Hub installs no hook (DECIDED 2026-09-28: none)

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

**Operator decision, 2026-09-28: no hooks ("yes" to the review's recommended answer, Open
question 8).** `ghcp-d2-native-files` listed hooks among the Copilot files the Hub writes; the
operator decided none are wanted. Every fact a hook carries arrives richer in a raw event (D1);
every deciding hook is barred by D3; `additionalContext` would open a second input channel beside
the inbound queue. Revisit only if task 1.1 shows the raw event types are not emitted over ACP, and
even then **do not pre-build the fallback**: stop group A and bring the finding to the operator.
Nothing in this change's tasks, specs or test guide builds, installs or renders a hook.

**Not built — the overrule path, kept only as a record of what a revisit would cost.** R1–R3 wrote
it for the case the operator overruled; the operator did not, so none of it is implemented, and no
task builds it. It was: use a `type:"command"` hook with `exec` = the Python the Hub runs
under, and `args` = [the pinned `mcp_server.py` copy that `tool_server.py` maintains, `--call`, a
tool that receives the hook's payload]. That is the shim call mode of
`a-run-reaches-the-hub-without-mcp` (its D4: `mcp_server.py --call <tool>`, fastmcp not imported).
R2: that mode calls a registered `@mcp.tool()`, and **no tool that receives a hook payload
exists**, so this alternative also needs a new tool and route. R3: slice 3's call mode is also
closed over the MCP tools and **refuses stdin** (its open item 5), while a command hook receives its
payload on stdin. So the overrule path needs its own mode as well; slice 3 provides none, and this
change asks it for none. It reads `AW_RUN_TOKEN` and `HUB_URL`
from the environment it inherits from `copilot.exe`. (Consistency pass, 2026-09-28.) Two more
constraints on that path: the new tool is registered with slice 3's `@_tool()` decorator, as every
tool is once slice 3 lands (its D3, review note 12), so it joins the callable-set parity test; and
the hook file is written **through slice 2's `.agentweave-owned.json` recorder** (slice 2's
§ *Provided to slices 3–5* item 20), because slice 2's before-spawn sweep removes every hook,
setting, MCP config and agent file in the home that the Hub did not record there. **(IMPL
pre-check, 2026-10-03: moot, not wrong — `a-run-reaches-the-hub-without-mcp` is archived and its
`.agentweave-owned.json`/`@_tool()` machinery exists, but D2 was DECIDED "none" 2026-09-28 and no
task builds this overrule path, so nothing depends on it.)** **Not `type:"http"`**, for four
reasons:

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
    `a-run-records-that-its-calls-were-allowed` extends). R2: `:971` confirmed at `ef55e6f`; the
    argument holds whatever shape that change gives the record, because a hook-answered request
    never reaches any recorder. **(rebase at IMPL: `a-run-records-that-its-calls-were-allowed`
    unbuilt at R2.)**

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
    **R2 answered question 3 (VERIFIED-CODE, 1.0.88 `app.js`):** `allow_all` does not trust the
    folder. `applyAllowAll` only sets the session's permission mode to `allow-all`. Folder trust,
    which decides `deferRepoHooks`, is `trustWorkingDirectory` (an SDK session option the ACP path
    never sets), `COPILOT_ALLOW_ALL==="true"`, or `folderTrustIsTrusted(cwd, configDir)` (the
    config's trusted folders). So the two things this requirement forbids are exactly the two ways
    an ACP run's folder becomes trusted, and full access stays safe.
  - Slice 2's D4 writes no config file with trusted folders into the home, so test 1.6 is a guard
    against a later writer, not a fix. (Consistency pass, 2026-09-28.) Slice 2's D4 also sweeps the
    home before every spawn: hooks, `settings.json`, MCP configs, plugins and agent files it did not
    record in `.agentweave-owned.json` are removed, and `trustedFolders` is dropped from
    `config.json` (its § *Provided* item 20). **This change writes nothing into the home** (D2: no
    hook; D8: the review agents are Copilot's built-ins; D9: the GitHub server is a spawn flag; D7:
    BYOK is environment only), so nothing of this change's is swept. Any later write there,
    including D2's overrule path if it were ever built (it is not; operator decision 2026-09-28),
    goes through that recorder.
  - **Review fixes, 2026-09-28 (finding 6): "the Hub must not set" is not enough.** Nothing strips a
    `COPILOT_ALLOW_ALL` the Hub did not set. `resolve_agent_env` copies `os.environ` and merges the
    agent's `env_vars` (`launchability.py:157-179`), so an operator's shell or an agent's `env_vars`
    carrying `COPILOT_ALLOW_ALL=true` would trust the folder and load this repository's
    `.claude/settings.json` hooks and `.mcp.json` servers into the run. **Decided: slice 2 owns the
    strip**, for every Copilot spawn (its Copilot `guard_env` and `one_shot_env`), from both the
    ambient environment and `env_vars`, under every posture (*Required of slices 1–4*, 2.9; provided
    as slice 2's § *Provided to slices 3–5* item 18). It is not
    this change's code, so it cannot be cut with any group here. Test 1.6 sets it ambient and in
    `env_vars` and asserts it is absent; task 2.6 adds the strip only if slice 2 landed without it.

## D4 — A compaction counts as the threshold being crossed

**Where it enters.** The funnel is `output_recording.record_agent_output`
(`hub/hub/output_recording.py:22-35`). It already resolves the conversation from `run_id` and then
`session_id` (`:36-54`). This mirrors how `record_context_usage` dispatches `consider_from_reading`
(`:233-238`). When a recorded event has `kind == "status"` and `payload.phase == "compacted"`,
`record_agent_output` dispatches a new `checkpoint_trigger.consider_from_compaction(project_id,
agent, conversation_id, payload)`.

**R3: the test is `isinstance(payload, dict) and payload.get("phase") == "compacted"`.**
`POST /agents/{name}/output` accepts `kind: "status"` with `payload: null`
(`AgentOutputCreate.payload: Optional[Dict[str, Any]]`, `schemas/agents.py:323`). A bare
`payload.get(...)` would raise `AttributeError` *after* `db.commit()` (`output_recording.py:93`),
so the route would answer 500 for a stored row and a retry would store it twice. Test 1.5 posts
exactly that. The route is a compatibility self-report route, so a caller holding the project's key
can post a `compacted` status and prompt a consideration; `POST /agents/{name}/context-usage` with
`percent: 99` does the same today, so this adds no new authority.

- It is fire-and-forget, with the `_in_flight` / `_dispatched` discipline of
  `consider_from_reading` (`checkpoint_trigger.py:365-410`).
- **R2: a compaction is never dropped for being in flight.** `consider_from_reading` returns
  silently when the conversation is already in `_in_flight` (`:382-383`). For a reading that is
  harmless, because another reading follows within the turn. A compaction is a one-off event, and
  it lands exactly when readings are dense: Copilot sends a `usage_update` around every step, and
  one arrives just after the compaction with the reduced context. Dropping it would make the
  backstop fail precisely in the case it exists for. So when the conversation is in flight,
  `consider_from_compaction` stores the payload in `_compaction_pending[conversation_id]`, and the
  `finally` of every dispatched `_run` (reading or compaction) re-dispatches a pending compaction
  after discarding the in-flight mark. Two considerations of one conversation still never run
  concurrently, so `automatic` cannot generate twice. R3 re-derived it at `fc33ff9`: the early
  return is still `:382-383`, and `_run`'s `finally` (`:398-399`) is the only place the mark is
  discarded for a dispatched task, so that `finally` (in `consider_from_reading` too, not only in
  the new function) is where the pending compaction must be picked up. A copy of
  `consider_from_reading` alone would not see a compaction parked by a *reading's* task.
- **It never raises into its caller**, like `consider_from_reading`: a missing loop drops it (a
  test or synchronous caller), and every exception inside `_run` is logged. That matters for what
  the routes return: `record_agent_output` has committed the row before it dispatches, so a raise
  would make `POST /agents/{name}/output` answer 500 for a stored row (a retry would store it
  twice), and make the RPC executor's `_record_observation` log an output failure for an output
  that succeeded.
- The entry is runner-agnostic. Only Copilot emits the phase today. Claude's stream-json
  `compact_boundary` is R2 question 5 (carried: out of scope, see the Open questions).

**The event.** Copilot's `session.compaction_complete` with `success: true` maps to
`status_event("compacted", summary=…)`. Its payload carries:

- `pre_tokens` / `post_tokens` / `token_limit` (from `preCompactionTokens` / `postCompactionTokens` /
  `tokenLimit`);
- `trigger`, Copilot's own value. **R3:** that is the schema's `CompactionTrigger` (`threshold`,
  `context_limit_retry`, `manual`, `memory_pressure`, `model_switch`), not the `preCompact` hook's
  `auto`/`manual` that R1 copied. Only `manual` is a requested compaction; the summary says
  "requested" for it and "automatic" otherwise;
- `percent = round(pre_tokens / token_limit * 100, 2)`, only when both are present.

**Only the root agent's compaction (R3).** An event whose envelope carries `agentId` is a
subagent's (D1), and maps to nothing here: a subagent compacting its own context neither replaced
the conversation's context nor makes a checkpoint of the conversation due. Without this rule a
subagent's compaction would hand over the main conversation under `automatic`.

**Omitted data (R3).** When the event arrives with `dataOmitted == "too-large"`, its `data` holds no
`success` and no counts (D1). A failed compaction carries only `error` and small numbers, so an
oversized report is a report that carried a summary, which only a successful compaction has
(**INFERRED** from the schema's field descriptions). It maps to `compacted` with the counts taken
from the turn's latest root `session.compaction_start` (`currentTokens` → `pre_tokens`,
`tokenLimit` → `token_limit`) when one arrived, `post_tokens` absent, and the summary *"Copilot
compacted this conversation; its report was too large to relay."* `dataOmitted == "unserializable"`
maps to the D5 diagnostic `copilot.compaction_unreadable` and does not count. A mapper that required
`data.success is True` would silently drop exactly the large compactions this backstop exists for;
test 1.2 feeds a `too-large` envelope.

**R2: `status_event` cannot carry these today, and the obvious way to add them destroys them.**
`status_event(phase, *, summary)` (`runner_events.py:221-228`) builds `{version, phase, summary}`
and takes nothing else. It gains `facts: Optional[Dict[str, Any]] = None`, merged into the payload.
Those facts must **not** pass through `redact_secrets` whole: its key rule `_SECRET_FIELD_RE`
(`runner_events.py:28`) matches any key containing `token`, so `pre_tokens`, `post_tokens`,
`token_limit` (and D6's `total_tokens`) would each be stored as `"<redacted>"`. Numbers are kept as
they are, and only string values are passed through the value rule (`_SECRET_VALUE_RE`). Test 1.2
asserts the integers survive, which fails if anyone "tidies" this into a whole-dict redaction.

The `summary` is what the operator reads: a `status` row renders as a card with its `content`
(`AgentTimeline.tsx:511-518`, `ResultCard`). It says, for example, *"Copilot compacted this
conversation (152,000 → 31,000 tokens of 200,000)."*

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
| `offered` | warning `due`, no generation (`:281-309`) | the same. **Warn before spend still holds** |
| `automatic` | generate (`trigger="context_pressure"`) and `cut_over` (`:311-362`) | the same |
| `automatic`, no checkpoint runner chosen (`_resolve_runner`, `:311-318`) (R3, row added) | logged, nothing generated | the same |

R3 re-derived every row against `checkpoint_trigger.py` at `fc33ff9` (unchanged since `ef55e6f`):
each line reference holds, and each row's `compacted=True` column is reachable by skipping exactly
the final-warning branch's percent test, the notes branch and `should_checkpoint`. Two open changes
move rows, both unbuilt:

- `worker-spend-counts-against-the-budget` (its D3a) rewrites both `not policy.automatic` tests
  (`:192`, `:281`) to `not policy.automatic or await budget_blocked()`. At an exhausted budget an
  `automatic` conversation then takes the `offered` rows, and a compaction warns instead of
  generating. That is the right outcome for a compaction too, and needs nothing here beyond
  keeping the `compacted` branches inside those same two tests. **(rebase at IMPL.)**
- Slice 4 (its D10) resolves the runner's `compaction_percent` *inside* `consider` and passes it to
  `resolve_policy`. R2 asked `consider(..., compacted=True)` to pass the same policy inputs; R3
  finds there is nothing to pass, because the compaction path runs the same `consider`.

**R2: no `"compacted": true` on `checkpoint_due`, and no banner that says the runner compacted.**
R1 put that flag on the broadcast and told the drive to see "the checkpoint-due banner saying the
runner compacted it". Nothing could show it:

- No UI code reads the `checkpoint_due` payload. `grep -rn checkpoint_due hub/ui/src` finds
  nothing. `every-event-the-hub-sends-reaches-the-app` (unbuilt at R2) only makes the payload's
  `conversation_id` refetch the conversation list (its design `:127`).
- The due banner is a fixed sentence derived from the persisted `conversation.checkpoint_warning`
  alone (`AgentOutputPanel.tsx:649-653`, message at `:720-721`). A broadcast field does not survive
  a reload.
- When the warning is already `due` (a threshold warned earlier), `consider` broadcasts nothing at
  all (`checkpoint_trigger.py:295`).

A test asserting the flag would pass while no operator ever saw it. So the flag is dropped. What
the operator sees is the `compacted` card in the run's timeline (above), next to the unchanged due
banner. A banner variant would need a persisted fact (a column, or reading the conversation's
`compacted` rows) and a UI change, which is why R2 did not add it silently. **Operator decision,
2026-09-28: not now** (Open question 8). The due banner keeps its threshold sentence, and the
timeline's `compacted` card is the signal. A banner that says the runner compacted is recorded as a
possible follow-up change, not built here.

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
declines the compaction's attempt until another run happens. (R2: they did collide on
`_in_flight`, which is fixed above.)

**Open changes touching this site:**

- `every-event-the-hub-sends-reaches-the-app`. R2 re-verified its design: `checkpoint_due` only
  triggers a conversation-list refetch. With the flag dropped, nothing here depends on it.
- Slice 4 (`a-copilot-run-shows-its-credits`, its D10) changes `resolve_policy` to take
  `compaction_percent` and moves the final-warning percent per runner. R3: that happens inside
  `consider`, which the compaction path shares, so no separate plumbing is needed (above).
  **(IMPL pre-check, 2026-10-03: VERIFIED-CODE. `consider` (`checkpoint_trigger.py:173-200`)
  resolves `compaction_percent` internally; `consider_from_reading` passes only raw
  `percent`/`context_tokens`.)**

## D5 — A Copilot error is one error event; a failed compaction is a diagnostic

**R2 changed the kind.** R1 mapped `session.error` to a `diagnostic`. That breaks an existing
requirement: `agent-stream-events` *Tool and diagnostic presentation* says *"Errors SHALL remain
prominent, while diagnostics SHALL be visually distinct and hideable without hiding errors"*, with
the scenario *"diagnostic events SHALL be hidden while error events … remain visible"*. A Copilot
`session.error` is an authentication failure, a spent allowance or a refused request: the operator
must not be able to hide it. It also agrees with slice 2, whose D10 already records Copilot's
errors as `error_event`s. So a `session.error` is an **`error`** event, and only a *failed
compaction* (a degraded state, not a failure of the turn) is a `diagnostic`.

**The builders** (`runner_events.py`).

- `error_event(*, code, message, exit_code=None, retryable=False)` (`:231-243`) gains
  `facts: Optional[Dict[str, Any]] = None`, merged into the payload. The `message` is bounded as
  today and, new, passed through the **value** rule of `redact_secrets`: today `error_event` does
  not redact its message at all, and an authentication error can quote the credential it refused.
- `diagnostic_event`. **R3: this change adopts slice 2's builder and its names.** (contract reconciliation, 2026-09-28: slice 2's
  R3 now ships `diagnostic_event(*, stream, severity, summary, code=None, facts=None)`, keyword-only,
  payload `{version: 1, stream, severity, summary, code?, facts?}`, `stream="copilot"` on every
  Copilot diagnostic. This change calls it with those names, `summary=` where R3 wrote `message=`,
  and adds nothing to it. The rest of this bullet is R3's reasoning, now met by slice 2.) R3 read
  slice 2's R2 signature, `diagnostic_event(*, code, message, severity="info", facts=None)`. One thing
  was still missing: `agent-stream-events` *Versioned kind-specific
  payloads* says *"Diagnostic payloads SHALL identify stream and severity"*, and the CLI's payload
  carries `stream` (`src/agentweave/stream_events.py:556-573`). Slice 2's builder has no `stream`.
  That is a requirement of slice 2's own diagnostics (its `Warning:`/`Info:` and model-substitution
  notices), not of this change, so it is listed under *Required of slices 1–4*. This change calls
  the builder with `stream="copilot"` and, if slice 2 lands without the keyword, adds it
  (`stream: str = "runner"`, written into the payload). The UI renders a diagnostic's `content`
  (`AgentTimeline.tsx:806-822`), so the payload key names do not change what the operator reads.
  **(IMPL pre-check, 2026-10-03: VERIFIED-CODE. `diagnostic_event(*, stream, severity, summary,
  code=None, facts=None)` (`runner_events.py:231-238`) ships exactly those keywords.)**
- Neither builder passes `facts` through `redact_secrets` whole, for the `token`-key reason in D4.
  String values go through the value rule; numbers are kept.

**The mapping.**

- `session.error` → `error_event(code="copilot." + kind, message=message, facts={status_code,
  error_code, remediation})`, where `kind` is `errorType` when it matches `^[a-z_]{1,32}$` and
  `unknown` otherwise (`errorType` is an open string, VERIFIED from the schema). `stack`,
  `providerCallId`, `serviceRequestId`, `url` and `eligibleForAutoSwitch` are dropped. This replaces
  slice 2's single `copilot_session_error` code for the case where the raw event arrived.
  `remediation` is a string enum (`sign_in`, `switch_account`, …; R3, schema), so it is a string
  fact and passes the value rule unchanged. An error with `agentId` is a subagent's; it is still an
  error event, with `subagent_id` among its facts (R3).
- `errorType` `quota`/`rate_limit` is recorded like any other error. **The mapper and the recorder
  place no hold.** Slice 4's D8 does place one from the same raw event, through the run's allowance
  reading (`quota` + `quota_exceeded` → `rejected` → `hold_for_reading`), and that is slice 4's to
  keep. The requirement says what this change owns: recording the event neither places nor lifts a
  hold, so there is no second hold and no second hold path. It does not claim a quota error leaves
  the queue unheld.
- `session.compaction_complete` (root, data present) with `success:false` →
  `diagnostic_event(code="copilot.compaction_failed", summary=<its error, else a fixed sentence>,
  severity="warning", stream="copilot", facts={status_code})` (R3, reconciled 2026-09-28: slice 2's parameter names;
  `statusCode` is in the schema for a failed compaction).

**The echo.** Copilot also turns `session.error` into an ACP `agent_message_chunk` whose text is
exactly `` `Error: ${message}` `` (VERIFIED-CODE, R3). **One fact, one record.**

**R3: the order is known from the code, and R2's hold was both unnecessary and insufficient.**

- *The order.* `setupEventForwarding` sends the raw notification synchronously and only then
  queues the ACP update (D1 table, VERIFIED-CODE). For one `session.error`, the raw event is
  written to the pipe **before** its `Error:` chunk. The only way the chunk arrives without its raw
  event is the in-flight drop (more than 256 raw notifications outstanding), and then the raw event
  never arrives at all.
- *Why R2's hold did not work.* R2 held a *block* whose text begins `Error:`. But slice 2
  accumulates chunks into one block until a non-message update arrives, and the echo is a single
  chunk appended to whatever is accumulating. A model that streamed "Let me run the tests." and
  then hit a failure produces one block `"Let me run the tests.Error: …"`, which does not begin with
  `Error:`. R2's rule would let it through, and slice 2's flush-time classifier, finding the raw
  message inside it, would turn the whole block, prose included, into a second error event. The
  case R2 built the hold for (raw event later) does not occur.
- *The rule.* The match is on the **chunk**, at arrival, before accumulation: an
  `agent_message_chunk` whose text equals `"Error: " + message` of a root `session.error` already
  received in this turn, and not yet matched, is dropped (each raw error matches at most one
  chunk). The error event was already emitted when the raw event arrived. Nothing is held, and the
  surrounding prose is recorded as it is.
- *Slice 2's `Error:` branch.* With the chunk dropped before accumulation, slice 2's D10 branch
  "an `Error:` match → `error_event(code="copilot_session_error")`" can no longer match anything
  this change emits, so this change deletes it; its `Warning:`/`Info:` branches stay slice 2's.
- *No raw event.* The chunk accumulates exactly as under slice 2, which records it as text.
  "Recorded as it is without this change" means that.
- **Review fixes, 2026-09-28 (finding 7): a subagent's error is echoed too.** In 1.0.88 the ACP
  update mapper (`KDo`, `case"session.error"`) has no `agentId` test, and `updateSession`'s only
  subagent check (`oa(o)`) guards `session.model_change`. So a subagent's `session.error` is also
  echoed as `Error: …`. This change records it as an error event (with `subagent_id`); leaving its
  echo as text would record the same fact twice. So the echo match is against **any** unmatched
  `session.error` of the turn, root or subagent, still at most one chunk per raw error.
- **Which events are a subagent's.** Wherever `data` is present, the mapper uses Copilot's own
  test (`_d()` in 1.0.88, VERIFIED-CODE, review 2026-09-28): the envelope's `agentId`, else
  `data.agentId`, else `data.parentToolCallId`. It does not rely on the envelope's `agentId` alone.
  That test decides D4's "only the root's compaction" and the `subagent_id` fact here.
- **A subagent's error does not fail the reviewer's turn (finding 8, decided: slice 2's).** Slice 2
  R3 ends the turn `failed` on any armed `session.error`, with no subagent distinction. With group B
  a failed `code-review` subagent would fail, re-queue and re-bill the reviewer's whole turn. Only a
  root `session.error` may fail the turn; that rule is slice 2's (*Required of slices 1–4*, 2.11;
  provided as slice 2's § *Provided to slices 3–5* item 19, which also says this change replaces its
  `copilot.subagent_error` diagnostic with the error event below).
  This change records a subagent's error as an error event with `subagent_id`, and the turn goes on.

**The test follows the code's order** (CLAUDE.md: the ordering the source actually emits, and some
test fails if it is reversed). Test 1.3 feeds the captured order (task 1.1 confirms raw-first) and
asserts one error event and no `Error:` text. Reversed, the same fixture yields the error event *and*
the text, so the main assertion fails, which is the check that the fixture's order matters. The
spec no longer claims "whichever arrives first": nothing emits the other order, and building for it
cost the hold above.

**Open change:** `a-file-path-is-not-redacted-as-a-credential` narrows the catch-all alternative of
`_SECRET_VALUE_RE` (`runner_events.py:57-60`; its design `:25-30`). R2 re-verified it: the `sk-`
and `aw_live_` word-start alternatives are unchanged, and those are what catch a BYOK key (D7). No
conflict. **(rebase at IMPL: unbuilt at R2.)**

## D6 — Subagents in the timeline

`subagent.started` maps to `status_event("subagent_started", summary=f"{agentDisplayName} started")`.
`subagent.completed` and `subagent.failed` map to `status_event("subagent_completed" |
"subagent_failed")`.

- The payload carries, as `status_event` facts (D4), `call_id` = `toolCallId`, `agent_name`,
  `model`, `total_tokens`, `duration_ms`, `total_tool_calls`, `cancelled` (R2: the schema has it on
  `completed`), and `error` (value-redacted) for failures.
- `call_id` pairs them with the parent `task` tool call that slice 2's mapper already emits as
  `tool_use` (`toolCallId` is required on all three types, VERIFIED from the schema).
- R3: because a raw notification overtakes queued ACP updates (D1 table), `subagent.started` can be
  recorded *before* the `tool_use` of its `task` call. The pairing is by `call_id`, never by
  position, and test 1.2 feeds the captured order.
- R3: `subagent.failed` also reports `totalTokens`, `durationMs` and `totalToolCalls` (schema), so
  the failure event carries them too. The summaries are `"<agentDisplayName> finished"` and
  `"<agentDisplayName> failed: <error>"`, since a `status` row renders its `content` as a card
  (`AgentTimeline.tsx:511-518`, `agentTimelineModel.ts:9`).
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
  `test_migrations.py` (`HEAD_REVISION`, `:40`, `"0110"` at R2) and `test_project_persistence.py`.
  It comes **after** slice 2's migration, which widens `ck_runners_cli` (`db/models.py:340`). No
  night-queue migration had landed at R2; the number is assigned in build order.

**R2: `openai` is deferred with Azure; `anthropic` is the only provider this change offers.** R1
validated an `openai` runner's model against the `codex` catalog. Since `3b3563a`
(`the-codex-models-offered-are-the-ones-its-cli-lists`), that catalog is read at run time from the
installed Codex CLI's `models_cache.json` (`model_catalog.py:303-422`): it is the list a ChatGPT
plan's Codex CLI was offered, per machine, not a statement about what the OpenAI API serves an API
key. Its fallback list names models declared from a changelog. Validating an API model against it
would accept ids nobody verified for the API, and a runner valid on one machine could be refused on
the next. The `claude` catalog's ids are the ones Claude Code passes to the Anthropic API, and the
drive's model (`claude-haiku-4-5-20251001`) is a dated API id (the other entries are **INFERRED**
to be API ids too; only Haiku is driven). `type` stays a field, so a later change can add a
provider with a catalog of its own. **Operator decision, 2026-09-28: both deferred** (OpenAI and
Azure; Open question 8).

**Validation.** R2: returned as **400 with a string `detail`** from `api/v1/runners.py`, like
`_reject_undeclared_model` (`:24-44`), not as a Pydantic `ValueError` (which would be a 422 whose
sentence sits in `detail[0].msg` behind a `"Value error, "` prefix, and which the Runners page would
have to dig out). The schema types the fields; the route decides.

- Only `cli == "copilot"` may carry `provider_config`.
- `type` must be `anthropic`.
- `api_key_var` must match `^[A-Z_][A-Z0-9_]*$`. A value that is not an environment variable *name*
  is refused **before** it is stored, with a sentence saying to put the key in the Hub's environment
  and name the variable. This is what stops a pasted key from reaching the database. (`sk-ant-api03-…`
  fails the pattern on its lowercase letters and `-`.)
- `base_url` defaults to `https://api.anthropic.com`. **Review fixes, 2026-09-28 (finding 10):** it
  is parsed with `urllib.parse.urlsplit`, not prefix-matched: a prefix check on `http://localhost`
  accepts `http://localhost.evil.com` and `http://localhost@evil.com` and would send the key in
  cleartext off the machine. The scheme must be `https` with a hostname, or `http` with
  `hostname in {"localhost", "127.0.0.1", "::1"}`; no userinfo in either case.
- **Review fixes, 2026-09-28 (finding 15 note): `api_key_var` must not name one of the Hub's own
  credentials.** `GH_TOKEN`, `GITHUB_TOKEN`, `COPILOT_GITHUB_TOKEN`, `DATABASE_URL` and any `AW_*`
  name are refused with a sentence: such a runner would ship that secret to `base_url`. Operator
  authority, but an easy mistake.
- **Review fixes, 2026-09-28 (finding 11): a provider runner's `flags` may not carry `--model`.**
  Slice 2 appends the runner's `flags` after `--model` (its D3), so `--model haiku` in `flags` would
  send an alias to the API past every check below. `POST`/`PATCH /runners` refuse a provider
  runner whose `flags` contain `--model` or `--model=…` (400), and a `PATCH` adding
  `provider_config` is judged on the flags it leaves behind as well.
- The model must be set, since BYOK requires one; a `PATCH` that sets it to `null` on a provider
  runner is refused too.
- **R3: a `PATCH` is judged on the pair it leaves behind.** `update_runner` checks `model` only when
  `model` was sent, and exempts `model == current` (`runners.py:37`, `:152-154`) so a legacy runner
  stays editable. Adding or removing `provider_config` changes which catalog the *stored* model must
  come from, without sending `model`. So when `provider_config` is in `model_fields_set` (absent vs
  explicit `null` distinguished as `model` already is), the resulting `(provider_config, model)`
  pair is validated as on create, and the legacy exemption does not apply. Adding a provider to a
  runner on `auto` is refused unless the same PATCH sets a declared Claude id; removing it from a
  runner on `claude-haiku-4-5-20251001` is refused unless the same PATCH sets a `copilot` model or
  `null`. Each refusal is a 400 before any attribute is assigned, so nothing is stored.
- ~~`ProviderConfig` is a `RequestModel` (`extra="forbid"`) whose three fields carry no Pydantic
  constraint, so a pasted key never meets a 422.~~ **Review fixes, 2026-09-28 (finding 15): that was
  false.** `extra="forbid"` is itself a Pydantic check: the likely paste
  `{"type":"anthropic","api_key":"sk-ant-…"}` gets FastAPI's default 422 with the key in
  `detail[].input`, and the Hub has no `RequestValidationError` handler (`main.py`). So the create
  and update schemas type `provider_config` as `Optional[Dict[str, Any]]`, and the route does every
  check as a 400 whose sentence names an unknown **key** (`api_key`) but never a value, and refuses a
  non-string value for a known key the same way. Only after those checks is it read into
  `ProviderConfig` (a plain internal model) for storage.
- **A stored row is read defensively.** `runner_probe_config` and every reader of
  `runners.provider_config` treat a non-dict or incomplete value as "no valid provider" (the runner
  is reported not launchable with a sentence), never as an exception: one bad row must not 500
  `GET /agents/launchability` for every agent (review 2026-09-28, *Checked and found sound*).
- **R2: the model must be a declared model *id*, checked by this change, not by the existing rule.**
  Since `63d9f34` (`a-model-alias-is-a-model-choice`), `ProviderDescriptor.model()` resolves a
  declared alias (`model_catalog.py:149-155`), so the existing rule now *accepts* `haiku`, and its
  sentence `undeclared_model_reason` names the aliases as acceptable (`:432-446`). An alias is not an
  API id, and `COPILOT_MODEL=haiku` would reach the Anthropic API. So the provider rule is
  `any(m.id == model for m in CATALOG["claude"].models)`, read from the **literal** `CATALOG`, with
  its own sentence naming the ids only.
- **Every site that asks "which catalog is this runner's model from" must ask the runner, not the
  CLI** (R2). Slice 1's `catalog_provider` is a `ClassVar` on the adapter, so it cannot vary by a
  runner's `provider_config`, and the controls (Copilot's `--reasoning-effort`) *are* Copilot's
  either way. The model is the one thing that differs. The sites, at `ef55e6f`:
  - `runners.py:24-44` `_reject_undeclared_model(cli, model)`, on create and PATCH: a provider
    runner is checked by the provider rule instead.
  - `schemas/runners.py` `RunnerResponse._flag_unrecognised_model` reads `get_provider(self.cli)`:
    it would flag every provider runner `model_unrecognised: true`, because the `copilot` catalog
    does not declare `claude-haiku-4-5-20251001`. It reads the provider rule for a provider runner.
  - `agent_trigger.py:1618` `validate_overrides(runner_row.cli, body.overrides)`: a per-run `model`
    override on a provider runner is **refused** (400), because the provider's model is the
    runner's, and an override from the `copilot` catalog (`auto`, `claude-haiku-4.5`) would be sent
    to the Anthropic API. Other controls validate as today.
  - **R3: the spawn, not only the route.** Overrides are stored on the conversation
    (`conversation.runtime_overrides`, `:1624`), *"trusted here rather than re-validated per turn"*
    (`agent_trigger.py:797-802`: `model = conversation_overrides.get("model") or
    config.get("model")`), inherited by later conversations (`conversations.inherit_runtime_overrides`,
    `:66-111`) and carried through a handover (`checkpoint_cutover.py:182-183`). A `model` stored
    before the runner gained a provider, or before the agent was rebound to a provider runner, would
    reach the spawn although the route now refuses new ones. So at `:802`, a provider runner's model
    is `runner_row.model` whatever the conversation stores; the stored `model` is left in place
    (rebinding back restores it) and not applied. Test 1.8 stores one directly and triggers.
  - The UI's `providerForRunner` (`hub/ui/src/api/modelCatalog.ts`; slice 2's D19 adds
    `copilot → 'copilot'`): the composer offers no model choice for an agent on a provider runner,
    and shows the runner's model instead.
  - **Review fixes, 2026-09-28 (finding 9): the Runners page's own model picker.**
    `RunnersPage.tsx:208-313` fills the picker from `catalog.providers.find(p => p.provider === cli)`,
    so a `copilot` runner is offered the Copilot catalog, a "Latest" alias group and "Provider
    default", and the provider rule refuses every one of them: no valid provider runner can be made
    through the UI. With a provider set, the picker lists `CATALOG["claude"]` **ids only** (no alias
    group, no "Provider default"), and turning the provider on or off in the dialog resets the model
    to empty, so the operator chooses again from the right list.
  - **Review fixes, 2026-09-28 (finding 1): the one-shot spawns, and the checkpoint model.** Slice 2's
    D14 puts `copilot` in `worker.SUPPORTED_CLIS` and the titler's, so checkpoint generation, the
    handover and titles can run on a Copilot runner. Four sites choose that runner:
    `checkpoint_trigger._resolve_runner` (`:139-153`), `checkpoint_handover._resolve_runner`
    (`:176-188`), `api/v1/checkpoints.py:183`, and `conversation_titles._resolve_runner`
    (`:203-219`), which falls back to **the agent's own runner**. `projects.py:483-493` accepts any
    project runner for the checkpoint and title seats. Their environment is slice 1's
    `one_shot_env(purpose)`, which sees no runner row, and `resolve_agent_env` (whose only caller is
    `agent_trigger.py:849`) is never reached. So a provider runner in either seat, or an agent on one
    with generated titles, would run on the GitHub subscription with a Claude API id, and would
    inherit any ambient `COPILOT_PROVIDER_*`. **Chosen: plumb, not refuse.** Refusing a provider
    runner in those seats (and skipping titles for its agents) would leave an operator who runs only
    on BYOK with no checkpoints and no titles. Instead:
    - slice 1's `one_shot_env` takes the runner's `config` (as `guard_env` does), carrying
      `provider_config` (*Required of slices 1–4*, 1.7); the worker already receives `runner_id`
      (`worker.run_worker`, `:430`) and the titler holds the runner row, so each reads
      `provider_config` from the row it spawns for;
    - the Copilot `one_shot_env` calls **the same function** as the Copilot `guard_env`,
      `copilot_provider_env(env, provider_config)` (below), so a one-shot spawn gets exactly a run's
      provider variables, or none;
    - `project.checkpoint_model or runner.model` is a fifth "which model may this runner use" site
      (the three generation sites share it). For a checkpoint runner with a provider,
      `PATCH /projects` refuses a `checkpoint_model` that fails the provider rule (400, the same
      sentence), and at generation a stored `checkpoint_model` that fails it (stored before the
      runner gained a provider) is ignored in favour of `runner.model`, as `:802` ignores a stored
      run override. One helper, `one_shot_model(runner, checkpoint_model)`, serves the three sites.

  **(IMPL pre-check, 2026-10-03: VERIFIED-CODE. `catalog_provider` is still a `ClassVar`
  (`runner_adapters/base.py:268`), so the collapse condition did not happen; these sites still
  apply.)**

**Azure is deferred (DECIDED 2026-09-28, together with OpenAI).** An Azure model is a deployment
name the catalog cannot declare (`COPILOT_PROVIDER_WIRE_MODEL`), which conflicts with the catalog
rule. Review 2026-09-28 adds: Azure also needs `COPILOT_PROVIDER_AZURE_API_VERSION` and possibly
`API_KEY_COMMAND`, the very variables the spawn now strips, so supporting it means a per-runner
"declared deployment + base model id" concept, not a catalog entry. The operator accepted the
deferral (Open question 8); `type` stays a field so a later change can add it.

**Spawn (rewritten, review fixes 2026-09-28, findings 3 and 10).** One function,
`copilot_provider_env(env, provider_config) -> env`, used by the Copilot `guard_env` (runs) and the
Copilot `one_shot_env` (checkpoints, handovers, titles; finding 1), does two steps in order:

1. **Strip**, from the environment it is given (the ambient environment already merged with the
   agent's `env_vars`, so both sources): every name with the prefix `COPILOT_PROVIDER_`, plus
   `COPILOT_MODEL` and `COPILOT_OFFLINE`. The prefix, not a list: the 1.0.88 bundle reads **15**
   `COPILOT_PROVIDER_*` names (`grep -o "COPILOT_PROVIDER_[A-Z_]*" app.js | sort -u`, re-counted in
   this fix; the review said 13), and `copilot help providers` documents that
   `COPILOT_PROVIDER_BEARER_TOKEN` "takes precedence over API key", that `WIRE_MODEL` replaces the
   model sent to the API (bypassing the catalog-id rule), that `API_KEY_COMMAND` runs a command per
   request, and that `HEADERS` adds arbitrary headers. R1–R3 overwrote only four names, so any of
   these left in the Hub's shell or an agent's `env_vars` survived on a provider runner.
2. **Set**, only for a runner with a valid `provider_config`, exactly four:
   - `COPILOT_PROVIDER_TYPE` and `COPILOT_PROVIDER_BASE_URL`;
   - `COPILOT_PROVIDER_API_KEY` = `os.environ.get(api_key_var, "")`. **Not** `os.environ[...]`:
     `guard_env` must not raise (slice 1 D15), and at `agent_trigger.py:849` a `KeyError` would answer
     500. A missing key still sets `TYPE`/`BASE_URL`/`MODEL` with an empty key, so the run fails with
     the provider's 401 and never falls back silently to the GitHub subscription, as
     `claude_proxy`'s explicit-401 comment already reasons (`launchability.py:164-167`).
     Launchability reports the missing variable before any spawn (below), so this is a race, not
     the normal path;
   - `COPILOT_MODEL` = `runner.model` (for a one-shot, `one_shot_model(...)`), and slice 2's
     `--model` spawn flag carries the same value (the override refusal above guarantees it).

**The strip of step 1 does not belong to group C (review 2026-09-28, finding 6; decided).** Without
it, an operator's shell `COPILOT_PROVIDER_BASE_URL` silently turns every subscription Copilot run
into BYOK, and that hole would reopen if the operator REJECTED group C. So step 1, for a runner
without a provider, is asked of **slice 2** for every Copilot spawn, beside its `COPILOT_ALLOW_ALL`
strip (*Required of slices 1–4*, 2.10; provided in slice 2's D3 and § *Provided* item 18,
consistency pass 2026-09-28). This change's step 1 then only has to keep doing it for a
provider runner. If slice 2 lands without it, task 2.8 here adds it; that task is tagged with no
group and is not cut with C. It mirrors the ambient `ANTHROPIC_BASE_URL` strip
(`launchability.py:190-194`): an operator's shell must not silently turn a subscription runner into a
BYOK one.

**R3: stripped whatever their source, unlike the Claude rule.** `resolve_agent_env` merges the
agent's `config.env_vars` into the run environment (`launchability.py:157-179`), and the Claude
guard deliberately spares a variable the agent's `env_vars` name. Copied as is, that exemption
would let an agent's `env_vars` carry `COPILOT_PROVIDER_*` and turn the run into a BYOK run the
runner never validated, which is the "one fact on two records" D7 exists to prevent. So the Copilot
guard strips those names from both sources when the runner has no provider, and (review fixes,
2026-09-28) strips the whole prefix from both sources and then sets exactly the four when it has one.

R2: **where** this happens is not "the adapter's `build_launch`". Slice 1's `build_launch` is a
`StreamTransport` member returning argv only; an RPC transport (ACP) has none, and its environment
arrives as `RpcTurnRequest.env`. The environment is built by `resolve_agent_env` and ends in the
adapter's `guard_env(proc_env, config)` (slice 1 D10; R2 read `env_vars` there, consistency pass
2026-09-28), and slice 2 D3 puts its `GH_TOKEN` strip
there. `guard_env` receives no runner row. **R3: no new parameter on `resolve_agent_env` is
needed.** The trigger already builds `config` from `get_agent_config` and overwrites `runner`/`model`
from `runner_row` (`agent_trigger.py:764-765`), then calls `resolve_agent_env(runner, config)`
(`:849`). Putting `config["provider_config"] = runner_row.provider_config` in the same place (and
in `get_agent_config`, below) delivers it. What was missing is the last hop: slice 1's
`guard_env(proc_env, env_vars)` saw only `env_vars`, not `config`. That was listed under *Required
of slices 1–4*, and slice 1's R3 provides it: `guard_env(proc_env, config)`, must not raise (contract reconciliation, 2026-09-28). **(IMPL pre-check, 2026-10-03: VERIFIED-CODE. The base adapter
declares `guard_env(self, proc_env, config: Mapping[str, Any])` (`runner_adapters/base.py:297-299`)
and the Copilot adapter implements it (`copilot.py:248-254`), calling
`copilot_guard_env(base, config.get("env_vars") or {})`. It does not yet read
`config["provider_config"]` — that plumbing is this change's own unbuilt task 3.3, not a gap in
slice 1 or 2.)**

**R2: the key reaches everything `copilot.exe` starts. R1's "explicit allow-list" was false.**
Slice 2's D3, as written, puts **no** `env` block in `agentweave-mcp.json`: *"The stdio MCP child
inherits it (VERIFIED), so `agentweave-mcp.json` carries no secret and no `env` block."* So the
Hub's tool server inherits `COPILOT_PROVIDER_API_KEY`, and so does every shell command the agent
runs. A test asserting the key is absent from the config file's `env` would pass while the key sat
in the tool server's environment. This is the same exposure a `claude_proxy` run has today
(`ANTHROPIC_API_KEY` is in Claude's environment, `launchability.py:162-169`, and Claude's
`--mcp-config` sets no `env`), and it is inherent to BYOK: the CLI needs the key in its own
environment. Whether Copilot's stdio `env` field *replaces* or *merges* with the inherited
environment is not known, so the Hub cannot scrub it there either. The requirement therefore no
longer claims the key stays out of the tool server. It claims what holds: the key is stored nowhere,
returned nowhere, and redacted from everything recorded. The shell exposure is stated to the
operator (test guide, human-only 3). **Operator decision, 2026-09-28: accepted** (Open question 8),
as a proxy runner's key is today; the throwaway, spend-capped key drive 7.6 uses makes it
acceptable there.

**R3: this change declines slice 2's hand-off of an MCP `env` filter, with reasons.** Slice 2's R2
D3 now says *"Whichever lands the BYOK variables adds that filter (an `env` map that blanks them)"*.
It is not added here:

- It protects nothing the run cannot already read. The key must be in `copilot.exe`'s environment,
  and every shell command the agent runs inherits it (`echo $env:COPILOT_PROVIDER_API_KEY`).
  Blanking it for the Hub's own tool server, which never prints its environment, closes no path.
- It could break the tool server. Whether Copilot's stdio `env` *merges* over the inherited
  environment or *replaces* it is Open question 10, still unanswered. Under replacement, an `env`
  holding only blanked names leaves the server without `AW_RUN_TOKEN`, `HUB_URL` and `PATH`, and
  every AgentWeave tool call fails. That is a fix that passes a test reading the file and breaks
  the product.

If the operator wants the tool server scrubbed anyway, it becomes safe only once 1.1 or slice 3
settles question 10.

**Launchability** (adapter member `launchability`): a BYOK runner is authorized iff `api_key_var` is
set and non-empty in the Hub's environment. The reason names the variable, not its value, following
`claude_proxy` (`launchability.py:108-114`). A GitHub login is not required, so slice 2's cached
`CopilotProbe` verdict, whose `session/new` under the `_worker` home reads GitHub auth, supplies only
`present` and the version for a provider runner. **R3 (Open question 9, VERIFIED-CODE):** under
BYOK, ACP `session/new` does not demand a GitHub login: `hasSessionCredential` passes when the ACP
server was given a `providerContextId`, which the provider set-up supplies (D1 table). The rule
stands; task 1.1(c) still records what `session/new` returned.

**R2: the verdict can only reach the operator if `provider_config` reaches the probe.** A unit test
of the adapter's `launchability` passes while every surface reports the subscription verdict ("not
signed in") for a provider runner. So one helper, `runner_probe_config(runner_row)`, builds
`{runner, model, provider_config}`, and test 1.8 asserts the verdict through
`GET /runners/launchability`, `GET /agents/launchability` and `POST /agents`.

**R3: R2's site list was wrong in three of its six entries.** `agents.py:552` and `:2004` are
display code (the roster's model label and the context's *Team* list), not probes, and
`launchability.py:524` is not a caller but the runner overwrite inside `get_agent_config`
(`:469-535`). The real `probe_agent(` calls at `fc33ff9` are (the same six slice 2's D15 lists):

| Call | How its `config` is built | Fix |
|---|---|---|
| `agents.py:234` (`GET /agents/launchability`, which the app's agent indicators read, `ui/src/api/agents.ts:384`; `GET /agents` itself carries no verdict) | `get_agent_config` | in `get_agent_config` |
| `inbound_queue.py:223` (why a queued turn has not started) | `get_agent_config` | in `get_agent_config` |
| `agent_trigger.py:766` (the trigger) | `get_agent_config`, then `runner`/`model` overwritten at `:764-765` | the helper at `:764-765`, which also carries it on to `resolve_agent_env` (`:849`) |
| `agent_trigger.py:731` | no runner bound | unaffected |
| `agents.py:728` (`POST /agents`, which refuses an unlaunchable agent with 409) | by hand, `runner.cli`/`runner.model` | the helper. Without it, no agent can even be *created* on a provider runner when GitHub is not signed in |
| `runners.py:96-99` (`GET /runners/launchability`) | by hand | the helper |
| `runners.py:118` (`launchability-by-provider`) | no runner row | unaffected |

`get_agent_config`'s result is also what `resolve_agent_env` receives in the trigger, so one
addition there (`meta["provider_config"] = runner_row.provider_config` beside `:524-526`) serves
both. **(IMPL pre-check, 2026-10-03: VERIFIED-CODE. The Copilot adapter implements
`launchability(self, agent, config)` (`copilot.py:231-240`); `get_agent_config` and the other call
sites in the table above are unchanged. `provider_config` is not yet threaded through them —
unbuilt task 3.3, not a gap here.)**

**Where the key could leak, and why it does not:**

- It is in no database row.
- The runners API returns `api_key_var`, which is a name.
- `ROSTER_CONFIG_KEYS` (`api/v1/agents.py:651`) is agent config and unaffected.
- ~~Stream text passes `redact_secrets` (`runner_events.py:63-81`).~~ **Review fixes, 2026-09-28
  (finding 2, blocking): it does not.** `text_event` and `thinking_event` (`runner_events.py:136-149`)
  store their text raw; only `tool_use_event` (`:177`) and `tool_result_event` (`:206`) call
  `redact_secrets`. The key is in the run's environment, so an agent that runs
  `echo $env:COPILOT_PROVIDER_API_KEY` has the tool result redacted, and if it then repeats the key
  in its reply the reply is stored verbatim, and from there reaches the checkpoint transcript, the
  checkpoint runner's prompt and the title excerpt. A permission card's `tool_input`
  (`agent_trigger.py:3004`, `dict(subject)`) stores a command quoting the key unredacted. And a
  `base_url` on a localhost proxy can take a key of any format, which the `sk-`/`aw_live_` pattern
  rules do not match at all.
- **So the key is scrubbed by its exact value, per run.** The Hub knows the resolved key at spawn.
  A small in-process registry (`run_secrets.register(run_id, values)`, `scrub(run_id, obj)`,
  `forget(run_id)`, never persisted) holds it:
  - the trigger registers `COPILOT_PROVIDER_API_KEY`'s resolved value (when non-empty) for the run
    before the spawn, and forgets it when the run is finalised;
  - `record_agent_output` (`output_recording.py:22`), the funnel every recorded run event goes
    through (the executor's `_record_observation` sites and `POST /agents/{name}/output` alike),
    replaces each literal occurrence with `<redacted>` in `content` and in every string of `payload`,
    **before** it stores or broadcasts, for every kind (text, thinking, tool, error, diagnostic,
    status);
  - `_await_operator_permission` (`agent_trigger.py:2977-3007`) scrubs `tool_input` before storing
    the card and before its broadcast;
  - the run's stored failure text (`Run.error`) is scrubbed the same way.

  An exact-value match has no F31/F118-style false positives, needs no pattern for the key's
  format, and the same registry can later cover `claude_proxy`'s `ANTHROPIC_API_KEY`. The pattern
  rules stay as they are underneath it. One-shot spawns record no run events; what they read (a
  transcript, an excerpt) was recorded through the scrub.
- `sk-ant-…` is still also caught by the `sk-` word-start alternative (`:58`), which
  `a-file-path-is-not-redacted-as-a-credential` does not change. D5 adds the value rule to
  `error_event`'s message, which today is not redacted.
- Stderr summaries are "secret-safe" per `runtime-diagnostics`, and pass the scrub when recorded.
- It **is** in the environment of the run's tool server and shell commands (above). Accepted by
  the operator, 2026-09-28.
- `RpcTurnRequest.env` holds it in memory for the run. A dataclass `repr` in any log line would
  print it, so slice 1's `env` field is `repr=False` (*Required of slices 1–4*, 1.8), and the trigger
  fills `RpcTurnRequest.agent_config` with only the keys the run needs (`copilot_github_mcp`), never
  the whole config with its `env_vars` (review 2026-09-28, finding 14).

Test 1.9 asserts the key value appears in none of the runner response, the agent context file, a
recorded run event, a permission card, or an error or diagnostic payload, feeding it through a
**text** event, a **thinking** event and a permission subject (a tool result alone would pass on
today's code: the F190 pattern).

**The happy-path drive's key (DECIDED 2026-09-28, Open question 8).** The operator will supply a
real key for drive 7.6, and only on these conditions: the fixes for review findings 2 (the
exact-value scrub, task 3.5), 3 (the whole-prefix strip, task 3.3) and 10 (the `urlsplit` address
check and the `KeyError`-free key read, tasks 3.2 and 3.3) are built and their tests green; the key
is a dedicated Anthropic workspace key with a hard monthly spend limit of a few dollars; it is set
only in the trial Hub's launch environment (not user-wide, so not visible to the `:8000` Hub); and
it is revoked after 7.6.

**Plainly: a Claude Max subscription cannot back this.** Copilot's BYOK takes an API key. A Max plan
authenticates Claude Code and claude.ai by OAuth, and routing it through another harness is not a
supported use (DECISIONS `ghcp-d4`). Runner management states this beside the key field.

**Accounting note for slice 4.** Under BYOK the provider bills tokens, and Copilot's AI credits
probably read 0 (**INFERRED**). D3 already makes tokens the unit. Slice 4 should not present 0
credits as "free" (R2 question 6, carried to slice 4).

## D8 — A Copilot reviewer consults Copilot's review agents

**The setting.** Agent `config.copilot_review_agents` is a list drawn from `code-review`,
`security-review` and `rubber-duck`, empty by default. It is stored in `Agent.config` (an open JSON
object, merged by `_merge_patch`, `api/v1/agents.py:632-644`, in `PATCH /agents/{name}`, `:2562`,
applied at `:2686`), so no migration is needed. The PATCH route refuses unknown names with a 400
before the merge, so a refused PATCH changes nothing. The UI presents it only for an agent bound to a
`copilot` runner (*"A setting with no backing state is not presented"*).

**R2: the UI needs a read path, and R1 named none.** The Settings page does not read raw
`Agent.config`; the roster exposes only the keys in `ROSTER_CONFIG_KEYS` (`api/v1/agents.py:651`,
filtered at `:622`), an allow-list kept small so credentials never reach a polled listing (F244).
A control whose value never comes back would render "off" after every reload while the setting was
on. So `copilot_review_agents` (B) and `copilot_github_mcp` (D) are each added to
`ROSTER_CONFIG_KEYS` by their own group. Neither can hold a credential: the first is a list from a
closed vocabulary validated on write, the second a boolean.

**The effect.** In the review section of the rendered context (`api/v1/agents.py:1724-1787` at
`ef55e6f`), directly after the verdict line (`:1756-1761`) and before the evidence-gate sentence,
and only when `review is not None` and the agent's runner is `copilot` and the list is non-empty,
add one bullet:

> Before your verdict, run Copilot's `code-review` (and `security-review`) agent as a subagent on the
> changes from `<base>` to `<commit>`. Weigh what it reports and check it yourself. It does not see
> this repository's instructions, and its findings are not your verdict. The verdict is yours, and
> it is recorded only by `update_task`.

The review section sits in the workspace block, which slice 2's D5 classes as **per-turn**, so on a
Copilot run the bullet travels in the prompt's per-turn block, not the agent file. **(IMPL
pre-check, 2026-10-03: VERIFIED-CODE. `RpcTurnRequest.per_turn_context` and `_context_block`
(`copilot_acp.py:1633-1661,2254`) build the per-turn prompt block exactly as described.)**

**`<base>` (R2 answered question 4).** `ReviewContext` (`review_turn.py:47-67`) does **not** know the
merge target: it carries `commit_sha`, `branch` (the evidence's branch) and `earlier_commits`.
"The branch approval merges into" is `Project.main_branch` (nullable; set by the operator or adopted
by `_adopt_detected_main_branch`, `api/v1/projects.py:325-363`); `task_integration.integrate` takes
it as `main_branch`. There is **no** merge-base helper in the codebase. So:

- `ReviewContext` gains `base_sha: Optional[str] = None`.
- `prepare_review_turn` (`review_turn.py:240-293`) reads the project's `main_branch` through the
  `session` it already has, and computes `git merge-base <commit_sha> <main_branch>` in `repo_root`
  with the same `_git` pattern `task_integration.py:148-157` uses (R3: before the checkout is
  provisioned; see the last bullet).
- `base_sha` is `None` when `main_branch` is unset, the branch does not exist, the command fails, or
  the merge base **equals** the commit (the commit is already on the main branch, so the range is
  empty). Then the bullet names `<commit>` alone and says to review that commit's own changes.
- **It never raises.** `prepare_review_turn`'s refusals (`ReviewTurnRefused`) are about whether a
  review can happen at all, and the trigger turns them into a refused dispatch
  (`agent_trigger.py:962`). A missing base only narrows one bullet, so it must not refuse the turn.
- **R3: what the trigger returns if it did raise, and where it runs.** `_git` passes
  `check=False` but `timeout=` (`task_integration.py:148-157`), so `subprocess.TimeoutExpired`
  can still raise, and `OSError` on a vanished binary. The trigger catches only
  `ReviewTurnRefused` (`agent_trigger.py:961-971`); anything else escapes as a **500**. Worse, it
  would escape *after* `ensure_review_checkout` has provisioned `.agentweave/reviews/<reviewer>` and
  *before* the trigger records `review_claim.repo_root` (`:973-974`), so the checkout would not be
  released (the F326 class). So the merge base is computed **before** `ensure_review_checkout`
  (after `is_git_repo`, when the commit is already resolved), and catches
  `(subprocess.SubprocessError, OSError)` into `None`. Test 1.11 patches `_git` to raise
  `TimeoutExpired` and asserts the turn proceeds with the commit alone.

**Open changes touching this section (R2 re-verified their designs; both unbuilt at R2/R3 — IMPL
pre-check, 2026-10-03: `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` is now
archived; `a-flow-stages-its-review-in-the-dispatch` is still open):**

- `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` gives `_render_hub_agent_context`
  an optional `runner` parameter (its design `:61-65`) and deliberately leaves the review verdict's
  `update_task` bare (its design `:69-75`). This change uses that `runner` parameter to know the
  runner is `copilot` if it has landed, and otherwise reads it from `agent_row.runner_id`. The
  bullet names `update_task` bare, matching the verdict line. **(IMPL pre-check, 2026-10-03:
  VERIFIED-CODE. `_render_hub_agent_context` has `runner: Optional[str] = None`
  (`api/v1/agents.py:1770-1788`).)**
- `a-flow-stages-its-review-in-the-dispatch` edits the loop briefing's `_briefing_verdict_lines`
  (its design `:168-170`), not this renderer. No conflict.

**Why not a flow step naming a Copilot agent.** A flow's reviewer is an AgentWeave agent, resolved
*"by the same resolution the rest of the product already uses for a declared reviewer, never a second
one"* (`agent-flows`, *A flow resolves a reviewer by declaration, then by availability*).
`code-review` is not on the roster, cannot hold a run token and cannot call `update_task`. Making it
a reviewer would need a second resolution, and a verdict nobody could record. Built-ins are tools a
reviewer uses. They are not reviewers.

**Why not `/review` or `/research`.**

- A slash command over ACP must be the whole prompt (`acp-server.md:184`). The Hub prepends turn
  notices to every prompt (`agent_trigger.py:1170-1194`), and R2 adds that slice 2's D5 sends the
  per-turn context as a **separate content block** ahead of the message on every Copilot turn. So
  no Copilot turn the Hub starts is ever a single text block, and no operator message reaches
  Copilot as a slash command. (This also answers drive task 7.2's condition: it is driven by
  replaying the captured fixture.)
- `/review` would also end with the code-review agent's report, not with an AgentWeave verdict.
- `research` cannot be started by the main agent at all (`about-custom-agents.md:71`).

**Cost.** Built-ins default to `claude-sonnet-4.6` (`ref.md:1190-1195`). On Free, subagents follow
Auto. Each consult is at least one extra model call, so the setting is off by default.

**On a BYOK runner (review 2026-09-28, finding 13, a note).** `claude-sonnet-4.6` is Copilot's own
id, not an Anthropic API id. Under group C's provider a built-in subagent either sends an id the
provider refuses, or spends Sonnet on the operator's key; which one is unknown. The bullet is **not**
suppressed on a provider runner: that would make group B read group C's state, which D10 forbids,
and the failure is bounded: with slice 2's root-only turn failure (*Required*, 2.11) a refused
subagent ends as one `subagent_failed` status and the reviewer's turn goes on. What is recorded: task
1.1 cannot observe it (run (c) has an invalid key), so drive 7.6, when the operator supplies a key
and group B is kept, adds one `explore` consult and records the subagent's reported `model`; the
review-agents control states that on a provider runner the review agents may not run.

**Other writers of `Agent.config` (review 2026-09-28, finding 14).** `POST /agents/register`
(`agents.py:2288-2334`) merges a raw `config` dict with no validation, so the PATCH check alone does
not guarantee a stored value is well-formed. So:

- the PATCH check first requires a **list** (`"code-review"` as a string is refused, not iterated
  character by character), then the closed vocabulary;
- the renderer filters the stored value to the closed vocabulary at render time, and ignores a
  non-list, so a value stored by another writer can only narrow the bullet, never inject into it.

## D9 — The built-in GitHub MCP server as a per-agent toggle

- **The setting.** Agent `config.copilot_github_mcp` is a boolean, default false. The Copilot argv
  builder omits `--disable-builtin-mcps` when it is true. R2: that builder is slice 2's
  `copilot_acp.build_acp_argv(...)` (its D3), not an adapter `build_launch` (slice 1's
  `build_launch` is a stream-transport member), and it must be given the agent's config. **(rebase
  at IMPL: `a-copilot-agent-runs-over-acp` unbuilt at R2.)** R3: the builder runs inside the RPC
  transport's `run_turn`, which receives only slice 1's `RpcTurnRequest` (`cli, cwd, env, prompt,
  model, resume_session_id, yolo, mcp_command, config_overrides, permission_mode, workspace,
  extra_flags, restrict_spec_writes`). None of those carries an agent setting, so the toggle needs
  one field. Slice 1's D16 (R3) fixes it as `RpcTurnRequest.agent_config: Mapping = {}`, which this
  change adds and the trigger fills from the agent's config; `copilot_acp.run_turn` reads
  `agent_config.get("copilot_github_mcp", False)` and passes it as the keyword `github_mcp: bool` to
  both `build_acp_argv` and `decide_permission` (below). An empty default leaves slices 1–2
  byte-identical. (contract reconciliation, 2026-09-28: R3 here asked for a `github_mcp: bool` request field; slice 1 owns the
  request's shape and had fixed `agent_config` for this need, so this change adopts it.)
- **The decision.** A permission request for the `github-mcp-server` is an MCP-kind request.
  - **R2: `_decide` would allow it, which is why the rule is needed.** R1 wrote that `_decide` "has
    no ground to allow it". It has, by default: `_decide` (`mcp_server.py:1543-1592`) refuses only
    through a path key (`_PATH_KEYS`) or a `command` it can read, and otherwise returns
    `{"allow": True, "reason": "inside your workspace"}`. A GitHub tool's input (`owner`, `repo`,
    `title`, `body`) has neither. Slice 2's D8 maps every foreign MCP request onto
    `_decide("mcp__<server>__<tool>", args)` under `workspace`, so without this rule a Copilot agent
    under Workspace only would open issues on GitHub as the operator with no card. Test 1.13's
    fail-before evidence is exactly that `allow`.
  - So under `workspace`, with the toggle on, the rule answers a request whose reported server is
    not `agentweave` (review fixes 2026-09-28: not only `github-mcp-server`, see below) with
    slice 2's `ASK_OPERATOR` outcome **before** `_decide` is reached. The client then holds the
    request and waits on the operator through `_await_operator_permission`
    (`agent_trigger.py:2977`), bounded by `AW_DECISION_TIMEOUT`, a timeout denying.
  - Under `acceptEdits` (slice 2 emulates it and refuses every foreign MCP request) it stays
    refused.
  - Under full access (`allow_all`) it is allowed as everything else is.
  - Under `manual` it goes to the operator anyway.
  - **Where it lives (R2 answered):** slice 2's `copilot_acp.decide_permission(params, *, posture,
    workspace, hub_url, calls)` (contract reconciliation, 2026-09-28: R2 wrote `mcp_server_names`), a pure function in the Hub process that calls
    `_decide`. It is not in `mcp_server.py`, so `.claude/rules/mcp-server.md`'s import restriction
    does not apply, and `mcp_server.py` is unchanged. The server name comes from slice 2's per-turn
    `calls` map (`toolCallId → CallFacts(tool_name, mcp_server, mcp_tool)`), fed **first** by the raw
    `tool.execution_start` (`mcpServerName`) and otherwise by `permission.requested` (slice 2 D8 R3;
    review fixes 2026-09-28 corrected R2's "fed by `permission.requested`").
  - **An unidentified server is refused, not asked (DECIDED 2026-09-28, closing Open question 11).**
    Slice 2 REJECTs a `kind:"other"` request whose server Copilot did not report ("Copilot did not
    report which server this tool belongs to"), at its identify step, **before** this rule runs, in
    every posture and whatever the toggle. This rule applies only to requests whose server Copilot
    reported. R2's premise (unidentified → foreign → `_decide` → allow) is no longer slice 2's
    behaviour, and the R2/R3 bullet that treated an unidentified server as `github-mcp-server` is
    removed. Reasons (review 2026-09-28): a GitHub-labelled card on a request whose server the Hub
    could not establish would assert something the Hub does not know; the toggle should only ever
    widen access to the server it names; and an unidentified request is rare (a dropped or omitted
    raw event), and a refusal costs the model one retry.
  - **The rule matches everything that is not `agentweave`, not the name `github-mcp-server`
    (review fixes 2026-09-28, finding 4).** R1–R3 asked only when the reported server was exactly
    `github-mcp-server`, and every other foreign server fell through to `_decide`, which allows it
    (`mcp_server.py:1573-1592`). The risk is a GitHub call not named `github-mcp-server` being
    allowed: Copilot's built-in list comes from the native `githubMcpGetBuiltinServerNames()`
    (plural, not visible in `app.js`), and omitting `--disable-builtin-mcps` enables all of it. So,
    **with the toggle on, under `workspace`, every MCP request whose reported server is not exactly
    `agentweave` is `ASK_OPERATOR`**. With the toggle off, slice 2's rows stand unchanged. A
    non-GitHub server mistaken for GitHub is now harmless (it asks, under its own name), and GitHub
    mistaken for something else cannot be allowed. Task 1.1(c) records the `mcpServerName` Copilot
    reports for the built-in server.
  - **The toggle is read as `is True`** (review 2026-09-28, finding 14): `POST /agents/register`
    stores a raw `config`, and `"false"` as a string is truthy. `run_turn` passes
    `agent_config.get("copilot_github_mcp") is True`.
  - **Pre-approval flags bypass the card (finding 11, stated).** A copilot runner's `flags` could
    carry `--allow-tool …`, `--allow-all-tools` or `--enable-all-github-mcp-tools`, which pre-approve
    GitHub tools inside Copilot with no permission request, so no card. Flags are operator-set, so
    this is the operator's authority, not an exploit; runner management is where it is set, and the
    toggle's help text says a runner's pre-approval flags override it.
  - R3: slice 2's signature (its D8 R3) is `decide_permission(params, *, posture, workspace, hub_url,
    calls)` (`calls` replaced `mcp_server_names`; contract reconciliation, 2026-09-28); nothing in it says whether the toggle is on.
    This change adds the keyword `github_mcp: bool = False`, fed from
    `RpcTurnRequest.agent_config["copilot_github_mcp"]`. The rule sits after the
    `agentweave` row and before the foreign-MCP row of slice 2's table, and nowhere else. With the
    toggle off the built-in server is disabled and no workspace servers load (untrusted folder,
    D3), so no foreign MCP request is expected at all, and slice 2's rows stand unchanged.
  - **The card must not carry `_decide`'s verdict (R3, re-derived against the card as it exists).**
    A permission card has no reason or verdict field today: `PermissionRequest` stores `tool_name`
    and `tool_input` (`db/models.py:1618-1635`), and `_await_operator_permission` fills `tool_name`
    from a label table (`agent_trigger.py:3001`). `an-ask-me-card-says-what-workspace-only-would-decide`
    (unbuilt) adds `workspace_verdict {allow: bool, reason}`, which slice 1 routes through
    `RpcTransport.workspace_verdict(method, subject, workspace) -> Optional[dict]` (its D3, "`None`
    on failure"), and slice 2 fills from its `workspace` column. A two-valued `allow` cannot say
    "Workspace only would ask you", and for a GitHub request slice 2's column, computed without this
    rule, is `_decide`'s allow. So:
    - the Copilot `workspace_verdict` for a request this rule sends to the operator is **`None`**,
      under `workspace` and under `manual` alike, so the card shows no verdict line;
    - the card's `tool_name`, from slice 1's `permission_card_label(method, subject)`, is
      `github-mcp-server/<tool> — acts on GitHub as you`, which is where the sentence the spec
      requires is carried (well inside the column's 128 characters for any tool name Copilot's
      GitHub server has);
    - (review fixes 2026-09-28, finding 4) the label is built from the **reported** server name.
      Only a request reported as `github-mcp-server` gets the GitHub sentence; any other server this
      rule asks about gets `<server>/<tool> — a tool of MCP server <server>, not the Hub's`
      (truncated to the column's 128 characters), so a card never claims GitHub for a server that
      is not GitHub. Its `workspace_verdict` is `None` too.

    This depends on no field of the ask-me change. R2's longer sentence ("The Hub does not decide
    GitHub actions on your behalf") had nowhere to live and is dropped. **(IMPL pre-check,
    2026-10-03: VERIFIED-CODE. `an-ask-me-card-says-what-workspace-only-would-decide` is archived;
    `PermissionRequest.workspace_verdict` (`db/models.py:1648`) and the adapter's
    `permission_card_label`/`workspace_verdict` members (`runner_adapters/base.py:237,244`) exist.
    The GitHub-specific case in both is still this change's own unbuilt task 5.1/1.6, not a gap in
    the sibling changes.)**
- **When the server fails to start (R2 correction).** R1 said slice 3's MCP status handling
  surfaces a failed GitHub server. It does not: slice 2's D10 reports only a failure of the server
  named `agentweave`, and slice 3 reads the same status for `agentweave` only. With the toggle on
  and the server failing (a BYOK agent with no GitHub login, or a policy that blocks it), the
  operator would see nothing. So group D adds one mapping: a raw `session.mcp_servers_loaded` /
  `session.mcp_server_status_changed` naming `github-mcp-server` in a state other than connected,
  **while the toggle is on**, gives one `diagnostic_event(code="copilot.github_mcp_unavailable",
  summary=…, severity="warning", stream="copilot")` per turn. With the toggle off the server is
  disabled on purpose and nothing is reported.
  - **R3: "other than connected" is too wide.** The schema's `McpServerStatus` includes `pending`,
    *"still being established"*, which a slow server reports before `connected`. Reporting it would
    tell the operator the server is unavailable on every slow start. The diagnostic fires for
    `failed`, `needs-auth`, `disabled`, `stopped` (which the schema says a managed policy can pin)
    and `not_configured`, and never for `pending` or `connected`.
  - **R3: delivery is unmeasured.** Slice 3 subscribed `session.mcp_servers_loaded` and saw none
    within its prompt-less window (its D9). Task 1.1's run (c) therefore starts **without**
    `--disable-builtin-mcps` under a home with no GitHub sign-in, so the GitHub server should fail,
    and records whether and when a status event names it. If none arrives within a turn, this
    diagnostic cannot fire: it is removed from the change and the spec, and the operator is told
    that a failed GitHub server shows only as tool calls that never happen. **Operator decision,
    2026-09-28: accepted** (Open question 8). No other signal is built in its place.

## D10 — Independence of the groups

- **A** touches `runner_events.py`, `checkpoint_trigger.py`, `output_recording.py` and the Copilot
  mapper.
- **C** touches runners (schema, route, migration, UI), `get_agent_config`, `resolve_agent_env` /
  the Copilot `guard_env`, the adapter's `launchability`, the probe-config sites (D7), the per-run
  override check (`agent_trigger.py:1618`) and the spawn's model resolution (`:802`, R3), and the
  composer's model control. Review fixes 2026-09-28 add: the one-shot spawns' environment and
  model (`one_shot_env`, the three checkpoint sites, the titler, `PATCH /projects`'s
  `checkpoint_model`), the per-run exact-value scrub (`run_secrets`, `record_agent_output`,
  `_await_operator_permission`, `Run.error`), and the Runners page's model picker.
- **Not cuttable with any group:** the strip of `COPILOT_PROVIDER_*`, `COPILOT_MODEL`,
  `COPILOT_OFFLINE` and `COPILOT_ALLOW_ALL` from every Copilot spawn that names no provider. It is
  asked of slice 2 (*Required*, 2.9 and 2.10); task 2.8 here adds whatever of it slice 2 did not,
  and survives a REJECT of any group (review 2026-09-28, finding 6).
- **B** touches the context renderer, `review_turn.py`, `ROSTER_CONFIG_KEYS`, and the agent
  Settings UI.
- **D** touches slice 2's argv builder and `decide_permission`, slice 1's `RpcTurnRequest`
  (`agent_config`, reconciled 2026-09-28) and its Copilot `permission_card_label` / `workspace_verdict`, the Copilot
  mapper (one diagnostic), `ROSTER_CONFIG_KEYS`, and the agent Settings UI.

B and D share one UI section and one tuple. Each adds its own control and its own key, so rejecting
one leaves the other's standing. No group's test imports another group's code. R2: groups A and D
both use `diagnostic_event`'s widened shape (D5); if A is cut, D's task 5.1 widens it.

## Required of slices 1–4 (R3, the cross-slice contract)

Slice 1 (`each-runner-cli-is-one-adapter`) is the authority on adapter and transport member names,
slice 2 (`a-copilot-agent-runs-over-acp`) on what the ACP client, executor and permission handler
provide, and slice 3 (`a-run-reaches-the-hub-without-mcp`) on the shim. This change uses their names
as their designs stood on 2026-09-28 (all four in concurrent R3, all unbuilt at `fc33ff9`; read,
never edited). R3 re-verified R2's 16 rows against those designs: 9 are resolved in the siblings'
own text or need nothing from them, and are dropped; the rest, plus four R3 found, are below. Each
item is **needed** (the sibling should add it), **owned here** (this change adds it if the sibling
has not), **correction** (sibling text that is wrong about this change), or **nothing required**.

### Slice 1 — `each-runner-cli-is-one-adapter`

| # | Item | Kind |
|---|---|---|
| 1.1 | **Drop the reserved `hooks` row of D16.** This change writes no hook file (D2), and D16's own rule is that no member exists without a caller. | correction; **done** in slice 1's R3 D16 (contract reconciliation, 2026-09-28) |
| 1.2 | **D16's `hooks` row also says slice 5 reads `provider_config` "in Copilot's spawn argv" through "a `RpcTurnRequest` field slice 5 adds".** It does not. `provider_config` reaches `launchability` through its existing `config: Mapping`, and reaches the environment through `resolve_agent_env(runner, config)` (D7). The argv's `--model` is `RpcTurnRequest.model`, which is already the runner's (D7, spawn). No `provider_config` field on `RpcTurnRequest`. | correction; **done** in slice 1's R3 D16 (contract reconciliation, 2026-09-28) |
| 1.3 | **`guard_env(proc_env, env_vars)` needs the runner's `config`** (keyword `config: Mapping`, or at least `provider_config`), because the Copilot guard sets or strips the provider variables from it (D7). Claude and Codex ignore it. If slice 1 lands without it, this change adds `provider_config: Optional[Mapping] = None` as a keyword with that default. | **provided** by slice 1's R3 as `guard_env(proc_env, config)` (contract reconciliation, 2026-09-28) |
| 1.4 | ~~`RpcTurnRequest.github_mcp: bool = False`~~ → **slice 1's `RpcTurnRequest.agent_config: Mapping = {}`** (its D16 R3), filled by the trigger from the agent's config; `run_turn` passes `agent_config.get("copilot_github_mcp", False)` as the `github_mcp` keyword of slice 2's `build_acp_argv` and `decide_permission` (D9). An empty default keeps slices 1–2 unchanged. | owned here; name adopted from slice 1 (contract reconciliation, 2026-09-28) |
| 1.5 | `catalog_provider` stays a `ClassVar`. This change does not ask for a per-runner provider: it checks a provider runner's model itself at the four sites in D7. If slice 1 ever makes it per-runner, those sites collapse onto it. | nothing required |
| 1.6 | The Copilot `permission_card_label(method, subject)` returns `github-mcp-server/<tool> — acts on GitHub as you` for a request D9 routes to the operator (review 2026-09-28: `<server>/<tool> — a tool of MCP server <server>, not the Hub's` for any other reported server), and `workspace_verdict(method, subject, workspace)` returns `None` for it. Both members are slice 1's; their Copilot bodies are slice 2's, with this change's case. | owned here |
| 1.7 | (review 2026-09-28, finding 1) **`one_shot_env(purpose)` needs the runner's `config`** (as `guard_env(proc_env, config)` has it), carrying `provider_config`, so a checkpoint, handover or title spawn on a provider runner gets the provider's variables and one on a plain runner gets them stripped. Claude and Codex ignore it. If slice 1 lands without it, this change adds `config: Optional[Mapping] = None` as a keyword with that default. | **provided** in slice 1's D16 as `one_shot_env(purpose, config: Optional[Mapping] = None)` (consistency pass, 2026-09-28) |
| 1.8 | (review 2026-09-28, finding 14) **`RpcTurnRequest.env` is `field(repr=False)`**: it carries the BYOK key (and today's tokens) for the run, and a dataclass `repr` in any log line would print it. | **provided** in slice 1's D3 and D16 (consistency pass, 2026-09-28) |

### Slice 2 — `a-copilot-agent-runs-over-acp`

| # | Item | Kind |
|---|---|---|
| 2.1 | **`diagnostic_event` lacks `stream`.** Slice 2 ships `diagnostic_event(*, code, message, severity="info", facts=None)` (its D10). `agent-stream-events` *Versioned kind-specific payloads* requires diagnostic payloads to *"identify stream and severity"*, and that applies to slice 2's own `Warning:`/`Info:`/model-substitution diagnostics. Add `stream` (keyword) and write it into the payload. This change adopts slice 2's parameter names and, if slice 2 lands without `stream`, adds it with a default (D5). | needed; **provided** by slice 2's R3 as `diagnostic_event(*, stream, severity, summary, code=None, facts=None)`; this change uses `summary=` (contract reconciliation, 2026-09-28) |
| 2.2 | **D10's sentence about slice 5 is stale:** *"Slice 5 (its D5) later re-maps a raw `session.error` to a `diagnostic_event(severity="error")` and suppresses the echoed `Error:` block in either order."* Since R2, slice 5 records `session.error` as an **`error_event`** with facts, not a diagnostic. Since R3, it drops the echo at the **chunk**, not the block, relying on the raw-first order (VERIFIED-CODE), and deletes slice 2's `Error:` → `copilot_session_error` branch (D5). | correction; **done** in slice 2's R3 D10 (contract reconciliation, 2026-09-28) |
| 2.3 | **The mapper must see the whole `github.com/copilot/sessionEvent` params**, including `agentId` and `dataOmitted`, not only `{sessionId, type, timestamp, data}` as slice 2's VERIFIED row describes the envelope. D4 ignores a subagent's compaction by `agentId` and handles an oversized `session.compaction_complete` by `dataOmitted`. `on_raw_event(type, data)` loses both; this change does not use it. | needed; **provided** at contract reconciliation, 2026-09-28: slice 2's `_on_armed_raw_event(type, data, params)` hands the whole params to `CopilotEventMapper` |
| 2.4 | **`COPILOT_RAW_EVENTS`**: this change appends `subagent.started`, `subagent.completed`, `subagent.failed` and `session.compaction_start`, and ensures `session.compaction_complete` and `session.error`, relying on slice 2's de-duplication in first-seen order (D1). | nothing required |
| 2.5 | **`decide_permission` gains a keyword `github_mcp: bool = False`** from this change (D9). This change's rule sits between the `agentweave` row and the foreign-MCP row of slice 2's D8 table. | owned here |
| 2.6 | **The Copilot `workspace_verdict` is `None` when this change's rule routes the request**, under `workspace` and `manual` alike. Slice 2's D8 fills the verdict from its `workspace` column, which for a GitHub call is `_decide`'s allow. Unchanged, the ask-me card would read "Workspace only would allow this" on a card raised because Workspace only does not. | needed / owned here |
| 2.7 | **D3's hand-off of an MCP `env` filter** ("whichever lands the BYOK variables adds that filter") is declined here, with reasons (D7): the key is in every shell command's environment anyway, and a blanking `env` map breaks the tool server if Copilot's `env` replaces rather than merges (Open question 10). Slice 2 should reword the sentence as an open question, not an obligation. | correction; **recorded** in slice 2's D3 and item 16 (contract reconciliation, 2026-09-28) |
| 2.8 | Slice 2's non-`connected` `agentweave` status report has the same `pending` hazard D9 found (the schema's `McpServerStatus` has `pending`). Slice 3 now owns that report (its D9). | observation |
| 2.9 | (review 2026-09-28, finding 6; **decided: slice 2 owns it**) **Strip `COPILOT_ALLOW_ALL`** from every Copilot spawn's environment (the Copilot `guard_env` and `one_shot_env`), from both the ambient environment and the agent's `env_vars`, under every posture. Otherwise an operator's shell or an agent's `env_vars` trusts the folder and loads the repository's hooks and `.mcp.json` servers into the run (D3). Test 1.6 here asserts it. | needed (slice 2's) |
| 2.10 | (review 2026-09-28, finding 6) **Strip every `COPILOT_PROVIDER_*` name, `COPILOT_MODEL` and `COPILOT_OFFLINE`** from every Copilot spawn's environment, both sources, beside 2.9. It must not depend on this change's group C surviving: without it an ambient `COPILOT_PROVIDER_BASE_URL` turns every subscription run into BYOK. This change's `copilot_provider_env` then only sets the four for a provider runner (D7). If slice 2 lands without it, this change's ungrouped task 2.8 adds it. | **provided** in slice 2's D3 and § *Provided* item 18 (consistency pass, 2026-09-28) |
| 2.11 | (review 2026-09-28, finding 8; **decided: slice 2 owns it**) **Only a root `session.error` fails the turn.** Slice 2 R3 (`design.md:770-780`) ends the turn `failed` on any armed `session.error`. A subagent's error (envelope `agentId`, else `data.agentId`/`data.parentToolCallId`, Copilot's `_d()`) must not: with group B a failed `code-review` subagent would fail, re-queue and re-bill the reviewer's turn and, under slice 4, possibly hold the queue. Test with a captured or synthetic subagent error. | needed (slice 2's) |
| 2.12 | (review 2026-09-28, finding 16) **Stale sentence:** slice 2 `design.md:763-768` still says slice 5 "holds an `Error:` block until prompt completion so the echo is dropped in either order". That is R2's design, replaced in R3 by a chunk match at arrival (D5); 2.2 above is marked done while this sentence remains. Reword at slice 2's next touch. | correction; **done** in slice 2's D10 (consistency pass, 2026-09-28) |
| 2.13 | (DECIDED 2026-09-28) Slice 2's identify step REJECTs a request whose server Copilot did not report **before** D8's step 3, so this change's rule never sees one. Slice 2's text already says so (its D8, *Identifying the MCP server*, item 3); its open question 12 can be closed. | nothing required; **already closed** in slice 2's open question 12 (review ghcp-s2) |

### Slice 3 — `a-run-reaches-the-hub-without-mcp`

| # | Item | Kind |
|---|---|---|
| 3.1 | No "hook call mode" is needed. D2 installs no hook (DECIDED 2026-09-28: none). Its overrule path, not built, would need its own stdin mode and tool, which slice 3's closed, stdin-refusing call mode rightly does not offer. | nothing required |
| 3.2 | A failed **GitHub** server is reported by this change's mapper (D9), not by slice 3's `agentweave`-only status handling. | owned here |
| 3.3 | Open question 10 (does a stdio `env` block replace or merge the inherited environment) decides what reaches the tool server, which is slice 3's subject. If slice 3 settles it, D7's declined filter can be revisited. | nothing required |

### Slice 4 — `a-copilot-run-shows-its-credits`

| # | Item | Kind |
|---|---|---|
| 4.1 | Quota holds stay slice 4's (its D8). This change's requirement says only that *recording* an error places or lifts no hold. | nothing required |
| 4.2 | Slice 4 resolves `compaction_percent` inside `consider` (its D10 *Callers*), so the compaction path gets the same policy with no plumbing (D4). | nothing required |
| 4.3 | Under BYOK, Copilot's credits are probably 0 and the provider bills tokens (Open question 6). Slice 4's design does not mention BYOK; it should not present 0 credits as free. | needed (carried) |

### Other open changes named above

- `an-ask-me-card-says-what-workspace-only-would-decide`: nothing required. The GitHub card gets no
  verdict (`None`), so its two-valued `allow` is never asked to say "would ask" (D9).
- `worker-spend-counts-against-the-budget` (its D3a) and `a-run-records-that-its-calls-were-allowed`:
  rebase notes in D4 and D3.
- Migration order: slice 2 adds one (widening `ck_runners_cli`). The head is `0110` at `fc33ff9`. C's
  migration takes the next free number in build order.

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

- **R2, 2026-09-28** (Opus, independent re-derivation from the code, not from R1's text).
  - **Drift, stated plainly.** R1 read master `97b86ed`. R2 read `ef55e6f`. Only 5 of the
    2026-09-27 night ORDER's 28 changes have landed (`a-runner-choice-names-its-model`,
    `an-estimate-that-misses-turns-says-so`, `a-model-alias-is-a-model-choice`,
    `the-codex-models-offered-are-the-ones-its-cli-lists`,
    `a-firing-is-counted-once-however-many-agents-it-starts`). **Slices 1–4 are all unbuilt**, each
    in its own R2 concurrently. `git log 97b86ed..HEAD` over every file this design cites: only
    `model_catalog.py` (`63d9f34`, `3b3563a`) and `api/v1/agents.py` (+4 lines at `:707`) moved.
    Nothing here pretends a slice landed: every dependency is marked *(rebase at IMPL: … unbuilt at
    R2)*, and the new section *Dependencies on slices 1–4, as written at R2* tabulates 16
    mismatches against those slices' designs as written today.
  - **Code read at `ef55e6f`:** `output_recording.py` (all); `checkpoint_trigger.py:150-410`;
    `runner_events.py:1-260`; `review_turn.py:40-70,240-293`; `task_integration.py:148-192`;
    `api/v1/agents.py:540-560,622-660,1609-1640,1718-1800,2562,2686,2940-2985`;
    `api/v1/runners.py` (all); `schemas/runners.py` (all); `launchability.py:54-196`;
    `model_catalog.py:140-470,532-560` and the `97b86ed..HEAD` diff; `mcp_server.py:1543-1600,
    1698-1720`; `api/v1/agent_trigger.py:745-775,1168-1196,1400-1420,1618,2977-3017,3135-3160`;
    `db/models.py:330-342,1130-1175,1645-1656`; `src/agentweave/stream_events.py:550-573`;
    `hub/ui/src`: `AgentOutputPanel.tsx:600-760`, `AgentTimeline.tsx:480-560,795-840`,
    `streamModel.ts:20-40`, `grep checkpoint_due` (no hits), the settings components' config reads.
  - **Specs read:** `agent-stream-events` (*Versioned kind-specific payloads*, *Tool and diagnostic
    presentation*), `runtime-diagnostics` (diagnostic requirements).
  - **Other designs read:** slice 1 (all), slice 2 `:85-883`, slice 3 `:120-170` + grep, slice 4
    grep for its `session.error`/compaction/hold/threshold decisions,
    `every-event-the-hub-sends-reaches-the-app` (`checkpoint_due` rows),
    `a-file-path-is-not-redacted-as-a-credential`, `an-ask-me-card-says-what-workspace-only-would-decide`,
    `a-claude-run-is-told-its-agentweave-tools-by-their-full-names`,
    `a-flow-stages-its-review-in-the-dispatch` (greps).
  - **Copilot (no process spawned):** 1.0.88 `session-events.schema.json` parsed for the six
    definitions' required/optional fields; `app.js` read around `applyAllowAll`,
    `resolveTrustDeclaration`, `folderTrustIsTrusted` and `loadDeferredRepoHooks`.
  - **Wrong in R1, and changed:**
    1. **D4: the `"compacted": true` flag and "the banner says the runner compacted it" could never
       be seen.** No UI code reads `checkpoint_due`; the banner is a fixed sentence from the
       persisted `checkpoint_warning`; an already-`due` warning broadcasts nothing. Dropped from the
       design, the spec scenario, tests 1.4 and drive 7.2; a banner variant is now operator question.
    2. **D4: a compaction arriving while a reading is being considered was silently dropped**
       (`_in_flight`, `checkpoint_trigger.py:382-383`), which is the backstop failing in its own
       case. Now held in `_compaction_pending` and re-dispatched. New scenario and test.
    3. **D4/D6: `status_event` takes no facts, and routing facts through `redact_secrets` would
       redact every `*_tokens` key** (`_SECRET_FIELD_RE` matches `token`). Builder extended; value
       rule only; test 1.2 pins the integers.
    4. **D5: `session.error` as a `diagnostic` broke `agent-stream-events`** ("Errors SHALL remain
       prominent … diagnostics hideable"). It is now an `error` event with facts. The `diagnostic`
       builder follows the CLI's `{stream, severity, summary}` shape the existing spec requires.
       `error_event`'s message was never redacted; now it is.
    5. **D5: "suppress in either order" was impossible as written** — slice 2 flushes text blocks
       mid-turn, and a flushed block is committed. `Error:` blocks are now held to prompt completion.
    6. **D7: aliases are no longer refused by the existing rule** (`63d9f34` made `haiku` an
       accepted choice). The BYOK rule checks ids itself, with its own sentence.
    7. **D7: `openai` → the `codex` catalog is unsound after `3b3563a`** (a per-machine ChatGPT-plan
       CLI cache, not API ids). `openai` is deferred with Azure; `anthropic` only.
    8. **D7: "slice 2 builds the MCP `env` as an allow-list" is false**; slice 2 sets none and the
       tool server inherits the key. The runner-registry requirement no longer claims the key stays
       out of the tool server; the exposure is stated.
    9. **D7: the BYOK launchability verdict could not reach any surface** — six call sites build the
       probe config from `runner`+`model` only. One helper; test 1.8 goes through the routes.
    10. **D7: four sites choose a runner's model catalog by CLI** (create/PATCH check, response
        flag, per-run override, composer). A provider runner would be refused its own model or
        flagged unrecognised. Listed; per-run model overrides refused on a provider runner.
    11. **D8/D9: the settings had no read path** — the roster filters config to
        `ROSTER_CONFIG_KEYS`. Each group adds its key.
    12. **D9: `_decide` does allow a GitHub tool call** ("inside your workspace": no path, no
        command). R1's premise was inverted; the rule is needed *because* of that, and is placed
        before `_decide` in slice 2's `decide_permission`.
    13. **D9: nobody surfaces a failed GitHub server** (slice 2/3 watch `agentweave` only). Group D
        adds one diagnostic while the toggle is on.
    14. **Drive 7.4/7.8 read a "recorded argv/environment" that does not exist** (`Run` stores
        neither). 7.8 reads the live process's command line; 7.4's environment half is left to
        test 1.6.
    15. Smaller: D2's fallback needs a hook-receiving tool (slice 3's `--call` calls tools only);
        task 1.1's argv lacked slice 2's `--stdio`; line numbers corrected where they moved or
        were off (`checkpoint_trigger.py:382-383`, `AgentOutputPanel.tsx:720-721`,
        `runner_events.py:28,57-60,63-81`, `agents.py:1724-1787`, `model_catalog.py:149-155,
        432-446`).
  - **Held after checking:** D1's supersession (schema fields confirmed, plus `cancelled`,
    `error`); D3's four prohibitions; D4's table rows against `consider` (`:156-362`);
    `CHECKPOINT_TRIGGERS` and `ck_checkpoints_trigger` (`db/models.py:1649-1655`, `:1807`);
    `context_pressure` as the offered trigger (`AgentOutputPanel.tsx:617-619`); the review
    renderer's structure; `ROSTER_CONFIG_KEYS` at `:651`; `POST /permission-decisions` at
    `agent_actions.py:971`; migration head `0110`.
  - **Open questions answered:** 1 (slice 2's list, `Error:` classification site and
    `decide_permission`, above and in the dependency table), 3 (`allow_all` does not trust the
    folder, VERIFIED-CODE), 4 (`Project.main_branch` + a new merge-base in `prepare_review_turn`;
    `ReviewContext` gains `base_sha`), and drive 7.2's condition (no bare `/compact` reaches
    Copilot). **Carried:** 2 (delivery: task 1.1), 5 (Claude's `compact_boundary`: out of scope,
    not filed), 6 (to slice 4), 7 (drive 7.7), 8 (operator, now also: a banner variant after a
    compaction; OpenAI BYOK deferred), and new 9 and 10 below.
  - **Cross-slice gaps reported, not fixed here** (other agents own those directories): slice 2's
    `diagnostic_event(code, message)` lacks the `stream`/`severity` the existing spec requires;
    slice 2's `decide_permission` lets a foreign MCP tool with no path through under `workspace`
    (true for any foreign server, not only GitHub; Claude's approver does the same today); slice 1
    D16 reserves a `hooks` member no slice will add; slice 1's `catalog_provider` cannot express a
    per-runner catalog; `an-ask-me-card-says-what-workspace-only-would-decide` would put an
    "allow" verdict on a card raised because Workspace only does not allow.
  - **Routes, what they return when the called function raises** (R3 re-derives): `PATCH
    /agents/{name}` with bad `copilot_review_agents` → 400 before the merge, nothing stored;
    `POST`/`PATCH /runners` with bad `provider_config` → 400 string `detail`, nothing stored;
    `record_agent_output` → the dispatch never raises, so `POST /agents/{name}/output` stays 201;
    `prepare_review_turn` → a failed merge-base yields `base_sha=None`, never a refusal.

- **R3, 2026-09-28** (Opus, a second independent re-derivation; R2's entry read only after).
  - **Base.** master `fc33ff9`. `git log ef55e6f..fc33ff9` touches only the five slices' change
    folders, so every product line R2 cited still holds; R3 re-read them rather than trusting that.
    Slices 1–4 are still unbuilt, and their designs were being edited concurrently (read, never
    edited). Every "(rebase at IMPL)" site was re-checked and kept.
  - **Code read at `fc33ff9`:** `checkpoint_trigger.py` (all), `output_recording.py` (all),
    `runner_events.py:20-82,100-318`, `review_turn.py:40-70,236-293`, `task_integration.py:145-160`,
    `launchability.py:54-198,469-535`, `api/v1/runners.py` (all), `schemas/runners.py` (all),
    `schemas/agents.py:319-335`, `schemas/common.py:21-32`, `model_catalog.py:145-158,432-446` and the
    live `CATALOG["claude"]` ids, `mcp_server.py:1543-1592`, `api/v1/agents.py:205-240,545-560,
    712-733,1720-1790,1995-2010,2958-2980`, `api/v1/agent_trigger.py:715-770,790-810,840-850,
    950-975,1596-1625,2977-3007`, `api/v1/inbound_queue.py:205-228`, `db/models.py:1618-1635`,
    `conversations.py` (grep `runtime_overrides`), `checkpoint_cutover.py:182`; `hub/ui/src`:
    `AgentTimeline.tsx:490-530,806-822`, `lib/agentTimelineModel.ts:1-28`, `AgentOutputPanel.tsx`
    (grep), `api/agents.ts:384`, grep `checkpoint_due` (still no reader); CLI
    `stream_events.py:556-573`.
  - **Copilot (no process spawned):** 1.0.88 `schemas/session-events.schema.json`, parsed for
    `CompactionStart/CompleteData`, `ErrorData`, `Subagent{Started,Completed,Failed}Data`, the six
    `*Event` envelopes, `CompactionTrigger`, `RemediationAction`, `McpServerStatus`,
    `McpServersLoaded*`, `McpServerStatusChangedData`; `app.js` around the raw-event passthrough
    (`bDn`, `LDo`, `sendRawEventNotification`, `setupEventForwarding`), `mapEventToACPUpdate`'s
    `session.error` case, `newSession`/`hasSessionCredential` and the ACP server's
    `providerContextId`.
  - **Sibling designs read:** slice 1 (tables and D10, D14–D16), slice 2 (D3, D4, D8, D10, D15),
    slice 3 (D4, D9, its slice-5 items), slice 4 (D1, D8, D10, its slice-5 note),
    `worker-spend-counts-against-the-budget` D3a, `an-ask-me-card-says-what-workspace-only-would-decide`
    (grep).
  - **D1 re-derived from the schema:** the raw event still supersedes the hook for every fact
    (compaction: success, counts, window, trigger; errors: category, code, status, remediation;
    subagents: model, tokens, duration, tool calls, cancelled). Held.
  - **D4 re-derived row by row:** every row holds; one row added (automatic with no checkpoint
    runner).
  - **Wrong before R3, and changed:**
    1. **D5: R2's `Error:` hold could not work, and was not needed.** The raw event is sent before its
       echo (VERIFIED-CODE), and the echo is one chunk appended to whatever block is accumulating,
       so a block that began with model prose escaped R2's "begins `Error:`" rule and slice 2's
       classifier would have made a second error event of it. Now: exact-text match on the chunk at
       arrival, no hold; the test follows the real order; the spec drops "whichever arrives first".
    2. **D1/D4: an oversized raw event loses its whole `data`** (`LDo`), so a large compaction arrives
       with no `success` and no counts. It now counts as a compaction, with counts from
       `session.compaction_start`; a mapper keyed on `success is True` would have missed exactly
       the large ones.
    3. **D4: a subagent's compaction would have handed over the main conversation.** Envelopes carry
       `agentId`; only root events count.
    4. **D4: `trigger` values** are `threshold`, `context_limit_retry`, `manual`, `memory_pressure`,
       `model_switch`, not `auto`/`manual`.
    5. **D4: `record_agent_output`'s dispatch would raise on `payload: null`**, which
       `POST /agents/{name}/output` accepts: 500 after the commit, duplicate on retry. Guarded;
       test 1.5 posts it. Test 1.5's "no running loop through the route" was impossible (an ASGI
       route always runs in a loop); split into a route test and a direct call.
    6. **D7: 3 of R2's 6 probe sites were wrong** (`agents.py:552`/`:2004` are display code;
       `launchability.py:524` is inside `get_agent_config`). The real set is the six slice 2's D15
       lists; `get_agent_config` covers three of them. `POST /agents` (`:728`) would refuse to
       create any agent on a provider runner without GitHub sign-in. Test 1.8 now names
       `GET /agents/launchability` (`GET /agents` carries no verdict) and `POST /agents`.
    7. **D7: stored per-conversation `model` overrides reach the spawn unvalidated**
       (`agent_trigger.py:797-802`, inherited and carried through handovers). The route refusal R2
       added could not stop them; the spawn now uses the provider runner's model regardless.
    8. **D7: a runner `PATCH` that adds or removes `provider_config`** left the stored model judged by
       the wrong catalog, protected by the legacy `model == current` exemption. The pair is now
       validated.
    9. **D7: the ambient-only strip would let an agent's `env_vars` carry `COPILOT_PROVIDER_*`.**
       Stripped from both sources.
    10. **D7: no new `resolve_agent_env` parameter is needed** (the trigger's `config` already reaches
        it); the missing hop is slice 1's `guard_env` signature.
    11. **D8: an escaping `TimeoutExpired` from the merge base would 500 the trigger and leak the
        provisioned review checkout** (F326 class). Computed before provisioning; catches
        `SubprocessError`/`OSError`.
    12. **D9: the card sentence had nowhere to live** (no reason field on `PermissionRequest`), and a
        two-valued `workspace_verdict` cannot say "would ask". Label carries it; verdict `None`.
    13. **D9: "other than connected" included `pending`**, which would report every slow start.
        Narrowed; delivery made a 1.1 measurement with a removal path.
    14. **D5: `diagnostic_event`** now uses slice 2's shipped parameter names; only `stream` is asked
        of slice 2.
    15. **D7: slice 2's hand-off of an MCP `env` filter is declined** (the shell keeps the key; a
        blanking map breaks the server under replace semantics, which is unknown).
  - **R2's claims the task named, re-derived:** held — the `compacted` flag was never visible (no
    `checkpoint_due` reader in `hub/ui/src`; the banner reads the persisted warning,
    `AgentOutputPanel.tsx:653`); the `_in_flight` drop (`:382-383`) and the pending retry, with the
    addition that the pickup must be in `consider_from_reading`'s `finally` too; `redact_secrets`
    redacting `*_tokens` (`_SECRET_FIELD_RE`, `runner_events.py:28,72`); `session.error` as an error,
    not a diagnostic; BYOK checking ids itself (`ProviderDescriptor.model` resolves aliases,
    `model_catalog.py:149-155`); `openai` deferred; the MCP server inheriting the key; the GitHub rule
    before `_decide` (`mcp_server.py:1592` allows a call with no path or command). Changed — R2's
    "hold `Error:` blocks" (1), the probe-site list (6), and "`consider(..., compacted=True)` must
    pass the same policy inputs" (moot: slice 4 resolves them inside `consider`).
  - **Routes, what they return when the called function raises (re-derived):**
    - `PATCH /agents/{name}` with bad `copilot_review_agents`: a 400 raised before `_merge_patch`,
      so nothing is stored.
    - `POST /runners` with bad `provider_config`: a 400 raised by the route before `session.add`,
      so nothing is stored. No Pydantic constraint on the fields, so no 422 echoes a pasted key.
    - `record_agent_output` when `consider_from_compaction` cannot find the conversation: the
      dispatch never raises. `consider` declines a missing or closed conversation itself, and a
      raise inside it is logged by `_run`. The route answers 201 with one row, including for
      `payload: null` (5).
    - `POST /agent/trigger` with a `model` override on a provider runner: a 400 at `:1618`, before
      `conversation.runtime_overrides` is written and before any queue entry or run exists.
    - `prepare_review_turn` when the merge base cannot be computed: `base_sha=None`, no refusal, no
      500, and nothing is provisioned before it (11).
  - **Questions:** 9 answered (VERIFIED-CODE). 2 narrowed and carried. 5, 6 (to slice 4), 7, 8
    (operator, one item added) and 10 carried.
  - **Contract:** R2's dependency table (16 rows) replaced by *Required of slices 1–4*: 9 rows
    dropped as resolved or needing nothing; needed from slice 1: drop `hooks`, correct the
    `provider_config` note, `guard_env` gets `config`, `RpcTurnRequest.github_mcp`; needed from
    slice 2: `stream` on `diagnostic_event`, the stale slice-5 sentence, the whole `sessionEvent`
    params to the mapper, `None` verdict for a GitHub card, reword the `env` filter hand-off;
    nothing needed from slice 3; BYOK credits carried to slice 4.

- **Contract reconciliation, 2026-09-28** (a textual pass over the five slices' contract sections after their
  concurrent R2/R3 rounds; not a design round; no code read). Changed here:
  - D5, D9, task 2.1: `diagnostic_event` calls use slice 2's R3 signature (`stream`, `severity`, `summary`,
    `code`, `facts`): `summary=` where R3 wrote `message=`; nothing is added to the builder.
  - D7: `guard_env(proc_env, config)` is provided by slice 1 R3.
  - D9, D10, *Required* 1.4, tasks 1.13/5.1: `RpcTurnRequest.github_mcp` replaced by slice 1's
    `RpcTurnRequest.agent_config["copilot_github_mcp"]`, passed as the `github_mcp` keyword; `decide_permission`'s
    `mcp_server_names` corrected to `calls`.
  - *Required* table: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.7 marked done/provided/recorded.
  - Open question 6 points at slice 4's Q11; open question 11: **contract conflict** with slice 2 over an
    unidentified MCP server with the toggle on, left open.

- **Review fixes, 2026-09-28** (applying `spec-queue/tracks/reviews/ghcp-s5-2026-09-28.md`, Opus,
  verdict APPROVE WITH FIXES, C: REVISE). Each finding was re-checked against the code at `450de52`
  before it was applied; none was disagreed with. Code re-read: `runner_events.py:136-243`,
  `launchability.py:145-196`, `checkpoint_trigger.py:139-153`, `checkpoint_handover.py:176-188`,
  `api/v1/checkpoints.py:175-190`, `conversation_titles.py:68,203-219`, `api/v1/projects.py:475-495`,
  `worker.py:71,421-476`, `api/v1/agent_trigger.py:849,1983,2995-3010`, `output_recording.py:22-35`,
  `api/v1/agents.py:2288-2340`, `main.py` (exception handlers), `RunnersPage.tsx:160-310`; Copilot
  1.0.88 `app.js` (`grep COPILOT_PROVIDER_`, `_d()`, `KDo`'s `session.error` case, `updateSession`);
  slice 2's D8 (identify step, `calls`), D10 (`:760-780`) and D14.
  1. **BLOCKING (C), one-shot spawns bypass BYOK** — verified (`resolve_agent_env`'s only caller is
     `agent_trigger.py:849`; the four `_resolve_runner`-style sites; the titler's fallback to the
     agent's runner; `checkpoint_model` unchecked). Fixed by plumbing, not refusing: slice 1's
     `one_shot_env` takes the runner's `config` (*Required* 1.7), the Copilot `one_shot_env` calls the
     same `copilot_provider_env` as `guard_env`, and `one_shot_model` + a `PATCH /projects` check
     apply the provider rule to `checkpoint_model` (D7). Spec: the "Everywhere" sentence names the
     checkpoint, handover and title spawns; new scenario. Tests 1.8 (one-shot half) and task 3.3.
  2. **BLOCKING (C), text not redacted** — verified (`text_event`/`thinking_event` raw;
     `PermissionRequest.tool_input = dict(subject)`). Fixed: per-run exact-value scrub
     (`run_secrets`) in `record_agent_output`, `_await_operator_permission` and `Run.error` (D7). Spec
     sentence and scenario widened to permission cards and to a key of any format. Test 1.9 feeds
     text, thinking and a permission subject; task 3.5 added.
  3. **BLOCKING (C), unstripped provider variables** — verified and understated: 1.0.88 reads 15
     `COPILOT_PROVIDER_*` names, not 13. Fixed: strip the whole prefix + `COPILOT_MODEL` +
     `COPILOT_OFFLINE` from both sources, then set exactly four (D7). Spec sentence and scenario;
     test 1.8 adds `BEARER_TOKEN`, `WIRE_MODEL`, `API_KEY_COMMAND`, ambient and in `env_vars`.
  4. **SHOULD-FIX (D), name match** — verified (`_decide` allows a foreign call with no path).
     Fixed: with the toggle on, under `workspace`, every reported server not `agentweave` asks;
     label from the reported name; server source wording now `tool.execution_start` first (D9).
     Spec and test 1.13; task 1.1(c) records the built-in's `mcpServerName`.
  5. **SHOULD-FIX (D), contract conflict** — **DECIDED 2026-09-28 (with this review's application): REJECT.** Rule
     placed after slice 2's identify-step refusal; spec sentence now "is refused, as it is with the
     server disabled"; task 1.13's unidentified case is `REJECT`; the R2-premise bullet removed; Open
     question 11 closed.
  6. **SHOULD-FIX (A), `COPILOT_ALLOW_ALL`** — verified (nothing strips it). **Decided: slice 2
     owns the strip** for all Copilot spawns (*Required* 2.9); the no-provider strip is also asked of
     slice 2 (2.10) and backed here by the ungrouped task 2.8, so it survives a REJECT of C. Test 1.6
     sets it ambient and in `env_vars`. Drive 7.3's "if C was cut" fallback, which relied on the
     hole, now replays the captured error fixture.
  7. **SHOULD-FIX (A), subagent echo** — verified in `KDo` (no `agentId` test). Fixed: the echo
     matches any unmatched `session.error` of the turn; subagent test via Copilot's `_d()` (D5).
     Test 1.3 adds a subagent-error case; spec scenario added.
  8. **SHOULD-FIX (A/B), subagent error fails the turn** — verified in slice 2 `design.md:770-780`.
     **Decided: slice 2 owns it** (*Required* 2.11); referenced in D5 and D8.
  9. **SHOULD-FIX (C), Runners page picker** — verified (`RunnersPage.tsx:208-313`). Fixed: ids
     only with a provider, reset on toggling (D7); task 3.4, test 1.14.
  10. **SHOULD-FIX (C), localhost prefix and `KeyError`** — verified (`launchability.py:164-167`
      reasoning). Fixed: `urlsplit` hostname check; `.get` with an empty key that fails 401 (D7).
      Test 1.7 and 1.8.
  11. **NOTE (D/C), runner flags** — answered: a provider runner's `flags` may not carry `--model`
      (400, D7, test 1.7); D9 states that pre-approval flags bypass the card and the toggle's help
      text says so.
  12. **SHOULD-FIX (A, drive), 7.2 in the wrong process** — agreed. The script maps the fixture and
      `POST`s the event to `/agents/cp5/output` on `:8010`, so the trial Hub's own process
      dispatches the consideration.
  13. **NOTE (B), BYOK × review agents** — answered: not suppressed (B must not read C's state,
      D10); bounded by 2.11; drive 7.6 records the subagent's model when a key exists; the control
      states the limitation (D8).
  14. **NOTE (B/D), `/register` bypass** — answered: `copilot_github_mcp` read as `is True`;
      `copilot_review_agents` type-checked as a list on PATCH and filtered at render time;
      `agent_config` filled with only the needed key; `RpcTurnRequest.env` `repr=False`
      (*Required* 1.8). Tests 1.12, 1.13.
  15. **NOTE (C), 422 echo** — answered: the claim was false. `provider_config` typed as a dict and
      checked by the route with 400s naming keys, never values; `api_key_var` naming the Hub's own
      credentials refused (D7). Test 1.7.
  16. **NOTE, stale slice-2 text** — listed as *Required* 2.12 (a correction for slice 2).
  - *Checked and found sound*, one addition taken: a non-dict stored `provider_config` never 500s
    `GET /agents/launchability` (D7).
  - Operator questions: the reviewer's recommendations recorded as recommended answers in Open
    question 8; they stay operator questions.
  - Sibling changes needed (not edited here): slice 1 — *Required* 1.7, 1.8; slice 2 — 2.9, 2.10,
    2.11, 2.12, and closing its Q12 (2.13).

- **Consistency pass after review fixes, 2026-09-28** (no redesign).
  - D3: slice 2's before-spawn sweep of the home (its § *Provided* item 20) stated; checked every write of this change
    into `COPILOT_HOME`: there is none (D2, D7, D8, D9), so nothing is swept; D2's overrule path must write through
    `.agentweave-owned.json` and register its new tool with slice 3's `@_tool()`.
  - D3, D5, D7 reference slice 2's § *Provided* items 18 (trust and, now, provider strip) and 19 (root-only
    `session.error`). D7's `guard_env(proc_env, env_vars)` corrected to `guard_env(proc_env, config)`.
  - *Required of slices 1–4*: 1.7, 1.8, 2.10 marked provided; 2.12 done; 2.13 already closed.

- **Operator decisions, 2026-09-28** (interactive session; the operator said "yes" to every
  recommendation; no design round, no code read). Open question 8 is DECIDED item by item:
  1. D2, hooks: **none**. Revisit only if task 1.1 shows the raw types are not emitted over ACP, and
     even then do not pre-build the fallback.
  2. D7, Azure BYOK: **deferred**, with OpenAI; `type` stays a field.
  3. D7, OpenAI BYOK: **deferred** with Azure.
  4. D7 / task 7.6, a key for the happy-path drive: **yes, only after findings 2, 3 and 10 are
     built**, with a dedicated Anthropic workspace key, hard monthly spend limit of a few dollars,
     set only in the trial Hub's launch environment, revoked after 7.6.
  5. D7, the key in the run's shell and tool server: **accepted**, as for a proxy runner today.
  6. D4, a runner-compacted banner: **not now**; the `compacted` card is the signal; possible
     follow-up.
  7. D9, removing the GitHub-unavailable diagnostic if 1.1 finds no status event within a turn:
     **accepted**, no other signal.

  Sections changed:
  - design: D2 heading and body (decision stated; the overrule path marked **not built**, kept as a
    record); D4 (the banner paragraph: decided, follow-up); D7 (R2 `openai` paragraph, Azure
    paragraph, the shell-exposure paragraph, the "where the key could leak" bullet, a new paragraph
    on the 7.6 key's conditions); D9 (the delivery bullet: removal accepted); *Required* 3.1 (overrule
    path not built); Open question 2 (no hook fallback pre-built); Open question 8 (each item marked
    DECIDED with the operator's word; the review's heading no longer says "not decided").
  - tasks: 0.3 (decisions note), 1.1 (run (c) removal path accepted; the not-delivered branch no
    longer names a hook fallback), 1.7 (the `azure`/`openai` refusal cites the decision), 1.13 and
    5.1 (removal path accepted, and the spec text that goes with it), 7.6 (the preconditions as a
    list; the key's visibility accepted).
  - proposal: the dependency on slice 3's shim (none now); *What R1 found* (hooks decided: none;
    the name note); group C (deferrals decided; the key's visibility accepted); group D (the
    unavailable-server report is conditional on 1.1).
  - test-guide: agent-verifiable A.7; human-only 1 (hooks decided), 2 (banner decided), 3 (the 7.6
    preconditions and what the agent can see), 6 (the removal path).
  - specs: none needed. No spec builds or renders a hook (`agent-run-sandboxing` is the prohibition,
    `agent-stream-events` already says the facts do not depend on a hook process);
    `runner-registry` already offers `anthropic` only and already states that the key is visible to
    what the CLI starts; `agent-configuration`'s unavailable-server paragraph stays until task 1.1
    decides it (tasks 1.13, 5.1 say what to delete if it is removed).
  - The change's name still says "hooks" although it installs none; not renamed (proposal note).

- **IMPL pre-check, 2026-10-03** (tasks.md "Before you start": slices 1–4 and
  `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` and
  `an-ask-me-card-says-what-workspace-only-would-decide` are now archived; re-read against the
  code as built, not their R2/R3 designs). `worker-spend-counts-against-the-budget` and
  `a-run-records-that-its-calls-were-allowed` and `a-file-path-is-not-redacted-as-a-credential`
  remain open/unbuilt, so the rebase markers naming only them are left as they stand.
  - **Held, VERIFIED-CODE against the built slices** (every rebase site below is resolved in place):
    D1's `COPILOT_RAW_EVENTS` (`copilot_acp.py:94-111`) already carries `session.error` and
    `session.compaction_complete`, added by slices 2 and 4 as D1 said, and still lacks the three
    `subagent.*` types and `session.compaction_start` (this change's own task 2.2, correctly
    unbuilt); D4's claim that slice 4's `consider` (`checkpoint_trigger.py:173-200`) resolves
    `compaction_percent` internally, with no separate plumbing (confirmed: `consider_from_reading`
    passes only raw `percent`); D5's `diagnostic_event(*, stream, severity, summary, code=None,
    facts=None)` (`runner_events.py:231-238`) ships exactly those keywords; D7's `catalog_provider`
    (`runner_adapters/base.py:268`) is still a `ClassVar`; D7's `guard_env(proc_env, config)` and
    `one_shot_env(purpose, config=None)` exist on the base adapter (`base.py:297-299,333-335`) and
    the Copilot adapter (`copilot.py:248-254,283-286`), wired through `agent_trigger.py` as
    described — the adapter reads only `config["env_vars"]` today (`copilot_env.py`'s unconditional
    strip), because `provider_config`-aware behaviour is this change's own unbuilt task 3.3, not a
    sibling's gap; D7's probe move onto the adapter holds (`copilot.py:231`'s `launchability`
    method; `get_agent_config` and the other call sites are unchanged, as the note predicted); D8's
    `_render_hub_agent_context` (`api/v1/agents.py:1770-1788`) has the `runner: Optional[str] = None`
    parameter `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` added, and the review
    bullet still travels through `per_turn_context`/`_context_block` (`copilot_acp.py:1633-1661`,
    `:2254`), not the agent file; D9's `PermissionRequest.workspace_verdict`
    (`db/models.py:1648`) and the adapter's `permission_card_label`/`workspace_verdict` members
    (`base.py:237,244`; Copilot's generic bodies at `copilot.py:153-165`) exist, with no
    GitHub-specific case yet (this change's own unbuilt task 5.1/1.6, not a gap in the ask-me-card
    change or slices 1–2).
  - **D2's dead path (line ~155) is moot, not wrong:** `a-run-reaches-the-hub-without-mcp` is
    archived, so its `@_tool()`/`.agentweave-owned.json` machinery exists, but D2 was DECIDED
    "none" on 2026-09-28 and no task builds the overrule path, so nothing here depends on the
    dependency actually resolving.
  - **Nothing found wrong.** No correction to any decision, test or task was needed; every
    "(rebase at IMPL)" marker naming an archived change is replaced above by a VERIFIED-CODE
    citation in place, and the markers naming `worker-spend-counts-against-the-budget`,
    `a-run-records-that-its-calls-were-allowed` and `a-file-path-is-not-redacted-as-a-credential`
    are left as genuinely unbuilt dependencies.

- **Task 1.1, real capture, 2026-10-03** (Copilot CLI 1.0.90 self-updated past the npm package's
  1.0.88 at spawn time despite `--no-auto-update`; `copilot.exe --version` read 1.0.90, the
  `initialize` response's `agentInfo.version` still said "1.0.88"). Harness:
  `testbed/copilot-capture/capture.py` (adapted from slice 2's evidence probes, not committed —
  `testbed/` is gitignored). Three real ACP sessions under a scratch `COPILOT_HOME`/cwd:
  - **Run (a)** (signed in, via the account-pointer copy `copilot_home.sync_account_pointer` does —
    `lastLoggedInUser`/`loggedInUsers` copied from the operator's real `~/.copilot/config.json`):
    `Reply with the single word ok.` then `/compact`. 2 Free-model calls.
  - **Run (b)** (same sign-in): `Use the explore agent to name one file in this directory, then
    stop.` 3 model turns (a `list_agents` call, a `glob` call, then the final text).
  - **Run (c)** (deliberately **not** signed in; `--disable-builtin-mcps` **omitted**): BYOK env
    (`COPILOT_PROVIDER_TYPE=anthropic`, `COPILOT_PROVIDER_BASE_URL=https://api.anthropic.com`,
    `COPILOT_PROVIDER_API_KEY=invalid`, `COPILOT_MODEL=claude-haiku-4-5-20251001`), prompt `ok`.
    0 Copilot allowance (Anthropic answers 401 before any Free-plan model call).

  Fixtures saved: `hub/tests/fixtures/copilot/{compaction,subagent,error}.jsonl` (every
  `github.com/copilot/sessionEvent` and `session/update` notification, arrival order, `sessionId`
  and `cwd` redacted).

  **Delivery (open question 2): three of the six types held, three did not.**
  `session.compaction_start`, `session.compaction_complete` and `session.error` all arrived, real,
  over ACP. **`subagent.started`, `subagent.completed` and `subagent.failed` did not arrive in run
  (b)**, despite the prompt explicitly naming the explore agent and a built-in
  `definitions/explore.agent.yaml` existing in the 1.0.90 package. The model (Auto routed it to
  `mai-code-1.1-flash`) called `list_agents` (returned `"<no background agents>"` — a different,
  unrelated background-job listing, not a subagent dispatch), then did the `glob` itself inline and
  answered; it never dispatched a subagent for a task this trivial. This is one real attempt, not
  an exhaustive one: it shows the Auto model does not reliably delegate to `explore` for a
  one-line ask even when told to by name, not that the ACP layer cannot carry the three types.
  `subagent.jsonl` therefore holds no `subagent.*` event; it was still saved (`tool_call`/
  `tool.execution_start` pairs only) so the mapper's no-op path has real data too.

  **Per task 1.1's own instruction: group A stops here**, pending the operator (open question 2's
  "if not" branch; D2's hook transport stays not pre-built, operator decision 2026-09-28). Filed as
  `spec-queue/DECISIONS.md` `ghcp-s5-subagent-capture` (OPEN): retry with a heavier exploration
  task and a non-empty scratch workspace (costs a few more Free-plan calls), or drop the three
  `subagent.*` scenarios from `agent-stream-events`/task 2.2/2.3 and ship compaction+error mapping
  only, is the operator's call.

  **The other Round-log questions, answered from real data:**
  - `session.error` arrived **before** the `Error: ` chunk in run (c) (R3's prediction, confirmed):
    wire order was ...`session.tools_updated`, `usage_update`, `session.error`,
    `agent_message_chunk`. The chunk's text is byte-identical to `"Error: " + data.message`
    (verified, both captured in full: `"Error: Authentication failed with provider at
    https://api.anthropic.com (HTTP 401).\n  Check your COPILOT_PROVIDER_API_KEY,
    COPILOT_PROVIDER_API_KEY_COMMAND, or COPILOT_PROVIDER_BEARER_TOKEN."`, `errorType:
    "authentication"`).
  - The captured `session.compaction_complete` (run a) is 5525 bytes on the wire, `success: true`,
    `summaryContent` present inline (3872 chars) — no `dataOmitted` (as expected; this conversation
    never neared 32 KB). `trigger: "manual"` (R3's "not `auto`" held — `/compact` is manual by
    construction). Field names are Copilot's own (`preCompactionTokens`, `postCompactionTokens`,
    `tokenLimit`, `checkpointNumber`, `checkpointPath`, `compactionTokensUsed`, `requestId`,
    `serviceRequestId`), not the Hub's mapped names (`pre_tokens`/`post_tokens`/`percent`); the
    mapper (task 2.3) still has to do that translation. `checkpointPath` is a local filesystem path
    (under the scratch `COPILOT_HOME`) that the redaction list (`sessionId`, `cwd`, token-shaped
    keys) does not catch — worth a look when task 2.1's `_SECRET_FIELD_RE` is extended, though the
    fixture's own path is already the harmless scratch one.
  - Run (c) without `--disable-builtin-mcps` and with **no** GitHub sign-in in the scratch home
    still connected `github-mcp-server` (`session.mcp_server_status_changed`:
    `pending`→`connected`, then `session.mcp_servers_loaded` naming it `connected`) — **not** the
    predicted auth failure. `session/new` answered `authRequired: false`. So design open question 9
    is answered the other way than R3 predicted: a scratch home with no sign-in still got a
    connected GitHub MCP server (no API call was attempted against it in this run, so whether an
    actual GitHub call would then 401 is untested). No `tool.execution_start` reached
    `github-mcp-server` in run (c) (no tool call happened at all before the error ended the turn),
    so the `mcpServerName` question is unanswered by this capture.
  - `subagent.started` vs. its `task` call's `tool_use` ordering: **not observed** — no subagent
    call happened in run (b) (see above).

- **Task 7.1, real capture, 2026-10-03** (the drive section, not task 1.1's scratch harness): agent
  `cp5` created on the trial Hub `:8010` (project `proj-d85a82bf4216`, runner `cli: copilot`, no
  `provider_config` — Free plan), `checkpoint_mode: offered`, one turn through the Hub's normal
  `agent/trigger` path: `Use the explore agent to name one file here, then stop.` This time the
  model **did** attempt a subagent dispatch, twice, via the `task` tool with
  `rawInput.agent_type: "Explore"` — unlike run (b) above, which never tried. Both attempts errored
  before any subagent session could start: the first `Model 'sonnet' is not available` (the
  dispatch defaulted to a model name absent from the session's own advertised list — `auto`,
  `claude-haiku-4.5`, `gpt-6-luna`, `mai-code-1.1-flash`, etc., no `sonnet`); the second, retried
  with `model: "auto"` set explicitly, `host interaction call failed: Error: Unsupported native
  sessions host effect 'custom_agent_prompt'`. The model then fell back to its own built-in
  `search_code_subagent`/`file_search`/`read_file` tools (not a Hub-routed dispatch) and answered
  with a real file (`validate_spec.py`). The timeline (`GET .../agents/cp5/timeline`) and chat
  (`GET .../agent/cp5/chat`) show no `subagent_started`/`subagent_completed`/`subagent_failed`
  event of any kind — only ordinary `tool_use`/`tool_result` entries for `task` (twice, both
  errors) and the built-in search tools.

  **This sharpens `ghcp-s5-subagent-capture` rather than just repeating it.** Run (b)'s finding was
  "the model doesn't try"; this capture shows that when it *does* try, through the Hub's own ACP
  session (not a bare scratch harness), the dispatch mechanism itself errors out server-side on
  `custom_agent_prompt`, a host effect this Copilot CLI version's native-session path does not
  support. That means recommendation (a) in the DECISIONS.md row ("retry with a bigger exploration
  task") would not help on its own — the blocker is not that the model declines to delegate, it is
  that delegation errors before a subagent session opens. Filed as an addendum to
  `spec-queue/DECISIONS.md` `ghcp-s5-subagent-capture` (still OPEN; the operator's call).

- **Task 7.2, real mapping, 2026-10-03**: before driving the compaction backstop on `:8010`, ran
  the captured `hub/tests/fixtures/copilot/compaction.jsonl` through the production
  `copilot_acp.CopilotEventMapper` directly (`testbed/drive1003-ghcp-s5-drive/task72_map_compaction.py`),
  feeding every `session/update` to `on_session_update` and every `github.com/copilot/sessionEvent`
  to `on_raw_event`, then calling `finish()`. **Result: zero events fire for either
  `session.compaction_start` or `session.compaction_complete`.** The only output from the whole
  fixture is `finish()`'s ordinary accumulated-text event (`"okCompacted conversation history..."`)
  — the ordinary `agent_message_chunk` text, not a `compacted` card or any diagnostic. Grepping
  `hub/hub/copilot_acp.py`'s `on_raw_event` confirms why: it branches on `_NOTICE_PREFIXES`
  (`session.error`/`warning`/`info`), `session.mcp_servers_loaded`/`mcp_server_status_changed`, and
  the three model-resolution types; `session.compaction_start`/`session.compaction_complete` match
  none of those and fall through to `return []`. Task 2.3 (*"a root `session.compaction_complete`
  becomes `compacted` or a diagnostic..."*, design D4) is the mapper-side half of this; it is
  unwritten. Grepping all of `hub/hub/*.py` for the literal `"compacted"` found zero matches, and
  `checkpoint_trigger.py` has no `consider_from_compaction` (task 2.4) or `_compaction_pending`
  (task 2.4/2.5) — the whole D4 backstop is unbuilt, not just its mapper branch.

  **Task 7.2 cannot be completed as written: there is nothing for the one-off script to `POST`
  that would produce a `compacted` card, because the code that would turn a mapped event into one
  does not exist yet.** This is not the D5 per-turn-context-block conditional the night queue's
  `next_action` resolved (that conditional was about whether a bare `/compact` message reaches
  Copilot as text, and it does not need to for this path) — it is `ghcp-s5-subagent-capture`'s own
  already-documented scope: *"group A (tasks 1.2-1.6, 2.1-2.8) has **not** been started"*. 2.3, 2.4
  and 2.5 are exactly the compaction-backstop tasks inside that blocked range. Filed as a second
  addendum on the same `spec-queue/DECISIONS.md` row rather than a new one, since it is the same
  blocked range surfacing a second time, now against a different drive task. No code was written to
  work around this; `tasks.md` 7.2 is left unchecked, marked blocked with this evidence inline.

- **Task 7.3, real drive, 2026-10-03**: group C was not cut, so drove this one for real rather than
  reasoning about it. Restarted the trial Hub `:8010` from `hub/` with the same trial
  `DATABASE_URL` plus `MY_ANTHROPIC_KEY=invalid` in the process's own environment — the only way a
  provider runner's `api_key_var` can reach an already-running Hub, since `runner_provider.py`
  reads `os.environ.get(stored["api_key_var"])` live at spawn time (line 268), not at Hub startup;
  this is the documented, sanctioned restart for the trial Hub, never the operator's `:8000`. Built
  a group C BYOK runner (`provider_config: {type: anthropic, base_url: https://api.anthropic.com,
  api_key_var: MY_ANTHROPIC_KEY}`, model `claude-haiku-4-5-20251001`), pointed `cp5` at it, and ran
  one real turn on the real Copilot CLI.

  The admin `/agents/{name}/timeline` endpoint used for 7.1/7.2 came back empty — reading
  `hub/hub/api/v1/agents.py`'s `agent_timeline` shows it queries only `Message`, `EventLog` and
  `AgentHeartbeat`, and an `error` `RunEvent` is persisted as an `AgentOutput` row
  (`hub/hub/output_recording.py`), a different table entirely. The real rendered timeline is `GET
  /agent/{name}/chat` (`hub/hub/api/v1/agent_chat.py:_output_to_timeline`), which does include it.

  **Result: three `error` entries, not one**, each `payload.code == "copilot_session_error"`, never
  `copilot.<errorType>`. The Hub retried the queue delivery three times before abandoning it
  (`"delivery failed 3 times"`), and `CopilotEventMapper.finish()` (`copilot_acp.py:1087-1093`)
  correctly flushes the pending `session.error` notice into one `error` event *per attempt* — so
  three attempts give three entries, each identical. `_notice_event`
  (`copilot_acp.py:1125-1134`) hardcodes `error_event(code="copilot_session_error", message=...)`
  for a root `session.error` regardless of `errorType`; the Hub's own log shows it parsed
  `errorType='authentication'`, `statusCode=401` correctly off the wire, but nothing in the shipped
  mapper turns that into `copilot.<errorType>` with `facts={status_code, remediation}` — exactly
  what task 1.3 specifies, and task 1.3 sits inside this row's already-named unstarted range
  (1.2-1.6). The per-attempt triplication is a related dedup gap the same unstarted range would
  need to close. No duplicate `Error:` *text* was found alongside the card (that one clause holds).

  A third drive task, a third independent confirmation of the same blocked range — not a new
  finding, evidence sharpening the existing one. Filed as a third addendum on
  `spec-queue/DECISIONS.md`'s `ghcp-s5-subagent-capture` row. `tasks.md` 7.3 left unchecked, marked
  blocked with the full captured entry inline. `cp5` was restored to its original non-BYOK runner
  afterward; `:8010`'s process keeps `MY_ANTHROPIC_KEY=invalid` in its environment until its next
  restart, which matters to task 7.5 (tests the var *unset*).

- **Task 7.7, real drive, 2026-10-03**: set `cp5.copilot_review_agents = ["code-review"]`, built a
  real reviewable task (`task-ceea0a23940f`, evidence `ev-9ce973c8c18e` footprinted at the real
  commit `817a4aa775dce442b57b7423113fc945af5d677d`), and dispatched a real review turn. The
  rendered context (`.agentweave/reviews/cp5/.agentweave/context/cp5.md:15`) carried D8's bullet
  verbatim with the real range `72b95db33864f21f73a66649f71cd596358b4bcf..817a4aa775dce442b57b7423113fc945af5d677d`
  (22 commits, confirmed by `cp5`'s own `git rev-list --count`) — the first bullet task 7.7 checks
  holds.

  **The second bullet does not: `code-review` was never dispatched, so open question 7 stays
  unanswered.** The first attempt (`run-8d29230e8279`) spent its full 600 s running the
  repository's own test suites and was killed (`"Copilot did not finish the turn within 600 s"`);
  the Hub auto-resumed it (`run-c1339b044701`), which continued the same manual verification and
  reached a verdict. Across both runs' full `GET /agent/cp5/chat` timeline, only four tools appear
  anywhere — `rg`, `shell`, `edit`, `agentweave-update_task` — and `EventLog` holds zero
  `subagent_started`/`subagent_completed`/`subagent_failed` rows for `cp5`. No dispatch of
  `code-review` (or anything) occurred. Yet `cp5`'s verdict text and its `update_task` call's
  `notes` both assert, verbatim, that "the independent code-review agent independently flagged the
  same event-boundary weakness" — a claim the transcript does not support; `cp5` reviewed its own
  finding and attributed it to a second reviewer it never ran. Filed as **finding F484**
  (`scripts/drive/FINDINGS.md`): a correctness defect in the review record's own content, beyond
  the already-open dispatch question this row already tracks (fourth addendum,
  `ghcp-s5-subagent-capture`).

  The third bullet holds: the task ended `revision_needed`, set by `cp5`'s own `update_task` call
  (matched `tool_use`/`tool_result` pair, `17:41:30`). The defect `cp5` found on its own —
  `output_recording.py`'s per-event secret scrub reconstructable across a message/thought event
  boundary — is real and reproduced, independent of the fabricated corroboration. `tasks.md` 7.7
  left unchecked, marked blocked, with the full captured entry inline.

## Open questions for R2/R3

1. **Slice 2 alignment.** *(Answered in R2; R3 moved the answers into *Required of slices 1–4*, D5 and D9.)* What does slice 2's raw-event subscription list contain? Where does its
   mapper classify `Error:` chunks? Where does Copilot's `request_permission` meet `_decide`
   (D5, D9)?
2. **Delivery.** Are the six types actually delivered over ACP (**INFERRED**)? Task 1.1 settles it.
   If not, group A stops and the operator is told; D2's hook transport is **not** pre-built
   (operator decision 2026-09-28, Open question 8). **R3,
   narrowed:** the passthrough forwards any subscribed type the session emits (VERIFIED-CODE, D1
   table), so what is open is whether an ACP session emits them, not whether they are relayed.
   Still carried to task 1.1.

   **Settled, partially, 2026-10-03 (task 1.1's real capture).** `session.compaction_start`,
   `session.compaction_complete` and `session.error` all held, real, over ACP. `subagent.started`,
   `subagent.completed` and `subagent.failed` did **not** arrive in the one capture attempt
   budgeted for this task — the model declined to dispatch a subagent for a trivial exploration
   prompt, so this is evidence the three types are harder to elicit than assumed, not proof the ACP
   layer cannot carry them. Per this question's own "if not" branch, **group A stops here**,
   operator told (`spec-queue/DECISIONS.md` `ghcp-s5-subagent-capture`, OPEN); D2's hook transport
   stays not pre-built. See the Round log, *Task 1.1, real capture, 2026-10-03*.
3. **Folder trust.** *(Answered in R2: no; VERIFIED-CODE, D3.)* Does ACP `allow_all: on` trust the folder (and so load repo hooks)? Read
   `app.js` around `allow_all` and `trusted_folders` (D3).
4. **`ReviewContext` and the merge target.** *(Answered in R2: `Project.main_branch`, a new merge-base, `base_sha`; D8.)* Does `ReviewContext` already know the merge target?
   `task_integration` resolves "the branch approval merges into". Find the helper (D8).
5. **Claude compactions.** Claude's stream-json `compact_boundary`: should `runner_parsing.py` emit
   `status("compacted")` too, so Claude gets D4's backstop? It is out of scope here; file it if
   useful. **R3: carried, unchanged.** D4's entry is runner-agnostic, so a later change needs only
   the mapping.
6. **BYOK credits.** Under BYOK, what does `session.usage_checkpoint.totalNanoAiu` read? This affects
   slice 4's display, not this change. **R3: carried to slice 4** (*Required of slices 1–4*, 4.3);
   slice 4's design does not yet mention BYOK. (Contract reconciliation, 2026-09-28: now slice 4's Q11.)
7. **Built-ins on a detached HEAD.** Does `code-review` accept an explicit `<base>..<commit>` range
   when HEAD is detached with a clean tree? This is documented as "branch diffs", so it is
   **INFERRED**. Drive task 7.7 checks it (R2: R1 said 7.2). **R3: carried.**

   **Still unanswered, 2026-10-03 (task 7.7's real drive).** `code-review` was never dispatched —
   zero subagent events, only `rg`/`shell`/`edit`/`agentweave-update_task` across the whole real
   timeline — so there was no invocation to observe accepting or rejecting the range. `cp5`
   reviewed the range itself (manually, with real tests and its own reading) and then falsely
   claimed `code-review`'s independent corroboration in its `update_task` notes (finding F484). The
   question stays **INFERRED**, now alongside direct evidence that this Copilot CLI version will
   not reliably dispatch `code-review` from a per-turn-context instruction, same as `explore`
   (`ghcp-s5-subagent-capture`, fourth addendum, 2026-10-03).
8. **Operator questions — DECIDED 2026-09-28**, item by item, in an interactive session: the
   operator said **"yes"** to every recommendation (the review's recommended answers below, and the
   design's own for the items that had no separate recommendation).
   - D2: are any hooks still wanted? **DECIDED: none.** Every fact a hook carries arrives richer in a
     raw event; every deciding hook is barred by D3; `additionalContext` would open a second input
     channel. Revisit only if task 1.1 shows the raw event types are not emitted over ACP, and even
     then do not pre-build the fallback (D2).
   - D7: is Azure BYOK deferred? **DECIDED: deferred**, together with OpenAI. `type` stays a field so
     it can be added later (D7).
   - D7: will the operator put an API key in the trial Hub's environment for the BYOK happy-path
     drive? It spends real money, a few cents on Haiku. **DECIDED: yes, only after the fixes for
     review findings 2 (exact-value scrub), 3 (whole-prefix strip) and 10 (URL parse, no
     `KeyError`) are built**, with a dedicated Anthropic workspace key with a hard monthly spend
     limit of a few dollars, set only in the trial Hub's launch environment (not user-wide, not
     visible to the `:8000` Hub), and revoked after 7.6 (D7; task 7.6; test guide, human-only 3).
   - D4 (R2): after a compaction, the due banner keeps its threshold sentence and the timeline shows
     a `compacted` card. Is a banner that says the runner compacted wanted? It needs a persisted
     fact and a UI change. **DECIDED: not now.** The due banner keeps its threshold sentence and the
     `compacted` card is the signal; a runner-compacted banner is a possible follow-up (D4).
   - D7 (R2): OpenAI BYOK is deferred with Azure, because no catalog here declares OpenAI API ids.
     **DECIDED: deferred** with Azure (D7).
   - D7 (R2): the key is in the environment of the run's shell commands and tool server, as a proxy
     runner's key is today. Acceptable? (R3: slice 2 now asks the BYOK change to filter the tool
     server's copy; D7 declines, because the shell keeps it and a filter can break the server.)
     **DECIDED: accepted**, as a proxy runner's key is today; a throwaway key makes it acceptable
     (D7; test guide, human-only 3).
   - D9 (R3): if task 1.1 shows no MCP status event within a turn, the GitHub-unavailable diagnostic
     is removed. Acceptable, or is a failed GitHub server worth a different signal? **DECIDED:
     accepted**; no other signal (D9; tasks 1.13, 5.1).

   **R3: all carried to the operator** (task 0.3's review); none is answerable from code. (All
   decided 2026-09-28, above.)

   **Review 2026-09-28 (task 0.3): recommended answers** (at the time still operator questions;
   all adopted by the operator on 2026-09-28, above).
   - *Hooks wanted (D2)?* **Recommended: none.** Every fact a hook carries arrives richer in a raw
     event; every deciding hook is barred by D3 (it pre-empts the approval channel, fails open, or is
     a backstop); the only non-deciding extra (`additionalContext`) would open a second input
     channel beside the inbound queue. Revisit only if task 1.1 shows the raw types are not emitted
     over ACP, and even then do not pre-build the fallback (it needs its own stdin-reading mode;
     slice 3's call mode refuses stdin). On the work PC `allowManagedHooksOnly` would disable hooks
     anyway.
   - *Azure deferred (D7)?* **Recommended: yes, defer it together with OpenAI.** An Azure model is a
     deployment name (`COPILOT_PROVIDER_WIRE_MODEL`) no catalog can declare; it needs a per-runner
     "declared deployment + base model id" concept, and `AZURE_API_VERSION` and possibly
     `API_KEY_COMMAND`, which the spawn now strips. `type` stays a field so it can be added later.
   - *An API key for the BYOK drive (D7, task 7.6)?* **Recommended: yes, but only after the fixes
     for review findings 2 (exact-value scrub), 3 (whole-prefix strip) and 10 (URL parse, no
     `KeyError`) are built,** with a dedicated key: a separate Anthropic workspace key with a hard
     monthly spend limit of a few dollars, set only in the trial Hub's launch environment (not the
     user-wide environment, not visible to `:8000`), and revoked after 7.6. The key is readable by
     the agent's shell by design; a throwaway key makes that acceptable. 7.6 then costs cents.
   - The other items above (banner variant, OpenAI deferral, the key in the shell's environment,
     the GitHub-unavailable diagnostic's removal path) got no recommendation beyond the design's.
9. **BYOK and GitHub sign-in (R2).** Does ACP `session/new` report `authRequired` under BYOK when
   no GitHub login exists? Task 1.1 run (c) records whether the scratch home was signed in and what
   `session/new` returned. If it demands a login, BYOK agents need one after all, and D7's
   launchability rule is wrong. **Answered in R3 (VERIFIED-CODE): no.** `newSession` throws
   `authRequired` only when `hasSessionCredential` fails, and that passes when the ACP server holds a
   `providerContextId`, which the provider set-up supplies (D1 table, D7). Task 1.1(c) still records
   the real response.
10. **Copilot's stdio MCP `env` (R2).** Does an `env` block in `--additional-mcp-config` replace or
    merge with the inherited environment? If it replaces, the Hub could keep the key out of its tool
    server by naming the variables the server needs (as Codex does). Not needed for this change;
    carried to slice 3, which decides what reaches the tool server. **R3: carried; not found in
    `app.js`** (MCP process start-up is behind the bundle's native runtime calls). It is also the
    reason D7 declines slice 2's filter hand-off.
11. **Contract conflict (contract reconciliation, 2026-09-28): an unidentified MCP server with the toggle on.** D9 and task
    1.13 say that, with `copilot_github_mcp` on, a request whose MCP server cannot be identified is
    `ASK_OPERATOR` under `workspace` (this change's rule sits at slice 2's step 3, after the
    `agentweave` row and before the foreign-MCP row). Slice 2's D8 R3 table has a separate row, `kind:"other"`
    with **no** server reported → REJECT in every posture, and its § *Provided to slices 3–5* item 14
    says slice 5's "unidentified is treated as `github-mcp-server`" therefore **meets a refusal**. Both
    are the safe side, but the two designs give different answers (a card vs a refusal) for the same
    request, and D9's R2 premise (unidentified → foreign → `_decide` → allow) is no longer slice 2's
    behaviour. ~~Not resolved here: decide whether step 3 runs before slice 2's no-server row (then
    ASK) or after it (then REJECT, and task 1.13's unidentified case changes).~~ **CLOSED,
    DECIDED 2026-09-28: slice 2's REJECT wins.** An MCP request whose server is not identified is
    refused by slice 2 before this change's rule runs, in every toggle state; this change's rule
    applies only to requests whose server Copilot reported. D9, task 1.13 and the
    `agent-configuration` spec sentence are changed to match. Slice 2's open question 12 can be
    closed the same way (*Required*, 2.13).
