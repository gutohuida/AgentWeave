# Design — a Copilot agent uses hooks and its own agents

Slice 5 of `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`. It is written against
master `97b86ed` (2026-09-27), **before** the 28-change night queue and slices 1 to 4 land.

Every `file:line` below was read on 2026-09-27. Where an open change touches the same site, that
change is named and marked **re-verify in R2**.

**R2 (2026-09-28) re-read every cited site at master `ef55e6f`.** Only 5 of the night's 28 changes
have landed, and **slices 1–4 are all unbuilt**. Of the files cited here, only `model_catalog.py`
(`63d9f34`, `3b3563a`) and `api/v1/agents.py` (+4 lines at `:707`) moved. Line numbers below are
`ef55e6f`'s where R2 corrected them. Every dependency on an unbuilt slice is marked **(rebase at
IMPL: <change> unbuilt at R2)**, and the section *Dependencies on slices 1–4, as written at R2*
lists where their designs, as currently written, do not match what this change assumed.

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
| The built-in GitHub server authenticates as the logged-in Copilot user | **INFERRED** | It is first-party and has no separate token. R2 did not settle it (no process spawned); the drive's card (7.8) shows it |
| `ErrorData` requires `errorType` and `message`; also `errorCode`, `statusCode`, `remediation`, `eligibleForAutoSwitch`, `stack`, `providerCallId`, `serviceRequestId`, `url`. `errorType` is an **open string** ("e.g. authentication, authorization, quota, rate_limit, context_limit, query") | **VERIFIED** (schema, R2) | 1.0.88 `session-events.schema.json` |
| `CompactionCompleteData` requires only `success`; it also has `error`, `tokensRemoved`, `messagesRemoved`, `compactionTokensUsed`, `requestId`. `SubagentCompletedData` has `cancelled`; `SubagentFailedData` requires `error` | **VERIFIED** (schema, R2) | same file |
| The ACP `allow_all` option does **not** trust the folder. It calls `session.permissions.setMode({mode:"allow-all"})` only. A session's workspace trust is `trustWorkingDirectory` (an SDK option the ACP path never sets) **or** `COPILOT_ALLOW_ALL==="true"` **or** `folderTrustIsTrusted(cwd, configDir)` | **VERIFIED-CODE** (R2) | 1.0.88 `app.js`: `async applyAllowAll(t,n)`, `resolveTrustDeclaration`, and the three `COPILOT_ALLOW_ALL==="true"\|\|await b.folderTrustIsTrusted(...)` sites that set `deferRepoHooks` |

## D1 — The facts come from raw events, not hooks

**Decision.** Compaction, errors and subagent lifecycle reach the Hub from the raw session events
that slice 2's ACP client subscribes to. This change needs six types in that subscription:
`session.compaction_complete`, `session.error`, `subagent.started`, `subagent.completed`,
`subagent.failed` and `session.compaction_start`. `session.compaction_start` is subscribed for the
drive's evidence only and maps to nothing.

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
under, and `args` = [the pinned `mcp_server.py` copy that `tool_server.py` maintains, `--call`, a
tool that receives the hook's payload]. That is the shim call mode of
`a-run-reaches-the-hub-without-mcp` (its D4: `mcp_server.py --call <tool>`, fastmcp not imported).
R2: that mode calls a registered `@mcp.tool()`, and **no tool that receives a hook payload
exists**, so this alternative also needs a new tool and route. It reads `AW_RUN_TOKEN` and `HUB_URL`
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
  concurrently, so `automatic` cannot generate twice.
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
- `trigger` (`auto` / `manual`);
- `percent = round(pre_tokens / token_limit * 100, 2)`, only when both are present.

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
  `compaction_percent` and moves the final-warning percent per runner. `consider(..., compacted=True)`
  must pass the same policy inputs as the reading path. **(rebase at IMPL:
  `a-copilot-run-shows-its-credits` unbuilt at R2.)**

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
- `diagnostic_event`. Slice 2's D10 adds one as `diagnostic_event(code, message)`. That shape
  violates `agent-stream-events` *Versioned kind-specific payloads* (*"Diagnostic payloads SHALL
  identify stream and severity"*), and `runner_events.py` states it mirrors the CLI's taxonomy "and
  payload shapes exactly" (`:1-8`). The CLI's is `diagnostic_event(*, stream, severity, summary)`
  → `{version, stream, severity, summary}` (`src/agentweave/stream_events.py:556-573`). So the Hub's
  builder is `diagnostic_event(*, stream, severity, summary, code=None, facts=None)` →
  `{version, stream, severity, summary, code?, facts?}`, `summary` bounded and value-redacted.
  If slice 2 lands its narrower builder first, this change widens it with keyword defaults, so its
  calls keep working. **(rebase at IMPL: `a-copilot-agent-runs-over-acp` unbuilt at R2; cross-slice
  gap reported to its R2.)**
- Neither builder passes `facts` through `redact_secrets` whole, for the `token`-key reason in D4.
  String values go through the value rule; numbers are kept.

**The mapping.**

- `session.error` → `error_event(code="copilot." + kind, message=message, facts={status_code,
  error_code, remediation})`, where `kind` is `errorType` when it matches `^[a-z_]{1,32}$` and
  `unknown` otherwise (`errorType` is an open string, VERIFIED from the schema). `stack`,
  `providerCallId`, `serviceRequestId`, `url` and `eligibleForAutoSwitch` are dropped. This replaces
  slice 2's single `copilot_session_error` code for the case where the raw event arrived.
- `errorType` `quota`/`rate_limit` is recorded like any other error. **The mapper and the recorder
  place no hold.** Slice 4's D8 does place one from the same raw event, through the run's allowance
  reading (`quota` + `quota_exceeded` → `rejected` → `hold_for_reading`), and that is slice 4's to
  keep. The requirement says what this change owns: recording the event neither places nor lifts a
  hold, so there is no second hold and no second hold path. It does not claim a quota error leaves
  the queue unheld.
- `session.compaction_complete` with `success:false` → `diagnostic_event(stream="copilot",
  severity="warning", code="copilot.compaction_failed", summary=<its error, else a fixed
  sentence>)`.

**The echo.** Copilot also turns `session.error` into an ACP `agent_message_chunk` whose text is
`Error: <message>` (appendix A §A; slice 4's R1 read the mapping in `app.js`). **One fact, one
record:**

- Slice 2's D10 accumulates message chunks and flushes a block as one `text_event` when any
  non-message update arrives, and at prompt completion. A block already flushed has been recorded
  (`_on_event` → `record_agent_output` commits it), and cannot be taken back. So "suppress in
  either order" needs a hold, not a filter: **a block whose text begins `Error:` is not flushed
  until prompt completion.** At completion it is dropped when a raw `session.error` of the same turn
  has a `message` the block contains, and emitted as slice 2 would emit it otherwise.
- When the raw event arrives first, the error event is emitted at once; the later block is dropped
  at completion by the same rule.
- When no raw event arrives, the block is emitted exactly as slice 2 emits it. Under slice 2 as
  written, that is **plain text**: its classification needs a matching raw event, so an unmatched
  `Error:` block "stays `text`". "Classified as it is without this change" means that.
- The cost is that an `Error:` block reaches the timeline at the end of the turn rather than
  mid-turn. A model writing prose that starts with "Error:" is delayed the same way, and is emitted
  unchanged.

**Which order is real is unknown**, and CLAUDE.md requires the test to use the real one. Task 1.1
captures it, and task 1.3 tests both orders so that reversing them is caught.

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

R2: **where** this happens is not "the adapter's `build_launch`". Slice 1's `build_launch` is a
`StreamTransport` member returning argv only; an RPC transport (ACP) has none, and its environment
arrives as `RpcTurnRequest.env`. The environment is built by `resolve_agent_env` and ends in the
adapter's `guard_env(proc_env, env_vars)` (slice 1 D10), and slice 2 D3 puts its `GH_TOKEN` strip
there. `guard_env` receives no runner row, so this change passes `provider_config` into
`resolve_agent_env` from the trigger, which holds `runner_row` (`agent_trigger.py:751-765`), and
the Copilot `guard_env` sets or strips from it. **(rebase at IMPL: `each-runner-cli-is-one-adapter`,
`a-copilot-agent-runs-over-acp` unbuilt at R2.)**

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

**Launchability** (adapter member `launchability`): a BYOK runner is authorized iff `api_key_var` is
set and non-empty in the Hub's environment. The reason names the variable, not its value, following
`claude_proxy` (`launchability.py:108-114`). A GitHub login is not required, so slice 2's cached
`CopilotProbe` verdict, whose `session/new` under the `_worker` home reads GitHub auth, supplies only
`present` and the version for a provider runner.

**R2: the verdict can only reach the operator if `provider_config` reaches the probe.** Every
caller builds the probe's `config` from the runner row by hand, with `runner` and `model` only:
`agents.py:552` (the agents list), `:728` (create), `:2004`; `agent_trigger.py:764` (the trigger);
`runners.py:98` (`GET /runners/launchability`); `launchability.py:524`. A unit test of the adapter's
`launchability` passes while every one of those surfaces reports the subscription verdict ("not
signed in") for a provider runner. So one helper, `runner_probe_config(runner_row)`, builds
`{runner, model, provider_config}` and every site above uses it, and test 1.8 asserts the verdict
through `GET /runners/launchability` and the agents list. `launchability-by-provider`
(`runners.py:118`) has no runner row and is unaffected. **(rebase at IMPL: slice 1 D14 moves
`probe_agent` onto the adapter; the call sites stay.)**

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
  with the same `_git` pattern `task_integration.py:148-157` uses.
- `base_sha` is `None` when `main_branch` is unset, the branch does not exist, the command fails, or
  the merge base **equals** the commit (the commit is already on the main branch, so the range is
  empty). Then the bullet names `<commit>` alone and says to review that commit's own changes.
- **It never raises.** `prepare_review_turn`'s refusals (`ReviewTurnRefused`) are about whether a
  review can happen at all, and the trigger turns them into a refused dispatch
  (`agent_trigger.py:962`). A missing base only narrows one bullet, so it must not refuse the turn.

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
  at IMPL: `a-copilot-agent-runs-over-acp` unbuilt at R2.)**
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
  - **The card must not carry `_decide`'s verdict.** `an-ask-me-card-says-what-workspace-only-would-decide`
    (unbuilt at R2) attaches what Workspace only would decide to an operator card. For this card
    that would read "Workspace only would allow this", while the card exists because Workspace only
    does not. The card's verdict is this rule's own sentence: *"This tool acts on GitHub as you. The
    Hub does not decide GitHub actions on your behalf."* **(rebase at IMPL: that change and slice 2
    unbuilt at R2.)**
- **When the server fails to start (R2 correction).** R1 said slice 3's MCP status handling
  surfaces a failed GitHub server. It does not: slice 2's D10 reports only a failure of the server
  named `agentweave`, and slice 3 reads the same status for `agentweave` only. With the toggle on
  and the server failing (a BYOK agent with no GitHub login, or a policy that blocks it), the
  operator would see nothing. So group D adds one mapping: a raw `session.mcp_servers_loaded` /
  `session.mcp_server_status_changed` naming `github-mcp-server` in a state other than connected,
  **while the toggle is on**, gives one `diagnostic_event(stream="copilot", severity="warning",
  code="copilot.github_mcp_unavailable")` per turn. With the toggle off the server is disabled on
  purpose and nothing is reported.

## D10 — Independence of the groups

- **A** touches `runner_events.py`, `checkpoint_trigger.py`, `output_recording.py` and the Copilot
  mapper.
- **C** touches runners (schema, route, migration, UI), `resolve_agent_env` / the Copilot
  `guard_env`, the adapter's `launchability`, the probe-config sites (D7), the per-run override
  check (`agent_trigger.py:1618`) and the composer's model control.
- **B** touches the context renderer, `review_turn.py`, `ROSTER_CONFIG_KEYS`, and the agent
  Settings UI.
- **D** touches slice 2's argv builder and `decide_permission`, the Copilot mapper (one
  diagnostic), `ROSTER_CONFIG_KEYS`, and the agent Settings UI.

B and D share one UI section and one tuple. Each adds its own control and its own key, so rejecting
one leaves the other's standing. No group's test imports another group's code. R2: groups A and D
both use `diagnostic_event`'s widened shape (D5); if A is cut, D's task 5.1 widens it.

## Dependencies on slices 1–4, as written at R2

R2 read each slice's `design.md` as it stood on 2026-09-28 (each is in its own R2 concurrently, so
these may move). Every row is **(rebase at IMPL: unbuilt at R2)**.

| This change assumed (R1) | The slice's design says | Consequence here |
|---|---|---|
| Adapter member `map_events` maps Copilot's events | Slice 1 D3: `map_events(line) -> ParsedLine` is a **`StreamTransport`** member. An RPC transport maps inside `run_turn` via `cb.on_event`. Slice 2 D10 puts the mapping in `copilot_acp.CopilotEventMapper` | Group A's mapping edits `CopilotEventMapper`. Tests 1.2/1.3 drive that class |
| Adapter member `build_launch` sets env and argv | Slice 1: `build_launch(req) -> list[str]`, argv only, **stream** transports only. Slice 2 D3: `copilot_acp.build_acp_argv(...)`; env from the trigger through `resolve_agent_env` + `guard_env` | C's env goes through `resolve_agent_env`/`guard_env` with `provider_config` passed in (D7). D's flag goes in `build_acp_argv` (D9) |
| Adapter member `decide_posture` decides Copilot's approvals | Slice 1: `posture_at_rest` (adapter) and `posture_for` (RPC transport) map the operator's posture; neither decides a request. Slice 2 D8: `copilot_acp.decide_permission` decides each request | D's rule lives in `decide_permission` (D9) |
| Adapter member `launchability` authorizes BYOK | Slice 1: `launchability(agent, config)`, must not raise. Slice 2 D15: a cached `CopilotProbe` verdict | C passes `provider_config` in `config` from every probe site (D7) |
| Adapter member `catalog_provider` names the provider's catalog | Slice 1: `catalog_provider: ClassVar[str]`, one per adapter | Cannot vary per runner. C checks the model per runner at the four sites in D7 |
| Slice 2 builds the MCP `env` as an allow-list | Slice 2 D3: **no** `env` block; the tool server inherits the whole run environment | The BYOK key reaches the tool server; the requirement no longer claims otherwise (D7) |
| Slice 2 writes hook files at creation | Slice 2 D4: writes the agent file and `agentweave-mcp.json` only. Slice 1 D16 reserves `write_native_files` "hooks for slice 5" and a `hooks` member | Nothing to remove; test 1.6 is a guard. Slice 1's reservation should drop `hooks` (reported) |
| Slice 2's `Error:` classification is independent | Slice 2 D10: an `Error:` block matching a raw `session.error` becomes `error_event(code="copilot_session_error")`; unmatched stays `text` | D5 replaces the matched case with the raw event's own error event and holds `Error:` blocks to turn end |
| Slice 2 has no `diagnostic_event` | Slice 2 D10 adds `diagnostic_event(code, message)` without `stream`/`severity`, which `agent-stream-events` requires | D5 widens it to the CLI's shape; reported to slice 2 as a spec gap |
| Slice 2 subscribes what it needs; this change adds six | Slice 2 D10 already has `session.error`; slice 4 D1 adds `session.compaction_complete` and `session.error` | This change unions four new types in (D1) |
| `/compact` might reach Copilot as a bare prompt | Slice 2 D5: every turn carries a per-turn context block before the message | Never; drive 7.2 replays the fixture |
| Full access = `allow_all` | Slice 2 D8 | R2 verified in `app.js` that `allow_all` does not trust the folder (D3) |
| Slice 3's shim has a "hook call mode" | Slice 3 D4: `mcp_server.py --call <tool>` calls registered tools only | D2's fallback also needs a hook-receiving tool (D2) |
| Slice 4 owns quota holds | Slice 4 D8: a `quota`/`quota_exceeded` `session.error` places a hold through the allowance reading | The requirement claims only that *recording* adds no hold (D5); test 1.3 checks the recorder, not the run |
| Slice 4 per-runner thresholds | Slice 4 D10: `resolve_policy(..., compaction_percent=)`, `final_warning_percent` | `consider(..., compacted=True)` passes the same policy inputs (D4) |
| Migration order | Slice 2 adds one (widening `ck_runners_cli`), slices 3 and 4 one each; head `0110` at R2 | C's migration numbers after whichever land first |

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

## Open questions for R2/R3

1. **Slice 2 alignment.** *(Answered in R2: see the dependency table, D5 and D9.)* What does slice 2's raw-event subscription list contain? Where does its
   mapper classify `Error:` chunks? Where does Copilot's `request_permission` meet `_decide`
   (D5, D9)?
2. **Delivery.** Are the six types actually delivered over ACP (**INFERRED**)? Task 1.1 settles it.
   If not, group A's source falls back to D2's hook transport, and the operator is told.
3. **Folder trust.** *(Answered in R2: no; VERIFIED-CODE, D3.)* Does ACP `allow_all: on` trust the folder (and so load repo hooks)? Read
   `app.js` around `allow_all` and `trusted_folders` (D3).
4. **`ReviewContext` and the merge target.** *(Answered in R2: `Project.main_branch`, a new merge-base, `base_sha`; D8.)* Does `ReviewContext` already know the merge target?
   `task_integration` resolves "the branch approval merges into". Find the helper (D8).
5. **Claude compactions.** Claude's stream-json `compact_boundary`: should `runner_parsing.py` emit
   `status("compacted")` too, so Claude gets D4's backstop? It is out of scope here; file it if
   useful.
6. **BYOK credits.** Under BYOK, what does `session.usage_checkpoint.totalNanoAiu` read? This affects
   slice 4's display, not this change.
7. **Built-ins on a detached HEAD.** Does `code-review` accept an explicit `<base>..<commit>` range
   when HEAD is detached with a clean tree? This is documented as "branch diffs", so it is
   **INFERRED**. Drive task 7.7 checks it (R2: R1 said 7.2).
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
     runner's key is today. Acceptable?
9. **BYOK and GitHub sign-in (R2).** Does ACP `session/new` report `authRequired` under BYOK when
   no GitHub login exists? Task 1.1 run (c) records whether the scratch home was signed in and what
   `session/new` returned. If it demands a login, BYOK agents need one after all, and D7's
   launchability rule is wrong.
10. **Copilot's stdio MCP `env` (R2).** Does an `env` block in `--additional-mcp-config` replace or
    merge with the inherited environment? If it replaces, the Hub could keep the key out of its tool
    server by naming the variables the server needs (as Codex does). Not needed for this change;
    carried to slice 3, which decides what reaches the tool server.
