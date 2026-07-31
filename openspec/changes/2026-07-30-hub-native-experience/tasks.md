# Implementation plan

## Working protocol — read before starting any phase

1. **Re-read the spec before beginning a phase.** Read `proposal.md`, `design.md`, and every
   `specs/*/spec.md` this phase touches. The decisions in `design.md` carry reasoning that the task
   lines below deliberately do not repeat.
2. **Run `/handoff` at every threshold** — after each numbered phase completes, and after any
   substantial chunk within a long phase. This is not for compaction; it is so that work can be
   resumed by a different session or a different model if this one is interrupted mid-implementation.
   A phase is not done until its handoff is written.
3. **Verify against scenarios, not intent.** Each phase ends with a verification task naming the
   spec whose scenarios must pass.
4. **Order is by dependency, not by value.** Where a phase seems out of order, the reason is stated
   under its heading.

## Ordering revision — 2026-07-31

The original order was authored incrementally and put four things in the wrong place. Corrected:

| Moved | From | To | Why |
|---|---|---|---|
| **Identity binding** | Phase 5b | **Phase 4**, before the queue | Every queue entry stamps an origin. Building the queue while identity is self-declared (`--from-agent`) means hop depth, attribution, timeline colours, and task assignment are all built on an unverified field. Retrofitting means reworking the queue's core record. |
| **Crash recovery** | Phase 5b | **Phase 3**, with the runtime | The moment the Hub owns processes, orphans and unreconciled runs are possible. Shipping the runtime without recovery means every crash during development leaves zombies and loses queued entries. |
| **Worktree isolation** | Phase 5b | **Phase 5**, before the queue | The scheduler is what causes concurrent turns. Concurrent turns in a shared directory produce silent lost updates. Isolation must exist before concurrency does, not after. |
| **Tool surface** | Phase 5b | **Phase 7**, right after the queue | `get_inbox` becomes a bypass around the hop budget and drain cap the instant the queue exists. Leaving it live across five phases means the governance is decorative for most of the project. |
| **Approval gates** | Phase 5 | **Phase 15**, after specs | Gates should cover both task lifecycle *and* specification gates. Building them before `spec-traceability` means building them twice. |

**Gap found and filled:** multi-project support had no phase at all. `hub-visual-language` requires
navigation to list projects with project-scoped views as tabs; `Project` is already a table and all
five tables already carry `project_id`, but there is no `projects` API and no UI. Now **Phase 10**.

**Numbering defect fixed:** the composer phase carried `4.x` task numbers belonging to the queue phase.

---

## 0. Decisions — closed

- [x] 0.1 **Install channel:** `uv tool install` primary, `pipx` supported, `pip` documented
      fallback. No npm (wrong runtime — would add Node without removing Python). No signed
      installer until there are users who lack Python.
- [x] 0.2 **Remote Hub: out of scope.** Local-only for this change. A future "AgentWeave Cloud"
      is a separate concept — see `openspec/explorations/2026-07-31-future-directions.md`.
- [x] 0.3 **Execution is unified.** All turns run through the Hub's direct execution path.
      The watchdog never triggers.
- [x] 0.4 **Inbound model:** one uniform per-agent queue holding both operator input and peer
      messages. Turns start whenever the queue is non-empty and the agent is idle — never waiting
      on operator input. Drain order is arrival order.
- [x] 0.5 **Loop control:** hop budget with depth stamped on the queue entry. Operator entries are
      depth 0; emitted messages carry `min(depth of drained entries) + 1`. Over-budget entries queue
      without starting a turn; operator input resets the chain.
- [x] 0.6 **Drain cap:** per-turn maximum entry count. Over-cap entries stay queued and arrive on
      following turns — never truncated or summarized.
- [x] 0.7 **Both limits configurable** with documented defaults.
- [x] 0.8 **Queueing is always the default.** Instead of interrupt-and-deliver, a running turn can be
      **stopped**. Queued entries survive the stop and drain into the following turn.
- [x] 0.9 **Defaults:** hop budget **6**; per-turn delivery cap **10** entries.
- [x] 0.10 **Runner / agent / behaviour are separate concepts.** Job-title personas
      (`VALID_ROLE_IDS`, the 21 guides in `templates/roles/`) are retired in favour of a charter
      (purpose · scope · default skills) plus invocable skills. `VALID_ROLES`
      (principal/delegate/reviewer/collaborator) survives as a per-task relationship.
- [x] 0.11 **Multi-agent machinery is absent, not merely off, in single-agent projects.**
- [x] 0.12 **Agents may request agents within a project agent budget**, mirroring the hop budget.
- [x] 0.13 **One git worktree per agent that writes**, optimistic, no file locking. In a shared
      directory there is no merge — only silent lost updates. Read-only agents may share the
      primary checkout.
- [x] 0.14 **Crash recovery reconciles runs**: absent process → `interrupted`, its delivered entries
      return to the queue undelivered; shutdown terminates the process group.
- [x] 0.15 **MCP inverts** — the Hub pushes state in at turn start, the tool surface carries intent
      out. ~9 of 24 tools survive; the two duplicate MCP servers collapse to one; the Hub injects
      tool configuration at spawn.
- [x] 0.16 **Account in tokens, not currency.** Currency is a labelled API-equivalent estimate;
      rate-limit allowance is preferred for subscription users.
- [x] 0.17 **Command-based operation is first-class**, not a fallback.
- [x] 0.18 **Tool-protocol availability is a per-runner capability, probed per environment.**
- [x] 0.19 **Runner priority: Claude Code and Codex first, locally. Copilot second.**
- [x] 0.20 **Agent identity is injected by the Hub at spawn and is not overridable.**
      `cli.py:1519` currently reads `sender=args.from_agent or "unknown"` from an optional flag.
- [x] 0.21 **Split the operator CLI from the agent surface.**
- [x] 0.23 **Requirement-level traceability is the differentiating capability** — requirement → task
      → diff → verified, in one place, self-hosted.
- [x] 0.24 **Requirement identifiers are stable and visible.**
- [x] 0.25 **Changing a requirement stales its evidence**, distinctly from having none.
- [x] 0.26 **Rigor is declared per document — sketch / contract / gate — defaulting to sketch.**
- [x] 0.27 **A new agent color palette is authored**, not assembled from existing status tokens.

---

## 1. Feel foundation

*No dependencies. Ships independently. Visibly changes the application on its own.*

- [x] 1.1 Vendor DM Sans Variable and JetBrains Mono as subset `.woff2` under `hub/ui/public/fonts/`;
      add `@font-face` rules with `font-display: swap` and explicit `unicode-range`.
- [x] 1.2 Remove the `fonts.googleapis.com` preconnects and both stylesheet `<link>`s from
      `hub/ui/index.html`; point `--font-sans` / `--font-mono` at the vendored families.
- [x] 1.3 Migrate the 24 files using the Material Symbols `Icon` wrapper to `lucide-react`; delete
      `components/common/Icon.tsx` and the Material Symbols usage in `common/EmptyState.tsx`.
- [x] 1.4 Add a motion scale to `hub/ui/src/index.css` (fast/base/deliberate durations, default
      easing) with a `prefers-reduced-motion` block that disables transitions.
- [x] 1.5 Rebuild the radius scale from one base value with `sm`/`md`/`lg`/`xl` steps, raising the
      base from 6px toward ~10px; add a distinctly softer radius for self-contained content surfaces.
- [x] 1.6 Rebuild the control base so **every** control reserves border space at rest and quiet
      variants render that border transparent; compensate horizontal padding for the border
      thickness. Verify no reflow on hover.
- [x] 1.7 Add press physicality to raised controls: resting top-edge highlight, inverted to an inset
      shadow while pressed, resting elevation removed while pressed and disabled; tint elevation with
      the control's own colour.
- [x] 1.8 Paint inner decoration via an inset pseudo-element at the outer radius minus the border
      thickness, so concentric corners stay parallel.
- [x] 1.9 Make icons subordinate by default using selectors that never override explicit emphasis;
      correct optical alignment against labels.
- [x] 1.10 Add coarse-pointer touch targets via an invisible overlay that leaves fine-pointer sizing
      unchanged; adopt a mobile-first size scale that shrinks on larger viewports.
- [x] 1.11 Apply hover / pressed / `focus-visible` treatments across Badge, Button, Card, list rows,
      tabs, and sidebar entries.
- [x] 1.12 Apply `tabular-nums` to every live numeric readout.
- [x] 1.13 Collapse navigation and content onto one ground plane; reduce the boundary to a single
      hairline lighter than any control outline near it.
- [x] 1.14 Restrict distinct fills to menus, popovers, dialogs, the composer, and content surfaces.
- [x] 1.15 Make the primary panes resizable — drag target wider than the visible line, clamped
      bounds, persistence across sessions, single-gesture reset.
- [x] 1.16 Restyle scrollbars as overlay handles: no track, no steppers, inset handle, stronger on
      hover.
- [x] 1.17 Verify: fonts render with the network offline; icons present at first paint;
      reduced-motion suppresses transitions; no control shifts layout when hovered or pressed;
      `hub-interface-feel` scenarios and the surface/separation/resize/scrollbar scenarios of
      `hub-visual-language`.
- [x] 1.18 **`/handoff`**

## 2. Streaming replaces polling

*No dependencies beyond an already-working SSE channel.*

- [x] 2.1 Inventory the 9 `refetchInterval` call sites in `hub/ui/src/api/` against the 12 event kinds
      in `hooks/useSSE.ts` (the plan's "9" undercounted — `agent_output`, `context_warning`,
      `spec_updated` were already added since this task was written). Findings:
      - **Fully covered** (poll is a redundant backstop): `status` (status.ts), `agent/:name/sessions`
        (agents.ts) via `agent_session_changed`, `logs` (logs.ts) via generic any-event invalidation.
      - **Bug, now fixed:** `agents` (agents.ts) has a `session_synced` listener that was dead code —
        `session_synced` (broadcast by `hub/hub/api/v1/session_sync.py:93-97` on every CLI roster sync)
        was missing from `SSE_EVENT_TYPES`, so `useSSE.ts`'s dispatch loop silently dropped it before
        the listener ever ran. Fixed by adding it to the allowlist; regression test added in
        `useSSE.test.tsx`.
      - **Correction after auditing the backend directly:** `jobs` was misclassified above as having
        "no event yet" — `jobs.py`/`scheduler.py` already broadcast `job_created`/`job_updated`/
        `job_deleted`/`job_fired`; they were just missing from the frontend allowlist, same bug class
        as `session_synced`. Fixed in 2.2 below.
      - **Second correction, after tracing the remaining three end to end:** none of them needed new
        backend broadcasts either. Each is a *derived read model* built entirely from rows that
        already trigger an existing event on write: `agents/:name/timeline` merges `Message`
        (`message_created`), `EventLog` (`log_event`), and `AgentHeartbeat` (`agent_heartbeat`);
        `agent/:name/chat/*` merges `Message` (`message_created`) and `AgentOutput` (`agent_output`);
        `session-sync`'s GET mirrors the exact row `session_synced` already fires on write. All three
        were pure frontend wiring gaps, same as `jobs`.
- [x] 2.2 Emit events for any uncovered entity so every live view has a corresponding event. No new
      backend events were needed in the end (see the corrected 2.1 findings above) — every entity's
      source rows already had a broadcast; the gap was always frontend wiring. Done:
      - `jobs` (agents.ts is unaffected; jobs.ts + useSSE.ts) — `job_created/updated/deleted/fired`
        added to `SSE_EVENT_TYPES` and the central switch, invalidating `['jobs']` + `['jobs', id]`.
      - `agent/:name/chat/*` (agentChat.ts) — new `eventTargetsAgent()` predicate matching
        `message_created` (`to`/`recipient`) and `agent_output` (`agent`), invalidating both chat
        query keys per-agent.
      - `agents/:name/timeline` (agents.ts) — new `eventBelongsToTimeline()` predicate matching
        `message_created`/`log_event`/`agent_heartbeat` for the given agent.
      - `session-sync` (status.ts) — direct listener on `session_synced`, invalidating
        `['session-sync']`.
      - All four keep their existing `refetchInterval` as a backstop (2.3 removes those). Regression
        tests: `useSSE.test.tsx` (job events), `agentChat.test.tsx` (`eventTargetsAgent`),
        `agentTimelineEvents.test.tsx` (`eventBelongsToTimeline`). tsc clean, 192/192 tests passing.
- [ ] 2.3 Remove all `refetchInterval` configuration; drive invalidation from events only.
- [x] 2.4 Add stream-health state: visible indicator on disconnect, automatic reconnect, and state
      reconciliation on resume. Automatic reconnect already existed (`scheduleReconnect`, 3s retry);
      added the other two:
      - **State machine** in `useSSE.ts`: `closed | connecting | open | reconnecting`, exposed via
        `getSSEConnectionState()` / `onSseStateChange()` / the `useSSEConnectionState()` hook.
      - **Indicator**: a red "Reconnecting…" chip in `StatusBar.tsx`, shown only in the
        `reconnecting` state — quiet by default like the existing context-warning chip, not a
        permanent "Live" badge cluttering the healthy path.
      - **Reconciliation on resume**: `useSSE()` now calls `queryClient.invalidateQueries()` (no
        filter — invalidate everything) on every reconnect via the existing `onSseReconnect` hook,
        so entities that lost SSE coverage while the stream was down catch up immediately rather
        than waiting for their next poll (or never, once 2.3 removes the poll).
      - Regression tests in `useSSE-lifecycle.test.tsx`: state reaches `open` then `reconnecting`
        when a stream ends unexpectedly; `invalidateQueries` fires on the real second connect (not
        the first). tsc clean, 194/194 tests passing.
- [ ] 2.5 Verify: task, message, agent-status and log views update live with polling removed; killing
      the stream shows the indicator and recovers on restore.
- [ ] 2.6 **`/handoff`**

## 3. Native runtime, packaging, and crash recovery

*Crash recovery moved here from Phase 5b: the moment the Hub owns processes, orphans are possible.*

- [ ] 3.1 Add a host-native start path for the Hub, keeping the Docker image building for
      coordination-only deployments.
- [ ] 3.2 Add a launchability probe: for each configured agent, report whether its CLI is present,
      authorized, and runnable, with a stated reason when it is not.
- [ ] 3.3 Introduce a run record — identity, agent, session identity as a typed field, start time,
      status, exit outcome, **process identity and heartbeat**.
- [ ] 3.4 Implement process spawn and output capture with a PTY. **Prototype on Windows first**;
      account for `.cmd` shims (`cli.py:2341`).
- [ ] 3.5 Rewrite `POST /api/v1/agent/trigger` to spawn directly and return a run identifier; delete
      the synthetic-message construction, the `[Session: …]` / `[NewSession]` body tags, and
      `execution_confidence` (`agent_trigger.py:133-161`).
- [ ] 3.6 Emit run lifecycle and output events on the SSE channel; render them in the agent view.
- [ ] 3.7 Implement interrupt and stop for an owned run.
- [ ] 3.8 Reconcile on Hub start: a run whose process is absent becomes `interrupted`.
- [ ] 3.9 Terminate the process group on Hub shutdown so no agent process is orphaned.
- [ ] 3.10 Route scheduled jobs through the direct execution path; remove the watchdog's
      message-scanning trigger branch, keeping only timer duties.
- [ ] 3.11 Remove `agentweave switch` and `agentweave agent set-session` from the Hub-managed path;
      resolve provider environment and session continuity inside the Hub.
- [ ] 3.12 Ship `alembic.ini` in `package-data` — a pip install currently logs
      *"alembic.ini not found … skipping migrations"* and runs unmigrated.
- [ ] 3.13 Bind `127.0.0.1` by default, not `0.0.0.0`; honour the documented port variable, currently
      ignored.
- [ ] 3.14 Remove the Docker gate from `cmd_hub_start` (`cli.py:3316`, `_docker_available()`).
- [ ] 3.15 Add `--app` to open a chromeless browser app-mode window at the Hub URL.
- [ ] 3.20 **Stop the Hub silently serving a stale UI.** `hub/hub/static/ui/` is a committed build
      artefact that no dev step refreshes, so the Hub served a bundle from 2026-07-20 while the
      source had moved on — the change looked like it had not applied. Either build the UI as part
      of the Hub's build/packaging, or have the Hub report the bundle's build stamp so staleness is
      visible rather than silent.
- [ ] 3.21 **Validate `Host` and `Origin` on `GET /api/v1/setup/token`.** It currently guards only
      on client IP (`_is_local_address`), so it hands a live API key to any caller from a loopback
      or Docker-bridge address. That admits any local process, and a browser-based DNS-rebinding
      attack, since CORS does not protect against a rebound `Host`. Require `Host` to be a loopback
      allowlist entry and `Origin` to be absent or same-origin.
- [ ] 3.22 **An unreachable Hub must not present the API-key prompt.** `bootstrapState === 'failed'`
      currently falls through to `SetupModal`, asking the operator to paste a key — which cannot fix
      "the server is not running". Report the connection failure and offer a retry; reserve the key
      prompt for a genuinely unconfigured remote Hub.
- [ ] 3.16 Update `hub/tests/` for direct execution; delete tests asserting the message-tag protocol.
- [ ] 3.17 Rewrite the README quick start to the actual one-command flow.
- [ ] 3.18 Verify: trigger starts a process and streams output with no watchdog running; a missing
      binary fails with a stated reason; killing the Hub mid-run leaves no orphan and marks the run
      interrupted.
- [ ] 3.19 **`/handoff`**

## 4. Identity, runner capability, and surface split

*Moved ahead of the queue. Every queue entry stamps an origin; building that on a self-declared
field means reworking the queue's core record later.*

- [ ] 4.1 Inject a per-run agent identity at spawn; bind identity to the connection on the
      tool-protocol path.
- [ ] 4.2 Remove `--from-agent` and every caller-supplied sender (`cli.py:1519`); refuse
      unattributed effects rather than falling back to `"unknown"`.
- [ ] 4.3 Probe tool-protocol availability per runner per environment; replace `hub_client_mode`
      with probed capability plus operator override. **Claude Code and Codex first; Copilot after.**
- [ ] 4.4 Split the agent surface from the operator CLI: a small identity-bound verb set for agents,
      injected and configured by the Hub, separate from the operator's Hub-management and
      diagnostic commands.
- [ ] 4.5 Tell the agent at turn start which access path is in use; never offer an unavailable one.
- [ ] 4.6 Verify the identity and access-path scenarios of `agent-tool-surface`, including that an
      agent cannot cause an effect attributed to another agent.
- [ ] 4.7 **`/handoff`**

## 5. Workspace isolation

*Moved ahead of the queue. The scheduler is what causes concurrent turns; isolation must exist
before concurrency does.*

- [ ] 5.1 Provision a git worktree per writing agent, on its own branch, sharing the object database;
      prepare it before the agent's first turn.
- [ ] 5.2 Let read-only agents share the primary checkout; share dependency directories by symlink to
      avoid per-worktree install cost.
- [ ] 5.3 Surface merge conflicts with the diverging agents identified.
- [ ] 5.4 Release worktrees on agent removal, reporting unmerged work rather than discarding it.
- [ ] 5.5 Verify the isolation scenarios of `hub-native-runtime` — two agents modifying the same file
      during overlapping turns lose nothing.
- [ ] 5.6 **`/handoff`**

## 6. Inbound queue and turn scheduling

- [ ] 6.1 Add the queue entry record: typed origin, content, arrival time, hop depth, delivery state,
      delivered-in-turn reference.
- [ ] 6.2 Reserve `user` as an agent name; delete every `sender == "user"` comparison
      (`watchdog.py:802`, `agent_chat.py:78,202`) and the subject-text discriminator.
- [ ] 6.3 Implement the scheduler: idle + non-empty queue → start turn; arrivals during a turn →
      queue; turn end with entries remaining → start the next turn.
- [ ] 6.4 Implement atomic drain — select up to the cap in arrival order and mark delivered in the
      same transaction that starts the turn.
- [ ] 6.5 Return entries to the queue when their run is interrupted (pairs with 3.8).
- [ ] 6.6 Build the turn prompt by inlining entry content with per-entry attribution. Delete the
      *"You have a new AgentWeave message … call `get_inbox()`"* indirection
      (`watchdog.py:3866,5178,5184,5370,5375`).
- [ ] 6.7 Implement hop depth: operator entries at 0, emitted messages at `min(drained depths) + 1`;
      over-budget entries queue without starting a turn.
- [ ] 6.8 Add configuration for hop budget and per-turn cap, with defaults, inspection, and visible
      rejection of invalid values.
- [ ] 6.9 Emit stream events for entry queued, delivered, withdrawn, and chain suspended.
- [ ] 6.10 Implement withdrawal of undelivered entries.
- [ ] 6.11 Implement stop-the-running-turn: terminate the process, record the turn as stopped
      (distinct from completed and failed), preserve queued entries, do not redeliver.
- [ ] 6.12 Verify against `agent-inbound-queue` — two agents messaging each other halt at the budget
      and resume on operator input; stopping a turn loses no queued work.
- [ ] 6.13 **`/handoff`**

## 7. Tool surface reconciliation

*Immediately after the queue: `get_inbox` becomes a bypass the instant the queue exists.*

- [ ] 7.1 Remove the bypass tools: `get_inbox`, `mark_read`, `register_agent`, `get_agent_config`,
      `update_agent_config`, `register_session`, `heartbeat`, `get_context`, `get_agent_context`,
      `get_status`.
- [ ] 7.2 Add `request_agent`, subject to the agent budget; gate the job tools (`create_job`,
      `run_job`, `delete_job`, `toggle_job`) behind allowance or approval.
- [ ] 7.3 Collapse `src/agentweave/mcp/server.py` and `hub/hub/mcp_server.py` into one surface;
      decide the fate of `save_checkpoint`, which exists only on the CLI side.
- [ ] 7.4 Inject tool configuration when the Hub spawns an agent; retire the `mcp-setup` ceremony.
- [ ] 7.5 Ensure every outbound capability is reachable by command, routed through the same queue,
      budgets, and attribution as the tool-protocol path.
- [ ] 7.6 Verify a full multi-agent session with the tool-protocol server disabled entirely.
- [ ] 7.7 **`/handoff`**

## 8. Conversation timeline and agent colours

*Placed here so the queue's behaviour becomes visible as soon as it exists.*

- [ ] 8.1 Assign each agent a stable colour index at registration, persisted on the agent record and
      independent of its name.
- [ ] 8.2 Define the agent colour palette as hue tokens, deriving bubble tint, accent, and foreground
      per theme via `color-mix(in oklab, …)`; verify legibility in light and dark.
- [ ] 8.3 Build the merged timeline read model over turns, output, and messages — replacing the
      timestamp-window attribution heuristic in `agent_chat.py:60-100`.
- [ ] 8.4 Render the four entry kinds: operator input, agent output, inbound peer tinted with the
      sender's colour, outbound peer accented with the recipient's colour. Always label with the name.
- [ ] 8.5 Render the undelivered state and its transition to delivered; render the
      hop-budget-suspended explanation.
- [ ] 8.6 Show waiting-entry counts and the reason when an agent is not running.
- [ ] 8.7 Type the timeline entries — conversational exchange, intermediate work, self-contained
      structured results — and render each in its own form rather than as a uniform bubble.
- [ ] 8.8 Make intermediate work collapsible and completed turns foldable to a summary.
- [ ] 8.9 Present structured results as content surfaces using the softer content radius, with a fade
      indicating clipped content.
- [ ] 8.10 Add the stop control to the running turn; render a stopped turn as deliberately stopped
      rather than as an error.
- [ ] 8.11 Verify against `agent-conversation-timeline`.
- [ ] 8.12 **`/handoff`**

## 9. Accounting and budgets

- [ ] 9.1 Parse runner token usage — Claude Code `result.usage` / `modelUsage` from stream-json,
      Codex `event_msg.payload.type == "token_count"` under `~/.codex`, OpenCode step telemetry —
      and record it per turn.
- [ ] 9.2 Aggregate usage per agent and per project; label currency as API-equivalent; prefer
      rate-limit allowance where the runner reports it; show unavailable rather than zero.
- [ ] 9.3 Implement the project token budget: exhausted budget pauses autonomous turns, operator
      turns still run.
- [ ] 9.4 Verify the accounting scenarios of `hub-native-runtime`.
- [ ] 9.5 **`/handoff`**

## 10. Multi-project support and navigation

*New phase. `Project` is already a table and all five tables carry `project_id`, but there is no
projects API and no UI. `hub-visual-language` depends on this.*

- [ ] 10.1 Add the projects API — list, create, open, and per-project settings including the hop,
      agent, and token budgets.
- [ ] 10.2 Give each project a working directory and record it.
- [ ] 10.3 Restructure navigation to list only projects and agents with live state; move per-project
      views (tasks, specs, jobs, activity, environment) into the content area as tabs.
- [ ] 10.4 Make a project's name navigate and its expander toggle its agents.
- [ ] 10.5 Make the containing project reachable from an agent conversation.
- [ ] 10.6 Apply agent identity colour consistently across navigation, conversation, task assignment,
      and activity.
- [ ] 10.7 Verify the navigation and identity-colour scenarios of `hub-visual-language`.
- [ ] 10.8 **`/handoff`**

## 11. Composer, first cut

- [ ] 11.1 Replace the chat input with an autosizing composer: bounded growth then scroll, submit vs.
      newline gestures, persisted per-conversation draft.
- [ ] 11.2 Implement trigger detection returning `{kind, query, rangeStart, rangeEnd}` for path,
      slash-command, and skill kinds, with line-start and token-start boundary rules.
- [ ] 11.3 Implement range replacement returning both new text and new cursor position; quote-escape
      references containing spaces.
- [ ] 11.4 Build the keyboard-navigable trigger menu: move, accept, dismiss; dismissal preserves text
      and focus.
- [ ] 11.5 Wire the three result sources — workspace paths, available skills, built-in commands.
- [ ] 11.6 Build the context-window meter: ring driven by dash-offset, animated over the deliberate
      duration, critical treatment above threshold, hover popover with exact figures, abbreviated
      token formatting, graceful degradation when capacity is unknown.
- [ ] 11.7 Feed the meter from context-usage events; render nothing rather than guessing when no
      event has been received.
- [ ] 11.8 Verify against `agent-composer`.
- [ ] 11.9 **`/handoff`**

## 12. Composer controls

- [ ] 12.1 Build the agent/runner selector: in-place switching, search, launchability indicators from
      the Phase 3 probe.
- [ ] 12.2 Add inline composer controls with responsive collapse into an overflow menu.
- [ ] 12.3 Add a banner stack above the composer for run errors, stream loss, and blocked states.
- [ ] 12.4 Verify the selector scenarios of `agent-composer`.
- [ ] 12.5 **`/handoff`**

## 13. Agent identity, charters, and skills

- [ ] 13.1 Introduce the runner record — CLI, model, environment — reusable across projects and
      independent of agent identity.
- [ ] 13.2 Reduce the agent record to identity: name, runner reference, working directory, colour,
      queue, session. Make `ix_agents_project_name` unique.
- [ ] 13.3 Add the charter — purpose, scope, default skills — with an empty charter meaning full
      project scope. **Design it as a portable artifact from the start** (see
      `explorations/2026-07-31-future-directions.md` §2 — retrofitting portability is expensive).
- [ ] 13.4 Enforce scope: work outside an agent's scope is reported, never performed silently.
- [ ] 13.5 Make skills invocable by any agent; invoking one changes neither identity nor scope.
- [ ] 13.6 Build the add-agent journey: choose a runner (with launchability), name it, optionally
      start from a template. **No persona step.**
- [ ] 13.7 Add agent templates and instantiation, with name-conflict resolution and no retroactive
      rewriting of existing agents.
- [ ] 13.8 Inject the live roster at turn start for projects with more than one agent.
- [ ] 13.9 Omit roster and all collaboration instruction entirely in single-agent projects; enable
      both on the addition of a second agent with no reconfiguration of the first.
- [ ] 13.10 Implement agent-requested agent creation with a per-project budget, automatic
      instantiation only from approved templates, operator decisions otherwise, attribution of every
      created agent to its request.
- [ ] 13.11 Implement behaviour resolution — project instructions → charter → skills → acceptance
      criteria — and make the effective composition for a turn inspectable.
- [ ] 13.12 Remove `roles.py`, `roles.json`, `VALID_ROLE_IDS`, and the 21 guides in
      `templates/roles/`; migrate anything worth keeping into `templates/skills/`.
- [ ] 13.13 Fix `cli.py:268` — `init` creates a single agent with no mode or role ceremony.
- [ ] 13.14 Verify against `agent-identity-and-skills`.
- [ ] 13.15 **`/handoff`**

## 14. Specification traceability and authoring

- [ ] 14.1 Add stable, visible requirement identifiers; report unidentified requirements; never
      reissue a retired identifier; keep identifiers stable across rewording, reordering, relocation.
- [ ] 14.2 Let a task declare the requirements it serves; persist the link past completion; report
      unserved requirements distinctly from unfinished ones.
- [ ] 14.3 Add evidence records carrying kind, origin, time, and the responsible agent/operator and
      run; refuse anonymous evidence.
- [ ] 14.4 Derive and display a verification state per requirement — not started, in progress,
      evidence awaiting review, verified — inline where the requirement is read. An agent's assertion
      is never verification.
- [ ] 14.5 Stale evidence when a requirement's meaning changes; distinguish stale from absent; retain
      superseded evidence; allow an operator to mark a change editorial.
- [ ] 14.6 Detect and report drift where linked implementation changes without its requirement;
      require deliberate resolution; change nothing automatically.
- [ ] 14.7 Make traceability navigable both ways.
- [ ] 14.8 Add project verification coverage, derived from the same per-requirement state.
- [ ] 14.9 Add the rigor declaration (sketch / contract / gate), defaulting to sketch; record
      promotion and demotion; preserve evidence on demotion.
- [ ] 14.10 Enforce the gate: refuse completion against a gate whose requirements lack accepted
      evidence, identifying which.
- [ ] 14.11 Make agent edits direct on sketches and proposals on contracts and gates; attribute
      accepted changes to both proposer and accepter.
- [ ] 14.12 Build authoring against a visible document: in-position proposals, individually
      acceptable, rejection leaving no residue.
- [ ] 14.13 Add the on-ramps — derive from implementation, grow from conversation, start from a
      template; mark derived specifications and start them as sketches.
- [ ] 14.14 Scope authoring assistance to specifications; discovered implementation work is proposed,
      not performed.
- [ ] 14.15 Make `aw-spec-explore`, `aw-spec-propose`, `aw-spec-apply`, `aw-spec-reindex`, and
      `aw-verify` reachable from the workspace; invert `aw-verify` to attach evidence to requirements.
- [ ] 14.16 Bring the specification workspace to the same standard as the agent conversation.
- [ ] 14.17 Keep specifications plain and portable; reconcile external edits without losing links or
      evidence.
- [ ] 14.18 Verify against `spec-traceability` and `spec-authoring`.
- [ ] 14.19 **`/handoff`**

## 15. Approval gates in the conversation

*Moved after specifications so gates cover both task lifecycle and specification gates, rather than
being built twice.*

- [ ] 15.1 Surface pending task-lifecycle and specification-gate decisions as an inline approval
      panel in the composer, actionable without leaving the conversation.
- [ ] 15.2 Connect approval actions to the existing task lifecycle transitions and to requirement
      evidence acceptance.
- [ ] 15.3 Verify the approval scenarios of `agent-composer` and `spec-traceability`.
- [ ] 15.4 **`/handoff`**

## 16. Closeout

- [ ] 16.1 Confirm every scenario in the ten delta specs is exercised.
- [ ] 16.2 Sync delta specs into `openspec/specs/`; reconcile `agent-stream-events`,
      `runtime-diagnostics`, and `agent-conversation-handoff` with their new behaviour.
- [ ] 16.3 Archive the change.
- [ ] 16.4 **`/handoff`**
