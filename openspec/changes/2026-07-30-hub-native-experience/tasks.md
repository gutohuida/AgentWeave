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
      Superseded 2026-08-04: the approved full mock uses distinct related rail/content planes with
      a subordinate boundary; see `2026-08-04-hub-ui-mock-alignment`.
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
- [x] 2.3 Remove all `refetchInterval` configuration; drive invalidation from events only. Removed all
      9 sites: `status`, `session-sync`, `logs` (the `opts.live ? 3000 : false` conditional), `jobs`,
      `agents` (including the running-agent 2s/10s adaptive poll — its comment explained it existed
      only as a fallback for a missed SSE event with no visible failure signal, which 2.4 now
      provides), `agents/:name/timeline`, `agent/:name/sessions`, and both `agent/:name/chat/*` hooks.
      `grep -rn refetchInterval hub/ui/src/` returns nothing. tsc clean, 194/194 tests passing.
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
      - **Real bug found by verification, not by the unit tests:** killing the live Hub process
        (`Stop-Process -Force`) left the indicator on "Live" forever. A killed process doesn't send
        FIN/RST for sockets it never explicitly closes, so `reader.read()` on the client neither
        rejects nor resolves `done: true` — it just hangs. A fresh `fetch()` to the same dead port
        failed immediately, proving the gap was specifically in the already-open stream never
        noticing. Fixed with a client-side idle watchdog: `events.py` already pings every 15s
        (`EventSourceResponse(ping=15)`) exactly so clients can detect this; added a timer that
        cancels the reader if no chunk (event *or* ping comment) arrives for 40s, which correctly
        flows into the existing reconnect path since the cancel doesn't set the `cancelled` flag.
        Verified twice end-to-end against the real dev server: killed the Hub process, watched the
        indicator appear at ~40s, restarted the Hub, watched it clear automatically. Test-only
        `__setIdleTimeoutForTest()` added so the regression test doesn't wait out the real 40s.
- [x] 2.5 Verify: task, message, agent-status and log views update live with polling removed; killing
      the stream shows the indicator and recovers on restore. Done as part of 2.4's verification pass
      above — real kill/restart of the live Hub process, not just the mocked unit tests.
- [x] 2.6 **`/handoff`** — `.claude/handoffs/2026-07-31-2314-hub-native-phase2-streaming-complete.md`

## 3. Native runtime, packaging, and crash recovery

*Crash recovery moved here from Phase 5b: the moment the Hub owns processes, orphans are possible.*

- [x] 3.1 Add a host-native start path for the Hub, keeping the Docker image building for
      coordination-only deployments. **The native path itself (`_hub_native_start`: PID
      tracking, health checks, migrations, scaffolding) already existed pre-branch (`a69f04e`),
      but only as an opt-in `--native` flag — Docker was the default this task's own wording
      contradicted.** Flipped: `agentweave hub start` now runs native by default; `--docker`
      (renamed from `--native`, sense inverted) opts into the container path for
      coordination-only/remote deployments; `--local` (Docker dev flow from `./hub/`) now implies
      `--docker` rather than being unreachable once native is default. Folded in 3.13 and 3.14
      (see below) since both are edits to this same code path. `tests/test_hub_commands.py`
      updated for the new flag semantics (996/996 CLI tests, 245/245 Hub tests pass). Live-verified:
      killed a stale dev-server Hub process, ran bare `agentweave hub start` (no flags) — native,
      bound `127.0.0.1`, `hub status`/`hub stop` correctly PID-tracked it; `--docker` still gates
      on Docker daemon availability. Docs/skill templates updated (README, docs/index.md,
      docs/getting-started/{quickstart,installation}.md, docs/reference/cli-commands.md,
      aw-setup.md, aw-setup-hub.md, config.py's generated-yml comment, pyproject.toml's mypy
      comment).
      - **3.13** (bind `127.0.0.1` not `0.0.0.0`; honour the port var) — the CLI's own native
        launcher (`_hub_native_start`) already correctly hardcoded `--host 127.0.0.1`, and `AW_PORT`
        was already honoured via `settings.aw_port`. The actual defect was the separate
        `agentweave-hub` console-script entry point (`hub/hub/main.py:run()`, `pyproject.toml`
        `[project.scripts]`), which hardcoded `host="0.0.0.0"` — reachable by running
        `agentweave-hub` directly (bypassing the CLI's scaffolding/migrations entirely), which is
        exactly the invocation the design doc's verification step used. Added `AW_HOST` setting
        (default `127.0.0.1`) and wired it into `run()`. Docker's `Dockerfile` CMD hardcodes
        `--host 0.0.0.0` independently of `run()` and is correctly unaffected — a container must
        bind all interfaces to be reachable through its port mapping. Documented `AW_HOST` in
        `docs/reference/env-variables.md` and `docs/getting-started/configuration.md`.
      - **3.14** (remove the Docker gate from `cmd_hub_start`) — done as part of the same flip:
        `_docker_available()` is now only consulted on the explicit `--docker`/`--local` path,
        never on the default.
- [x] 3.2 Add a launchability probe: for each configured agent, report whether its CLI is present,
      authorized, and runnable, with a stated reason when it is not. **The CLI side of this
      already existed** (`agentweave.diagnostics.check_agent_readiness`/`launch_blockers`,
      consumed only by the host watchdog before spawning) — but the Hub had nothing equivalent,
      and per Decision 1 the Hub now runs natively and can check PATH/env directly itself.
      Added `hub/hub/launchability.py` (`probe_agent`): a small, deliberately independent
      reimplementation (Hub has zero dependency on the `agentweave-ai` package, so it cannot
      import the CLI's diagnostics module) covering CLI presence (`shutil.which`, respecting a
      pinned absolute-path `cli:` override), `claude_proxy` API-key-env-var authorization, and
      `copilot` GitHub-token authorization, plus pilot/manual-runner blocking — each returning a
      stated `reason` when not runnable. Exposed as `GET /api/v1/agents/launchability`
      (`hub/hub/api/v1/agents.py`), merging the session-synced per-agent config with any
      self-registered `Agent.config` the same way the existing agent-list endpoint already does.
      Read-only, side-effect-free, no spawning. 12 new tests (`hub/tests/test_launchability.py`);
      257/257 Hub tests pass. Live-verified against the running Hub: synced `claude`
      (present/runnable — the real CLI is on this machine's PATH), a `kimi`-runner agent
      (present/runnable), and a `manual`-runner agent (correctly not runnable, stated reason) —
      then reverted the sync to leave the dev Hub's state as found.
      **Scope note:** "authorized" only reflects what the Hub process's own environment can see
      today (e.g. `os.environ`), not a project's `.env` file — the Hub does not yet load or even
      track a project's working directory (that lands in Phase 10's `Project.working_dir`, and
      matters more concretely once 3.4/3.5 actually spawn processes in that directory). Noted
      here rather than solved now — solving it requires the working-directory tracking that is
      explicitly out of this task's scope.
      UI wiring (the composer's launchability indicators) is Phase 12 (`12.1`), not this task.
- [x] 3.3 Introduce a run record — identity, agent, session identity as a typed field, start time,
      status, exit outcome, **process identity and heartbeat**. Added `Run` to
      `hub/hub/db/models.py` (`runs` table) with exactly those fields: `id`, `agent`,
      `session_id`, `started_at`/`ended_at`, `status` (`RUN_STATUSES`: running / completed /
      failed / interrupted / stopped — "stopped" for 3.7's deliberate-interrupt, "interrupted"
      for 3.8's crash reconciliation), `exit_code` + `error` (exit outcome), `pid` +
      `last_heartbeat_at` (process identity/heartbeat, the fields Decision 8's crash-reconciliation
      needs on Hub restart). `AgentOutput.run_id` already existed pointing at nothing — this table
      is what it was always meant to reference (left as a loose reference, no FK constraint, since
      3.5/3.6 haven't wired real run_ids through the output pipeline yet). Migration
      `0012_add_runs_table.py`, following the existing fresh-install-guard pattern. Bumped the two
      hardcoded `"0011"` version assertions in `test_migrations.py` to `"0012"`; added a migration
      test simulating an existing (pre-0012) deployment and a Run-model ORM round-trip test. 259/259
      Hub tests pass. Live-verified: migration applied cleanly to the real persistent Hub DB
      (`sqlite3` query confirmed `alembic_version=0012` and the `runs` table's columns).
      **Deliberately not done here** (belongs to 3.5/3.6): nothing creates, updates, or queries a
      `Run` row yet — `agent_trigger.py` is untouched, still on the message-tag protocol. This task
      is schema-only, matching its own scope ("introduce a run record"), not wiring.
      **Unrelated finding, not fixed (out of scope):** `agentweave hub start`'s detached-mode health
      check intermittently times out at 60s even though the server actually starts and serves
      traffic correctly within seconds (confirmed via `--no-detach`, which succeeds every time) —
      first observed once during 3.1's testing, before any of this session's other code changes, so
      it predates this work. Also surfaced a harmless, already-swallowed, pre-existing warning
      (`_run_alembic_upgrade`'s `alembic.ini` `script_location` resolves relative to CWD, not to the
      ini file, so the Hub's own redundant migration-on-boot silently no-ops when started from
      outside `hub/` — harmless because `_hub_native_start` already ran migrations correctly via an
      absolute path before spawning). Both worth a future look but are pre-existing Hub-lifecycle
      issues, not run-record issues.
- [x] 3.4 Implement process spawn and output capture with a PTY. **Prototype on Windows first**;
      account for `.cmd` shims (`cli.py:2341`). Added `hub/hub/pty_runner.py`
      (`resolve_executable`, `PtySession`): a thin adapter over `pywinpty` (Windows, wraps
      ConPTY) / `ptyprocess` (POSIX, wraps `pty.fork()`) — the two libraries expose a
      near-identical surface by the Windows library's own design, so one small adapter covers
      both, normalizing their different EOF signaling (`ptyprocess` raises `EOFError`;
      `pywinpty` returns `""`) to one shape. New Hub dependencies, platform-gated:
      `pywinpty>=2.0; sys_platform == 'win32'`, `ptyprocess>=0.7; sys_platform != 'win32'` —
      chosen over hand-rolled ConPTY ctypes after discussing the tradeoff (mature/maintained
      libraries vs. more from-scratch Windows API surface).
      **`.cmd` shims**: resolved by mirroring the watchdog's own existing fix
      (`watchdog.py`, "Resolve the CLI binary to an absolute path") — `shutil.which()` first
      (PATHEXT-aware), then hand the resolved absolute path to the PTY spawn call. Proven
      end-to-end against a synthetic `.cmd` shim (argument passing + exit code both correct);
      no `shell=True` needed anywhere, avoiding that injection surface entirely — this is the
      cleaner pattern `cli.py:2341`'s `shell=True` comment predates and should eventually be
      reconciled to (not done here — out of this task's scope, `cmd_mcp_setup` untouched).
      **Live-verified by hand on this repo's actual Windows dev environment** (this task's own
      instruction — "prototype on Windows first, since that is the primary development
      platform"): spawned real `python -c "print(...)"` and captured output including ConPTY's
      terminal-handshake escape sequences (`\x1b[1t\x1b[c...`) prefixing real output — expected
      ConPTY behavior, noted for whoever wires this into 3.6's SSE output rendering, not a bug;
      spawned a synthetic `fakecli.cmd` by bare name and confirmed output + argument + exit code
      (3) all correct; confirmed `FileNotFoundError` on a nonexistent binary before any spawn
      attempt; confirmed `terminate(force=True)` stops a 30s-sleeping process.
      10 new tests (`hub/tests/test_pty_runner.py`) — written to run meaningfully on whichever
      platform executes them (the `.cmd`-shim test is Windows-only via `skipif`; everything else
      is cross-platform using `sys.executable` so it exercises whichever backend is active).
      **CI will only ever exercise the POSIX/`ptyprocess` path** — `hub-test` in
      `.github/workflows/ci.yml` runs on `ubuntu-latest` only, not the 3-OS matrix the CLI's
      `test` job uses — so the Windows path's only verification is what was done by hand here;
      worth noting for anyone changing this module later without Windows access.
      269/269 Hub tests pass.
      **Deliberately not done here** (belongs to 3.5/3.6): nothing wires `PtySession` into
      `agent_trigger.py` or the `Run` record yet, and there's no output-streaming loop feeding
      SSE — this task is the spawn primitive only, proven working, not yet load-bearing.
- [x] 3.5 Rewrite `POST /api/v1/agent/trigger` to spawn directly and return a run identifier; delete
      the synthetic-message construction, the `[Session: …]` / `[NewSession]` body tags, and
      `execution_confidence` (`agent_trigger.py:133-161`). **Scoped per explicit user
      direction to full Claude Code + Codex CLI parity** ("I want a full integration of
      claude and codex... all the possible flags etc... no problems being a full
      re-implement of the watchdog"; kimi/opencode/copilot explicitly deferred — "ignore
      the others for now"). Context-window/token-usage tracking scope was resolved by
      checking what T3 itself does (per the user: "what does T3 do? ... if it gets the full
      tracking then we get that as well") — T3's own context meter is stdout-native only
      (design.md's Context-window-meter section: derived from the newest provider-emitted
      event, nothing else), so that's the bar met here; the CLI's *additional*
      rollout-file-cross-referencing collectors (`CodexRolloutCollector` etc.) are
      AgentWeave's own enhancement beyond T3 and were deliberately not ported (see below).

      **New modules**, all reimplemented rather than imported for the same reason as
      `launchability.py` (Hub has zero dependency on `agentweave-ai`):
      - `hub/hub/runner_commands.py` (`build_command`) — full flag construction for
        claude/claude_proxy/native and codex, mirroring `watchdog._agent_ping_cmd`'s
        branches for those runners exactly (model, `--resume`/`resume <id>`,
        `--append-system-prompt-file`/`-c model_instructions_file=`, codex's
        `--sandbox workspace-write` vs `--dangerously-bypass-approvals-and-sandbox`).
        **One deliberate divergence, not a reproduction**: `_agent_ping_cmd` never passes a
        permission-bypass flag for claude even when yolo is enabled (confirmed by reading
        the whole function — only codex/copilot/kimi apply yolo), despite
        `cli.py:4407`'s yolo-enable hint claiming `--dangerously-skip-permissions` "will be
        used" for claude. That gap is harmless for the watchdog (a human is usually nearby)
        but fatal for a headless Hub-spawned run (it would hang on a permission prompt with
        nobody to answer it) — fixed here since this is new code with no regression risk to
        existing watchdog users.
      - `hub/hub/runner_parsing.py` (`parse_claude_line`, `parse_codex_line`) — full JSONL
        event parsing mirroring `_parse_claude_stream_line`/`_parse_codex_stream_line`
        (text/thinking/tool_use/tool_result/error/status, exact payload shapes) plus their
        inline usage-sample extraction (`_claude_usage_sample`/`_codex_usage_sample`).
        **Claude's context-window limit is read directly from the CLI's own `result` event**
        (`modelUsage.<model>.contextWindow`) rather than porting the CLI's
        `CLAUDE_CONTEXT_LIMITS` substring table — that table is stale (no entry for Sonnet
        5, silently falls back to a wrong 200K default; live-verified Sonnet 5 actually
        reports 1,000,000). Self-reported beats hardcoded, and is the literal T3 principle
        cited above. Codex has no equivalent self-report, so `CODEX_MODEL_CONTEXT_LIMITS` is
        a small local fallback table (ported as-is, not verified further).
      - `hub/hub/runner_events.py` — event/payload construction + `redact_secrets`, mirroring
        `stream_events.py`'s constructors so output shape is identical to what a
        self-reporting agent already produces.
      - `hub/hub/output_recording.py` (`record_agent_output`, `record_context_usage`) — the
        DB-write + SSE-broadcast logic factored out of `agents.py`'s existing
        `POST .../output` and `POST .../context-usage` (both refactored to call it, behavior
        preserved, verified by the existing test suite staying green) so a Hub-spawned run's
        output flows through the exact same path a self-reporting agent's already does — one
        path, not two that can drift.
      - `hub/hub/launchability.py` gained `get_agent_config()` — factored out of (and now
        used by) both this endpoint and 3.2's launchability endpoint. Discovered a real,
        previously-unnoticed bug while writing this task's tests: `register-session` and
        `POST /agents/{name}/pilot` set pilot mode by writing `Agent.pilot` (a DB column)
        directly, never `Agent.config` or session.json — neither 3.2's launchability endpoint
        nor this endpoint's first draft ever read that column, so a self-registered pilot
        agent would never have been recognized as one. Fixed in the shared helper (both
        endpoints now correct).
      - `pty_runner.py` gained `strip_ansi_escapes()` — a real bug caught by live end-to-end
        testing (not the mocked unit tests): ConPTY prefixes real output with terminal-
        handshake control sequences (OSC title-set, CSI mode toggles) and can inject more
        (e.g. a cursor-restore sequence) at any later chunk boundary, not just the first. An
        unstripped leading sequence broke JSON parsing of the *entire first line* (silently
        degrading to a raw-text fallback event, including leaking session_id extraction), and
        an unstripped trailing sequence produced a spurious garbage output row after
        completion. Fixed by stripping CSI+OSC sequences from every line before parsing, not
        just leading ones on the first line.

      **`agent_trigger.py` rewrite**: pre-flight via `probe_agent()` (409 with its stated
      reason for pilot/manual/missing-CLI/unauthorized — manual gets its own precise 409
      rather than the generic "unimplemented runner" 501, since it's a permanent structural
      state, not a not-yet-built runner); runner-support check (501, listing what *is*
      supported, before the launchability check, so it's deterministic regardless of what
      happens to be installed on the Hub host — kimi/opencode/copilot/codex_mcp/manual all
      correctly 501 or 409 regardless of local CLI presence); a DB-based concurrency guard
      (reject a second trigger while a `Run` for that agent is still `status="running"` —
      simpler than the watchdog's file-lock, accepted as a known small race window rather
      than building equivalent locking, since this is human-driven UI triggering, not a
      hot path); spawns via `PtySession` in an `asyncio.create_task` background job (kept
      alive via a module-level set — a task with no other strong reference can be garbage-
      collected by asyncio mid-execution); records output/context-usage through
      `output_recording.py`; updates the `Run` row's `pid`/`session_id`/`status`/`exit_code`/
      `ended_at` throughout. Returns immediately with `run_id` + `status: "running"` — the
      run's eventual outcome is observable via the run record and `AgentOutput`/SSE, not
      blocking the response (matches "spawn directly, return an identifier").
      **Known limitation, not solved here**: the spawned process's working directory
      currently comes from the request's own `work_dir` field (validated, unchanged from the
      old endpoint) or the Hub's own CWD — the Hub still has no `Project.working_dir` (that's
      Phase 10), so multi-project correctness for this isn't solved, matching the same gap
      already noted in task 3.2.

      **Extensive live verification against the real installed CLIs on this machine**
      (Claude Code 2.1.220, codex-cli 0.146.0), per explicit user instruction to "spawn
      headless operations to test": real headless invocations (both direct and through a
      real `PtySession.spawn`) for new-session and `--resume`/`resume <id>` for both
      runners, confirming actual conversational continuity (asked codex/claude to recall a
      fact from a prior turn after resuming — both correctly did); confirmed
      `--dangerously-skip-permissions` alone is sufficient for claude (no companion
      `--allow-...` flag needed); confirmed codex's PTY-attached stdin does *not* trigger
      its "reading from stdin" prompt-append behavior the way a plain pipe does (codex
      detects the PTY as a real tty). **Then the full live loop end-to-end through the
      actual running Hub** (not just direct PtySession calls): triggered real claude and
      codex agents via `curl` against `POST /api/v1/agent/trigger` on the actual dev Hub
      instance, watched output arrive via `GET /agents/{name}/output`, confirmed `Run` rows
      reached `status="completed"`/`exit_code=0`/correct `session_id`, confirmed a real
      `context_warning` event was recorded for the codex run with real token counts. This is
      what caught the `strip_ansi_escapes` bug above — the mocked test suite's synthetic
      JSONL fixtures don't carry real ConPTY control sequences, so only a real spawn could
      have found it.

      44 new tests across `test_runner_parsing.py` (34, using JSONL fixtures trimmed from
      the real captured live output above), `test_agent_trigger.py` (6), and
      `test_pty_runner.py`'s new `TestStripAnsiEscapes` (5, retroactively covering the
      ANSI-stripping fix); `test_pilot_mode.py` and `test_runtime_diagnostics.py`'s
      obsolete `execution_confidence`/watchdog-heartbeat/message-queueing tests
      rewritten to assert the new direct-outcome behavior. 313/313 Hub tests pass.
      **Deliberately not done here** (belongs to 3.6): no new SSE event *types* for run
      lifecycle (`run_started`/`run_completed` equivalents) — output already broadcasts via
      the existing `agent_output` event (reused, not new), and a plain-text "Run
      completed/failed" status line is appended to the output stream as a stopgap, but
      there's no dedicated typed lifecycle event yet, and no frontend rendering work at all.
- [x] 3.6 Emit run lifecycle and output events on the SSE channel; render them in the agent view.
      Added three typed SSE events — `run_started`, `run_completed`, `run_failed` — broadcast
      from `agent_trigger.py`'s `_broadcast_run_lifecycle()` helper, which both persists to
      `EventLog` (so they show up in the existing timeline endpoint) and broadcasts over SSE
      (so they show up live), matching the existing `context_warning` persist+broadcast
      pattern rather than inventing a new one. `run_started` fires once the PTY spawn succeeds
      and a pid is recorded (not at trigger-accept time — `run_triggered`, already emitted by
      3.5, covers that); `run_failed` fires both on a spawn-time `FileNotFoundError` and on a
      nonzero exit code; `run_completed` fires only on exit code 0. **Kept alongside, not
      replacing,** the existing plain-text `agent_output`/`kind="status"` stopgap broadcast from
      3.5 — `AgentOutputPanel.tsx`'s Handoff-completion detection scans `lines` for
      `kind==="status" && payload.phase==="completed"`, and removing that broadcast would have
      silently broken it. The new typed events are additive.

      **A second, unplanned bug found and fixed in the same task, via the same "verify against
      the real running Hub" discipline flagged repeatedly in the 3.4/3.5 entries:** a
      Hub-triggered direct-spawn run never posted an `AgentHeartbeat` (that's the watchdog's
      mechanism, unused by this path), and `GET /api/v1/agents`'s `status` field was computed
      from heartbeats only (`effective_heartbeat_status`) — so a live direct-spawn run was
      invisible as "running" everywhere the UI reads `agent.status`: the AgentCard badge, the
      Overview page, and `AgentOutputPanel.tsx`'s `isRunning` gate (which locks the message box
      and shows the pulsing badge). Confirmed live: triggered a run, polled `GET
      /api/v1/agents` mid-run, saw `"status":"idle"` the whole time even while output was
      streaming. Fixed by bulk-fetching agents with an active (`status="running"`) `Run` row in
      `list_agents()` and overriding `effective_status` to `"running"` for them — Run-table
      state now takes precedence over heartbeat state, since it's strictly more current for a
      direct-spawn agent. Live-verified after the fix: `GET /api/v1/agents` correctly reported
      `"running"` mid-run and `"idle"` immediately after completion. This wasn't in 3.6's
      one-line task text, but without it "render [lifecycle events] in the agent view" would
      have had no visible effect on the one piece of UI (the status badge) users actually look
      at to answer "is this agent busy right now" — the gap was found by literally trying to
      answer that question against the real Hub, not derived from the task description.

      Frontend: `useSSE.ts`'s `SSE_EVENT_TYPES` allowlist extended with the three new event
      names (the exact "broadcast but not allowlisted → silently dropped" bug class flagged in
      the Phase-2 handoffs — checked explicitly this time) plus an `invalidateQueries(['agents'])`
      case so the status-badge fix above actually reaches the UI live, not just on next poll.
      `agents.ts`'s `eventBelongsToTimeline()` extended so the Activity tab's timeline query also
      invalidates live on these events (it previously only invalidated on `log_event`, which is
      only broadcast by the CLI→Hub log-bridge endpoint, never by `agent_trigger.py`'s direct
      `persist_event` calls — meaning `run_triggered`/`run_completed` from 3.5 already had this
      same live-update gap, silently, since 3.5 landed; fixed as a side effect of fixing it for
      the three new event types). `AgentActivityTab.tsx`'s event-timeline branch (previously a
      single fixed blue treatment for every `EventLog`-sourced entry) now colors `run_failed`
      red, `run_completed` green, `run_started` blue, with matching icons
      (`error`/`check_circle`/`play_arrow` — confirmed each name resolves in the lucide-react
      `Icon` map before using it; `play_circle` does not exist there and would have silently
      rendered nothing). Backend's `agent_timeline()` endpoint given a small
      `_run_lifecycle_summary()` helper so these three event types render as "Run started
      (claude)" / "Run completed (exit 0)" / "Run failed: <error>" instead of the bare enum
      string every other `EventLog`-derived timeline entry falls back to.

      4 new backend tests (`test_agent_trigger.py`: successful-run lifecycle broadcast
      assertions via `sse_manager.subscribe()` + queue draining, matching
      `test_context_usage.py`'s existing pattern; nonzero-exit → `run_failed` not
      `run_completed`; spawn-failure → `run_failed`) plus 1 new `test_agents.py` test
      (Run-active agent reports `"running"` with zero heartbeat rows). 1 new frontend test
      (`useSSE.test.tsx`, mirroring its existing `job_created`/etc. allowlist test). 317/317
      Hub tests pass (was 313), 196/196 frontend tests pass (was 195). `ruff check hub/`,
      `black --check hub/` (after one reformat), `tsc --noEmit` all clean.

      **Live-verified end-to-end against the real running dev Hub** (restarted to pick up the
      backend changes first): triggered a real Claude run via `curl`, captured the live SSE
      stream with a backgrounded `curl -sN`, confirmed `run_started` (with `runner`/`model`
      fields) then `run_completed` (with `exit_code`/`session_id`) arrived in order, confirmed
      `GET /api/v1/agents` showed `"running"` mid-run and `"idle"` after, confirmed
      `GET /api/v1/agents/claude/timeline` returned readable summaries. Then opened the actual
      Vite dev server in a real browser, navigated to the claude agent's "Messages" tab (the
      button is labelled "Messages" but renders `AgentActivityTab` — pre-existing, not
      renamed here, out of scope) via DOM-level clicks, and read the rendered rows directly:
      confirmed `run_started`/`run_completed` entries render with the correct
      blue/green `border-left` color and correct summary text, sourced live off the real running
      Hub, not a mock.

      **Deliberately not done here** (out of scope for this task's own text): no dedicated
      lifecycle-specific UI surface beyond the existing Activity-tab timeline (e.g. no toast, no
      run-duration timer, no distinct "run card" in the Output tab) — the task said "render them
      in the agent view," and the timeline plus the now-correct running/idle badge satisfy that;
      a richer run-lifecycle UI is 3.7+ territory (interrupt/stop needs *some* visible
      "this is the run you'd be stopping" affordance, which doesn't exist yet). No work on 3.7's
      interrupt/stop, 3.8's crash reconciliation, or 3.9's process-group cleanup.
- [x] 3.7 Implement interrupt and stop for an owned run. Added `POST /api/v1/agent/{agent}/stop`
      to `agent_trigger.py`: looks up the agent's in-progress `Run` row, force-terminates its
      tracked `PtySession` (`_active_ptys`, a new module dict populated/cleared around
      `_execute_run`'s own read/wait loop — the only place the PtySession instance exists), and
      returns immediately with `status: "stopping"` rather than blocking until the process is
      confirmed dead (that confirmation happens asynchronously, same as every other run-ending
      path). A new `_stop_requested` set of run_ids lets `_execute_run`'s own completion handling
      (unchanged in shape from 3.6, just now branching three ways instead of two) tell a
      deliberate stop apart from a crash/nonzero-exit: a forced kill rarely exits 0, so without
      this a stop would misreport as `run_failed`. Final status `"stopped"`, broadcast event
      `run_stopped` — both already reserved by 3.3's `RUN_STATUSES`/anticipated by 3.6's own
      wording, not newly invented here. Frontend: a red "Stop" button in
      `AgentOutputPanel.tsx`'s header (visible only while `isRunning`, with a local `isStopping`
      lock against double-submits, cleared once `agent.status` leaves `"running"`) posts to the
      new endpoint. `useSSE.ts`, `agents.ts`'s `eventBelongsToTimeline()`, and
      `AgentActivityTab.tsx`'s event-row coloring all extended for `run_stopped` the same way
      3.6 wired the first three lifecycle events (amber border/badge/icon, distinct from
      red-failed and green-completed — new `stop` icon added to `Icon.tsx`'s map, mapped to
      lucide's `Square`). `agents.py`'s `_run_lifecycle_summary()` renders "Run stopped (exit
      N)". 8 new tests (2 backend in `test_agent_trigger.py` — a real force-terminate via a
      blocking-read fake PTY released only by `.terminate()`, and a 404 when no run is in
      progress; extended the existing `useSSE.test.tsx` lifecycle-events test rather than adding
      a new one). 319/319 Hub tests pass (was 317+the 2 new; +2), 196/196 UI tests pass (count
      unchanged — extended not added). Live-verified twice: once via curl (triggered a
      long-running Claude prompt, called `/stop` mid-run, confirmed the OS process actually
      exited via `tasklist`, `Run.status` became `"stopped"` with a nonzero `exit_code`, the
      `run_stopped` SSE event arrived in order, `GET /api/v1/agents` flipped back to `"idle"`,
      and the timeline showed the human-readable summary), and again through the real browser
      (localhost:5175) driving the actual Stop button via `preview_evaluate`'s
      `document.querySelector(...).click()` workaround (same MCP schema-validation issue on
      `preview_click`/`preview_navigate` noted in 3.6's handoff, still present this session) —
      confirmed the button appears only while running, disappears once stopped, and the
      Activity tab's two `run_stopped` rows both render with the amber border/badge/`stop` icon
      and "Run stopped (exit 2)" summary text.
      **Deliberately not done here** (belongs to 3.8/3.9, per 3.6's own scoping note): no crash
      reconciliation (a run whose process dies without a stop request or clean exit — e.g. the
      Hub itself restarting mid-run — is still 3.8's `"interrupted"` status, not touched by this
      task), no process-group termination on Hub shutdown (3.9). No run-duration timer, toast, or
      dedicated "run card" UI beyond the existing Activity timeline and the status chip/Stop
      button pairing — matches the task's own text ("implement interrupt and stop"), not a
      broader run-lifecycle UI redesign.
      **Unrelated, pre-existing, not fixed:** `npm run lint` (hub/ui) fails outright —
      `eslint.config.js` doesn't exist anywhere in the repo (ESLint v9 requires flat config; no
      legacy `.eslintrc.*` exists either). Not something this session's changes touched or
      broke; `tsc --noEmit` and `vitest run` remain the meaningful gates per every prior task's
      verification in this chain. Worth a future look, not blocking.
- [x] 3.8 Reconcile on Hub start: a run whose process is absent becomes `interrupted`. New
      `hub/hub/run_reconciliation.py`, `reconcile_interrupted_runs()`, called from
      `main.py`'s `lifespan()` right after `init_db()` (before the scheduler starts, before
      the app accepts requests). Queries every `Run` row still `status == "running"`
      Hub-wide (not project-scoped — a restart can affect any project) and, for each,
      checks OS-level process liveness by the persisted `pid`; anything not alive (or
      `pid IS NULL`, e.g. a crash between Run-row creation and pid assignment) becomes
      `status="interrupted"`, `ended_at` stamped, a `run_interrupted` event persisted and
      broadcast — same persist+broadcast shape 3.6/3.7 already used, not reused via
      `agent_trigger.py`'s `_broadcast_run_lifecycle` helper since that's a request-handler
      concern and this runs at startup with no request in flight. A restarted Hub process
      has **no in-memory `PtySession`** for any run that was mid-flight when it died — only
      the bare `pid` int the row already carried — so `PtySession.isalive()` (which only
      works for a live in-process handle) can't be reused; added a new `pid_alive(pid)` to
      `pty_runner.py` instead, branching on `IS_WINDOWS` the same way the rest of that file
      does (POSIX: `os.kill(pid, 0)`; Windows: `OpenProcess`/`GetExitCodeProcess` via
      `ctypes`, no new dependency). Documented, not solved, limitation in `pid_alive`'s own
      docstring: this is existence-only, not identity — a sufficiently long Hub outage could
      see the OS recycle a dead run's pid onto an unrelated process before the Hub restarts,
      producing a false "still alive"; closing that fully would need the `Run` row to carry
      process start-time or command line, which it doesn't. `RUN_STATUSES`'s `"interrupted"`
      value (reserved since 3.3) is used by real code for the first time here.
      `list_agents()`'s existing `agents_with_active_run` query (3.6) needed no change —
      it already only matches `status == "running"`, so a reconciled row is automatically
      excluded, and `POST /agent/trigger`'s "already has a run in progress" guard (same
      query shape) is unblocked for that agent the moment reconciliation runs. Frontend:
      `run_interrupted` wired through `useSSE.ts` (allowlist + `['agents']` invalidation,
      grouped with the other four lifecycle events), `agents.ts`'s
      `eventBelongsToTimeline()`, and `AgentActivityTab.tsx`'s event-row coloring — purple
      (`var(--purple)`, previously only used for the session-ID chip, not any run-lifecycle
      event) with the existing `warning` icon (`AlertTriangle`), distinct from
      red/failed, green/completed, amber/stopped, blue/started. `agents.py`'s
      `_run_lifecycle_summary()` renders `"Run interrupted (Hub restarted)"`. 6 new backend
      tests: `test_run_reconciliation.py` (no-pid → interrupted with SSE assertion,
      implausible-large-pid → interrupted, live pid (the test process's own) → left
      running, and a reconcile-twice idempotency check — the last one deliberately does
      *not* assert `reconciled == 0` on a fresh call, since the shared in-memory test DB
      persists "running" rows other test modules deliberately leave behind across the whole
      pytest session; asserts idempotency instead, which holds regardless of what ran
      earlier) and `test_pty_runner.py::TestPidAlive` (current process alive; a real
      spawned-and-reaped subprocess not alive — exercises `pid_alive`'s actual OS-level
      behavior, which the reconciliation tests deliberately don't re-test). 325/325 Hub
      tests pass (was 319; +6), ruff/black clean (two lowercase-local-variable renames
      needed for `N806` in the Windows branch), `tsc --noEmit` clean, 196/196 UI tests pass
      (one extended, not added, mirroring the run_stopped precedent). Live-verified against
      the real dev Hub: inserted a `Run` row directly into the persistent dev DB with
      `status="running"` and an implausible pid, restarted the Hub process, confirmed via
      direct DB query the row flipped to `"interrupted"`, confirmed
      `GET /agents/claude/timeline` returned `"Run interrupted (Hub restarted)"`, confirmed
      `GET /agents` showed `"idle"` (not stuck), and confirmed in the actual browser
      (against the now-rebuilt static UI bundle, see below) that the Activity tab renders
      the row with the purple border/badge and correct summary text. The Hub restart for
      this verification was done only after asking the user first, since the user was
      actively using this exact dev Hub instance at the time.
      **Unplanned, adjacent fix in the same session, before this task started:** the Hub's
      checked-in `hub/hub/static/ui/` bundle (served at :8000 for non-Docker/local use,
      per `main.py`'s `UI_DIST` static mount) was stale since before task 3.5 — the user
      reported a stuck "active" badge after a response and no Stop button, both explained by
      that bundle predating all of 3.5-3.7's frontend work (confirmed by grepping the
      bundle's JS for `run_started`/`run_stopped` — neither string was present). Rebuilt via
      `npm run build` + manual copy into `hub/hub/static/ui/`, twice this session (once for
      the report, once more after this task's own frontend changes so the bundle doesn't
      immediately go stale again). This is the general problem already tracked as unchecked
      task 3.20 ("Stop the Hub silently serving a stale UI") — still not systemically fixed,
      only manually refreshed. **Deliberately not done here** (belongs to 3.9/6.5): no
      process-group termination on Hub shutdown (3.9 — this task only handles the Hub *not
      being there* when a run's process is still around; 3.9 handles the reverse, the
      process still being around when the Hub goes away cleanly). No "entries returned to
      the queue" behavior from Decision 8's second half — Phase 6's inbound-queue system
      (the thing that would hold such entries) doesn't exist in this codebase yet; that half
      is explicitly deferred to task 6.5, which already says "pairs with 3.8" in its own
      text.
- [x] 3.9 Terminate the process group on Hub shutdown so no agent process is orphaned. New
      `terminate_process_tree(pid, force=True)` in `pty_runner.py`: unlike
      `PtySession.terminate()` (which — checked by reading pywinpty's own source this
      session — only signals the *direct* child it wraps, no process-group/tree awareness
      at all), this reaches grandchildren the agent CLI itself spawned (e.g. a Bash-tool
      subprocess), which is what "no agent process is orphaned" actually requires. POSIX:
      `os.killpg(os.getpgid(pid), SIGKILL)` — a PTY child from `ptyprocess.PtyProcessUnicode
      .spawn()` is a session leader (`pty.fork()` calls `setsid()`), so its pgid equals its
      own pid, and `killpg` reaches the whole group. Windows has no process-group
      equivalent; used `taskkill /F /T /PID` instead (walks the OS-recorded parent-child
      tree) — the standard Windows idiom for this, not something pywinpty exposes. New
      `terminate_all_active_runs()` in `agent_trigger.py`: walks `_active_ptys` (from 3.7)
      and calls `terminate_process_tree` on each tracked run's pid; called from `main.py`'s
      `lifespan()` teardown, before `shutdown_scheduler()`. Deliberately does **not** touch
      any `Run` row's DB status — a shutdown-then-restart is picked up by 3.8's
      `reconcile_interrupted_runs()` on the *next* boot, which is the single place that
      owns transitioning persisted run status; duplicating that here would risk the two
      disagreeing about *when* a run's status actually changes (documented in both
      functions' docstrings). 6 new tests across three files:
      `test_pty_runner.py::TestTerminateProcessTree` (kills a real spawned long-running
      subprocess; already-dead pid doesn't raise), `test_agent_trigger.py` (walks
      `_active_ptys` and calls the patched `terminate_process_tree` with the right pid,
      releasing a blocking-read fake PTY exactly like the process actually exiting would;
      zero-active-runs returns 0), and a new `test_lifespan_shutdown.py` — the one test in
      this whole suite that exercises the **real** ASGI lifespan via Starlette's
      `TestClient` (which, unlike `conftest.py`'s `httpx.ASGITransport`-based `app` fixture,
      actually runs `lifespan()` on `__enter__`/`__exit__`) against a real spawned OS
      subprocess: populates `_active_ptys` directly with a genuine long-running process,
      enters and exits a `TestClient` context, confirms the process is actually dead
      afterward. Chosen deliberately as the live-verification method for this task instead
      of restarting the user's live dev Hub (as 3.7/3.8 did) — it exercises the exact same
      `main.py` wiring end-to-end, is repeatable and automated rather than one-off manual
      confirmation, and doesn't require disrupting an instance the user was actively using.
      330/330 Hub tests pass (was 325 after the static-UI-bundle fix and before this task
      started, then 329 with this task's first 4 tests, 330 with the lifespan test added
      last); ruff/black clean on the first pass this time. No frontend changes this task, so
      no `tsc`/`vitest`/static-bundle-rebuild needed.
      **Deliberately not done here:** no change to 3.7's `PtySession.terminate(force=True)`
      call in the stop endpoint — the task's own wording scopes tree-kill to Hub *shutdown*
      specifically (design.md Decision 8: "On shutdown the Hub terminates the process
      *group*"), distinct from a deliberate mid-session stop, which stays a single-process
      terminate as 3.7 shipped it. Revisit only if a stopped run is later found to leave
      orphaned grandchildren in practice — not something this session had evidence of.
- [x] 3.10 Route scheduled jobs through the direct execution path; remove the watchdog's
      message-scanning trigger branch, keeping only timer duties. First task in this
      session's Phase 3 chain to touch both sides of the CLI/Hub split.
      **Hub side:** `agent_trigger.py`'s `trigger_agent()` route handler had its entire body
      extracted into a new `trigger_agent_directly()` function (raises a new
      `TriggerAgentError` instead of `HTTPException`, so it has no FastAPI-request coupling)
      — the route is now a 10-line wrapper that calls it and converts the exception back.
      `scheduler.py`'s `_do_fire_job()` (the function every job fire — scheduled *and*
      manual "run now" — goes through) rewritten to call `trigger_agent_directly()` instead
      of writing a synthetic `Message` row for the watchdog to later scan and re-trigger
      from (the exact `[Session:]`/`[NewSession]` text-tag indirection proposal.md's
      finding #3 already fixed for manual triggers in task 3.5 — this closes the same gap
      for scheduled jobs). New `_job_agent_skip_reason()` helper ports two guards the
      removed watchdog function used to enforce (pilot mode; self-registered poll-mode
      agents) by querying the Hub's own `Agent` table directly, rather than the CLI's
      session.json — deliberately **not** added to `trigger_agent_directly()` itself, since
      that also backs the manual-trigger endpoint, which has never enforced either guard;
      adding them there would silently change manual-trigger behavior too, which nothing
      asked for. `JobRun.status` gained a third value, `"skipped"` (previously only
      `"fired"`/`"failed"` per the model's own comment) — a job skipped for pilot/poll
      reasons is not a failure, and conflating the two would misreport why nothing ran.
      **Found and fixed in the same task, not separately requested:** `jobs.py`'s
      `POST /{job_id}/run` endpoint treated any non-`True` return from `_do_fire_job` as a
      generic 500 "Failed to fire job" and additionally persisted its own duplicate
      `job_run_failed` event on top of the one `_do_fire_job` already persists internally —
      a pre-existing wart that would have made a manually-triggered "run now" on a
      pilot-mode agent surface as a confusing server error instead of the correct 409
      "skipped" outcome once `"skipped"` became a real return value. Fixed by reading back
      the just-written `JobRun` row's actual `status` instead of branching on the bare
      boolean, and removing the endpoint's now-redundant duplicate persist call.
      **Watchdog side:** removed the `if sender == "user" and ...:
      self._trigger_agent_from_message(recipient, msg)` auto-trigger block from
      `_check_once_http()`, and deleted `_trigger_agent_from_message()` itself (147 lines,
      `src/agentweave/watchdog.py`) — confirmed via grep it had exactly one call site before
      removal. `_check_jobs()`/`_fire_job()`/`_run_agent_subprocess()` (the local/git-
      transport "timer duties" the task's own wording says to keep) are untouched — they
      never routed through the removed function, confirmed by reading `_check_once_local`
      before touching anything (`_check_jobs` is gated on
      `transport_type in ("local", "git")` only). Two CLI-side tests
      (`tests/test_watchdog_pilot.py`, all 3 tests; 2 of 3 tests in
      `tests/test_watchdog_self_registered.py`) exercised the removed method directly and
      were deleted; the third test in the self-registered file (`_fire_job`'s own, separate
      self-registered-poll guard for local/git timer duties) is untouched and still passes,
      confirming that code path's independence from what was removed.
      **New tests:** `hub/tests/test_scheduler.py` (new file, 5 tests) — a fired job creates
      a `Run` row via direct execution and **zero** `Message` rows (the core architectural
      claim of this task, asserted directly against the DB); pilot-mode and self-registered-
      poll agents are skipped, not fired, with the real reason recorded; a job that hits a
      real `TriggerAgentError` (a same-agent run already in progress, chosen because it's
      deterministic with no CLI-availability mocking needed) records `"failed"` with the
      actual rejection detail, not an assumed success; `POST /jobs/{id}/run` returns 409 with
      the real reason for a skipped pilot-mode agent, not a generic 500. 335/335 Hub tests
      pass (was 330; +5), 991/991 CLI-side tests pass, 4 skipped (5 tests removed this task —
      3 in the deleted `test_watchdog_pilot.py`, 2 of 3 in `test_watchdog_self_registered.py`
      — not replaced 1:1 since the Hub-side equivalents in `test_scheduler.py` cover the same
      guards more directly, against real DB state instead of mocked watchdog internals).
      ruff/black clean on both `hub/` and `src/agentweave/`.
      `tsc --noEmit` clean; 196/196 UI tests pass (small `JobCard.tsx` polish for the new
      `"skipped"` status — amber `pause` icon/text, distinct from red/failed and
      gray/pending — no dedicated JobCard test existed before or after).
      **Live verification for this task relied on the automated test suite above, not a
      dev-Hub restart** (departing from 3.7/3.8's pattern) — `test_scheduler.py`'s tests call
      `JobScheduler._fire_job_internal` directly, the exact method both the real APScheduler
      cron callback (`_scheduled_job_runner` → `_fire_job_by_id` → `_fire_job_internal`,
      untouched by this task) and the manual "run now" HTTP endpoint actually invoke, using
      the same mocked-`PtySession.spawn` pattern already live-verified for the manual
      trigger endpoint in task 3.5's own live verification. Judged sufficient without a
      restart given how directly the tests exercise the real call graph; the user was not
      asked this time since no live instance needed to be touched.
      **Deliberately not done here:** no live-SSE push for a job that ends up `"skipped"` or
      synchronously `"failed"` via `TriggerAgentError` — only the success path broadcasts
      `job_fired` over SSE (`job_run_failed`/`job_run_skipped` are persisted to `EventLog`
      only). This is not a regression: the pre-existing exception-handling branch never
      broadcast anything either, for the same reason (no code path did before this task).
      Worth fixing in a future pass on job observability, not required by this task's own
      wording. No changes to `AIJob`/`JobRun`'s schema (no new columns, no migration) —
      `JobRun` still has no FK link to the `Run` table (task 3.3) a fired job actually
      creates, so cross-referencing a job's fire history with its run's live output/exit
      code still requires two separate lookups by agent+time rather than a direct join;
      out of scope for "route through direct execution," which this task's own wording is
      about the *trigger mechanism*, not job/run observability parity.
- [x] 3.11 Remove `agentweave switch` and `agentweave agent set-session` from the Hub-managed path;
      resolve provider environment and session continuity inside the Hub.
      **Hub side (the concrete architectural fix):** new `resolve_agent_env(runner, config)`
      in `hub/hub/launchability.py`, mirroring `agentweave.watchdog._prepare_agent_env`/
      `_prepare_runner_env`'s exact semantics (`ANTHROPIC_API_KEY_VAR` indirection, generic
      self-referencing placeholder resolution, native-Claude proxy-URL-leak stripping) —
      deliberately reimplemented rather than imported from the CLI package, matching this
      module's own stated principle (the Hub must stay probeable/runnable without the
      `agentweave-ai` package installed at all, e.g. a Docker-only deployment). Wired into
      `trigger_agent_directly()`: computes `env = resolve_agent_env(runner, config)` and
      threads it through `_execute_run()` (new `env` parameter) into
      `PtySession.spawn(cmd, cwd=work_dir, env=env)` — previously **no env override was ever
      passed to spawn at all**, so a Hub-triggered `claude_proxy` agent (Minimax, GLM) only
      ever worked if the operator had *already* exported the right key into the Hub
      process's own shell before starting it — i.e. exactly the `eval $(agentweave switch
      ...)` ceremony this task exists to remove, just aimed at the Hub's shell instead of a
      normal one. **Session continuity was already solved** by tasks 3.5–3.7's existing
      work — the agent detail panel's conversation picker (`GET /agent/sessions/{agent}`,
      `AgentOutputPanel.tsx`'s session dropdown) already lets the operator choose which
      session to resume; no gap found there, nothing changed.
      **CLI side:** `cmd_switch` and `cmd_agent_set_session` (`src/agentweave/cli.py`) now
      check `get_transport().get_transport_type() == "http"` first and, if so, print a
      short note steering the operator to the Hub UI instead of performing their old
      behavior (eval-able exports; writing a local session-id file) — a deliberate `return
      0`, not a hard failure, since running the command isn't wrong, just superseded.
      Scoped to exactly the two commands the task names; `cmd_run` (a related but
      unnamed command, still useful for local/git-transport claude_proxy runs) was
      deliberately left untouched. Local/git-transport behavior for both commands is
      unchanged — verified by a same-shaped test with no `transport.json` present
      confirming the old eval/write behavior still fires.
      **Found and fixed in the same task, not separately requested:** `agent_trigger.py`'s
      501 response for an unsupported runner (Kimi/OpenCode/Copilot) still said "This agent
      can still be triggered via the watchdog's own message-based path" — a claim task
      3.10 made false by removing that exact path. Confirmed via re-reading 3.10's own
      change that even *before* 3.10, this fallback only ever applied to job-triggered runs
      (a manual `POST /agent/trigger` for these runners has 501'd since task 3.5, since
      that endpoint never created a message for any runner); 3.10 additionally routed job
      firing through the same 501-raising function, so as of 3.10 these three runners have
      **no Hub-triggered execution path at all over HTTP transport** — local/git transport
      is unaffected (the watchdog's own `_check_jobs`/`_fire_job` "timer duties" still spawn
      them directly). Corrected both the module docstring and the 501 detail message to
      state this accurately instead of pointing at a path that no longer exists. Not
      otherwise fixed — extending `SUPPORTED_RUNNERS` to cover every runner is explicitly
      future work per the module's own docstring, predating this session.
      **Also discovered, not a bug, just documented for the record:** `launchability.py`'s
      `probe_agent()` *already* factored pilot mode into its `runnable` computation before
      this session started (`"runnable": present and authorized and not pilot`) — meaning
      the 3.10 handoff's claim that "the manual-trigger endpoint has never enforced pilot
      mode" was incomplete: `trigger_agent_directly()` doesn't mention "pilot" as a literal
      string, but it calls `probe_agent()`, which does check it. 3.10's `_job_agent_skip_reason`
      addition wasn't a redundant no-op because of this, though — it still meaningfully
      changes a pilot-skipped job's `JobRun.status` to `"skipped"` (not `"failed"`) and
      avoids wasted `build_command`/launchability work; and its self-registered-poll-agent
      half remains the only guard for that case, since `probe_agent()` never checked it.
      Noted here rather than amending 3.10's already-committed handoff.
      7 new tests: `test_launchability.py::TestResolveAgentEnv` (6 cases covering the env
      resolution matrix — no env_vars, named-var resolution, missing-var clears the
      inherited key without raising, self-referencing placeholder, native-Claude
      base-url stripping, non-claude runner keeps an intentionally-set base url),
      `test_agent_trigger.py::test_trigger_resolves_claude_proxy_env_at_spawn_time`
      (asserts the real spawn call's `env=` kwarg end-to-end through
      `trigger_agent_directly`/`_execute_run`), and `test_cli.py`'s new
      `TestSwitchAndSetSessionRemovedFromHubManagedPath` (4 cases: both commands steer to
      the Hub UI under http transport, both still work unchanged with no transport.json).
      342/342 Hub tests pass (was 335; +7), 995/995 CLI-side tests pass (was 991; +4).
      ruff/black clean on both sides. No frontend changes this task, so no
      `tsc`/`vitest`/static-bundle-rebuild needed.
      **Not live-verified against the running dev Hub this session** — that instance has
      been up since before task 3.9 and would need a restart to pick up 3.9/3.10/3.11's
      combined changes; deferred rather than restarting the user's active session
      unprompted again this session (see 3.8/3.9's own notes on asking first). The
      automated integration test above exercises the exact same `trigger_agent_directly`
      → `_execute_run` → `PtySession.spawn` call graph a live trigger would.
- [x] 3.12 Ship `alembic.ini` in `package-data` — a pip install currently logs
      *"alembic.ini not found … skipping migrations"* and runs unmigrated. Moved
      `alembic.ini` from the repo/distribution root (`hub/alembic.ini`, outside the
      packaged `hub` module entirely) into the package itself (`hub/hub/alembic.ini`),
      added it to `[tool.setuptools.package-data]`, and set `script_location =
      %(here)s/migrations` (Alembic's config-relative token, not a CWD-relative path —
      the old `script_location = hub/migrations` only ever worked because every
      invocation happened to be run from a specific CWD, which a bare `pip install
      agentweave-hub && agentweave-hub` from an arbitrary directory would not
      guarantee). Updated `hub/hub/db/engine.py`'s `_run_alembic_upgrade()` path
      calculation (`Path(__file__).parent.parent`, one level up from three), the
      Dockerfile/Dockerfile.dev (dropped the now-redundant separate `COPY alembic.ini
      ./` — it ships automatically via `COPY hub/ ./hub/` — and pointed their `CMD`s at
      `-c hub/alembic.ini`), the Makefile's `dev` target, and
      `hub/tests/test_migrations.py`'s `ALEMBIC_INI` constant.

      **Found and fixed a second, previously-undiscovered bug that directly blocked
      this task's own goal:** `migrations/versions/0001_add_agent_outputs.py` was the
      only migration (0002 onward all already guard this) that ran an unconditional
      `op.create_table("agent_outputs", ...)` with no existence check. Any database
      whose tables were created via `Base.metadata.create_all()` before alembic ever
      ran against it (true of literally every real deployment, dev or production, per
      `init_db()`'s own `create_all()`-then-`_run_alembic_upgrade()` sequence) hits
      `table agent_outputs already exists` on migration 0001, and
      `_run_alembic_upgrade()`'s try/except silently swallows that failure — meaning
      `alembic_version` never gets stamped, and *every* migration, including all future
      ones, silently never applies. Confirmed this was live and current: the actual
      local dev Hub's own `data/agentweave.db` had an empty `alembic_version` table
      despite the DB otherwise having the fully-current schema (via `create_all()`
      alone). Fixed by adding the same `inspector.get_table_names()` guard every
      migration from 0004 onward already uses.

      **Verified end-to-end**, not just via the existing test suite: built a real wheel
      (`py -m build --wheel`), confirmed `hub/alembic.ini` and the full
      `migrations/versions/*.py` tree are present inside it, installed it into a
      throwaway venv, and ran `init_db()` against a brand-new SQLite file from a
      directory containing no source checkout at all — `alembic_version` landed at
      `0013` (current head), with no "alembic.ini not found" warning. Also confirmed
      the CLI-style invocation matching Docker/Makefile (`alembic -c hub/alembic.ini
      upgrade head`, run from the repo's `hub/` directory) runs the full 0001→0013
      chain cleanly against a fresh file. Restarted the actual local dev Hub afterward;
      its long-broken `data/agentweave.db` finally stamped to `0013` for the first time
      this whole session's history.
- [x] 3.13 Bind `127.0.0.1` by default, not `0.0.0.0`; honour the documented port variable, currently
      ignored. Done alongside 3.1 above — see its entry for detail.
- [x] 3.14 Remove the Docker gate from `cmd_hub_start` (`cli.py:3316`, `_docker_available()`). Done
      alongside 3.1 above — see its entry for detail.
- [x] 3.15 Add `--app` to open a chromeless browser app-mode window at the Hub URL. Added
      `hub start --app` (`cli.py`): once the Hub is confirmed healthy — in the native detached
      path, the native foreground path (via a daemon thread polling health so it doesn't block
      `uvicorn.run`), the Docker path, and every "already running" early-return across all three —
      it launches an installed Chromium-based browser (Chrome, Edge, or Chromium; checked by
      known install path on Windows/macOS, `shutil.which` on Linux, since none of these ship on
      PATH from a standard installer on Windows/macOS) with `--app=<hub_url>` for a chromeless
      window. Falls back to `webbrowser.open()` (a normal tab) if no such browser is found — this
      environment's Windows machine had none at any of the checked paths, so the fallback is what
      actually exercised end-to-end here; the app-mode branch itself was verified by mocking
      `_find_app_mode_browser` and asserting the `subprocess.Popen` call shape
      (`[browser, "--app=<url>"]`). 5 new tests in `tests/test_hub_commands.py` (existing
      `TestHubStartCommand` tests updated to set `args.app = False` explicitly, matching this
      suite's established convention of setting every flag a `MagicMock` args object needs rather
      than relying on `getattr` defaults against auto-vivifying mock attributes). Full CLI suite:
      993 passed, 4 skipped (same skip count as before this task — no new skips introduced);
      `ruff`/`black`/`mypy` clean.
- [x] 3.23 **Stop the Hub silently serving a stale UI.** *(Renumbered from 3.20, which collided with
      the already-completed 3.20 below — see that task's own note.)* `hub/hub/static/ui/` is a
      committed build artefact that no dev step refreshes, so the Hub served a bundle from
      2026-07-20 while the source had moved on. Implemented the build-stamp option: `hub/hub/main.py`
      compares the last git-commit date of `hub/ui/src` against `hub/hub/static/ui` (both via
      `git log -1 --format=%cI`); `hub/ui/src` only exists in a source checkout, so this is a no-op
      for an installed package. A stale bundle now logs a warning at Hub startup and is reported as
      `ui_stale`/`ui_stale_detail` on `GET /health`; `agentweave hub status` (`cli.py`) prints it.
      5 new tests in `hub/tests/test_ui_staleness.py` using throwaway git repos (not this repo's own
      history, to stay deterministic).
- [x] 3.24 **Validate `Host` and `Origin` on `GET /api/v1/setup/token`.** *(Renumbered from 3.21,
      same collision.)* It previously guarded only on client IP (`_is_local_address`), handing a live
      API key to any caller from a loopback or Docker-bridge address — vulnerable to a browser-based
      DNS-rebinding attack, since CORS does not protect against a rebound `Host`. `hub/hub/api/v1/
      setup.py` now also requires `Host` to resolve to a loopback/Docker-internal allowlist entry
      (`_is_allowed_host`) and `Origin`, if present, to match `Host` (`_origin_is_same_or_absent`).
      4 new tests in `hub/tests/test_setup.py`.
- [x] 3.25 **An unreachable Hub must not present the API-key prompt.** *(Renumbered from 3.22 to stay
      unique within this phase.)* `bootstrapState === 'failed'` previously fell through to
      `SetupModal` even when the Hub process itself was unreachable, asking the operator to paste a
      key — which cannot fix "the server is not running". `hub/ui/src/api/setup.ts`'s
      `fetchSetupToken` now returns a discriminated `SetupTokenResult` (`ok` / `unreachable` /
      `unavailable`) instead of collapsing every failure to `null`; `configStore.ts` adds a new
      `unreachable` `BootstrapState`; `App.tsx` renders a distinct "Can't reach the Hub" screen with
      a Retry button, reserving `SetupModal` for a genuinely unconfigured/remote Hub. 3 new tests in
      `hub/ui/src/__tests__/configStore-bootstrap.test.ts`.
- [x] 3.16 Update `hub/tests/` for direct execution; delete tests asserting the message-tag
      protocol. **The task as literally stated was already satisfied by tasks 3.5–3.11's own
      rewrites** — `hub/tests/` has no stale `execution_confidence`/message-tag assertions left
      (329/329 Hub tests pass; the only remaining `[Session: ...]` references are
      `agent_chat.py`'s intentional backward-compat parsing of pre-migration message content, and
      `test_runtime_diagnostics.py`'s regression assertion that `execution_confidence` is gone —
      both correct as-is, not stale).
      **Found during this task's own audit, not separately requested:** `src/agentweave/
      watchdog.py`'s `_make_direct_trigger_callback` (~200 lines) — the CLI-side counterpart of
      the same message-tag protocol, on the Hub-UI-trigger side rather than the scheduled-job
      side task 3.10 already fixed — was still unconditionally registered for every HTTP-
      transport watchdog run, polling for messages with subject `"Direct message from Hub"` and
      parsing `[Session:]`/`[NewSession]` tags from their content. Confirmed dead via `git log -S
      "Direct message from Hub"` across the whole repo history (never created by any Hub UI or
      backend source, only ever checked for in the watchdog); task 3.10's own commit diff
      (removing the *other* watchdog branch that used to special-case this exact string) shows it
      was deliberately kept at the time, under the assumption the Hub UI still used it; and task
      3.5's own docstring already states unsupported runners get a 501 with "no fallback path
      left for them over HTTP transport" — directly contradicting the callback's comment claiming
      it "allows Hub UI 'Send Message' to work." `AgentOutputPanel.tsx` (the only place the Hub UI
      prompts an agent) calls `/agent/trigger` directly and has no message-based fallback.
      Removed: `_make_direct_trigger_callback` and its registration; `_load_triggered_ids`/
      `_save_triggered_id` (used only by it); the `TRIGGERED_DIRECT_FILE` constant and its
      `.gitignore`-pattern entry (both now write nothing, since the callback that wrote them is
      gone). Left `_make_ping_callback` (the unrelated, still-live agent-to-agent ping callback in
      the same file) untouched — it shares this module but not this dead code. 14 dependent tests
      removed (13 in `tests/test_watchdog_session.py`, 1 in `tests/test_diagnostics.py`); that
      file's unrelated `_make_ping_callback` tests were kept as-is. 979/979 CLI tests pass (was
      993; -14, all accounted for above); `ruff`/`black`/`mypy` clean. **Not done here:** this is
      narrower than design.md's Decision 4 ("one uniform inbound queue per agent"), which would
      replace the `sender == "user"` magic-string discrimination pattern more broadly — Decision 4
      has no tasks scheduled yet and is a real design effort, not a deletion; this task only
      removed the one branch that had become fully unreachable.
- [x] 3.17 Rewrite the README quick start to the actual one-command flow. Replaced the stale
      three-step `hub start` → `init` → `activate`/watchdog path with the native
      `agentweave hub start --app` entry point. The prerequisite now installs the CLI and Hub in
      one shared `uv tool` environment (`uv tool install agentweave-ai --with agentweave-hub`),
      with pipx and pip fallbacks; the result explains that the Hub runs migrations, obtains the
      local API key, opens app mode, and owns Claude/Codex execution directly. Also corrected the
      mode table and watchdog FAQ so they no longer contradict the new runtime, and aligned the
      README's environment, source-development, package-layout, and native-database descriptions
      with tasks 3.1/3.12–3.16.
- [x] 3.18 Verify: trigger starts a process and streams output with no watchdog running; a missing
      binary fails with a stated reason; killing the Hub mid-run leaves no orphan and marks the run
      interrupted. **Verified end to end on Windows against an isolated source Hub** (port 18188,
      throwaway SQLite database/project/API key, no watchdog started or consulted by the harness):
      real Claude spawned directly, obtained typed session
      `ca6b3401-75d2-46e7-b00b-cc56faaf2efc`, and streamed its actual account-limit response via
      `run_started` + two `agent_output` events + `run_failed` (exit 1; the external account was out
      of credits until 19:10, so a success response was not available); real Codex spawned directly,
      returned `PHASE3_CODEX_OK`, persisted its output/session, and streamed `run_started` +
      `agent_output` + `run_completed` (exit 0). A Codex config pinned to an absent executable was
      rejected at preflight with HTTP 409 and the exact missing path/reason. A second Codex run was
      kept active, then the isolated Hub received a controlled shutdown: its recorded child PID
      24908 was absent afterward (no orphan); restarting against the same database reconciled run
      `run-9e5f3857` from `running` to `interrupted` with an `ended_at` timestamp.

      **Two real ConPTY defects surfaced and were fixed before accepting the task.** First, the
      default 80-column PTY materialized visual wraps inside multi-kilobyte newline-delimited JSON,
      causing one Claude record to be persisted as dozens of invalid text fragments. Direct agent
      runs now use a named `(24, 32767)` structured-output dimension, with a Windows regression test
      proving a 2,000-character JSON record remains one intact line. Second, pywinpty's blocking
      native reader could remain stuck after a fast CLI exited, leaving the Run forever `running`;
      switching pywinpty itself to nonblocking was investigated and rejected because it dropped
      final output. The adapter instead places a 100 ms timeout on pywinpty's local reader socket:
      buffered bytes are preserved, while timeout polls return EOF once the child is dead. A delayed-
      output regression test prevents mistaking a temporary quiet period for EOF. Focused final
      result: 36 trigger/PTY tests pass; the complete verification commands and counts are recorded
      in the Phase 3 handoff.
- [x] 3.19 **`/handoff`** — Phase 3 completion checkpoint written to
      `.claude/handoffs/2026-08-01-1818-phase3-native-runtime-complete.md` after all implementation,
      live Claude/Codex verification, full Hub tests, and static checks completed.
- [x] 3.20 Correct the Codex resume grammar and Windows headless process integration after manual
      acceptance exposed two regressions: `codex exec resume ... --sandbox workspace-write` failed
      because `--sandbox` is an `exec` option rather than a `resume` option, and pywinpty/ConPTY
      created unintended terminal chrome for Codex's explicitly non-interactive `exec --json`
      protocol. Exec-level options now precede the `resume` subcommand, while Codex runs through a
      new `PipeSession` with closed stdin, merged JSONL/error output, and Windows
      `CREATE_NO_WINDOW`; Claude remains on `PtySession`. T3 Code's installed source and the current
      official Codex manual were reviewed: T3 likewise uses hidden stdio child processes and now
      uses `codex app-server` for rich conversation sessions, reserving `codex exec` for one-shot
      work. A full app-server migration is deliberately not folded into this compatibility fix: it
      requires persistent JSON-RPC request correlation, typed approval/user-input handling, a new
      event mapper, and process/session ownership beyond a one-turn run. Regression coverage proves
      resume option ordering, Codex pipe selection, hidden/noninteractive Windows flags, merged
      output, and lifecycle behavior. Live verification on Codex CLI 0.146.0 passed both a direct
      PipeSession new/resume pair (`PIPE_NEW_OK`, `PIPE_RESUME_OK`) and restarted-Hub runs
      `run-16ed2f4d` / `run-23f767c8` (`HUB_PIPE_NEW_OK`, `HUB_PIPE_RESUME_OK`) on the same typed
      session, returning the agent to idle with exit 0.
- [x] 3.21 Restrict the local filesystem session fallback to the bootstrap project. The fresh
      scaffold caused the full Hub suite's BOLA test to expose that a second project with no
      `ProjectSession` row could inherit the host checkout's unscoped `.agentweave/session.json`
      and see its configured Codex agent. `_get_session_data` now returns filesystem state only
      when the authenticated `project_id` equals `AW_BOOTSTRAP_PROJECT_ID`; synchronized DB rows
      remain authoritative for every project. The focused BOLA regression passes and the complete
      Hub suite returns to 337 passed / 4 skipped.

## 4. Identity, runner capability, and surface split

*Moved ahead of the queue. Every queue entry stamps an origin; building that on a self-declared
field means reworking the queue's core record later.*

- [x] 4.1 Inject a per-run agent identity at spawn; bind identity to the connection on the
      tool-protocol path. New `AW_AGENT_IDENTITY` env var, set once by whoever spawns an agent's
      process — `agent_trigger.py`'s `trigger_agent_directly` (native runtime; also stamps
      `AW_RUN_ID`), `watchdog.py`'s `_run_cmd` (ping-spawned local/git processes), `cmd_switch`
      (prints `export AW_AGENT_IDENTITY=<agent>` for the claude_proxy eval path; a printed tip for
      other runners' copy-paste launch commands), and `cmd_run`. Since `agentweave-mcp`
      (`src/agentweave/mcp/server.py`) is a stdio subprocess spawned by the agent's own CLI, it
      inherits this env var — "the connection" is 1:1 with the process for the life of that env,
      so binding at spawn *is* binding to the connection. New module
      `src/agentweave/tool_surface.py` holds `bound_identity()`/`UnboundIdentityError`.
- [x] 4.2 Remove `--from-agent` and every caller-supplied sender; refuse unattributed effects rather
      than falling back to `"unknown"`. Removed the `from_agent`/`assigner` parameters from
      `send_message`/`create_task`/`ask_user`/`update_task` in `mcp/server.py` — identity is read
      from `tool_surface.bound_identity()`, never accepted as a tool argument, so it cannot be
      reintroduced by a prompt-injected caller either. Removed `--from-agent`/`--assigner`/`--from`
      from the `quick`/`msg send`/`delegate`/`task create`/`question ask` CLI subcommands
      (`cli.py`); each now calls a new `_require_bound_identity()` helper and refuses (exit 1) with
      no bound identity, rather than the old `args.from_agent or "unknown"`/`"user"` fallback.
- [x] 4.3 Probe tool-protocol availability per runner per environment; replace `hub_client_mode`
      with probed capability plus operator override. `hub_client` in session.json is now purely the
      operator override (`"cli"`/`"mcp"`; `"auto"` is treated as unset) — when unset,
      `tool_surface.resolve_access_path()` (CLI/watchdog) and `hub.launchability.resolve_access_path()`
      (Hub, independent mirror per that module's existing no-CLI-dependency convention) shell out to
      `<cli> mcp list` for claude/claude_proxy/native/codex and check for `"agentweave"` in the
      output, cached 5 minutes per CLI binary. This closes a real defect: the old "auto" branch in
      `watchdog.py` never probed anything and unconditionally assumed MCP was available. Runners not
      yet probeable (kimi, opencode, copilot, manual) default to `"cli"` — the guaranteed-available
      path — rather than assuming an unverified server. Copilot is explicitly deferred per this
      task's own text.
- [x] 4.4 Split the agent surface from the operator CLI: a small identity-bound verb set for agents,
      injected and configured by the Hub, separate from the operator's Hub-management and
      diagnostic commands. Scoped as: the existing `quick`/`msg send`/`delegate`/`task create`/
      `question ask` subcommands *are* that verb set — they now refuse to run without
      `AW_AGENT_IDENTITY` bound (task 4.2), which is exactly what "separate from the operator's
      commands" cashes out to today, since the Hub/watchdog/`switch` are the only things that set
      that env var. **Scope decision, not literally in the task's wording:** did not fork a second
      console-script binary (e.g. `agentweave-agent`) — the operator's diagnostic/management verbs
      (`hub start`, `roles`, `agent configure`, `doctor`, …) need no identity and are unaffected, so
      a second binary would duplicate argument parsing for no behavioural gain; revisit only if a
      concrete need for a narrower agent-facing surface (e.g. hiding operator verbs from an agent's
      `--help`) appears.
- [x] 4.5 Tell the agent at turn start which access path is in use; never offer an unavailable one.
      `tool_surface.access_path_notice()` / `hub.launchability.access_path_notice()` produce one line
      naming either the MCP tools or the equivalent CLI commands; prepended to every Hub-triggered
      run's initial prompt (`agent_trigger.py`) and to every watchdog ping prompt (`watchdog.py`,
      replacing the old unconditional "Call get_inbox(...)" text) — the only two places a turn
      starts today.
- [x] 4.6 Verify the identity and access-path scenarios of `agent-tool-surface`, including that an
      agent cannot cause an effect attributed to another agent. New tests: `tests/test_mcp_server.py`
      (`TestBoundIdentity` — refusal without a bound identity, attribution to the bound identity,
      and `test_send_message_signature_has_no_from_agent_parameter` proving impersonation is
      structurally impossible, not just discouraged), `tests/test_watchdog_session.py` (codex/
      non-probeable-runner ping prompts), `hub/tests/test_launchability.py` (`TestAccessPath` +
      `get_agent_config`'s session-wide `hub_client` fallback), `hub/tests/test_agent_trigger.py`
      (identity env injection, access-path notice in the first prompt, explicit override skips
      probing). Full suites green: CLI 987 passed/4 skipped, Hub 357 passed/4 skipped (+12 from this
      session). `ruff`/`black` clean on every touched file. Manually smoke-tested the CLI end-to-end
      (`msg send`/`task create`/`quick` refuse without `AW_AGENT_IDENTITY` and succeed with it;
      `switch` prints the export/tip). **Not fully verifiable this phase:** the spec's
      "coordination state cannot be read around the Hub" and "cannot alter its own
      configuration/scope" scenarios depend on the queue (phase 6) and charter (phase 13) existing
      first — `get_inbox`/`register_agent`/etc. are unchanged until task 7.1 removes them; this
      session verified only the identity- and access-path-specific scenarios that are actually
      implemented so far.
- [x] 4.7 **`/handoff`** — written after this phase, per the working protocol.

## 5. Workspace isolation

*Moved ahead of the queue. The scheduler is what causes concurrent turns; isolation must exist
before concurrency does.*

- [x] 5.1 Provision a git worktree per writing agent, on its own branch, sharing the object database;
      prepare it before the agent's first turn. **Implemented in `hub/worktrees.py` and the direct
      trigger path: each validated writing-agent name maps to `.agentweave/worktrees/<agent>` on
      `agentweave/<agent>`, provisioned synchronously before spawn and passed as the process cwd.
      Provisioning fails closed (HTTP 409) when Git/isolation is unavailable; an explicit
      `work_dir` cannot bypass isolation. Released branches with retained work are reused, while a
      branch already merged into the primary checkout fast-forwards before reuse.**
- [x] 5.2 Let read-only agents share the primary checkout; share dependency directories by symlink to
      avoid per-worktree install cost. **Added the typed `read_only` agent setting end-to-end
      (`AgentConfig`, YAML validation/serialization, activation/session sync, generated config, and
      reference docs). Read-only agents use the primary checkout; new worktrees link existing
      `node_modules`, `.venv`, and `venv` directories where the host permits directory symlinks.**
- [x] 5.3 Surface merge conflicts with the diverging agents identified. **Runs snapshot dirty
      worktree state to the agent branch using an internal Git identity, then pairwise
      `git merge-tree --write-tree` checks expose conflicting paths and both agent names through
      authenticated `GET /api/v1/worktrees/conflicts`; `GET /api/v1/worktrees` lists only active
      isolated checkouts, not retained branches from removed agents.**
- [x] 5.4 Release worktrees on agent removal, reporting unmerged work rather than discarding it.
      **Session roster reconciliation snapshots any dirty state, removes only the linked checkout,
      preserves the agent branch, computes commits absent from primary HEAD, and emits persisted +
      SSE `worktree_released` events with the branch and unmerged-work signal.**
- [x] 5.5 Verify the isolation scenarios of `hub-native-runtime` — two agents modifying the same file
      during overlapping turns lose nothing. **Disposable-repository integration tests cover
      distinct writer cwd values prepared before spawn, read-only checkout sharing, conflicting
      same-file snapshots retaining both versions and identifying both agents, release with dirty
      work preserved, invalid-name path containment, failure-closed behavior, endpoint responses,
      branch reuse, and dependency sharing. Full verification: CLI `991 passed, 4 skipped`; Hub
      `396 passed, 4 skipped`. Ruff and Black checks pass; focused mypy passes for the new worktree
      module/endpoints (the wider Hub type-check still has pre-existing errors).**
- [x] 5.6 **`/handoff`** — `.claude/handoffs/2026-08-01-2151-phase5-workspace-isolation-complete.md`.

## 6. Inbound queue and turn scheduling

- [x] 6.1 Add the queue entry record: typed origin, content, arrival time, hop depth, delivery state,
      delivered-in-turn reference.
- [x] 6.2 Reserve `user` as an agent name; delete every `sender == "user"` comparison
      (`watchdog.py:802`, `agent_chat.py:78,202`) and the subject-text discriminator.
- [x] 6.3 Implement the scheduler: idle + non-empty queue → start turn; arrivals during a turn →
      queue; turn end with entries remaining → start the next turn.
- [x] 6.4 Implement atomic drain — select up to the cap in arrival order and mark delivered in the
      same transaction that starts the turn.
- [x] 6.5 Return entries to the queue when their run is interrupted (pairs with 3.8).
- [x] 6.6 Build the turn prompt by inlining entry content with per-entry attribution. Delete the
      *"You have a new AgentWeave message … call `get_inbox()`"* indirection
      (`watchdog.py:3866,5178,5184,5370,5375`).
- [x] 6.7 Implement hop depth: operator entries at 0, emitted messages at `min(drained depths) + 1`;
      over-budget entries queue without starting a turn.
- [x] 6.8 Add configuration for hop budget and per-turn cap, with defaults, inspection, and visible
      rejection of invalid values.
- [x] 6.9 Emit stream events for entry queued, delivered, withdrawn, and chain suspended.
- [x] 6.10 Implement withdrawal of undelivered entries.
- [x] 6.11 Implement stop-the-running-turn: terminate the process, record the turn as stopped
      (distinct from completed and failed), preserve queued entries, do not redeliver.
- [x] 6.12 Verify against `agent-inbound-queue` — two agents messaging each other halt at the budget
      and resume on operator input; stopping a turn loses no queued work.
      **Implemented a typed durable queue, atomic capped delivery with Run creation, per-agent turn
      scheduling, hop-depth suspension/reset, withdrawal, interruption recovery, stop semantics,
      inline attributed prompts, settings/status endpoints, stream events, and production UI event
      invalidation. Verification: CLI `995 passed, 4 skipped`; Hub `407 passed, 4 skipped`; UI
      `200 passed`; production UI build passes; Phase 6 Ruff and Black checks pass; focused mypy
      passes for the three new queue/scheduler/API modules. Repository-wide Ruff retains one
      pre-existing import-order finding in `tests/test_cli_watch.py`; the existing ESLint 9 script
      has no flat config.**
- [x] 6.13 **`/handoff`** — `.claude/handoffs/2026-08-01-2239-phase6-inbound-queue-complete.md`.

## 7. Tool surface reconciliation

*Immediately after the queue: `get_inbox` becomes a bypass the instant the queue exists.*

- [x] 7.1 Remove the bypass tools: `get_inbox`, `mark_read`, `register_agent`, `get_agent_config`,
      `update_agent_config`, `register_session`, `heartbeat`, `get_context`, `get_agent_context`,
      `get_status`. The canonical registered surface now contains only messaging, the task ledger,
      operator questions, budgeted agent requests, and gated job mutations; roster/job inspection
      and every coordination/configuration read are absent. Generated context and docs no longer
      instruct agents to retrieve inbound state.
- [x] 7.2 Add `request_agent`, subject to the agent budget; gate the job tools (`create_job`,
      `run_job`, `delete_job`, `toggle_job`) behind allowance or approval. Migration 0015 adds the
      project `agent_budget` (default 8) and `allow_agent_jobs` (default false). `/agents/request`
      derives the requester from a live Run, copies only a configured pre-approved template,
      refuses budget/name/template violations, creates the agent, and queues its first attributed
      turn at source depth + 1. Agent-originated job mutations require a matching live Run and the
      operator-controlled allowance.
- [x] 7.3 Collapse `src/agentweave/mcp/server.py` and `hub/hub/mcp_server.py` into one surface;
      decide the fate of `save_checkpoint`, which exists only on the CLI side. The Hub module is the
      sole implementation; the CLI module is a re-export-only compatibility shim and the standalone
      `agentweave-mcp` console script is removed. `save_checkpoint` is intentionally retired from
      the surface; `agentweave checkpoint` remains the workspace command.
- [x] 7.4 Inject tool configuration when the Hub spawns an agent; retire the `mcp-setup` ceremony.
      Claude receives a per-run `--mcp-config`; Codex receives per-run `mcp_servers.agentweave`
      overrides. Both start the canonical Hub stdio script and inherit bound identity, Run, project,
      URL, and a live project credential. Global registration probing is no longer part of Hub path
      selection; `agentweave mcp setup` is a non-mutating compatibility notice and `activate` no
      longer changes client MCP configuration.
- [x] 7.5 Ensure every outbound capability is reachable by command, routed through the same queue,
      budgets, and attribution as the tool-protocol path. `agentweave agent request` reaches the
      same budgeted endpoint; `HttpTransport` forwards bound agent/Run headers; existing message,
      task, and question commands remain the equivalents named in the turn prompt. Operator answers
      now resume agents as typed depth-zero queue entries instead of magic `user` messages.
- [x] 7.6 Verify a full multi-agent session with the tool-protocol server disabled entirely. New
      command-only integration coverage exercises task create/update, attributed peer queueing,
      operator question/polling, budgeted agent creation, and recipient queue inspection with every
      runner set to `hub_client: cli`. Canonical surface/signature, injection, governance, and shim
      tests accompany full CLI (**971 passed, 4 skipped**) and Hub (**383 passed, 4 skipped**) runs.
- [x] 7.7 **`/handoff`** — durable boundary state written to
      `.claude/handoffs/2026-08-02-0140-phase7-agent-tool-surface-complete.md`.

## 8. Conversation timeline and agent colours

*Placed here so the queue's behaviour becomes visible as soon as it exists.*

- [x] 8.1 Assign each agent a stable colour index at registration, persisted on the agent record and
      independent of its name. Added `Agent.color_index` (migration 0016, backfilling existing rows
      by `created_at` per project) and `hub/hub/agent_colors.py`'s `next_color_index()` — monotonic
      per project, not reused after removal, wired into all three creation sites (session sync,
      self-registration, budgeted agent requests). Exposed on `AgentSummary.color_index`.
- [x] 8.2 Define the agent colour palette as hue tokens, deriving bubble tint, accent, and foreground
      per theme via `color-mix(in oklab, …)`; verify legibility in light and dark. The raw
      `--agent-1..8` hue tokens already existed pre-tuned per theme; added derived
      `--agent-N-tint`/`--agent-N-border` via one shared `color-mix` formula per hue (works in both
      themes from one definition, same technique as the context ring). `hub/ui/src/lib/agentColors.ts`
      maps a `color_index` onto these vars, cycling past the 8-hue palette, with a neutral fallback
      when no colour is assigned. Live-verified legible in both themes against the real dev Hub.
- [x] 8.3 Build the merged timeline read model over turns, output, and messages — replacing the
      timestamp-window attribution heuristic in `agent_chat.py:60-100`. Rewrote `agent_chat.py`'s two
      endpoints to return typed `TimelineEntry` rows (operator_input/agent_output/inbound_peer/
      outbound_peer) placed by recorded association only: delivered `InboundQueueEntry`/`Run` join,
      `AgentOutput.session_id`, and `Message.session_id` (newly wired at send time from the sender's
      live `Run`, in both `messages.py`'s `create_message` and `agents.py`'s `request_agent` —
      `Message.session_id` existed since migration 0003 but was never populated). Still-queued entries
      are appended regardless of requested session. Old `test_agent_chat.py` (whose own docstring
      described a three-tier heuristic already gone from the real implementation) rewritten to test
      the actual merged-timeline behavior: recorded association, session isolation, peer traffic both
      directions, undelivered/hop-suspended flagging, sort order.
- [x] 8.4 Render the four entry kinds: operator input, agent output, inbound peer tinted with the
      sender's colour, outbound peer accented with the recipient's colour. Always label with the name.
      New `AgentTimeline.tsx` + `agentTimelineModel.ts`; a real bug caught by its own test
      (`labels an outbound peer message with the recipient name`): the first draft labelled an
      outbound entry with the *subject* agent's own name instead of the recipient's, contradicting the
      spec's explicit scenario. Fixed.
- [x] 8.5 Render the undelivered state and its transition to delivered; render the
      hop-budget-suspended explanation. Undelivered entries render in a distinct dashed "Waiting to be
      delivered" section with a withdraw control (reusing the Phase-6 `DELETE /queue/entries/{id}`
      endpoint, previously unwired to any UI); a queued agent-origin entry past the project hop budget
      shows "Autonomous continuation is paused — operator input will resume it."
- [x] 8.6 Show waiting-entry counts and the reason when an agent is not running. New
      `hub/ui/src/api/queue.ts`'s `useQueueStatus` consumes the existing Phase-6
      `GET /queue/{agent}/status` endpoint (already returned `waiting_count`/`running`/
      `waiting_reason` — no backend work needed, only wiring).
- [x] 8.7 Type the timeline entries — conversational exchange, intermediate work, self-contained
      structured results — and render each in its own form rather than as a uniform bubble.
      `entryCategory()` partitions every entry into `message`/`work`/`result`; each renders via its own
      component (`MessageBubble`/`WorkRow`/`ResultCard`).
- [x] 8.8 Make intermediate work collapsible and completed turns foldable to a summary. Entries are
      grouped into turns by `run_id` (`groupIntoTurns`); the last turn starts unfolded, every earlier
      one starts folded to its status/timestamp summary, independently toggleable. Work entries
      (thinking/tool_use/tool_result, tool_use paired with its tool_result by `call_id`) collapse
      behind one "N steps of intermediate work" toggle per turn.
- [x] 8.9 Present structured results as content surfaces using the softer content radius, with a fade
      indicating clipped content. `ResultCard` uses `var(--radius-content)`; content past 240 chars
      clips with a bottom gradient fade and a "Show more" control.
- [x] 8.10 Add the stop control to the running turn; render a stopped turn as deliberately stopped
      rather than as an error. The running turn's own header carries a Stop button (in addition to the
      existing header-level one from task 3.7); terminal turns look up their outcome via
      `runStatusByRunId()`, reusing the existing `/agents/{name}/timeline` run-lifecycle events (no new
      backend endpoint) so `run_stopped` renders amber/"Stopped", distinct from red/"Failed".
- [x] 8.11 Verify against `agent-conversation-timeline`. 27 new frontend tests (`agentTimelineModel.test.ts`,
      `agentTimeline.test.ts`, `agentColors.test.ts`) plus 10 new backend tests
      (`test_agent_chat.py`) map directly onto the spec's scenarios. Full suites green: CLI
      **971 passed, 4 skipped**; Hub **382 passed, 4 skipped, 3 pre-existing order-dependent failures**
      (confirmed identical against unmodified `d241d38` — shared in-memory test DB across the pytest
      session, already flagged in the Phase 7 handoff's dead-ends, not introduced here); UI **222
      passed**; `tsc --noEmit` clean. Then live-verified end-to-end against a real native Hub +
      real Vite dev server: seeded a realistic conversation directly in the dev DB (delivered turn
      with thinking/tool_use/tool_result/text, an outbound delegation, a completed run, a second
      running turn with an inbound peer reply, and a hop-budget-suspended queued entry), which
      incidentally triggered the project's own watchdog into running a **real** `kimi` agent turn —
      its genuine reply then flowed correctly through the new merged timeline and queue-status UI
      live via SSE, in both light and dark themes (folded/unfolded turns, coloured peer bubbles,
      Stop button on the running turn, "Waiting to be delivered (N)" with the suspended explanation).
      Cleaned up afterward: stopped the scratch Hub/watchdog/Vite processes, deleted the scratch
      project and seed script.
- [x] 8.12 **`/handoff`** — durable boundary state written to
      `.claude/handoffs/2026-08-02-0300-hub-native-phase8-timeline-complete.md`.

## 9. Accounting and budgets

> **Update (2026-08-03) — closed by verified successor implementation.** The archived
> `openspec/changes/archive/2026-08-03-accounting-and-budgets/` change closes all of phase 9:
> normalized Claude/Codex/OpenCode telemetry, immutable measured-or-unavailable turn outcomes,
> agent/project aggregates, allowance-first and explicitly API-equivalent presentation, and a
> project token budget that retains autonomous queue work while operator turns remain available.
> Evidence: 432 Hub tests, 289 UI tests, production build, and strict OpenSpec validation. These
> superseded checkboxes remain unchanged per the reconciliation rule; the archived successor's
> completed task list is authoritative.

> **SUPERSEDED (2026-08-02).** Re-cut as its own change; see the slice table in
> `openspec/changes/2026-08-02-agent-conversation-workspace/design.md`. Ready to propose, and
> independent of the conversation slice, so it may be picked up in parallel. Do not implement from
> this list — these items stay unchecked until the successor change closes them.

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

> **SUPERSEDED (2026-08-02) — split across two changes.** Items 10.3–10.7 belong to
> `openspec/changes/2026-08-02-agent-conversation-workspace/`. Items 10.1–10.2 belong to a
> local multi-project change that is ready for technical exploration after the single-runtime
> change. RQ-1's multi-tenant premise was resolved by the local-only product direction; project
> discovery, lifecycle, and SSE switching still need their own design. Do not implement from this
> list.
>
> **Update (2026-08-02) — partially closed by the successor's phase 1, real implementation, not on
> the strength of this note.** 10.4 (project name navigates, expander toggles) and 10.5 (project
> reachable from an agent conversation) are done — see that change's `tasks.md` 1.5 and
> `conversationShell.test.tsx`/`conversationNavigation.test.ts`. 10.3's navigation-restructure half
> is done (the rail lists only projects and agents), but its "move per-project views into the
> content area as tabs" half is not — `tasks`/`questions`/`activity`/`quality`/`logs`/`jobs`/
> `instructions`/`spec` remain top-level sidebar destinations, not project-scoped tabs. 10.6 is done
> only for the rail and the conversation timeline (`tasks.md` 1.3); task-assignment and activity
> colouring were not touched. 10.7 was verified against `agent-conversation-workspace`'s own spec,
> not literally `hub-visual-language`. 10.1–10.2 remain undone.
>
> **Update (2026-08-04) — phase 10 is now closed by real successor implementation.** The local
> multi-project workspace successor implemented and verified 10.1–10.3 and the remaining 10.6
> surfaces, while retaining the already-complete 10.4–10.5 behavior. Its phase 5 verification
> covered both `agent-conversation-workspace` and the referenced `hub-visual-language` navigation,
> responsive, keyboard, reduced-motion, and exact color-mapping scenarios. Its phase 6 closeout
> migrated a legacy project, created a second, ran both concurrently with isolated worktrees,
> switched during output, and repaired a moved directory. The checkboxes below remain unchanged
> under the reconciliation rule; durable phase handoffs exist in the successor change history.

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

> **SUPERSEDED (2026-08-02) — split across two changes.** Item 11.1 belongs to
> `openspec/changes/2026-08-02-agent-conversation-workspace/`. Items 11.2–11.5 belong to a composer
> intelligence change, which additionally needs a workspace path-listing endpoint that does not
> exist yet. Items 11.6–11.7 are **already implemented** but were never checked off:
> `record_context_usage` in `hub/hub/output_recording.py`, `context_usage` on the agent summary, and
> `hub/ui/src/components/context/ContextUsageIndicator.tsx` with a compact variant, covered by
> `contextPresentation.test.tsx`. Only placement in the composer remains, which is task 3.8 of the
> conversation change. Do not implement from this list.
>
> **Update (2026-08-02) — 11.1 and the remainder of 11.6–11.7 are now done, real implementation, not
> on the strength of this note.** 11.1 (autosizing composer, bounded growth then scroll, per-
> project-and-conversation draft persistence) shipped in that change's `tasks.md` 3.1–3.3
> (`Composer.tsx`, `composerDrafts.ts`, `conversationComposer.test.tsx`). 11.6–11.7's only remaining
> gap, placement, shipped in 3.8 (`ConversationControls.tsx`, `conversationControls.test.tsx`).
> 11.2–11.5 remain undone, still belonging to the composer intelligence change.
>
> **Update (2026-08-03) — phase 11 is now closed by real successor implementation.** Composer
> intelligence shipped and was archived at
> `openspec/changes/archive/2026-08-03-composer-intelligence/`: trigger detection, exact range
> replacement, the keyboard menu, and all three result sources are covered by that change's phases
> 1–4 and its final 285-test UI run. Together with the archived conversation successor cited above,
> every item in 11.1–11.8 is implemented and verified. The checkboxes below remain unchanged under
> the reconciliation rule; 11.9's durable handoffs exist in both successor archives.

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

> **SUPERSEDED (2026-08-02) — split across two changes.** Items 12.2–12.3 (inline controls with
> overflow collapse, banner stack) belong to
> `openspec/changes/2026-08-02-agent-conversation-workspace/`. Item 12.1 (the searchable in-place
> agent selector) belongs to the composer intelligence change — the conversation change shows which
> agent is active but does not reassign an in-flight conversation. Do not implement from this list.
>
> **Update (2026-08-02) — 12.2 and 12.3 are now done, real implementation, not on the strength of
> this note.** See that change's `tasks.md` 3.5 (`ConversationControls.tsx`: submit/stop/active-
> agent/context-usage inline, everything else in a fixed-order keyboard-operable overflow menu) and
> 3.9 (`BannerStack.tsx`). **Not a literal match to 12.2's own wording**: the shipped design is a
> fixed inline/overflow split, not a *responsive* collapse that moves items between the two based on
> viewport width — the approved `agent-conversation-workspace` requirement replaced "collapse when
> tight" with "only ever show four things inline," which closes the same underlying need (composer
> chrome shouldn't crowd out the text) by a different, simpler design. 12.1 remains undone.
>
> **Update (2026-08-03) — phase 12 is now closed by real successor implementation.** The searchable
> launchability-aware selector and immutable cross-agent redirect shipped in
> `openspec/changes/archive/2026-08-03-composer-intelligence/` phases 5–6. Combined with the
> conversation successor's controls and banner work cited above, every item in 12.1–12.4 is now
> implemented and verified. The checkboxes remain unchanged under the reconciliation rule; 12.5's
> durable handoffs exist in the successor archives.

- [ ] 12.1 Build the agent/runner selector: in-place switching, search, launchability indicators from
      the Phase 3 probe.
- [ ] 12.2 Add inline composer controls with responsive collapse into an overflow menu.
- [ ] 12.3 Add a banner stack above the composer for run errors, stream loss, and blocked states.
- [ ] 12.4 Verify the selector scenarios of `agent-composer`.
- [ ] 12.5 **`/handoff`**

## 13. Agent identity, charters, and skills

> **SUPERSEDED (2026-08-02).** Re-cut as its own change; see the slice table in
> `openspec/changes/2026-08-02-agent-conversation-workspace/design.md`. Ready to propose, and
> independent of the conversation slice. Do not implement from this list.

> **Update (2026-08-12) — reconciliation pass, PARTIAL. This phase is NOT fully closed.** Unlike
> phases 9–12, this one had no closure note, so each item was checked against the tree rather than
> assumed from the successors' names. Three items are genuinely unbuilt and one is half-built; they
> would have been buried by a wholesale "closed by successor" note.
>
> **Verified shipped** — `runner-agent-charter-separation` and `single-runtime`, plus
> `2026-08-11-charter-set-reshape` (archived today):
> - 13.1 — `Runner` exists (`hub/hub/db/models.py:231`), project-scoped and reusable.
> - 13.3 *(partly)* — `Charter` exists (`models.py:264`) as an editable markdown contract.
> - 13.8 — the live roster is injected at turn start (`hub/hub/api/v1/agents.py:1023`, `### Team`).
> - 13.10 — `request_agent` exists (`hub/hub/mcp_server.py:481`) with `Project.agent_budget`.
> - 13.12 — `roles.py`, `templates/roles/` and `VALID_ROLE_IDS` are gone; the 21 guides became
>   charters and were then re-shaped to 9 by today's B0.
> - 13.13 — stronger than asked: `init` does not exist at all. `cli.py` has five commands
>   (`status`, `doctor`, `stop`, `hub_start`, `reset`), so there is no ceremony left to fix.
>
> **13.2 — CLOSED (2026-08-12), real implementation.** Migration `0063` makes
> `ix_agents_project_name` unique, and `models.py` matches. What it fixes is a **race**, not a
> missing check: registration already refuses a duplicate with 409 (`api/v1/agents.py:627`,
> `:1152`), but both sites SELECT then INSERT, and two concurrent registrations interleave through
> that gap — after which every `(project_id, name)` lookup in the Hub returns whichever row the
> database hands back first. Pre-existing duplicates are **renamed**, not deleted: an agent owns
> conversations, runs, tasks and messages by `id`, so dropping a row to satisfy an index would
> destroy history, and failing the upgrade would leave the operator with no UI to repair it. The
> oldest row keeps the name; later ones become `<name>-2`, truncated to stay inside
> `AGENT_NAME_RE`. Five tests in `hub/tests/test_migrations.py`, including the rename and the
> length-limit path. Hub suite 1517.
>
> **Verified NOT done — these are real, and stay open:**
> - **13.4 scope enforcement.** No agent or charter scope field exists; every `scope` hit in the Hub
>   is the unrelated "project-scoped" phrasing. Nothing reports work as out-of-scope, so nothing
>   enforces it. A charter *saying* an agent should stay in scope is not the runtime enforcing it —
>   which is the same distinction B0 was about.
> - **13.9 single-agent omission.** `agents.py:1023-1039` always emits a `### Team` block, falling
>   back to "No other agents are registered in this project yet." The requirement is to omit the
>   roster and all collaboration instruction *entirely* in a single-agent project. Emitting a Team
>   section that says the team is empty is the opposite of that.
> - **13.3's remainder.** The shipped `Charter` is name + content; the "scope, default skills" and
>   "empty charter means full project scope" structure was not built.
> - **13.11 inspectable effective composition.** No composition-inspection surface exists; the
>   `effective_*` symbols in `agents.py` are heartbeat status, unrelated to behaviour resolution.
>
> **Not assessed** — 13.5 (skills invocable by any agent), 13.6 (add-agent journey), 13.7 (templates
> and instantiation), 13.14 (verify against `agent-identity-and-skills`). Recorded as unknown rather
> than assumed either way.

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

> **SUPERSEDED (2026-08-02) — ready for technical exploration under narrowed RQ-2.** See
> `openspec/changes/2026-08-02-agent-conversation-workspace/design.md`. Stable requirement
> identifiers, evidence, and proposals need one unambiguous home before any of this is built, and
> AgentWeave currently ships two specification systems: this repository's own `openspec/` workflow
> and the `aw-spec-workflow` capability it provides to user projects. Local-only removes
> cross-machine reconciliation from the problem, but file authority, stable identifiers, database
> indexing, and external-editor changes still need a decision. Do not implement from this list.

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

> **SUPERSEDED (2026-08-02).** Re-cut as its own change; blocked on the conversation change and on
> the specification slice. See
> `openspec/changes/2026-08-02-agent-conversation-workspace/design.md`. Do not implement from this
> list.

> **Update (2026-08-12) — reconciliation pass. Still open, and worth saying why it only looks
> closed.** A conversation-embedded approval surface *does* now exist and is verified:
> `PermissionRequestCard.tsx`, `AgentQuestionCard.tsx` and `UnaskedQuestionCard.tsx`, closed by
> `archive/2026-08-06-agent-permissions-tool-schemas-and-base-knowledge` and
> `archive/2026-08-11-permission-request-expiry`. It is easy to read that as closing this phase. It
> does not.
>
> Those cards gate **tool calls and questions** — "may I run this command", "answer this". 15.1's
> subject is **task-lifecycle and specification-gate decisions**, which is a different set of
> decisions reaching the operator through the same kind of surface. Task transitions today live on
> `TasksBoard.tsx`, not inline in the composer.
>
> - 15.1 — **open.** The pattern exists; these decisions are not routed through it.
> - 15.2 — **half-blocked.** Its task-lifecycle half is now possible, since
>   `archive/2026-08-10-task-transition-machine` shipped the transitions and
>   `task-lifecycle-governance` is a spec. Its "requirement evidence acceptance" half depends on
>   phase 14, which is unbuilt, so 15.2 cannot fully close before 14 is decided.
> - 15.3 — open; `spec-traceability` does not exist as a spec.

- [ ] 15.1 Surface pending task-lifecycle and specification-gate decisions as an inline approval
      panel in the composer, actionable without leaving the conversation.
- [ ] 15.2 Connect approval actions to the existing task lifecycle transitions and to requirement
      evidence acceptance.
- [ ] 15.3 Verify the approval scenarios of `agent-composer` and `spec-traceability`.
- [ ] 15.4 **`/handoff`**

## 16. Closeout

> **REDEFINED (2026-08-02).** This umbrella is archived once every successor change re-cut from
> phases 9–16 is done; see the slice table in
> `openspec/changes/2026-08-02-agent-conversation-workspace/design.md`. The ten delta specs under
> `specs/` remain authoritative for behaviour implemented in phases 1–8, and successor changes
> reference them rather than restating them. Note that two currently overstate the system:
> `agent-inbound-queue` and `agent-composer` describe behaviour the shipped UI does not honour —
> input accepted during a running turn, and drafts surviving navigation. The conversation change
> closes both.

> **Partial 16.2 (2026-08-03) — `agent-tool-surface` reconciled by its successor.** The
> `agent-capability-plane` change (phases 9's identity work, re-cut as its own successor) is
> complete and synced `openspec/specs/agent-tool-surface/spec.md`: the six unmodified requirements
> from this umbrella's delta plus the identity requirement as revised by
> `openspec/changes/agent-capability-plane/specs/agent-tool-surface/spec.md` (run-credential
> authentication in place of environment-variable binding, `HTTP, MCP, or command access` in place
> of `the tool surface`). It also synced the new `agent-capability-plane` capability spec. The other
> nine delta specs under this umbrella's `specs/` remain unsynced — 16.2 is not done until they are.

> **Additional partial 16.2 (2026-08-03) — single-runtime consequences reconciled.** The
> `single-runtime` successor synced its changes into `agent-context-onboarding`,
> `agent-context-usage`, `agent-stream-events`, `agent-tool-surface`, `project-instructions`,
> `runtime-diagnostics`, `spec-manifest-sync`, and `trace-timeline`; created the authoritative
> `app-lifecycle` spec; and retired the empty `opencode-runner` spec. This does not sync the nine
> remaining umbrella-originated delta specs listed above, so umbrella task 16.2 remains open.

> **Additional partial 16.2 (2026-08-03) — runner/agent/charter ownership reconciled.** The
> `runner-agent-charter-separation` successor synced its deltas into `agent-charter`,
> `agent-context-onboarding`, `agent-runtime-binding`, and `runner-management`, and created the
> authoritative `charter-management` spec. It also removed the legacy fixed-role runtime while
> preserving the starter documents as editable charters. Other unsynced umbrella deltas remain,
> so umbrella task 16.2 remains open.

> **Update (2026-08-12) — reconciliation pass. 16.2 is the concrete blocker to archiving this
> umbrella, and it is a mapping exercise, not a copy.** Checked each of the ten delta specs under
> this change's `specs/` against `openspec/specs/` by name:
>
> - **Present under the same name (2):** `agent-composer`, `agent-tool-surface`.
> - **Absent under that name (8):** `agent-conversation-timeline`, `agent-identity-and-skills`,
>   `agent-inbound-queue`, `hub-interface-feel`, `hub-native-runtime`, `hub-visual-language`,
>   `spec-authoring`, `spec-traceability`.
>
> **Absence by name is not evidence of being unsynced, and must not be treated as such.** The
> successors renamed capabilities as they re-cut them — `openspec/specs/` now holds
> `agent-conversation-workspace`, `hub-workspace-shell`, `hub-interaction-feedback`, `trace-timeline`,
> `app-lifecycle`, `conversation-lifecycle`, `agent-charter`, `runner-registry` and others that did
> not exist when these deltas were written. Several of the eight have plausibly landed under those
> names in whole or in part.
>
> So closing 16.2 requires deciding, per delta spec and per requirement, whether its content lives
> somewhere in the current 31 — not re-running a sync. Two of the eight are known-unbuilt rather than
> renamed: `spec-authoring` and `spec-traceability` are phase 14, which has never been implemented.
>
> **Recommended order before this umbrella can be archived:** settle phase 14's open design question
> (one home for requirement identifiers, evidence, and proposals — the note on phase 14 states it),
> then do the 16.2 requirement-level mapping, then 16.1. Phase 13's four verified gaps and phase 15
> are independent of that and can be picked up separately.

- [ ] 16.1 Confirm every scenario in the ten delta specs is exercised.
- [ ] 16.2 Sync delta specs into `openspec/specs/`; reconcile `agent-stream-events`,
      `runtime-diagnostics`, and `agent-conversation-handoff` with their new behaviour.
- [ ] 16.3 Archive the change.
- [ ] 16.4 **`/handoff`**
