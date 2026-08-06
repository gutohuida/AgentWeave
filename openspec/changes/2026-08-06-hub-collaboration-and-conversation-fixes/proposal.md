# Agents act on what they are told, Codex collaborates by default, and the conversation stops shouting

**Approved:** 2026-08-06, operator

## Why

The operator manually tested `proj-a35df4bc` ("Composer Review" — 2 Codex/`gpt-5.4-mini`, 2
Claude/`claude-haiku-4-5`) against the work shipped by `2026-08-06-hub-composer-and-chrome-refinement`
and reported six problems, verbatim:

> A couple of fixes from the last changes: claude doesn't seem to be getting my message. I've sent a
> clear instruction and it just ignored. The user message box in the conversation is too bright.
> Seems out of place, feels like it is using the old dark navy color palete. Let's remove the ability
> and the buttons that enable the user from one screen to send message to another agent. Is counter
> intuitive. Also codex not being able to be part of the collaboration defeats the purpose. We need
> codex collaborating. Around the conversation chat box seems to be a darker box. Feels weird. There
> is a charcoal chat box and then a black box around it? IT's weird. I don't want to altomatically
> fold previous conversation upon sending a new message.

Two of these are functional defects that make the product's central premise — multiple agents
collaborating under an operator — not work at all. Four are interaction and chrome defects.

### The message was delivered. The Hub told the agent to ignore it.

This is not a message-delivery defect, and the queue is not at fault. Evidence taken from the live
dev Hub and `hub/data/agentweave.db` before any code was changed:

- Both operator messages to `claude-haiku-1` are `state: "delivered"` carrying a real
  `delivered_in_run_id`; both runs completed with `exit_code: 0`. `format_turn_prompt`
  (`hub/hub/inbound_queue.py:88`) concatenates every selected entry's `content` verbatim, with no
  truncation, filtering, or dedup anywhere in the path.
- Yet the agent's own recorded thinking, in **both** runs, opens with *"The user hasn't given me any
  explicit task yet."* It then called `send_message` addressed to an agent literally named
  `principal`, which the Hub correctly rejected: `Unknown recipient 'principal': no agent by that
  name is registered in this project`.
- `GET /agents/agent-context?agent=claude-haiku-1` shows why. The Hub injects, as the agent's system
  prompt, this:

  ```
  # claude-haiku-1 - AgentWeave Onboarding Context
  - Project session has not been synced to Hub yet.
  ### Team
  - No declared agents are synced.
  ## External Agent Rules
  You are registered with AgentWeave but are not declared in `agentweave.yml`.
  Until the principal assigns you work:
  - do not modify files
  - do not claim tasks
  - send a short availability message to the principal
  ```

The agent followed its instructions exactly. The instructions were wrong.

### …and the prompt was being cut off at its first newline

Fixing the context was necessary but not sufficient. With the stand-down block gone and the real
roster in place, a re-test still produced *"the user hasn't given me any task yet"* — while the
agent correctly named its peers. That split is the tell: the roster arrives through
`--append-system-prompt-file`, a path containing no newlines, and the operator's message arrives
as the `-p` argument, which does.

`claude` installs from npm as **`claude.CMD`**. A `.cmd` is executed by `cmd.exe`, which parses
the command line before the target program ever sees it, and a raw newline inside an argument
terminates the command there. The Hub builds the turn prompt as
`access_path_notice(...) + "\n\n" + format_turn_prompt(...)`, so every Claude run on Windows
received exactly this and nothing else:

```
[AgentWeave] Tool access: the `agentweave` MCP tools are available — call send_message / …
```

The operator's instruction was queued, selected, delivered, and stamped `delivered_in_run_id` —
and never reached the model. Confirmed directly by spawning through a `.cmd` shim and reading the
child process's own `argv`: everything after the first newline is gone. `codex` resolves to a real
`.EXE` and is unaffected, which is why this never showed up in Codex runs.

Both defects were real and independent. The first made agents refuse work they understood; the
second meant they never saw it.

`_render_hub_agent_context` (`hub/hub/api/v1/agents.py:737`) decides which of three context shapes to
render by testing `declared = agent in session_data["agents"]`, where `session_data` is read from the
`project_sessions` table. **That table's only two writers — the CLI's `Session.save()` push and the
watchdog — were both deleted in `2026-08-03-single-runtime`.** `2026-08-06-hub-composer-and-chrome-refinement`
independently confirmed zero remaining callers. So `session_data` is `None` for every project created
the normal way, `declared` is permanently `False`, and every Hub-native agent lands in the
`elif registered:` branch: a stand-down block instructing it not to work, plus an empty `### Team`
that leaves it unable to name a single peer. `select * from project_sessions` holds rows for exactly
two projects, both seeded by direct API calls during earlier live testing; the two normally-created
projects have no row at all.

The same dead source explains a second symptom, flagged as an open question by the previous change
and never diagnosed: `_display_model`/`_runner` (`agents.py:456`) derive from `agent_meta`, assembled
from that same `session_agents_meta`, so every agent reports `runner: "native"` and
`display_model: "Native"` despite holding a correct `runner_id`.

### Codex was configured with a tool surface it could not call

`agent-tool-surface`'s shipped requirement "One tool surface, configured automatically" already says:

> A tool surface the Hub has configured SHALL be invocable by the agent it was configured for. The
> Hub MUST NOT start a run whose tool surface it has configured but which it knows the agent cannot
> call. […] Where a provider offers a mode in which approvals can be answered per request and a mode
> in which they cannot, the Hub SHALL use the mode that preserves the operator's protections.

Today's default Codex run violates every sentence of that. `_build_codex_command` registers the
AgentWeave MCP server and then launches `codex exec`, which is non-interactive and — verified against
the installed `codex-cli 0.146.0` — exposes **no `--ask-for-approval` flag at all**. Approvals resolve
by policy: deny everything (killing MCP tool calls) or `--dangerously-bypass-approvals-and-sandbox`
(killing the sandbox). `2026-08-06-agent-messaging-delivery` established this and built the fix —
`hub/hub/codex_appserver.py`, which answers approvals Hub-side and accepts the Hub's own server
without weakening the sandbox — but left it **opt-in** behind an `--app-server` sentinel in
`Runner.flags`. The Add-agent dialog creates runners with no flags (`agents.py:555`), so every Codex
agent an operator can actually make lands on the broken transport. All four runners in
`proj-a35df4bc` carry `flags: None`.

This change is therefore not a new capability. It brings the default into compliance with a
requirement that already shipped.

### Four chrome and interaction defects

- **The operator's own message bubble reads navy.** `AgentTimeline.tsx:445` tints it
  `color-mix(in oklab, var(--blue) 14%, var(--surface-2))` over a `--blue` 30% border. `--blue` is
  the single chromatic accent (`#7c8cff` dark / `#5063d8` light), otherwise reserved for `--ring`.
- **The composer sits inside a visible darker box.** Two layers paint dark regions around it:
  `.conversation-composer-surface`'s `box-shadow: 0 20px 52px rgba(2, 5, 18, 0.28)` — a large
  near-black halo rendered against an already near-black `--bg` — and `.conversation-composer-fade`'s
  `linear-gradient(to top, var(--bg) 70%, transparent)` behind the whole strip. `index.css:453` already
  states the intent that the border alone carries the separation.
- **Turns fold themselves.** `AgentTimeline.tsx:115` computes `folded = foldOverride[key] ?? !isLastTurn`.
  Nothing in the send handler folds anything — the rule is derived, so the instant a new run appends a
  turn, the turn the operator was reading stops being last and collapses under them.
- **Any conversation can silently send elsewhere.** `ComposerAgentSelector` puts a target-agent picker
  in every composer; `handleComposerSubmit` posts to a different agent when it differs, and unless the
  app happens to navigate, the message leaves no trace in the conversation the operator was looking at.

## What changes

1. Canonical agent context is built from the Hub's own tables. The `agentweave.yml`/"declared"/
   "principal" framing and the stand-down block are removed; the roster is real.
2. Agent summary `runner`/`display_model` derive from the bound `Runner`.
3. Codex runs use the app-server transport by default, with an explicit opt-out.
4. The operator's message bubble becomes neutral.
5. The composer's drop shadow and fade band are removed.
6. Turns never fold automatically; folding is entirely manual.
7. The cross-agent target picker is removed, and collaboration readiness moves to the agent card.

## Impact

- **Affected specs:** `agent-context-onboarding` (largest), `agent-composer`, `agent-conversation-workspace`,
  `agent-tool-surface`, `runner-registry`.
- **Affected code:** `hub/hub/api/v1/agents.py`, `hub/hub/api/v1/agent_trigger.py`,
  `hub/hub/codex_appserver.py`, `hub/hub/runner_commands.py`, `hub/ui/src/components/agents/*`,
  `hub/ui/src/index.css`.
- **No migration.** Existing Codex runners carry `flags: None`, so inverting the default repairs them
  in place. `project_sessions` is left untouched; this change merely stops reading it for context.
- **Behaviour change for external agents.** An agent registered with the Hub but never bound to a
  runner previously received a stand-down block. It now receives real runtime context. That block was
  protecting nothing — it was applied to every agent unconditionally, including the operator's own.
