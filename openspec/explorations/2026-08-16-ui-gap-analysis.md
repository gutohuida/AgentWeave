# Exploration: UI gap analysis against popular agent harnesses

**Status:** survey only — no proposal, design, or tasks yet. This is the AUTHOR-facing evidence base
for Q7's later spec round; per the queue item's own instruction ("Investigate everything before
implementing"), nothing here is a decision.

**Scope note on the operator's framing.** The operator's own example was T3's work-execution
detail ("file edit, bash, things like that ... a different font and a icon which is really nice").
They explicitly asked to go wider than that one example ("go beyond compare t3 and other tools...
Is there any functionality in the most popular harnesses that we lack?"). This document therefore
covers two kinds of evidence: (1) AgentWeave's own UI, read directly — `hub/ui/src/components/` —
and (2) public documentation and code for Cursor, Cline, Windsurf/Cascade, Claude Code's own CLI
and extension, T3 Chat, and OpenHands/Devin, gathered via `WebSearch` on 2026-08-16. Search results
are secondary sources (guides, comparison sites), not first-party docs read directly, except where
noted — flagged per finding so the later spec round can weigh confidence accordingly.

## 1. What AgentWeave's UI already does (read directly, not inferred)

Before listing gaps, the baseline it is being measured against, because several things a naive
comparison would flag as "missing" already exist:

- **Per-agent color identity** carried consistently across the timeline, activity feed, and event
  rows (`agentColorVars`, used in `AgentTimeline.tsx`, `EventRow.tsx`, `ActivityLog.tsx`).
- **A structured turn timeline**, not a raw log: `AgentTimeline.tsx` groups entries into turns,
  folds/unfolds them, and already separates "work" (tool calls) from message content into a
  collapsible `WorkBlockDisclosure` — this is the surface the operator's T3 comparison is about.
  Read closely below (finding 1) because the disclosure exists but is coarser than what it's
  compared against.
- **Operator-in-the-loop banners**: checkpoint-due, checkpoint-final, permission requests, unasked
  questions, hop-budget-suspended notices — all surfaced above the composer in a fixed order
  (`AgentOutputPanel.tsx:305-467`), which is more structured state-surfacing than a plain chat log.
- **A token/cost accounting surface already exists**: `AccountingPanel.tsx` +
  `useAccounting`/`useUpdateTokenBudget` — project-level and (per `PreferredDisplay`) either a
  rate-limit allowance or a USD API-equivalent estimate, with a settable budget that pauses
  autonomous turns. This is close to what the "token-monitor" / "TokenTelemetry" class of
  third-party tools bolts onto Claude Code, Codex, Cursor, etc. (see finding 6 for what it does not
  yet do: show cost at conversation/turn scope, not just project scope).
- **Live SSE activity feed** (`ActivityLog.tsx`) with severity filters and a project scope guard.
- **A spec-document-aware task board** (`TasksBoard.tsx`, `TaskDetailDrawer.tsx`) — built this same
  run under Q4-spec-ux-fixes, already Jira-drawer-shaped per the operator's own comparison there.

## 2. Gap list, ranked by user value (not ease of build)

Each item: evidence, comparison, rough cost, icon-system note.

### Gap 1 — Agent output renders no markdown at all (HIGHEST VALUE, evidenced directly)

**Evidence, read directly.** `hub/ui/package.json` has no markdown-rendering dependency at all —
no `react-markdown`, `markdown-it`, `marked`, `remark`, or any syntax-highlighter (`highlight.js`,
`prismjs`, `shiki`). Grepped for `dangerouslySetInnerHTML` across `hub/ui/src`: zero hits. Every
message in `AgentTimeline.tsx`'s `MessageEntry` (operator input, agent output, peer traffic) and
every work-row label in `WorkRow` renders `entry.content` through
`className="whitespace-pre-wrap"` — literal text. An agent response containing a fenced code block,
a bulleted list, a bold word, or a link renders with the literal backticks, `-`, `**`, and `[]()`
syntax visible, un-highlighted, un-clickable. (The Hub *does* have a server-side markdown renderer —
`hub/hub/spec_render.py`, built under Q4-spec-ux-fixes this run — but that renders spec *documents*
only; the live conversation surface, the one thing every session touches, has none.)

**Comparison.** T3 Chat's own selling points include "markdown/code/math formatting" as a named
core feature. Cline's diffs are described as "syntax-highlighted... alongside your file tree and
terminal." Claude Code's CLI and extension render fenced code with syntax highlighting natively.
This is not a nice-to-have feature some tools have — it's baseline table stakes every compared tool
does that AgentWeave currently does not, for every single message.

**Cost, rough.** A markdown renderer (e.g. `react-markdown` + `rehype-highlight` or `shiki`) applied
inside `MessageEntry`'s two text-rendering branches — bounded, well-scoped component swap, no new
data flow. The existing `whitespace-pre-wrap` styling gives a fallback for anything the renderer
doesn't recognize. Medium-low cost, contained to a handful of files
(`AgentTimeline.tsx`, `WorkRow`, possibly `AgentActivityTab.tsx`'s `content` strings).

**Icon-system note.** None needed for this gap directly, though a syntax-highlighting theme choice
would need to respect the existing CSS variable theming (light/dark) rather than shipping its own
palette — same constraint Q4's finding 2 already established for the spec document.

### Gap 2 — Tool-call detail has no type-specific formatting, icon, or diff view (the operator's named example)

**Evidence, read directly.** `AgentTimeline.tsx`'s `WorkBlockDisclosure`/`WorkRow` (lines 260-339)
groups tool calls under one generic "Work · N steps · Xs" summary with a single fold icon
(`expand_more`). Inside, every row uses the *same* icon-less, type-blind rendering: the label is
just `entry.content || 'Tool call'` in monospace, with a `· completed`/`· failed`/`· awaiting result`
suffix and, when expanded, the raw tool input/output concatenated as plain text
(`entry.content` + `paired.content`). There is no per-tool-type icon (a file edit, a bash execution,
and a search all render identically), no file-path-specific treatment, and — combined with Gap 1 —
no diff rendering for a file edit: an edit tool's before/after shows as two blobs of raw JSON-ish
text, not a diff.

**Comparison.** This is a closer, structural read of the operator's own comparison. T3 shows tool
execution "with a different font and a icon which is really nice." Cline goes further: "AI changes
appear as syntax-highlighted diffs in your editor... Every file change appears as a diff for
approval," with checkpoints per tool call. Cursor's Composer review is per-file diffs, accept/reject
per file. AgentWeave already has the right *structural* idea (grouped, foldable work blocks,
individually expandable rows) — the gap is that every tool type look identical and a file edit
carries no diff.

**Cost, rough.** Two independent pieces, gradeable separately: (a) per-tool-type icon/label — a
lookup from a known tool name (`Read`, `Edit`, `Bash`, `Grep`, etc. — the surface already carries
`entry.output_kind` and presumably a tool name in its payload/content) to an `Icon` name and a short
label, low cost, contained to `WorkRow`. (b) A real diff view for file-edit tools specifically —
higher cost: needs a diff-rendering component (or a lightweight diff library) and depends on the
edit tool's payload actually carrying old/new content in a parseable shape, which needs checking
against what each runner (Claude, Codex) actually emits before scoping.

**Icon-system note.** Must use the existing `Icon` (lucide-react) component only — CLAUDE.md forbids
a second icon system, and lucide already carries file/terminal/search-shaped icons, so this should
not need a new dependency.

### Gap 3 — No global command palette (cmd+k)

**Evidence, read directly.** Grepped `hub/ui/src` for `cmdk`, "command palette", and global
`keydown` handlers: the only keyboard handling found is local — dialog-focus trapping
(`useDialogFocus.ts`), Escape-to-close on specific panels (`SpecPage.tsx`, `ConversationView.tsx`,
`AgentQuestionCard.tsx`). Nothing binds a global shortcut to open a searchable command/navigation
surface.

**Comparison.** T3 Chat lists "keyboard shortcuts, hotkeys" as a named feature. Cursor and Claude
Code's extension both ship a command-palette-style surface for cross-cutting actions. This is a
common, low-controversy pattern across the surveyed tools (secondary-source evidence — comparison
guides, not first-party docs read directly, so weight this one down slightly versus Gaps 1-2).

**Cost, rough.** Self-contained: a new component (`cmdk` npm package is the common choice; would be
a new dependency, unlike Gap 1/2 which can mostly reuse what's there) plus wiring a handful of
existing navigation actions (switch project, open agent, open spec document, open task) into it.
Medium cost, but isolated — does not touch existing rendering paths.

**Icon-system note.** Command entries would use `Icon` per row; no conflict.

### Gap 4 — No persistent, chat-surfaced plan/todo list for long-running work

**Evidence, read directly.** AgentWeave has a task board (`TasksBoard.tsx`) that is a separate
surface from the conversation, populated from spec requirements/tickets. It does not have anything
resembling a live, in-conversation running plan the agent updates turn-by-turn while working
(distinct from the *task* concept, which is project-scoped and operator/spec-driven, not
per-conversation).

**Comparison.** Windsurf's Cascade "autonomously creates to-do lists when appropriate, directly in
the chat, to scope out long-running tasks," paired with a `plan.md` file, and by Wave 12 this
became automatic. Claude Code's CLI has `TodoWrite` for the same purpose — a live, visible plan
inside the session, not a separate board.

**Cost, rough.** This is the one gap that is genuinely architectural rather than a rendering
change: it would need either a new turn-scoped data model (a "current plan" attached to a
conversation, updated by tool calls) or reusing the existing task system in a way it wasn't built
for. Higher cost, and worth its own design discussion rather than a quick UI fix — flagged as
architecturally the most expensive item on this list, which is why it ranks below Gaps 1-3 despite
comparable user value; cost belongs in the ranking discussion even though the list is value-first.

**Icon-system note.** N/A until design exists.

### Gap 5 — No per-conversation or per-turn cost/token display

**Evidence, read directly.** `AccountingPanel.tsx` (section 1 above) shows project-level totals and
a project-level budget. Nothing in `AgentOutputPanel.tsx` or `AgentTimeline.tsx` shows what a
specific turn or the open conversation cost — the operator has no way to see "this turn used
40K tokens" without leaving the conversation for the Accounting settings surface.

**Comparison.** The token-tracking tools found in the general ecosystem search (token-monitor,
TokenTelemetry, Token Tracker) all foreground *session*-level and even *per-prompt* cost, not just
account/project totals — several show "tokens per prompt expandable to each reply's exact token
split." These are third-party add-ons bolted onto tools that don't show this natively, which is
itself a signal: the tools people reach for an external tracker on are ones whose own UI doesn't
show it close enough to where the work happens.

**Cost, rough.** Likely the cheapest gap on this list if the accounting API already returns
per-turn or per-conversation figures (unconfirmed — would need checking `hub/hub/api/v1/*` for
what `useAccounting`'s backing route actually scopes its numbers to before estimating further).
If the data already exists at finer grain than the UI surfaces, this is a pure display change.

**Icon-system note.** N/A — text/number display.

### Gap 6 — No cross-agent "all runs at a glance" view

**Evidence, read directly.** The agent roster (`AgentsPage.tsx`/`AgentCard.tsx`, not fully read this
pass) lists agents with status, but there is no dedicated grid/dashboard view of concurrently
running agents' live activity side by side — the operator moves between agents one conversation at
a time.

**Comparison.** Cursor 2.0's "Mission Control" is described as "a grid-view interface similar to
macOS Exposé for your AI agents," specifically for managing multiple concurrent agent runs. This
maps closely to AgentWeave's actual multi-agent premise (`CLAUDE.md`: "one Hub instance owns a
collection of projects," multiple agents), arguably more relevant to AgentWeave's shape than to a
single-agent editor tool like Cursor's base case.

**Cost, rough.** Medium — mostly composition of data AgentWeave already has (agent roster + live
SSE status), built as a new page/route rather than new data plumbing. Lower risk than Gap 1/2
because it's additive rather than touching existing render paths.

**Icon-system note.** Reuses `Icon` + existing `AgentCard`-style status treatment.

### Gap 7 (secondary-source, lower confidence) — Spend-limit / autonomy dial in the composer itself

**Evidence.** Secondary sources only — not read against AgentWeave's own permission code this pass.
Cline is described as offering "Spend limits, YOLO mode, and Lazy Teammate Mode" to "tune the
safety/autonomy trade-off" per-run, from inside the interaction surface rather than a settings page.
AgentWeave's `PERMISSION_MODE_CONTROL` composer pill (seen in `AgentOutputPanel.tsx:266-268`,
`ComposerModelControls.tsx` not read this pass) already exposes a permission-mode choice per
conversation — this may already partially cover this gap. Flagged as needing a closer read of
`Composer.tsx`/`ComposerModelControls.tsx` against what Cline actually exposes before this is a real
finding rather than a maybe.

## 3. What this exploration deliberately does not do

- No proposal, design, or tasks — per Q7's own `detail`, survey first.
- No implementation cost estimate below "rough" — several gaps (2b's diff view, 4's plan model, 5's
  data grain) need a closer read of specific files/APIs before a real estimate is possible, named
  above per-gap rather than glossed over.
- No ranking claim beyond what the evidence supports — Gap 7 is explicitly flagged lower-confidence
  because it rests on secondary sources describing a competitor feature AgentWeave's own composer
  was not checked against.

## Sources (web research, 2026-08-16)

- [Cursor 2026: Composer, Agent Mode, MCP & Background Agent](https://www.deployhq.com/guides/cursor)
- [Cursor AI 2026: The Complete Guide to the AI-Native IDE](https://dev.to/sahilkhurana/cursor-ai-2026-the-complete-guide-to-the-ai-native-ide-3n4h)
- [Cline IDE - The Coding Agent for VS Code, JetBrains, Cursor, and Windsurf](https://cline.bot/ide)
- [Cline for VS Code: Free AI Coding Agent — 2026 Setup Guide](https://www.deployhq.com/guides/cline)
- [Cline Review: Open-Source AI Coding Agent](https://aiidelist.com/ide/cline)
- [Windsurf Wave 10 Planning Mode Guide](https://baeseokjae.github.io/posts/windsurf-wave-10-guide-2026/)
- [Windsurf 2 Deep Dive: Cascade Agents + Workflows 2026](https://www.digitalapplied.com/blog/windsurf-2-deep-dive-cascade-agents-flows-2026)
- [Devin Desktop - Cascade docs](https://docs.windsurf.com/windsurf/cascade/cascade)
- [A developer's Claude Code CLI reference (2026 guide)](https://www.eesel.ai/blog/claude-code-cli-reference)
- [Claude Code Guide 2026: 25 Features with Examples + Demo](https://www.marktechpost.com/2026/06/14/claude-code-guide-2026-25-features-with-examples-demo/)
- [T3 Chat review](https://best-ai.org/tool/t3-chat)
- [T3 Chat — Grokipedia](https://grokipedia.com/page/T3_Chat)
- [Compare Devin vs. OpenHands in 2026](https://slashdot.org/software/comparison/Devin-vs-OpenHands/)
- [Best AI Agent Multiplexers Compared (2026)](https://amux.io/guides/best-ai-agent-multiplexers-2026/)
- [token-monitor (GitHub)](https://github.com/Javis603/token-monitor)
- [tokentelemetry (GitHub)](https://github.com/VasiHemanth/tokentelemetry)
- [Token Tracker](https://www.tokentracker.cc/)
