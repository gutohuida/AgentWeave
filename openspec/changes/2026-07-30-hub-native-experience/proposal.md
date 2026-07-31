## Why

AgentWeave's coordination substrate works, but the experience of using it does not. Daily use
feels dated, manual, and uncertain next to tools like T3 Code, Antigravity, and Kiro. Three
complaints recur, and each was traced to a specific, verifiable cause in this repository rather
than to taste:

1. **It looks stale.** Not a stack problem. `hub/ui` already runs the same stack T3 does — Radix
   UI, Tailwind, React Query, Zustand — and `hub/ui/src/index.css` already declares Linear/shadcn
   design tokens. The staleness comes from three concrete gaps: fonts are fetched from a
   third-party CDN and silently fall back to the system font when unavailable, `index.css`
   contains **one** `transition` declaration and **zero** `@keyframes`, and two icon systems
   coexist (Material Symbols in 24 files, `lucide-react` in 1) with the Material Symbols
   stylesheet loaded `display=block`, which blocks the entire icon set on a network request.

2. **Connecting an agent is manual.** `agentweave switch` prints a command for the operator to
   copy and paste (`src/agentweave/cli.py:5128-5139`); env vars are wired by hand via
   `eval $(agentweave switch <agent>)`; session IDs are carried by hand via
   `agentweave agent set-session`. The README promises "Quick Start — 3 Commands" while shipping
   three alternative modes, Options A/B/C for proxy agents, 56 `cmd_*` functions, and a
   6,294-line `cli.py`.

3. **Triggering an agent is indirect and unreliable.** `hub/hub/api/v1/agent_trigger.py:133-161`
   does not run anything. It writes a synthetic message attributed to `"user"`, appends
   `[Session: <id>]` or `[NewSession]` as **literal text inside the message body**, and marks it
   unread. The watchdog then polls every 5 seconds (`src/agentweave/watchdog.py:121`),
   string-parses those tags back out of the message text, and spawns the subprocess. Because the
   Hub cannot observe the result, the code invents an `execution_confidence` field with values
   `queued_watchdog_stale | queued_watchdog_healthy | queued_manual`. **The Hub guesses whether
   the agent will run.**

The root cause of (2) and (3) is architectural and is documented in this project's own research
(`AICollective/ResearchClub/t3code-team-layer/landscape-and-findings.md`, finding #1): T3 owns the
execution boundary — its server spawns the agent, owns the PTY, the git checkout, and the
filesystem. AgentWeave does not own anything; it observes agents that other processes launch. The
watchdog exists only because the Hub ships as a Docker container, and a container cannot spawn a
host agent CLI. The watchdog is the host-side limb the Dockerized Hub lacks.

This change makes the Hub own execution directly, and closes the interface-feel gap using T3 as a
studied reference rather than as an upstream to fork.

## What Changes

**Runtime ownership**

- The Hub SHALL be installable and runnable natively on the host, so it can spawn agent CLIs with
  the operator's own binaries, credentials, and workspace. Docker is demoted from the default to a
  deployment option for remote and multi-user installations.
- The Hub SHALL own agent process lifecycle: spawn, PTY attachment, output streaming, session
  identity, interrupt, and exit reporting.
- Triggering an agent SHALL be a direct, synchronous operation with an observable outcome.
  `execution_confidence` is removed; the Hub reports what actually happened.
- The synthetic-message trigger protocol, the `[Session: …]` / `[NewSession]` in-body string tags,
  and the watchdog's role as trigger transport are removed.
- The watchdog is retained only for genuinely time-based duties (scheduled jobs), not as the
  execution path.
- Manual connection ceremony — `switch`, `eval $(…)`, `agent set-session` — is removed from the
  supported path for Hub-managed agents.

**Inbound model**

- Each agent SHALL have **one uniform inbound queue** holding both operator input and messages from
  other agents, distinguished by a typed origin rather than by a magic sender name or by subject-line
  prose.
- A turn SHALL start whenever that queue is non-empty and the agent is idle. Turns never wait for
  operator input, and a turn ending with entries still queued starts another.
- Queued content SHALL be delivered **inline** at turn start, in arrival order, up to a configurable
  per-turn cap. Over-cap entries stay queued rather than being truncated. The
  *"you have a message, go call `get_inbox()`"* round trip is removed.
- A **hop budget** carried on each queue entry SHALL bound autonomous agent-to-agent chains.
  Operator entries are depth 0, so operator input always restarts a suspended chain.

**Conversation timeline**

- The agent conversation view SHALL show operator input, agent output, and peer messages in **both
  directions** on one chronological timeline, so agent-to-agent traffic is visible without opening a
  separate inbox.
- Timeline entries SHALL be **typed and rendered in the form that suits them** — conversational
  exchange, collapsible intermediate work, foldable completed turns, and self-contained structured
  results as content surfaces. A chat bubble is one presentation among several, not the default for
  everything.
- A running turn SHALL be stoppable, with queued entries surviving the stop.
- Each agent SHALL have a **stable assigned color**, used to tint inbound peer entries by sender and
  accent outbound entries by recipient, always alongside the agent's name in text.
- Entries that have arrived but not yet been delivered SHALL be visible in a distinct state, and
  withdrawable until delivery.

**Agent identity and behaviour**

- **Runner**, **agent**, and **behaviour** SHALL be separate concepts: a runner is reusable
  execution capability, an agent is an addressable participant in one project, and behaviour is a
  charter plus invocable skills.
- The twenty-one job-title personas SHALL be retired. An agent's behaviour is a **charter** —
  purpose, scope, default skills — which is a boundary rather than a personality. Creating an agent
  SHALL require only a runner and a name.
- **Skills** SHALL be invocable by any agent; invoking one changes neither identity nor scope.
- Agents SHALL receive a **live roster** of their collaborators at turn start — and a project with
  exactly one agent SHALL receive **no roster and no collaboration instruction at all**.
- An agent MAY **request a further agent** within a per-project agent budget, mirroring the hop
  budget; anything beyond it becomes an operator decision.

**Specifications**

- Every requirement SHALL carry a **stable, visible identifier**, citable outside the Hub and
  surviving rewording, reordering, and relocation.
- Tasks SHALL declare the requirements they serve; **evidence** SHALL attach to requirements with a
  named origin; each requirement SHALL show a **verification state** where it is read. An agent's
  assertion alone SHALL NOT constitute verification.
- Changing a requirement's meaning SHALL **stale** its evidence, distinctly from having none.
  Implementation moving without its requirement SHALL be reported as **drift**.
- Each specification SHALL declare its rigor — **sketch**, **contract**, or **gate** — defaulting to
  sketch. Rigor determines both whether the document blocks completion and who may change it without
  acceptance.
- Authoring SHALL be a conversation **against a visible document**, with each proposed change
  individually acceptable, and SHALL always offer a starting point other than an empty page.
- The specification workspace SHALL meet the same interface standard as the agent conversation.

**Workspace shell**

- Navigation and content SHALL share **one ground plane**, separated by a **single** signal — a
  contrast in fill or a line, never both.
- Primary panes SHALL be **resizable**, clamped, persisted, and resettable in one gesture.
- Scrollbars SHALL be overlay handles: no track, no steppers.
- Navigation SHALL list only **live entities** — projects and agents. Project-scoped views (tasks,
  specs, jobs, activity, environment) live in the content area, so a sixth view costs a tab rather
  than a navigation row.

**Interface feel**

- Fonts SHALL be self-hosted and variable, matching the quality bar T3 sets (DM Sans Variable +
  JetBrains Mono, shipped as local `.woff2`). No third-party font CDN on the render path.
- A motion layer SHALL exist: standard durations, easings, and hover/active/focus treatments
  applied consistently to interactive surfaces.
- Controls SHALL reserve their outline at rest so gaining emphasis **never shifts layout**, express
  press physically through inverted lighting and removed elevation, and subordinate their icons to
  their labels.
- A radius scale derived from one base value SHALL distinguish crisp chrome from softer
  self-contained content surfaces; the current base is roughly 60% of the intended roundness and has
  no `md` or `xl` step.
- Coarse pointer devices SHALL receive adequate touch targets without inflating the desktop
  interface.
- The interface SHALL use exactly one icon system.
- Live state SHALL be driven by the existing SSE channel. The nine `refetchInterval` polls in
  `hub/ui/src/api/` are removed.

**Agent interaction surface**

- A real composer SHALL replace the current chat input: multi-line autosizing, submit-on-Enter
  with newline modifier, in-composer trigger detection for `@path`, `/command`, and `$skill`, and
  a keyboard-navigable command menu.
- A context-window meter SHALL show live context consumption per agent.
- A model/agent selector SHALL allow switching without leaving the conversation.

## Non-Goals

- **Not forking T3 Code.** Upstream is a 244 MB, ≥100-commits-per-week alpha (`v0.0.32`, 923 open
  issues). We study it, we do not inherit it.
- **Not adopting Effect-TS, the monorepo layout, or typed-RPC-over-WebSocket.** The existing
  FastAPI + SSE + React Query stack stays.
- **Not building Electron, iOS, Android, or a hosted relay.**
- **Not reimplementing T3's event-sourced `OrchestrationEngine`.**
- **Not rebuilding the coordination primitives.** Tasks, messages, roles, jobs, quality gates, and
  the spec screen are the differentiated assets and stay as they are, except where they touch the
  trigger path.
- **Not changing the CLI's local/git transports.** This change concerns Hub-managed agents.

## Impact

- Affected specs: `hub-native-runtime` (new), `agent-inbound-queue` (new),
  `agent-conversation-timeline` (new), `agent-identity-and-skills` (new),
  `hub-visual-language` (new), `hub-interface-feel` (new), `agent-composer` (new),
  `spec-traceability` (new), `spec-authoring` (new), `agent-tool-surface` (new),
  `agent-stream-events` (modified), `runtime-diagnostics` (modified),
  `agent-conversation-handoff` (modified).
- Affected code: `hub/hub/api/v1/agent_trigger.py`, `hub/hub/api/v1/agent_chat.py`,
  `hub/hub/main.py`, `hub/hub/db/models.py`, `hub/ui/index.html`, `hub/ui/src/index.css`,
  `hub/ui/src/api/*`, `hub/ui/src/components/agents/*`, `src/agentweave/watchdog.py`,
  `src/agentweave/cli.py`, `src/agentweave/constants.py`, `src/agentweave/roles.py`,
  `src/agentweave/templates/roles/`, `src/agentweave/templates/skills/`, `hub/pyproject.toml`.
- Distribution: `uv tool install` becomes the primary channel, `pipx` supported, `pip` documented.
  No npm package — Python is the runtime, so an npm wrapper would add Node without removing Python.
  A signed installer is deferred until there are users who lack Python.
- Breaking: `agentweave switch`, `agentweave agent set-session`, and the Docker-first Hub install
  are no longer the supported path for Hub-managed agents. `user` becomes a reserved agent name.
  `agentweave roles` and the twenty-one role guides are removed; agent names become unique per
  project.
  Given the project has no external install base to protect, these are removed rather than
  deprecated.
