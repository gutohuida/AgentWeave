# Exploration — Spec journey, agent chat, and context tracking

**Date:** 2026-07-28
**Status:** Decisions made, not yet proposed. One change (`fix-spec-chat-session-resume`) exists on the board.
**Purpose:** Durable record so none of this has to be re-derived. Each section below is ready to expand into a full OpenSpec change when the work is picked up.

> Everything marked **MEASURED** was verified by running the actual tool, not inferred from code or docs.
> Everything marked **UNVERIFIED** is explicitly not confirmed and must be checked during implementation.

---

## Already done (2026-07-28)

- Archived 9 changes. Four completed ones were synced to main specs first (`trace-timeline`,
  `agent-context-onboarding`, `runtime-diagnostics`, `project-instructions` — `openspec/specs/` now
  holds 7 capabilities). Five abandoned ones were archived **without** sync, because their delta
  specs describe behaviour that was never built.
- Wrote `docs/archive/autonomous-dev-loop/index.md` recording the shelved autonomous-dev-loop idea
  and the investigation findings behind it. Added to `mkdocs.yml`.
- Created `openspec/changes/fix-spec-chat-session-resume/` (validates `--strict`, 4/4 artifacts).

---

## Change 0 — `fix-spec-chat-session-resume` ✅ proposed

**Already on the board.** See `openspec/changes/fix-spec-chat-session-resume/`.

`SpecPage.tsx` hardcodes `session_mode: 'new'`, so every message in the Spec tab spawns a fresh CLI
session and the agent loses all spec context. The Agents tab does it correctly
(`AgentOutputPanel.tsx`), which is why the bug is invisible there.

**Key finding — the fix is one line.** In `hub/hub/api/v1/agent_trigger.py`:

```python
if body.session_mode == "resume" and body.session_id:   # → [Session: <id>]
elif body.session_mode == "new":                        # → [NewSession]
#   resume + no session_id → neither branch → NO TAG
```

No tag → `watchdog.py` falls back to `_load_agent_session(agent)` → the agent's last saved session,
or `None` (new) if there isn't one. That is exactly "resume most recent, new if none exists", already
implemented and runner-agnostic.

**Decision:** resume across contexts is a *feature* — pulling a warm agent into the Spec tab and
continuing its conversation is desirable. So no spec↔session association, no session picker.
Add a deliberate "new session" escape since resume-always has no exit.

---

## Change 1 — `add-spec-manifest`

### The problem (confirmed)

Four layers disagree about what a spec file is:

| Layer | Knows about |
|---|---|
| Hub API `SPEC_PATH_RE` (`hub/hub/api/v1/spec.py`) | `spec/spec.html`, `spec/changes/<slug>/spec.html` |
| CLI `_discover_spec_files()` (`src/agentweave/watchdog.py`) | the same two |
| `aw-spec-*` skills | + roadmaps, discovery, archive, `spec/specs/` |
| `spec` role guide (`hub/hub/data/roles/spec.md`) | + system-map, roadmaps, living spec |

**MEASURED** — the regex was run against the paths the improved skills tell agents to write:

```
OK   spec/spec.html
422  spec/system-map.html
422  spec/roadmaps/hub-ui.html
OK   spec/changes/add-thing/spec.html
422  spec/changes/archive/2026-07-28-add-thing/spec.html
422  spec/discovery/add-thing/idea.md
422  spec/changes/add-thing/specs/cap/spec.html
```

**The failure is silent.** `_discover_spec_files()` globs only those two shapes, so a roadmap written
by an agent is never offered to the Hub at all — no error, no event, just absence.

**Internal contradiction to fix:** `aw-spec-archive.md` says to merge into `spec/specs/`, while the
role guide lists `spec/specs/` as an anti-pattern.

### Decisions

- **Manifest (`spec/index.json`), agent-generated and agent-maintained.**
- **Do not rely on it alone.** Watchdog globs `spec/**/*.html` for discovery; the manifest supplies
  structure (kind, title, parent, order, status). Anything on disk but absent from the manifest is
  still synced and shown as **unfiled**. A forgotten manifest entry must degrade to bad navigation,
  never to an invisible file.
- **Drift detection surfaced in the Hub UI**, not just a CLI command, so the user can see it and tell
  an agent to fix it.
- **One-click repair**: the Hub hands the user a prefilled "fix the manifest" message to the spec
  agent. A repair skill (e.g. `aw-spec-reindex`) consumes the same drift set the UI computed.

### Drift taxonomy (Hub can compute all of it at sync time)

| Drift | Detection | Surfaced as |
|---|---|---|
| File on disk, absent from manifest | glob ∖ manifest | **Unfiled** node |
| Manifest entry, no file | manifest ∖ glob | **Missing** node |
| `parent` points at nothing | link check | **Orphaned** badge |
| manifest `kind` ≠ `<meta aw-spec-kind>` | compare | **Conflict** badge |
| manifest `status` ≠ `<meta aw-spec-status>` | compare | **Conflict** badge |
| Hub row with no file and no manifest entry | prune pass | auto-deleted |

That last row fixes a real orphan problem: `ProjectSpec` is keyed `(project_id, path)`, upsert-only,
never pruned. Any Hub synced before the `specs/` → `spec/` rename (commit `968b8db`) still carries
dead `specs/…` rows.

### Also in this change — lean the spec role

`spec.md` line 31 tells the agent to read `html-spec-conventions.md`, then lines 34–44 **restate those
conventions inline**. Two copies with different lifecycles; they will drift. (The reference file is
real and installed — `cli.py` maps `aw-spec-propose → html-spec-conventions.md`.)

Split by **when information is needed**, not by topic:

```
ROLE  = always in context   → identity, boundaries, escalation, and WHICH SKILL to reach for WHEN
SKILL = loaded on demand    → the procedure, the conventions, the output format
```

The role's real job is *routing* — it is what makes the agent invoke the skill in the first place, which
a skill cannot do for itself. Expect ~91 lines → ~35.

### Open questions

- Manifest **generated** (scan + rewrite, deterministic) or **hand-maintained incrementally**?
  Generated is more reliable; hand-maintained is the only way to capture `parent`, which is semantic.
  Likely split: generate the file list, agent fills `parent` and `order`.
- Does `spec/discovery/*.md` belong in the Hub at all? It's markdown; the viewer assumes HTML.

---

## Change 2 — `add-spec-navigation`

### The unlock

`html-spec-conventions.md` **already mandates self-describing metadata** that nothing reads:

```html
<meta name="aw-spec-kind"   content="change-spec">  <!-- change-spec | roadmap | system-map | baseline -->
<meta name="aw-spec-status" content="draft">        <!-- draft | approved -->
```

Parse those (plus `<title>`) at sync time and navigation becomes a real tree with status badges, at
zero extra authoring cost.

### Decisions

- **Both** a persistent shell tree and rich in-document links. The tree answers *"where is
  everything?"* (structural, exhaustive, always correct); the system map answers *"how does this fit
  together?"* (semantic, curated, can go stale).
- **⌘K path search** — covers "I know the file, just take me there" without clicking. Highest
  value-per-effort item here.
- **The roadmap → change parent link is captured explicitly** in the manifest and made explicit in the
  skills and role, since it is semantic and not derivable from the filesystem.
- Cross-document link clicks inside the sandboxed iframe must be intercepted and `postMessage`'d to
  the shell. Precedent exists: `SpecPage.tsx` already injects an anchor-click interceptor for `#hash`
  navigation (without it the opaque-origin iframe blanks out).

---

## Change 3 — layout — **folded into Change 2**

> Not a standalone change. The recommended plan ships this inside `add-spec-navigation`, because the
> TOC hoist is simultaneously a navigation decision and a layout decision. Kept as its own section
> here only because the evidence is self-contained.

### MEASURED — the three-column squeeze

Both sidebars are exactly 220px (`Sidebar.tsx` `width: 220`; `nav.toc { width: 220px }` in the
conventions). Chat pane is 380px, hardcoded, `shrink-0`, no breakpoint.

```
│◀──────────────────── 1280px ────────────────────▶│
┌────────┬────────┬────────────────────┬───────────┐
│ Hub nav│ doc TOC│  content ~412px    │  chat 380 │
│  220   │  220   │  (32% of screen)   │           │
└────────┴────────┴────────────────────┴───────────┘
```

| Viewport | Chrome | Content |
|---|---|---|
| 1920 | 820 | 860 (capped by `max-width`) — fine |
| 1440 | 820 | 620 — tolerable |
| **1280** | 820 | **460 — broken** |
| 1024 | 820 | 204 — unusable |

Crisis zone is 1280–1440, i.e. every laptop.

### Decisions

- **Keep the chat.** The pattern is "Chat + Workbench" (split-screen), which is the documented right
  choice for co-authoring an artifact. Floating bubble and modal are both explicit anti-patterns.
- **Hoist the document TOC into the shell** — the chosen solution. The two sidebars are the same kind
  of thing at two scales ("which document" / "where in the document"), artificially split by an iframe
  boundary. Merging recovers 220px *and* removes the duplicate.
  - The conventions requirement that the TOC is "load-bearing — keep them" and that the file "renders
    offline" applies to **the file**, not to the Hub's rendering of it. The Hub injects CSS hiding
    `nav.toc` when embedding. **Zero spec documents need to change.**
  - The document already publishes its TOC in parseable form (`nav.toc` with `<a href="#…">`), and
    already runs scroll-spy internally. Needs a `postMessage` bridge both ways.
- **Hub nav → icon rail** on the Spec page (context-aware, no interaction required).
- **Chat → drawer below 1024px**, plus a collapse toggle as a preference.
- **Min-widths on both panes and persisted layout** — the current bug is a fixed *chat* minimum with
  no *spec* minimum, so the spec absorbs 100% of the squeeze.

Result: content goes from ~412px to ~640px at 1280.

### Open question

Hoisting couples the shell to the document's internal DOM (`nav.toc`). If an agent generates
different markup the shell nav degrades. Decide whether the fallback (show the in-document TOC) is
automatic or a user toggle. Same principle as Change 1: detect and surface, never fail silently.

### Sources

[AI chat layout patterns](https://medium.com/@anastasiawalia/ai-chat-layout-patterns-when-to-use-them-real-examples-d03f04a19194) ·
[split-pane min-size guidance](https://www.pkgpulse.com/guides/react-resizable-panels-vs-split-js-vs-allotment-2026) ·
[responsive breakpoints](https://www.framer.com/blog/responsive-breakpoints/) ·
[assistant placement anti-patterns](https://medium.muz.li/how-to-design-an-ai-assistant-users-actually-use-81b0fc7dc0ec) ·
[Cursor side chats](https://cursor.com/changelog/side-chat)

---

## Change 4 — `add-agent-stream-kinds`

### The problem

`SpecPage.tsx` filters agent output by **string-prefix sniffing**:

```tsx
lines.filter(line =>
  !line.content.startsWith('[watchdog]') &&
  !line.content.startsWith('[stderr]') && …)
```

But the watchdog **already knows** every block's type at parse time (`_parse_claude_stream_line`):
`thinking`, `text`, `tool_use`, `tool_result`, `result`, `error` — and destroys that knowledge by
flattening to an emoji-prefixed string (`💭`, `🔧`, `  → `). `AgentOutput` (`hub/hub/db/models.py`)
has `content: Text` and no `kind`.

Worse: each runner has its own renderer with different prefixes, so a UI filter tuned to Claude's
`🔧` silently fails for a copilot agent.

```
today     parse ──▶ flatten to string ──▶ POST ──▶ store ──▶ UI regex-guesses
proposed  parse ──▶ (kind, payload)   ──▶ POST ──▶ store ──▶ UI renders per kind
```

### Decisions

- **Normalization lives in the watchdog**, per-runner — that is where runner knowledge already sits.
  **Five parsers to update**, one per runner family: `_parse_claude_stream_line`,
  `_parse_codex_stream_line`, `_parse_opencode_stdout_line`, `_parse_copilot_stdout_line`,
  `_KimiCodeParser`. These are the **same five functions Change 6 rewrites** — see the execution
  order at the end of this document.
- **Structured `tool_use` payload**, not a pre-rendered string:
  ```jsonc
  { "kind": "tool_use", "tool": "Read",
    "input": { "file_path": "src/agentweave/cli.py", "offset": 100 },
    "summary": "Read cli.py:100" }
  ```
  Costs a JSON column; buys expandable diffs for `Edit`, file links for `Read`, grouped repeated
  calls. Chosen deliberately for the higher UI ceiling.
- **Nullable `kind`, default `text`** — old rows render as today, adapters can ship incrementally.

Everything else in this thread falls out for free once `kind` exists: the tool-call filter checkbox,
the thinking box (thinking blocks are *already captured and streamed*, just rendered as
indistinguishable mono text), collapsed tool chips, and real message bubbles.

### Thinking box / progress UX (thread 5)

Current state machine is `idle → queued → running → idle`, driven by polling `agent.status`, showing
one static string. Patterns to adopt: collapsed-by-default reasoning block that auto-collapses on
first `text` with a `Thought for 12s` summary; shimmer during `queued`; tool calls as one-line
expandable chips; elapsed timer.

**Check before building a Stop button** — whether `/agent/trigger` supports cancellation at all. If
not, a Stop button is a lie.

---

## Change 5 — `add-message-threading`

### The finding

`Question` is **a `Message` with a `blocking` flag and an inline answer**:

```
Message (db/models.py)             Question (db/models.py)
  sender ──▶ recipient               from_agent ──▶ (implicitly user)
  subject, content, type             question
  read, read_at   ◀── notifies       answer
  task_id, session_id                answered, answered_at
                                     blocking  ◀── the only real addition
```

It is a separate table only because the answer was modelled as a *column* instead of *another
message*. That is exactly why one notifies and one just sits there — `Message` has `read`/`read_at`
driving unread state; `Question` has a parallel lifecycle.

**The missing primitive: `Message` has no `reply_to` or `thread_id`.** Every message is an orphan.
This is why nothing is traceable today — not user↔agent, not A2A.

### Decisions

- Collapse `Question` into `Message(type='question', blocking=true)`; the answer becomes a reply in
  the thread. One inbox, one unread count, one notification path.
- Add a nullable self-referential FK for threading. Threads span user↔agent **and** agent↔agent —
  that is the whole value, since it is the only way to reconstruct why a decision was made.
- **Reply channel is a framework invariant, not a user-facing config.** Route by trigger origin:
  chat-originated → respond in stream; task/schedule/agent-originated → `send_message`. Carve-out:
  durable or cross-agent facts always get a Message regardless. Lives in the protocol/role guide, not
  in settings — configuration invites drift and this should be invariant.

Note: `agent_chat.py` currently merges `AgentOutput` and `Message` and uses time-window heuristics
with named tiers to attribute untagged messages to sessions. That guesswork exists because this
decision was never modelled; threading removes the need for it.

**This is the highest-value change on the list** — the only one that improves every surface rather
than one tab. It touches `Message`, `Question`, MCP tools (`ask_user`, `send_message`), the CLI
messaging layer, the Questions panel, the Messages feed, and A2A. Keep it separate from spec work.

**Highest value but scheduled late** — see the execution order. It is a schema migration with the
widest blast radius on the list, so it wants a clear runway rather than a slot between two in-flight
changes. It is fully independent, so it can be pulled forward at any time if traceability pain
becomes acute; nothing else reorders.

---

## Change 6 — `fix-context-tracking-all-runners`

### MEASURED — the full runner matrix

Every row below was produced by running the CLI, except copilot (docs + user confirmation).

| Runner | Channel | Fields | `input` incl. cache? | Scope |
|---|---|---|---|---|
| claude | stream `result.usage` | `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` | ❌ no | per-turn |
| codex | stream `turn.completed.usage` | `input_tokens`, `cached_input_tokens` | ✅ yes | ⚠️ **cumulative** |
| opencode | stream `step_finish.tokens` | `total`, `input`, `output`, `cache{}` | n/a — explicit `total` | per-step |
| copilot | **OTEL file**, env-gated | `inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens` | ❌ no | per-call |
| kimi v0.x | **`wire.jsonl`** in session dir | `inputOther`, `inputCacheRead`, `inputCacheCreation` + `maxTokens` | ❌ no | per-turn |

Three naming conventions. Two answers to "does input include cache". One cumulative outlier. Two
file-based channels vs three stream-based. **No runner where the data is genuinely unavailable.**

### Confirmed bugs

**Claude — under-reports catastrophically.** MEASURED on a trivial prompt:

```
input_tokens            =      2
cache_read_input_tokens = 25,875   ← dropped by the parser
TRUE context            = 25,877
watchdog computes 2 / 200,000 = 0%   (true ≈ 13%)
```

`_parse_claude_stream_line` extracts only `input_tokens` and `output_tokens`.

**Codex — over-reports cumulatively.** MEASURED across three resumed turns in one thread:

```
turn 1:  input = 18,860        →  14% of 128k
turn 2:  input = 37,736  (×2)  →  29%
turn 3:  input = 56,628  (×3)  →  44%
```

It sums every turn's input rather than reporting current context. Real context barely moved
(~18.9k). A working session pins at 100% within ~7 turns. Fix is a delta:
`current_cumulative − previous_cumulative`, which requires keeping the prior value per thread.

**Codex — stale limits table.** `CODEX_MODEL_CONTEXT_LIMITS` holds only
`{"gpt-5.5": 272000, "gpt-4o": 128000}` and uses **exact-match** `.get(model, 128000)`, unlike
`_get_context_limit` which does substring matching. Any `gpt-5-codex` / `gpt-5.1-codex` / `o3`
silently falls to 128k, compounding the over-report.

**OpenCode — data present, ignored.** MEASURED: `step_finish` carries
`tokens:{total:18491, input:16559, output:26, reasoning:0, cache:{…}}`. The parser returns
`usage_data=None`.

**Copilot — reading the wrong event.** The parser handles `result` and takes only `premiumRequests`
(a billing counter). Real usage lives on `assistant.usage`. User confirmed the CLI stream carries
only `outputTokens`; the full accounting requires OTEL file export, which is **off by default** and
must be enabled *before* the session starts (not retroactive):

```bash
COPILOT_OTEL_ENABLED=true
COPILOT_OTEL_EXPORTER_TYPE=file
COPILOT_OTEL_FILE_EXPORTER_PATH=<path>.jsonl
```

The watchdog spawns the process, so it controls this environment.

**Kimi v0.x — nothing on stdout, everything on disk.** MEASURED: headless output is only
`{"role":"assistant","content":"ok"}` plus a resume hint. But
`~/.kimi-code/sessions/<workspace>/<session_id>/agents/main/wire.jsonl` contains:

```jsonc
{"usage": {"inputOther": 18330, "output": 21,
           "inputCacheRead": 10496, "inputCacheCreation": 0}, "usageScope": "turn"}
{"llm.request": {"maxTokens": 262144}}
```

True context = 18,330 + 10,496 = 28,826 / 262,144 = **11%**. Correct and per-turn.
Bonus: `maxTokens` comes from the runner, so no hardcoded limits table is needed.
[Official docs](https://moonshotai.github.io/kimi-code/en/reference/kimi-command.html) confirm
nothing is exposed via headless flags — this file is the only route, and it is **undocumented**,
which is a durability risk worth noting.

### Writer schema divergence

There are **three** context-usage writers in `watchdog.py`, not two, and they disagree on schema.
All three write the *same* file (`.agentweave/shared/context_usage/<agent>.json`):

| Writer (`watchdog.py`) | Used by | Token keys emitted |
|---|---|---|
| `_write_context_usage` (1965) | claude, claude_proxy, copilot, opencode | `input_tokens`, `context_limit` |
| `_write_codex_context_usage` (2009) | codex | `tokens_used`, `tokens_limit` (+ cached/output) |
| `_write_context_usage_from_wire` (2311) | kimi wire mode | `input_tokens`, `context_limit` |

`hub/hub/api/v1/agents.py` `post_context_usage` takes `body: dict` and passes it through
verbatim (`payload = {**body, "agent": name}`) — no validation, no normalization. The UI's
`ContextUsage` interface (`hub/ui/src/api/agents.ts:31-42`) declares **only** `tokens_used` and
`tokens_limit`. **So codex is the only runner whose token counts reach the UI at all**; every
other runner's arrive as `undefined`. This is a better explanation for the earlier report ("it
always shows 100% when using codex") than the cumulative-token bug alone.

**Simplification, given "kimi 1.x is not supported":** `is_kimi_code = is_kimi and
"--output-format" in cmd` (`watchdog.py:2783`) is **always true** for kimi, so the guard
`is_kimi and not is_wire_mode and not is_kimi_code` never passes — `_KIMI_RESUME_RE` and
`_extract_kimi_session_from_stdout` are **unreachable dead code**. `is_wire_mode` is likewise
unreachable, making `_write_context_usage_from_wire` dead too. Deleting them is a real
simplification; it probably belongs inside this change rather than as a separate cleanup, since
this change has to reconcile the three writers anyway.

**Reframing #4/#6 as one architectural defect:** the watchdog knows something precise at parse
time and destroys it at a boundary. #4 loses the block kind to emoji-string flattening; #6 loses
the usage shape to three disagreeing writers. This argues for two changes sharing one design doc
that settles the normalization boundary once, rather than either a single merged change or two
fully independent ones.

### Design implications

1. **Normalize to `(context_tokens, limit_tokens)` at the adapter boundary.** Nothing downstream
   touches raw fields. A naive "add the cache fields everywhere" fix would double-count codex by ~59%.
2. **Prefer runner-reported limits** (kimi's `maxTokens`) over hardcoded tables.
3. **Two ingestion channels** — stdout stream and watched file. Copilot needs env vars set at spawn;
   kimi needs a session-dir path resolved from the session id.
4. **Scope normalization is mandatory** — cumulative (codex) vs per-turn (everyone else) is the
   highest-risk conversion.
5. **`unsupported` must be a first-class state.** Showing `0%` for a runner that cannot measure is
   exactly the current Claude failure.
6. `agentweave doctor` should verify copilot's OTEL env and that each runner's source is producing data.

The existence of a forked `_write_codex_context_usage` alongside `_write_context_usage` is evidence
the abstraction already broke once. This is a **contract + adapters** change, not four parser patches.

### UNVERIFIED — check during implementation

- Copilot's OTEL field names (from docs, not run locally).
- Kimi v1.x wire mode's `context_usage` ratio path (`watchdog.py` ~line 1364) — no v1.x binary available.
- The Hub path end-to-end: `_post_context_usage_to_hub` → storage → UI. The archived investigation
  left arrows C–G untested, and codex was the only runner producing plausible numbers — which we now
  know were wrong.

### Prior art

`docs/archive/autonomous-dev-loop/index.md` and
`openspec/changes/archive/2026-07-28-investigate-blockers/findings/` (732 lines) hold the earlier
investigation, including two further confirmed defects: the OpenCode parser bug above, and
`load_json` failing on a UTF-8 BOM (`src/agentweave/utils.py`) which makes `_check_context_usage`
read `None or {}` as "no data" and silently skip the warning.

---

## Change 7 — `add-session-lifecycle`

**Blocked on Change 6.** "Suggest a handoff when context is high" needs a percentage you can trust.

`aw-checkpoint` (35 lines) already covers the **write** side well — session intent, files modified,
decisions with rationale, blockers, next steps, verification commands, saved to
`.agentweave/shared/checkpoints/`.

| Piece | State |
|---|---|
| Write a checkpoint | ✅ `aw-checkpoint` |
| Read one back on resume | ❌ no `aw-resume` exists |
| Know *when* to checkpoint | ❌ depends on Change 6 |
| See/manage sessions in the Hub | ❌ Agents page has a raw id dropdown; Spec page has nothing |

Shape: `aw-checkpoint` + a new `aw-resume` that hydrates from the latest checkpoint, plus Hub UI for
session lifecycle (list, name, resume, retire). The user's personal `handoff`/`resume` skills are a
good template; the aw- versions differ in being multi-agent and Hub-visible.

Related: Change 0 makes the Spec tab resume forever, so sessions only grow. The deliberate
"new session" control added there is the manual escape until this change lands.

---

## Dependency graph

```
  0. spec-chat-session-resume     ✅ proposed · independent · ship first

  1. spec-manifest  ──────────▶  2. spec-navigation (incl. layout / Change 3)

  4. agent-stream-kinds       ┐  same five per-runner parsers — schedule adjacent
  6. context-tracking         ┘
                              └──▶  7. session-lifecycle

  5. message-threading           independent · highest value · widest blast radius
```

---

## Execution order

```
1.  #0  spec-chat-session-resume    one line · ship today · unblocks daily use
         │
2.  #1  spec-manifest               stops ACTIVE silent loss · unblocks #2
         │
3.  #4  agent-stream-kinds     ┐    SAME FIVE PARSERS —
4.  #6  context-tracking       ┘    schedule adjacent, do not separate
         │
5.  #2  spec-navigation + layout    the payoff of #1
         │
6.  #5  message-threading           biggest blast radius · needs runway
         │
7.  #7  session-lifecycle           blocked on #6
```

### Why this order

- **#0 first** is not a judgment call. It is one line, and spec context is lost on every message
  until it lands.
- **#1 second** because it is the only *actively worsening* item. The improved skills tell agents to
  write `spec/roadmaps/*.html` and `spec/system-map.html`; those never reach the Hub and never error.
  Every day the spec agent runs, more work silently fails to sync.
- **#4 and #6 adjacent** because they rewrite the *same five per-runner parsers* for claude, codex,
  and opencode. Splitting them means opening those functions twice and re-running verification
  twice for those three runners. **Correction:** copilot and kimi are not covered by this
  parser-adjacency argument — #6 needs an entirely new *ingestion channel* for them (copilot: OTEL
  file export, env vars set at spawn; kimi: `wire.jsonl` in the session dir), not a parser edit. The
  adjacency case is strongest for claude/codex/opencode and weaker, but still real, for the rest —
  see "Writer schema divergence" above. If only one can be done, do #4 first — legible agent output
  is a force multiplier for supervising everything below it.
- **#2 fifth**, once #1 gives it a manifest to render.
- **#5 sixth** despite being the highest-value change. Schema migration across `Message`, `Question`,
  MCP tools, the CLI messaging layer, two UI surfaces and A2A. It wants a clear runway.
- **#7 last** — genuinely blocked. A handoff prompt driven by an untrustworthy context percentage is
  worse than no prompt at all.

### Legitimate alternative

If traceability pain is acute — you cannot reconstruct why an agent decided something — pull **#5 to
position 3**. It is fully independent, so nothing else reorders. The cost is running the largest
migration before the smaller wins land.

---

## Proposal cadence

**Decision: write proposals just-in-time, one or two ahead of implementation — not all at once.**

Nine changes were archived on 2026-07-28, five of them abandoned proposals written far ahead of the
work. A proposal drifts from the code the moment it is written, and a board full of untouched changes
teaches you to ignore the board. This document is the durable record; proposals are scoped when the
work is picked up.

Several open questions must be answered *at* proposal time rather than now, because answering them
cold is guessing:

| Change | Question to settle before proposing |
|---|---|
| #1 | Manifest generated-and-scanned, or hand-maintained incrementally? |
| #2 | Is the TOC-hoist fallback automatic or a user toggle? |
| #4 | How many `kind` values; does `result` / `error` need its own? |
| #5 | Does `blocking` stay a column, or become a message type? |
| #6 | Does codex delta-tracking live in the parser or the writer? |

---

## Notes for a fresh session

- `openspec/explorations/` was created for this document; there was no prior convention for it. It
  sits outside `openspec/changes/`, so it does **not** appear in `openspec list`.
- Board state as of writing: `fix-spec-chat-session-resume 0/16` is the only active change.
- The raw CLI captures behind the MEASURED numbers were written to a session scratchpad and are
  **not** durable. The figures quoted in this document are the record. Re-running them costs real
  tokens against claude, codex, opencode and kimi.
- `openspec/specs/` holds 7 capabilities after today's sync. None of them cover the work above.
