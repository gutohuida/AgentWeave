## Context

This design uses **T3 Code as a studied reference**, not as an upstream. All observations below
were verified against T3's actual shipped source, recovered from the sourcemaps bundled with the
installed desktop build at
`%LOCALAPPDATA%/Programs/t3code/resources/app.asar.unpacked/apps/server/dist/client/assets/*.js.map`.
Those maps embed `sourcesContent`, yielding **577 original application source files** across
`src/`, `packages/contracts/`, `packages/client-runtime/`, and `packages/shared/`.

T3 Code is MIT licensed. Studying and reimplementing its behaviour is unrestricted. If any code is
lifted verbatim, the MIT copyright notice must travel with it; the intent of this change is
reimplementation in our own stack, which carries no such obligation.

### Measured gap summary

| Symptom reported | Measured cause | Evidence |
|---|---|---|
| "The font is prettier" | T3 self-hosts **DM Sans Variable** + JetBrains Mono as bundled `.woff2`. We request `Inter` 400/500/600 from `fonts.googleapis.com` with `display=swap`, with **0** `@font-face` rules and **0** bundled font files — so we silently fall back to Segoe UI whenever the CDN is slow, blocked, or offline. | `hub/ui/index.html`; T3 `index-6Ivh-FEr.css` + `dm-sans-latin-wght-normal-*.woff2` |
| "Everything is in a square box frozen in place" | T3's built CSS carries **47** `transition-duration`, **42** `transition-timing-function`, **39** `transition-property`, **3** `transition-delay`. Ours carries **1** `transition` and **0** `@keyframes`. | `hub/ui/src/index.css` vs T3 built CSS |
| Icons feel slow / inconsistent | Two icon systems. Material Symbols used in 24 files, `lucide-react` in 1. The Material Symbols stylesheet is loaded with `display=block`, so **every icon is invisible until a third-party request completes**. | `hub/ui/index.html`, `src/components/common/Icon.tsx` |
| UI feels laggy / dead | Nine `refetchInterval` polls (3s/5s/10s/30s/60s) run **alongside** a working SSE channel that already handles 9 event kinds. | `hub/ui/src/api/*`, `hub/ui/src/hooks/useSSE.ts` |
| "The watchdog feels weird as hell" | The Hub does not execute agents. It writes a fake message, embeds session directives as text in the body, and waits for a 5-second poller to parse them back out. | `hub/hub/api/v1/agent_trigger.py:133-161`, `src/agentweave/watchdog.py:121` |
| Connecting an agent is fiddly | `switch` prints a command to copy-paste; env vars set via `eval`; session IDs pasted by hand. | `src/agentweave/cli.py:5128-5139` |

**Conclusion: the stack is not the problem.** Every gap above is either a missing layer of polish
we never applied, or a consequence of not owning the execution boundary. Replacing React, Tailwind,
FastAPI, or Python would fix none of them.

## Goals / Non-Goals

**Goals**

- The Hub owns agent execution end to end, with observable outcomes.
- Starting AgentWeave is one command, with no per-agent wiring ceremony.
- The interface meets a modern feel bar: real typography, real motion, real streaming.
- The agent conversation surface is a genuine composer, not a text input.

**Non-Goals**

- Matching T3 feature-for-feature. Most of T3 is explicitly unwanted (see rejection table).
- Any multi-platform client work.
- Any change to the coordination model (tasks, roles, gates, specs) beyond the trigger path.

## Decisions

### Decision 1 — The Hub runs natively on the host; Docker becomes optional

**What:** Ship the Hub as a host process (`agentweave hub start` running uvicorn locally, installed
via pipx/uv), not as a Docker container by default. Docker remains supported for remote or
multi-user deployments where the Hub is not expected to spawn local agents.

**Why:** This is the single unlock. A container cannot see the operator's `claude` binary, their
provider credentials, their git worktree, or a usable PTY. Every downstream awkwardness — the
watchdog, the synthetic-message protocol, `execution_confidence`, `switch`, `set-session` — exists
to work around that one boundary. T3 gets its seamlessness from `npx t3@latest` running *on your
machine*.

**Consequences:** Remote-Hub deployments lose the ability to spawn agents directly and must run a
host-side executor. That is acceptable: it becomes an explicit, named deployment topology instead
of the implicit default that currently degrades everyone's experience.

**Alternatives rejected:** Docker socket mounting (fragile, privileged, still no host credentials);
keeping the watchdog but shortening the poll interval (treats the symptom, keeps string-parsed IPC).

### Decision 2 — Direct execution replaces the message-tag protocol

**What:** `POST /api/v1/agent/trigger` spawns the agent process directly, returns a real run
identifier, and streams output over the existing SSE channel. Session identity becomes a typed
field on a run record, never text embedded in a message body.

**Why:** The current path is inter-process communication by string-parsing through a database
inbox, with a 5-second floor and no delivery guarantee. It is the direct cause of the Hub having to
guess at `execution_confidence`.

**Consequences:** `execution_confidence`, `[Session: …]`, `[NewSession]`, and the watchdog's
message-scanning trigger branch are deleted. Agent-to-agent messages remain messages; only the
human-triggers-agent path changes.

### Decision 3 — Keep the stack; add the missing layers

**What:** Retain FastAPI + SQLAlchemy + SSE on the server, React + Radix + Tailwind + React Query +
Zustand on the client. Add self-hosted variable fonts, a motion layer, and a single icon system.

**Why:** We already run T3's client stack. The gap is applied craft, not technology. Adopting
Effect-TS and typed RPC would cost months and address none of the six measured symptoms.

**Consequences:** No migration risk. Work is additive and independently shippable.

**Verified, not assumed.** `agentweave-hub` 0.35.0 was installed from PyPI into a clean virtualenv
and run with no Docker: `GET /` returned 200 with the full UI served from package data, `/health`
returned 200, and `/api/v1/agents` returned 401 with auth active. The Hub is *already* a
self-contained local application — SQLite via `aiosqlite`, one service in `docker-compose.yml`, the
built UI shipped as `static/ui/**` package data, and a working `agentweave-hub` console script at
`hub/main.py:133`. The only thing preventing local use is `cmd_hub_start` (`cli.py:3316`), which
calls `_docker_available()` and refuses to proceed without Docker. **The Docker requirement is
ceremony in the CLI, not a technical dependency.**

Two defects surfaced during that test and are folded into Phase 2: `alembic.ini` is not in
`package-data`, so a pip install logs *"skipping migrations"* and runs unmigrated; and the server
binds `0.0.0.0` while ignoring the documented port variable, exposing a local-first app to the LAN.

**On distribution channel:** the quality worth copying from `npx t3@latest` is *"one command,
nothing installed first"* — not npm itself. T3 uses npx because T3 is TypeScript and Node is its
runtime. An npm package here would be a JavaScript shim shelling out to Python: Python would still
be required, and Node would be added. `uv tool install` delivers the same one-command property on
the runtime we already use, and provisions Python itself. A signed installer is deferred until
there are users who do not already have Python — which today's users, who run Claude Code and Codex
CLI, do.

### Decision 4 — One uniform inbound queue per agent, drained at turn boundaries

**What:** Each agent has a single ordered queue holding **both** operator input and peer messages.
A turn starts whenever the queue is non-empty and the agent is idle — never waiting on operator
input. A turn ending with entries still queued immediately starts another. Delivery is inline, in
arrival order, up to a configurable per-turn cap; over-cap entries stay queued for following turns.

**Why:** This makes the U2A/A2A discrimination problem disappear rather than solving it. Peer
messages genuinely need a mailbox — provenance, queue state, delivery guarantees, persistence.
Operator input genuinely needs a run — a process, a session, output, an exit. They are different in
kind, so they need no discriminating string field. The two current discriminators are both defects:
`sender == "user"` is a magic string that `AGENT_NAME_RE` permits as a real agent name, and
`watchdog.py:802` additionally branches on whether the **subject line prose** contains
`"Direct message from Hub"`.

Inline delivery also removes the *"You have a new AgentWeave message from X. Call `get_inbox('Y')`
to retrieve it and respond"* round trip that both paths perform today
(`watchdog.py:3866,5178,5184,5370,5375`). An inlined-content path already exists for some client
modes, so this is a consolidation rather than new ground.

**Consequences:** `agent_chat.py:60-100` currently reconstructs conversation history by inferring
which session a message belonged to from timestamp windows against session start/end times and
other sessions' first-output times. With recorded turns, that heuristic is deleted rather than
maintained.

**Alternatives rejected:** adding a `channel: direct | peer` field to Message — smaller, but keeps
one table carrying two different lifecycles and leaves the discriminator available to get wrong.

### Decision 5 — Hop budget on the queue entry bounds autonomous chains

**What:** Every queue entry carries a hop depth. Operator entries are depth 0. A turn's depth is the
**minimum** among the entries it drained, and messages emitted during that turn carry that plus one.
An arriving entry whose depth exceeds the configured budget is queued but does not start a turn; it
waits for a turn started for any other reason. Both the budget and the per-turn cap are
configurable.

**Why:** Agents that auto-start turns on inbound messages can ping-pong indefinitely, burning tokens
unattended. This is the classic multi-agent failure mode, and the current watchdog has the same
exposure. Taking the *minimum* depth across a drained batch is what makes operator input a reset:
any depth-0 entry in the batch returns the whole chain to depth 0.

**Consequences:** Autonomous chains terminate. Recovery is always available and always the same
gesture — the operator sends a message. Depth living on the **entry** rather than the turn means
continuation turns caused by the per-turn cap inherit depth naturally and cost no extra hops.

## What we take from T3, surface by surface

Each item below was read in T3's recovered source and is specified concretely enough to
reimplement without further reference.

### A. Context-window meter — `src/components/chat/ContextWindowMeter.tsx`, `src/lib/contextWindow.ts`

This is the single best example of why T3 feels considered. The mechanics worth reproducing:

- **A 24×24 SVG ring**, `r = 9.75`, `strokeWidth = 3`, rotated `-90°` so fill begins at twelve
  o'clock. Progress is drawn with `strokeDasharray = 2πr` and
  `strokeDashoffset = circumference − (pct/100) × circumference`.
- **The ring animates**: `transition-[stroke-dashoffset] duration-500 ease-out`, with an explicit
  `motion-reduce:transition-none`. This is the "fluid" quality — the value glides rather than jumps.
- **Track and fill use `color-mix(in oklab, …)`** against theme tokens (24% for the track, 72% for
  the fill) rather than hardcoded greys, so it adapts to light/dark automatically.
- **Overload state at >90%** switches the fill to red. One threshold, not a gradient of warnings.
- **Hover popover with `delay={150}` / `closeDelay={0}`** — deliberate asymmetry: slow to open so it
  does not flicker on pass-through, instant to close.
- **The popover shows** percentage, `used/max`, a horizontal bar that animates
  `transition-[width,background-color] duration-500 ease-out`, total processed tokens, and a note
  when the provider compacts automatically.
- **Token formatting** (`formatContextWindowTokens`): `<1000` → integer; `<10_000` → one decimal
  `k` with trailing `.0` stripped; `<1_000_000` → rounded `k`; else one decimal `m`.
- **Percentage formatting**: below 10% shows one decimal, otherwise rounded integer.
- **`tabular-nums`** on every numeric readout, so digits do not jitter as values change.
- **Data derivation** (`deriveLatestContextWindowSnapshot`): scan activities **backwards** for the
  most recent `context-window.updated` event and defensively coerce every numeric field. The meter
  never computes context itself — it renders the newest event the provider emitted.

We already emit a `context_warning` SSE event and have an `agent-context-usage` capability. This
gives us the presentation contract to render it properly.

### B. Composer trigger detection — `packages/shared/src/composerTrigger.ts` (149 lines)

Small, self-contained, and directly portable in behaviour. `detectComposerTrigger(text, cursor)`
returns `{ kind, query, rangeStart, rangeEnd }` or null, where `kind` is `path` | `slash-command` |
`slash-model` | `skill`:

- **Slash commands** match only at **line start** (`/^\/(\S*)$/` against the current line prefix),
  so a URL mid-sentence never opens a command menu.
- **`@path`** and **`$skill`** are detected by walking backwards from the cursor to the nearest
  whitespace boundary and inspecting the token's first character.
- **`/model`** is special-cased into its own `slash-model` kind so the model picker opens inline.
- The whitespace test is **injectable** (`isWhitespaceChar?`), so surfaces with inline chip
  placeholders can treat those as token boundaries.
- `replaceTextRange(text, start, end, replacement)` returns both the new text **and the new cursor
  position** — the detail that makes autocomplete insertion feel correct rather than jarring.
- Paths with spaces or quotes are serialized quoted with escapes
  (`serializeComposerMentionPath`); file mentions render as markdown links with URI-encoded
  destinations (`serializeComposerFileLink`).

**Adopt the behaviour and the boundary rules; write our own implementation.**

### C. Composer shell — `src/components/chat/ChatComposer.tsx`

**3,178 lines.** This is the honest cost of "the chat box is 10,000× better," and the reason this
change specifies a staged subset rather than parity. T3 decomposes it into ~31 collaborating
modules; the ones that define the experience:

| Module | Role | Take? |
|---|---|---|
| `ComposerCommandMenu` | Keyboard-navigable menu for `/`, `@`, `$` results | **Yes — phase 1** |
| `ContextWindowMeter` | Live context ring | **Yes — phase 1** |
| `ComposerControl` / `CompactComposerControlsMenu` | Inline controls, collapsing responsively | **Yes — phase 2** |
| `ComposerBannerStack` | Stacked inline banners above the input (errors, state) | **Yes — phase 2** |
| `ComposerPendingApprovalPanel` / `…Actions` | Approve/deny agent requests inline in the composer | **Yes — phase 3**, maps to our quality gates |
| `ProviderModelPicker` + `ModelPickerContent`/`Sidebar`/`ListRow` + `modelPickerSearch` | Searchable, sidebarred model picker (212 + 683 lines) | **Yes — phase 2**, scoped to agents/runners |
| `ComposerPendingElementContexts` / `…TerminalContexts` / `TerminalContextInlineChip` | Attach UI elements and terminal output as context chips | **No** — depends on owned terminals and preview |
| `ComposerPromptEditor`, `composerInlineTokens` | Rich inline token rendering | **Defer** — plain textarea + chips first |

**Sequencing rule:** the composer is built in three phases and each phase ships. We do not attempt
3,178 lines in one pass.

### D. Typed activity stream — `packages/contracts/src/orchestration.ts`

T3's thread activity is a closed set of named event kinds — `thread.created`,
`thread.message-sent`, `thread.turn-start-requested`, `thread.turn-interrupt-requested`,
`thread.approval-response-requested`, `thread.checkpoint-revert-requested`, `thread.reverted`,
`thread.session-set`, `thread.turn-diff-completed`, `thread.activity-appended`,
`context-window.updated`, and others. The client's read model is derived purely by folding this
stream.

**What we take:** the discipline. Every state change an agent produces should be a named,
typed event on one stream that the UI folds — not a mixture of polled REST snapshots, log tailing,
and heartbeat inference. We already have `useSSE` handling 9 kinds; this change extends that set to
cover run lifecycle and makes it the **only** source of live state.

**What we do not take:** the event-sourced `OrchestrationEngine` with command decision functions,
idempotent receipts, and projection rebuilds. That is a large investment aimed at replay and
reproducibility, which are not current pain points.

### E. The control system — `src/components/ui/button.tsx`

The recovered button component explains the quality described as *"controls floating in nothing that
gain form when you touch them."* It is a small number of techniques applied without exception.

**Every control carries a border at all times; quiet variants make it transparent.** The base class
includes `border` unconditionally; the `ghost` variant is `border-transparent … [:hover,[data-pressed]]:bg-accent`.
The border therefore always occupies layout, and only its colour changes. **Nothing reflows when a
control gains emphasis** — the usual approach of adding a border on hover shifts content by a pixel
and is exactly what reads as cheap.

**Horizontal padding subtracts the border thickness** — `px-[calc(--spacing(3)-1px)]` — so label
insets look identical whether or not the border is visible.

**Press is physical, expressed as inverted lighting.** At rest a raised control carries
`inset-shadow-[0_1px_--theme(--color-white/16%)]`: a one-pixel top-edge highlight, lit from above.
On `:active` / `[data-pressed]` that highlight becomes `inset-shadow-[0_1px_--theme(--color-black/8%)]`
— the light inverts and the surface reads as depressed. Simultaneously
`[:disabled,:active,[data-pressed]]:shadow-none` removes the resting elevation, so the control sits
down onto the surface.

**Elevation is tinted by the control's own colour** — `shadow-primary/24 shadow-xs`,
`shadow-destructive/24` — never neutral grey.

**An inset `::before` paints inner decoration at the correct concentric radius** —
`before:absolute before:inset-0 before:rounded-[calc(var(--radius-lg)-1px)]`. The inner radius is
the outer radius minus the one-pixel border, so the curves stay parallel.

**Icons are subordinate by default** — `[&_svg:not([class*='opacity-'])]:opacity-80`, plus
`[&_svg:not([class*='text-'])]:text-muted-foreground` on the quiet variants. Both use
`:not([class*='…'])` so explicit emphasis is never overridden. `[&_svg]:-mx-0.5` corrects optical
alignment against the label.

**Coarse pointers get a full-size target without inflating the desktop interface** —
`pointer-coarse:after:absolute pointer-coarse:after:min-h-11 pointer-coarse:after:min-w-11` adds an
invisible touch target only where the pointer is coarse. The size scale is also mobile-first and
*shrinks* on larger viewports (`h-9 sm:h-8`), across `xs · sm · default · lg · xl`.

`disabled:opacity-64` and `disabled:pointer-events-none` complete it.

T3 builds this on Base UI with a `useRender` + `mergeProps` polymorphism pattern and `cva` for
variants. We do not need to adopt Base UI; the techniques are stack-independent.

### F. Radius scale

T3 derives everything from one base value:

| Token | T3 | AgentWeave today |
|---|---|---|
| `--radius` (base) | **0.625rem (10px)** | **6px** |
| `sm` | `calc(base − 4px)` = 6px | 4px |
| `md` | `calc(base − 2px)` = 8px | — |
| `lg` | `base` = 10px | 8px |
| `xl` | `calc(base + 4px)` = 14px | — |

We are at roughly 60% of their roundness, with no `md` or `xl` step. Content surfaces then go well
beyond the chrome scale: `ProposedPlanCard` is `rounded-[24px] border-border/80 bg-card/70` —
strongly rounded, with *both* a translucent border and a translucent fill so it sits **in** the
surface rather than on it, and a `bg-linear-to-t from-card/95 via-card/80 to-transparent` fade at
the bottom edge to signal clipped content.

The rule worth adopting: **chrome is crisp, self-contained results are soft.**

### G. Typed timeline — `src/components/chat/MessagesTimeline.logic.ts`

T3's conversation view is not a stream of bubbles. Its entries are typed:

```
message (user | assistant | system) · state · work · work-toggle
turn-fold · proposed-plan · working
```

Only `message` renders as conversational exchange. `work` is intermediate tool activity, collapsible
via `work-toggle`. `turn-fold` collapses an entire completed turn. `proposed-plan` is a card.

This is the *"not everything should be a chat"* principle implemented rather than argued. It matters
directly for AgentWeave: a quality-gate decision, a spec diff, and a task hand-off are all
self-contained results, and presenting them as chat bubbles would be the same mistake.

*Note: a prior research document stating this principle was searched for in
`AICollective/ResearchClub/` and the standalone `ResearchClub/` and not found. The principle is
adopted here on the strength of T3's implementation.*

### H. Typography and motion baseline

- **DM Sans Variable** (UI) and **JetBrains Mono** (code/terminal/numeric), self-hosted `.woff2`,
  subset to latin + latin-ext.
- Variable weight axis rather than three static cuts — a real contributor to the "prettier"
  impression.
- A named motion scale (fast ≈150 ms for hover/press feedback, base ≈250 ms, deliberate ≈500 ms for
  value transitions such as the context ring), `ease-out` by default, and `motion-reduce` honoured
  everywhere.
- Every interactive surface carries hover, active/pressed, and `focus-visible` treatments. T3's
  button pattern — `transition-colors`, `hover:bg-accent`, `data-[pressed]:bg-accent`,
  `focus-visible:ring-2 ring-ring ring-offset-1 ring-offset-background` — is the reference.

## What we explicitly reject

| T3 capability | Why not |
|---|---|
| Effect-TS + typed RPC over WebSocket | Months of migration; fixes none of the six measured symptoms. SSE + React Query already work. |
| Monorepo (`apps/*` + `packages/*`) with pnpm | Our two-surface layout is adequate. |
| Electron / iOS / Android / hosted relay | Explicitly unwanted. |
| Event-sourced `OrchestrationEngine` | Solves replay/reproducibility, which we do not need. |
| Clerk authentication | The Hub has its own `aw_live_*` key model. |
| Five-driver `ProviderAdapterRegistry` | We support our own runner set; the abstraction is premature. |
| Per-turn hidden-git-ref checkpoints | Genuinely excellent, but wired into their engine's command/event cycle. Revisit only after the runtime lands. |
| Element/terminal context chips | Depend on owned terminals and an in-app preview we do not have. |

## Risks / Trade-offs

- **Native Hub weakens the containerized deployment story.** Mitigation: keep the Docker image
  building and supported for coordination-only/remote topologies; document the two topologies
  explicitly rather than pretending one covers both.
- **PTY handling on Windows is the hard part.** The existing code already notes that agent CLIs are
  `.cmd` shims requiring `shell=True` (`cli.py:2341`). Mitigation: prototype the spawn+stream path
  on Windows first, since that is the primary development platform; treat POSIX as the easier case.
- **The composer can absorb unlimited time.** T3 spent 3,178 lines. Mitigation: the three-phase
  rule above, with each phase shipped before the next starts.
- **Deleting the watchdog trigger path touches scheduled jobs.** Jobs legitimately need a timer.
  Mitigation: keep the watchdog process for jobs only; remove only its message-scanning branch.
- **Self-hosted fonts add bundle weight.** Roughly 100–200 KB subset. Accepted: it removes a
  render-blocking third-party request, so net first-paint improves.

### Decision 6 — Split runner, agent, and behaviour; replace personas with charters and skills

**What:** Model three separate concepts — a **runner** (capability to execute: CLI + model +
environment, reusable everywhere), an **agent** (an addressable participant in one project: name,
runner, working directory, colour, queue, session), and **behaviour** (a charter of purpose and
scope, plus invocable skills). Retire the twenty-one job-title personas.

**Why:** "Role" already means two unrelated things in this codebase:

```python
constants.py:270   VALID_ROLES    = ["principal", "delegate", "reviewer", "collaborator"]
constants.py:309   VALID_ROLE_IDS = ["tech_lead", "architect", "backend_dev", …]   # 21 personas
```

The first is a *relationship within a session*; the second is a *job title* with a markdown guide in
`templates/roles/`. The list is even self-labelled `# Human-title (developer) roles` versus
`# AI-native (function-first) roles` — a migration that was started and stalled.

This is the *"persona, not capability boundary"* anti-pattern that
[`agentweave-strategy-discussion.md`](../../../../AICollective/ResearchClub/agent-operating-model/agentweave-strategy-discussion.md)
identified: roles carry no tool, permission, or scope binding, so they shape prose without
constraining anything.

**On "skills instead of roles":** correct in the main, with one necessary exception. Skills are
**pull** — invoked when needed, and rightly available to any agent. But something must remain
**push**, because a purely pull-based model loses three properties:

1. **Addressability.** "Send this to the reviewer" requires an agent that *is* the reviewer. An
   address cannot be a capability an agent might choose to invoke.
2. **Scope.** Skills grant capability; they cannot withhold it. Without an ambient boundary nothing
   constrains what an agent may touch.
3. **Predictability.** An agent that can become anything mid-turn cannot be reasoned about.

The charter supplies exactly that ambient layer and nothing more — purpose, scope, default skills.
It is a *boundary*, not a personality, which is the correction the research asks for. `VALID_ROLES`
survives as a **per-task relationship** rather than as agent identity, which is the elastic-delegation
conclusion made literal.

**Consequences:** `roles.py`, `roles.json`, `VALID_ROLE_IDS`, and the 21 guides in
`templates/roles/` are removed. `templates/skills/` becomes the place capability lives.
`Index("ix_agents_project_name")` in `models.py` gains `unique=True`, since a name is an address.

**On single-agent projects:** the roster and every collaboration instruction are omitted entirely
when a project holds one agent. This is the real fix for the friction diagnosed at `cli.py:268` —
not merely changing the default mode, but making multi-agent machinery *absent* until a second agent
exists.

**On spawning:** an agent budget bounds agent creation exactly as the hop budget bounds message
chains. Within budget and from a pre-approved template, creation is automatic; otherwise it becomes
an operator decision rendered on the structured-result surface already specified. `Agent` already
carries `self_registered` and `spawn_cmd` columns, so this extends existing ground.

**Alternatives rejected:** keeping personas as optional prose (leaves two vocabularies and no
boundary); pure skills with no charter (loses addressability, scope, and predictability as above).

## Agent identity colors

The timeline tints peer entries with the other agent's color, so a color system is required. No
per-agent color exists today, and the theme's five accent tokens (`--blue`, `--purple`, `--green`,
`--amber`, `--red`) already carry status meaning and cannot be reused.

- **Assignment is by registration order into a fixed palette, with the index persisted on the agent
  record** — not derived from the agent name. Hashing a name produces collisions, unpredictable
  adjacent pairs, and a color that changes on rename.
- Each hue derives three per-theme values — a low-saturation **bubble tint**, a higher-chroma
  **accent** for border and name label, and a **foreground** legible on the tint — via
  `color-mix(in oklab, …)` against surface tokens, the same technique T3 uses for the context ring
  so light and dark both work from one definition.
- **The agent's name is always present in text.** Color reinforces identity; it never carries it
  alone. This covers colorblind operators and every agent past the end of the palette.
- Beyond the palette size, hues cycle and the name label disambiguates.

### Decision 7 — One git worktree per agent

**What:** Each agent that writes gets its own git worktree on its own branch, sharing the repository's
object database. Conflicts are resolved at merge, optimistically. No file locking.

**Why — the framing that settles it:** *in a shared working directory there is no merge.* A merge
requires two divergent versions. Two agents in one folder produce a **lost update**: A reads
`models.py`, B reads `models.py`, A writes, B writes over it, and A's work is gone with no conflict
marker, no git event, and no error. This is the problem
[distributed databases have solved since the 1970s](https://christophermeiklejohn.com/ai/agents/distributed/zabriskie/2026/03/30/multi-agent-systems-have-a-distributed-systems-problem.html).

Worktrees do not *create* the merge problem — they **convert silent loss into a visible conflict**.
Resolving that conflict costs tokens; losing the work costs the work. The trade is clearly correct.

**Prior art — the space has converged here.** [Conductor](https://www.augmentcode.com/tools/open-source-agent-orchestrators)
gives each agent its own worktree; [Vibe Kanban](https://nimbalyst.com/blog/best-agent-management-tools-2026/)
gives each task card a worktree and branch; Sculptor goes further and uses containers; swarm-protocol
coordinates claims and conflict detection over MCP; **Wit** locks individual *functions* via
Tree-sitter rather than whole files; agent-coherence detects stale reads. This is settled practice.

**Why not locks.** A source-file lock needs four things we do not have: declared intent (agents do
not announce which files they will edit before editing them — this alone is fatal), workable
granularity (file-level over-blocks; Wit's function-level is the sophisticated answer), expiry
(a turn dying while holding a lock jams everything, hence *leases*), and a pessimistic/optimistic
choice. The decisive objection is simpler: **a lock serializes exactly the work you parallelized.**
Two agents on one hotspot file behind a pessimistic lock is one agent and a queue.

Note `src/agentweave/locking.py` already provides `acquire_lock`/`release_lock`/`is_locked`, but it
guards task JSON, not source files, and should not be extended to them.

**Consequences and honest costs:** disk, plus per-worktree environment setup (`npm install` in each
tree). Mitigations: share dependency directories by symlink, and isolate only agents that *write* —
read-only agents can share the main checkout. Revisit leases only if hotspot contention is
demonstrated.

### Decision 8 — Crash recovery reconciles runs and returns their entries

**What:** The run record carries a process identifier and a heartbeat. On Hub start, any run marked
running whose process is absent becomes `interrupted`, **and the entries delivered to it are
returned to the queue** with their delivery stamp cleared. On shutdown the Hub terminates the
process *group*, so no agent process is orphaned.

**Why:** Decision 4's atomic drain covers failure *during turn startup* but not death *mid-turn*.
Without reconciliation, entries marked delivered to a turn that no longer exists are silently lost —
exactly the failure the atomic requirement exists to prevent.

### Decision 9 — MCP inverts: the Hub pushes state in, MCP carries intent out

**What:** MCP ceases to be an input channel. The Hub pushes everything the agent needs at turn start
— queued entries, roster, charter, project instructions. MCP retains only the agent's ability to
*cause effects* in shared state.

**The rule that follows:** any tool that lets an agent **read coordination state it was not given**,
or **modify its own configuration**, is a bypass and is removed.

Applied to the Hub's 24 tools:

| Fate | Tools | Reason |
|---|---|---|
| **Removed — bypass** | `get_inbox`, `mark_read` | Circumvents the queue, hop budget, and drain cap entirely; an agent could fetch entries never delivered to it |
| **Removed — bypass** | `register_agent` | Circumvents the agent budget; makes Decision 6's spawn control decorative |
| **Removed — bypass** | `update_agent_config`, `get_agent_config` | An agent editing its own charter is a scope escape |
| **Removed — superseded** | `register_session`, `heartbeat` | The Hub owns the process and the session; it does not need to be told they exist |
| **Removed — superseded** | `get_context`, `get_agent_context`, `get_status` | Pushed at turn start |
| **Demoted to optional read** | `list_agents` | The roster is pushed; re-add only if long-turn staleness proves real |
| **Gated** | `create_job`, `run_job`, `delete_job`, `toggle_job` | A job is autonomous recurring spawn — the same fan-out the agent budget guards. Operator-gated or budgeted |
| **Survives** | `send_message`, `create_task`, `update_task`, `list_tasks`, `get_task`, `ask_user`, `get_answer` | Genuine outbound intent; the agent's only channel for causing effects |
| **New** | `request_agent` | Replaces `register_agent`, subject to the agent budget |

Roughly nine of twenty-four survive.

**Second finding — there are two MCP servers.** `src/agentweave/mcp/server.py` (24 tools) and
`hub/hub/mcp_server.py` (24 tools) are near-identical surfaces. The CLI server exists to serve the
local and git transports. Once the Hub owns local execution, it is redundant duplication and should
collapse into one server. (`save_checkpoint` exists only on the CLI side and needs a decision.)

**Third finding — MCP configuration ceremony can largely disappear.** The Hub spawns the agent and
the Hub *is* the MCP server, on localhost. It can inject the MCP configuration at spawn time rather
than requiring the operator to maintain client config files. This removes the onboarding step the
landscape research singled out: *"configure MCP in your client's config."*

**Not to be confused with:** AgentWeave Colab (see
[`../../explorations/2026-07-31-future-directions.md`](../../explorations/2026-07-31-future-directions.md)),
where MCP is exactly right *because* the peer is on another machine.

### Decision 10 — Account in tokens; treat currency as derived and plan-dependent

**What:** Record token counts as the primary unit of accounting, per turn and per run. Report
currency as a clearly-labelled **API-equivalent** figure, never as "what you paid". Budgets are
configurable in tokens.

**Why:** cost reporting differs fundamentally between metered and subscription users, and the tools
say so themselves — Claude Code's `/cost` *"tracks API billing, not subscription usage"*, and
directs subscribers to `/stats` instead. For a Pro or Max user the marginal cost of a turn is not
its API price; what actually constrains them is **rate-limit headroom** — five-hour windows and
weekly caps. Presenting `total_cost_usd` to such a user as "spend" is simply wrong.

**Availability is good.** Tokens are reported by every runner we support:

- **Claude Code** — `--output-format stream-json` emits a `result` message carrying `usage`
  (`input_tokens`, `output_tokens`), `total_cost_usd`, and per-model `modelUsage`.
- **Codex CLI** — writes session JSONL under `~/.codex`; `event_msg` entries with
  `payload.type === "token_count"` carry cumulative totals and the latest request delta.
- **OpenCode** — records per-step provider telemetry including fresh input, cache reads and writes,
  output, reasoning, and its own recorded cost.

`ccusage` already aggregates across Claude Code and Codex from exactly these sources, which
confirms the shape is stable enough to depend on.

**Consequences:** a **spend budget** joins the hop budget and the agent budget, expressed in tokens,
pausing autonomous turns when exceeded while leaving operator-initiated turns available. Three
budgets, one mechanism: **hops bound loops, tokens bound cost, agents bound fan-out.** Where a
runner reports rate-limit headroom, that is surfaced *instead of* currency for subscription users.

### Decision 11 — Requirement-level traceability is the differentiating capability

**What:** Every requirement carries a stable, visible identifier. Tasks declare the requirements
they serve. Evidence attaches to requirements with an origin. Each requirement shows a verification
state where it is read. Gate-level documents refuse completion until evidence is accepted.

**Why this and not authoring:** authoring is crowded — GitHub Spec Kit, AWS Kiro, and Tessl all do
it. What none of them closes is the loop **requirement → task → diff → verified**, visible in one
place and self-hosted. The research pass in
[`spec-as-contract.md`](../../../../AICollective/ResearchClub/spec-driven-development/spec-as-contract.md)
ended with an open question that could not be answered from the literature: *whether
requirement-level verification is practised anywhere at professional scale, or remains
aspirational.* No shipped example was found.

AgentWeave already holds all three pieces separately — a spec viewer, a task lifecycle with
`under_review`/`approved`, and (after Phase 2) run records carrying diffs. Connecting them is a
smaller job than building any one of them, and it is the thing that makes a specification a **gate**
rather than a document.

**Prerequisite that must not be skipped:** requirements are addressed by *title text* today. Stable
identifiers are the precondition for every part of this — without them a task cannot cite a
requirement, status cannot be tracked, drift cannot be detected, and renaming a requirement orphans
its history. `spec-decomposition.md` already calls for them.

**Why identifiers are visible rather than internal:** traceability that only functions inside one
tool is not traceability. An identifier must be quotable in a commit message, a pull request, and a
conversation.

**The mechanism that keeps specifications honest:** changing a requirement's meaning **stales its
evidence**. Without that, a specification decays into claims — every documentation effort dies of
drift, and this is the counter-pressure. Stale is deliberately distinguished from absent, and
superseded evidence is retained, so a regression stays legible.

### Decision 12 — Rigor is a property of each document, defaulting to the least binding

**What:** Every specification declares itself a **sketch**, a **contract**, or a **gate**. New
documents are sketches. Promotion is deliberate and recorded.

**Why:** the same research found *both* failure modes are real and named. Too little specification
produces "costly vibe-coding" — a polished system existing before anyone agreed what it means. Too
much produces competing sources of truth, and degrades the agent it was written for, because
*"model performance gets less reliable as the input grows, even on simple tasks."*

The resolution is not a single correct amount but **rigor chosen per work type**: lighter for
exploratory work (specify boundaries, not outcomes), heavier for deterministic work and for
agent-to-agent contracts. Making rigor a declared property of each document puts that choice in the
operator's hands per document rather than imposing one level project-wide.

**Second job the same concept performs:** rigor determines **who may change a document without
asking**. Agents edit sketches freely; contract and gate changes are proposals an operator accepts.
One concept, two purposes.

**Defence against the failure mode this project has itself demonstrated:** defaulting to sketch means
a large binding specification cannot appear by accident — producing one requires deliberately
promoting a document twice.

**The test for whether heavy rigor is earned** (from the same research): *if this specification turns
out to be wrong, is the implementation regenerated or repaired?* Repaired means keep it a sketch.

## The workspace shell

Three lessons came out of building the interactive mock
([`mock.html`](./mock.html)) and are specified in `hub-visual-language`:

- **One ground plane.** The first mock gave navigation its own fill *and* a dividing line. Two
  simultaneous boundary signals read as far heavier than either alone — the pane appeared "boxed
  out." Removing both went too far and the boundary vanished. The rule is **one signal**: shared
  fill plus a single hairline, lighter than the outline of any control near it.
- **Elevation is earned.** Only menus, popovers, dialogs, the composer, and self-contained content
  surfaces get their own fill. Regions do not.
- **Navigation holds live things; views are reached in the content area.** Per-project chips
  (Specs · Tasks · Activity · Jobs · Environment …) do not survive contact with a fifth entry at a
  sidebar's width. Navigation therefore lists only entities with live state — projects and agents —
  while project-scoped views live in the content area as tabs. Adding a sixth view costs a tab, not
  a navigation row. A project's **name** navigates; its **expander** reveals agents.

The cost is honest: reaching a project's tasks from inside an agent conversation becomes two
gestures rather than one, mitigated by the project being directly reachable from the conversation
header. A command palette would close the gap and is worth adding independently.

## Open Questions

1. **Interrupt-and-deliver.** Should submitting operator input while a turn is running offer an
   explicit interrupt action alongside plain queueing? *Recommendation: yes, as a distinct action —
   queueing stays the default, interrupting is deliberate.*
2. **Default limits.** What hop budget and per-turn delivery cap ship as defaults?
3. **Per-agent limit overrides.** Project-level configuration is specified. Whether individual
   agents may override the hop budget or cap is deferred until there is a case for it.
