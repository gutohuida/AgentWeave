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
the other's entries standing. **(rebase at IMPL: `a-copilot-agent-runs-over-acp`,
`a-copilot-run-shows-its-credits` unbuilt at R2.)**

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
under, and `args` = [the pinned `mcp_server.py` copy that `tool_server.py` maintains, `--call`, a
tool that receives the hook's payload]. That is the shim call mode of
`a-run-reaches-the-hub-without-mcp` (its D4: `mcp_server.py --call <tool>`, fastmcp not imported).
R2: that mode calls a registered `@mcp.tool()`, and **no tool that receives a hook payload
exists**, so this alternative also needs a new tool and route. R3: slice 3's call mode is also
closed over the MCP tools and **refuses stdin** (its open item 5), while a command hook receives its
payload on stdin. So the overrule path needs its own mode as well; slice 3 provides none, and this
change asks it for none. It reads `AW_RUN_TOKEN` and `HUB_URL`
from the environment it inherits from `copilot.exe`. **(rebase at IMPL:
`a-run-reaches-the-hub-without-mcp` unbuilt at R2.)** **Not `type:"http"`**, for four reasons:

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
    against a later writer, not a fix.

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
banner. Whether a banner variant is wanted is an operator question (Open question 8): it needs a
persisted fact (a column, or reading the conversation's `compacted` rows) and a UI change, which is
why R2 did not add it silently.

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
  **(rebase at IMPL: `a-copilot-run-shows-its-credits` unbuilt at R3.)**

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
- `diagnostic_event`. **R3: this change adopts slice 2's builder and its names.** Slice 2's R2
  (its D10) now ships `diagnostic_event(*, code, message, severity="info", facts=None)`, keyword-only,
  and states that slice 5 extends rather than re-adds it. R2's own signature (`stream`, `summary`) is
  therefore dropped here. One thing is still missing: `agent-stream-events` *Versioned kind-specific
  payloads* says *"Diagnostic payloads SHALL identify stream and severity"*, and the CLI's payload
  carries `stream` (`src/agentweave/stream_events.py:556-573`). Slice 2's builder has no `stream`.
  That is a requirement of slice 2's own diagnostics (its `Warning:`/`Info:` and model-substitution
  notices), not of this change, so it is listed under *Required of slices 1–4*. This change calls
  the builder with `stream="copilot"` and, if slice 2 lands without the keyword, adds it
  (`stream: str = "runner"`, written into the payload). The UI renders a diagnostic's `content`
  (`AgentTimeline.tsx:806-822`), so the payload key names do not change what the operator reads.
  **(rebase at IMPL: `a-copilot-agent-runs-over-acp` unbuilt at R3.)**
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
  `diagnostic_event(code="copilot.compaction_failed", message=<its error, else a fixed sentence>,
  severity="warning", stream="copilot", facts={status_code})` (R3: slice 2's parameter names;
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
provider with a catalog of its own. Operator question 8 now carries both deferrals.

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
- `base_url` defaults to `https://api.anthropic.com` and must be an `https://` URL or
  `http://localhost…`.
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
- `ProviderConfig` is a `RequestModel` (`extra="forbid"`, `schemas/common.py:21-32`) whose three
  fields are plain `str`/`Optional[str]` with no Pydantic constraint: the route owns every check, so
  a pasted key never meets a 422 whose `detail[].input` would echo it back.
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

  **(rebase at IMPL: `each-runner-cli-is-one-adapter` unbuilt at R2; if `catalog_provider` becomes
  per-runner there, these sites collapse onto it.)**

**Azure is deferred.** An Azure model is a deployment name the catalog cannot declare
(`COPILOT_PROVIDER_WIRE_MODEL`), which conflicts with the catalog rule. This is an operator question.

**Spawn.** For a runner with `provider_config`, the run environment carries:

- `COPILOT_PROVIDER_TYPE` and `COPILOT_PROVIDER_BASE_URL`;
- `COPILOT_PROVIDER_API_KEY` = `os.environ[api_key_var]`, resolved at spawn as `resolve_agent_env`
  does (`launchability.py:162-169`);
- `COPILOT_MODEL` = `runner.model`, and slice 2's `--model` spawn flag carries the same value (the
  override refusal above guarantees it).

For a `copilot` runner **without** `provider_config`, every ambient `COPILOT_PROVIDER_*`,
`COPILOT_MODEL` and `COPILOT_OFFLINE` is **stripped** from the child environment. That mirrors the
ambient `ANTHROPIC_BASE_URL` strip (`launchability.py:190-194`): an operator's shell must not
silently turn a subscription runner into a BYOK one.

**R3: stripped whatever their source, unlike the Claude rule.** `resolve_agent_env` merges the
agent's `config.env_vars` into the run environment (`launchability.py:157-179`), and the Claude
guard deliberately spares a variable the agent's `env_vars` name. Copied as is, that exemption
would let an agent's `env_vars` carry `COPILOT_PROVIDER_*` and turn the run into a BYOK run the
runner never validated, which is the "one fact on two records" D7 exists to prevent. So the Copilot
guard strips those names from both sources when the runner has no provider, and overwrites them from
`provider_config` when it has one.

R2: **where** this happens is not "the adapter's `build_launch`". Slice 1's `build_launch` is a
`StreamTransport` member returning argv only; an RPC transport (ACP) has none, and its environment
arrives as `RpcTurnRequest.env`. The environment is built by `resolve_agent_env` and ends in the
adapter's `guard_env(proc_env, env_vars)` (slice 1 D10), and slice 2 D3 puts its `GH_TOKEN` strip
there. `guard_env` receives no runner row. **R3: no new parameter on `resolve_agent_env` is
needed.** The trigger already builds `config` from `get_agent_config` and overwrites `runner`/`model`
from `runner_row` (`agent_trigger.py:764-765`), then calls `resolve_agent_env(runner, config)`
(`:849`). Putting `config["provider_config"] = runner_row.provider_config` in the same place (and
in `get_agent_config`, below) delivers it. What is missing is the last hop: slice 1's
`guard_env(proc_env, env_vars)` sees only `env_vars`, not `config`. That is listed under *Required
of slices 1–4*. **(rebase at IMPL: `each-runner-cli-is-one-adapter`, `a-copilot-agent-runs-over-acp`
unbuilt at R3.)**

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
operator (test guide, human-only 3).

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
both. **(rebase at IMPL: slice 1 D14 moves `probe_agent` onto the adapter; the call sites stay.)**

**Where the key could leak, and why it does not:**

- It is in no database row.
- The runners API returns `api_key_var`, which is a name.
- `ROSTER_CONFIG_KEYS` (`api/v1/agents.py:651`) is agent config and unaffected.
- Stream text passes `redact_secrets` (`runner_events.py:63-81`). `sk-ant-…` is caught by the `sk-`
  word-start alternative (`:58`), which `a-file-path-is-not-redacted-as-a-credential` does not
  change. D5 adds the value rule to `error_event`'s message, which today is not redacted.
- Stderr summaries are "secret-safe" per `runtime-diagnostics`.
- It **is** in the environment of the run's tool server and shell commands (above).

A test asserts the key value appears in none of the runner response, the agent context file, a
recorded run event, or an error or diagnostic payload.

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
Copilot run the bullet travels in the prompt's per-turn block, not the agent file. **(rebase at
IMPL: `a-copilot-agent-runs-over-acp` unbuilt at R2.)**

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

**Open changes touching this section (R2 re-verified their designs; both unbuilt):**

- `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` gives `_render_hub_agent_context`
  an optional `runner` parameter (its design `:61-65`) and deliberately leaves the review verdict's
  `update_task` bare (its design `:69-75`). This change uses that `runner` parameter to know the
  runner is `copilot` if it has landed, and otherwise reads it from `agent_row.runner_id`. The
  bullet names `update_task` bare, matching the verdict line. **(rebase at IMPL.)**
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

## D9 — The built-in GitHub MCP server as a per-agent toggle

- **The setting.** Agent `config.copilot_github_mcp` is a boolean, default false. The Copilot argv
  builder omits `--disable-builtin-mcps` when it is true. R2: that builder is slice 2's
  `copilot_acp.build_acp_argv(...)` (its D3), not an adapter `build_launch` (slice 1's
  `build_launch` is a stream-transport member), and it must be given the agent's config. **(rebase
  at IMPL: `a-copilot-agent-runs-over-acp` unbuilt at R2.)** R3: the builder runs inside the RPC
  transport's `run_turn`, which receives only slice 1's `RpcTurnRequest` (`cli, cwd, env, prompt,
  model, resume_session_id, yolo, mcp_command, config_overrides, permission_mode, workspace,
  extra_flags, restrict_spec_writes`). None of those carries an agent setting, so the toggle needs
  one field, `github_mcp: bool = False`, set by the trigger from `config.copilot_github_mcp` and read
  both by `build_acp_argv` and by `decide_permission` (below). A `False` default leaves slices 1–2
  byte-identical. This change adds the field if slice 1 has not (*Required of slices 1–4*).
- **The decision.** A permission request for the `github-mcp-server` is an MCP-kind request.
  - **R2: `_decide` would allow it, which is why the rule is needed.** R1 wrote that `_decide` "has
    no ground to allow it". It has, by default: `_decide` (`mcp_server.py:1543-1592`) refuses only
    through a path key (`_PATH_KEYS`) or a `command` it can read, and otherwise returns
    `{"allow": True, "reason": "inside your workspace"}`. A GitHub tool's input (`owner`, `repo`,
    `title`, `body`) has neither. Slice 2's D8 maps every foreign MCP request onto
    `_decide("mcp__<server>__<tool>", args)` under `workspace`, so without this rule a Copilot agent
    under Workspace only would open issues on GitHub as the operator with no card. Test 1.13's
    fail-before evidence is exactly that `allow`.
  - So under `workspace`, the rule answers a request whose server is `github-mcp-server` with
    slice 2's `ASK_OPERATOR` outcome **before** `_decide` is reached. The client then holds the
    request and waits on the operator through `_await_operator_permission`
    (`agent_trigger.py:2977`), bounded by `AW_DECISION_TIMEOUT`, a timeout denying.
  - Under `acceptEdits` (slice 2 emulates it and refuses every foreign MCP request) it stays
    refused.
  - Under full access (`allow_all`) it is allowed as everything else is.
  - Under `manual` it goes to the operator anyway.
  - **Where it lives (R2 answered):** slice 2's `copilot_acp.decide_permission(params, *, posture,
    workspace, hub_url, mcp_server_names)`, a pure function in the Hub process that calls
    `_decide`. It is not in `mcp_server.py`, so `.claude/rules/mcp-server.md`'s import restriction
    does not apply, and `mcp_server.py` is unchanged. The server name comes from slice 2's per-turn
    `toolCallId → (serverName, toolName)` map, fed by the raw `permission.requested` event; a
    request whose server cannot be established is judged foreign by slice 2, which under
    `workspace` means `_decide` and therefore allow. So this rule also treats an **unidentified**
    MCP server as `github-mcp-server` while the toggle is on: asking is the safe side.
  - R3: slice 2's signature (its D8) is `decide_permission(params, *, posture, workspace, hub_url,
    mcp_server_names)`; nothing in it says whether the toggle is on. This change adds the keyword
    `github_mcp: bool = False`, fed from `RpcTurnRequest.github_mcp`. The rule sits after the
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
      GitHub server has).

    This depends on no field of the ask-me change. R2's longer sentence ("The Hub does not decide
    GitHub actions on your behalf") had nowhere to live and is dropped. **(rebase at IMPL: that
    change and slices 1–2 unbuilt at R3.)**
- **When the server fails to start (R2 correction).** R1 said slice 3's MCP status handling
  surfaces a failed GitHub server. It does not: slice 2's D10 reports only a failure of the server
  named `agentweave`, and slice 3 reads the same status for `agentweave` only. With the toggle on
  and the server failing (a BYOK agent with no GitHub login, or a policy that blocks it), the
  operator would see nothing. So group D adds one mapping: a raw `session.mcp_servers_loaded` /
  `session.mcp_server_status_changed` naming `github-mcp-server` in a state other than connected,
  **while the toggle is on**, gives one `diagnostic_event(code="copilot.github_mcp_unavailable",
  message=…, severity="warning", stream="copilot")` per turn. With the toggle off the server is
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
    that a failed GitHub server shows only as tool calls that never happen.

## D10 — Independence of the groups

- **A** touches `runner_events.py`, `checkpoint_trigger.py`, `output_recording.py` and the Copilot
  mapper.
- **C** touches runners (schema, route, migration, UI), `get_agent_config`, `resolve_agent_env` /
  the Copilot `guard_env`, the adapter's `launchability`, the probe-config sites (D7), the per-run
  override check (`agent_trigger.py:1618`) and the spawn's model resolution (`:802`, R3), and the
  composer's model control.
- **B** touches the context renderer, `review_turn.py`, `ROSTER_CONFIG_KEYS`, and the agent
  Settings UI.
- **D** touches slice 2's argv builder and `decide_permission`, slice 1's `RpcTurnRequest`
  (`github_mcp`, R3) and its Copilot `permission_card_label` / `workspace_verdict`, the Copilot
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
| 1.1 | **Drop the reserved `hooks` row of D16.** This change writes no hook file (D2), and D16's own rule is that no member exists without a caller. | correction |
| 1.2 | **D16's `hooks` row also says slice 5 reads `provider_config` "in Copilot's spawn argv" through "a `RpcTurnRequest` field slice 5 adds".** It does not. `provider_config` reaches `launchability` through its existing `config: Mapping`, and reaches the environment through `resolve_agent_env(runner, config)` (D7). The argv's `--model` is `RpcTurnRequest.model`, which is already the runner's (D7, spawn). No `provider_config` field on `RpcTurnRequest`. | correction |
| 1.3 | **`guard_env(proc_env, env_vars)` needs the runner's `config`** (keyword `config: Mapping`, or at least `provider_config`), because the Copilot guard sets or strips the provider variables from it (D7). Claude and Codex ignore it. If slice 1 lands without it, this change adds `provider_config: Optional[Mapping] = None` as a keyword with that default. | needed / owned here |
| 1.4 | **`RpcTurnRequest.github_mcp: bool = False`**, set by the trigger from `config.copilot_github_mcp`, read by slice 2's `build_acp_argv` and `decide_permission` (D9). A `False` default keeps slices 1–2 unchanged. | needed / owned here |
| 1.5 | `catalog_provider` stays a `ClassVar`. This change does not ask for a per-runner provider: it checks a provider runner's model itself at the four sites in D7. If slice 1 ever makes it per-runner, those sites collapse onto it. | nothing required |
| 1.6 | The Copilot `permission_card_label(method, subject)` returns `github-mcp-server/<tool> — acts on GitHub as you` for a request D9 routes to the operator, and `workspace_verdict(method, subject, workspace)` returns `None` for it. Both members are slice 1's; their Copilot bodies are slice 2's, with this change's case. | owned here |

### Slice 2 — `a-copilot-agent-runs-over-acp`

| # | Item | Kind |
|---|---|---|
| 2.1 | **`diagnostic_event` lacks `stream`.** Slice 2 ships `diagnostic_event(*, code, message, severity="info", facts=None)` (its D10). `agent-stream-events` *Versioned kind-specific payloads* requires diagnostic payloads to *"identify stream and severity"*, and that applies to slice 2's own `Warning:`/`Info:`/model-substitution diagnostics. Add `stream` (keyword) and write it into the payload. This change adopts slice 2's parameter names and, if slice 2 lands without `stream`, adds it with a default (D5). | needed / owned here |
| 2.2 | **D10's sentence about slice 5 is stale:** *"Slice 5 (its D5) later re-maps a raw `session.error` to a `diagnostic_event(severity="error")` and suppresses the echoed `Error:` block in either order."* Since R2, slice 5 records `session.error` as an **`error_event`** with facts, not a diagnostic. Since R3, it drops the echo at the **chunk**, not the block, relying on the raw-first order (VERIFIED-CODE), and deletes slice 2's `Error:` → `copilot_session_error` branch (D5). | correction |
| 2.3 | **The mapper must see the whole `github.com/copilot/sessionEvent` params**, including `agentId` and `dataOmitted`, not only `{sessionId, type, timestamp, data}` as slice 2's VERIFIED row describes the envelope. D4 ignores a subagent's compaction by `agentId` and handles an oversized `session.compaction_complete` by `dataOmitted`. `on_raw_event(type, data)` loses both; this change does not use it. | needed |
| 2.4 | **`COPILOT_RAW_EVENTS`**: this change appends `subagent.started`, `subagent.completed`, `subagent.failed` and `session.compaction_start`, and ensures `session.compaction_complete` and `session.error`, relying on slice 2's de-duplication in first-seen order (D1). | nothing required |
| 2.5 | **`decide_permission` gains a keyword `github_mcp: bool = False`** from this change (D9). This change's rule sits between the `agentweave` row and the foreign-MCP row of slice 2's D8 table. | owned here |
| 2.6 | **The Copilot `workspace_verdict` is `None` when this change's rule routes the request**, under `workspace` and `manual` alike. Slice 2's D8 fills the verdict from its `workspace` column, which for a GitHub call is `_decide`'s allow. Unchanged, the ask-me card would read "Workspace only would allow this" on a card raised because Workspace only does not. | needed / owned here |
| 2.7 | **D3's hand-off of an MCP `env` filter** ("whichever lands the BYOK variables adds that filter") is declined here, with reasons (D7): the key is in every shell command's environment anyway, and a blanking `env` map breaks the tool server if Copilot's `env` replaces rather than merges (Open question 10). Slice 2 should reword the sentence as an open question, not an obligation. | correction |
| 2.8 | Slice 2's non-`connected` `agentweave` status report has the same `pending` hazard D9 found (the schema's `McpServerStatus` has `pending`). Slice 3 now owns that report (its D9). | observation |

### Slice 3 — `a-run-reaches-the-hub-without-mcp`

| # | Item | Kind |
|---|---|---|
| 3.1 | No "hook call mode" is needed. D2 installs no hook. Its overrule path would need its own stdin mode and tool, which slice 3's closed, stdin-refusing call mode rightly does not offer. | nothing required |
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

## Open questions for R2/R3

1. **Slice 2 alignment.** *(Answered in R2; R3 moved the answers into *Required of slices 1–4*, D5 and D9.)* What does slice 2's raw-event subscription list contain? Where does its
   mapper classify `Error:` chunks? Where does Copilot's `request_permission` meet `_decide`
   (D5, D9)?
2. **Delivery.** Are the six types actually delivered over ACP (**INFERRED**)? Task 1.1 settles it.
   If not, group A's source falls back to D2's hook transport, and the operator is told. **R3,
   narrowed:** the passthrough forwards any subscribed type the session emits (VERIFIED-CODE, D1
   table), so what is open is whether an ACP session emits them, not whether they are relayed.
   Still carried to task 1.1.
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
   slice 4's design does not yet mention BYOK.
7. **Built-ins on a detached HEAD.** Does `code-review` accept an explicit `<base>..<commit>` range
   when HEAD is detached with a clean tree? This is documented as "branch diffs", so it is
   **INFERRED**. Drive task 7.7 checks it (R2: R1 said 7.2). **R3: carried.**
8. **Operator questions:**
   - D2: are any hooks still wanted?
   - D7: is Azure BYOK deferred?
   - D7: will the operator put an API key in the trial Hub's environment for the BYOK happy-path
     drive? It spends real money, a few cents on Haiku.
   - D4 (R2): after a compaction, the due banner keeps its threshold sentence and the timeline shows
     a `compacted` card. Is a banner that says the runner compacted wanted? It needs a persisted
     fact and a UI change.
   - D7 (R2): OpenAI BYOK is deferred with Azure, because no catalog here declares OpenAI API ids.
   - D7 (R2): the key is in the environment of the run's shell commands and tool server, as a proxy
     runner's key is today. Acceptable? (R3: slice 2 now asks the BYOK change to filter the tool
     server's copy; D7 declines, because the shell keeps it and a filter can break the server.)
   - D9 (R3): if task 1.1 shows no MCP status event within a turn, the GitHub-unavailable diagnostic
     is removed. Acceptable, or is a failed GitHub server worth a different signal?

   **R3: all carried to the operator** (task 0.3's review); none is answerable from code.
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
