# Proposal — Conversation formatting and quick navigation

## Why

Q7's survey (`openspec/explorations/2026-08-16-ui-gap-analysis.md`, 2026-08-16) read AgentWeave's
own conversation-rendering UI directly and researched Cursor, Cline, Windsurf/Cascade, Claude Code,
T3 Chat, and OpenHands/Devin. Two findings came straight from the code, not from comparison:

1. `hub/ui` renders **zero markdown** anywhere in the live conversation surface. No
   `react-markdown`/`marked`/`remark` dependency, no `dangerouslySetInnerHTML` — every operator
   message, agent message, and tool-call label goes through `whitespace-pre-wrap` as literal text.
   A fenced code block, a bulleted list, or a bold word renders with its raw syntax characters
   visible. Every surveyed tool treats this as baseline, not a feature.
2. The tool-call disclosure the operator explicitly compared to T3
   (`AgentTimeline.tsx`'s `WorkBlockDisclosure`/`WorkRow`) is structurally sound — grouped, foldable,
   individually expandable — but every tool type renders identically: one fold icon, no per-tool
   icon, and (combined with finding 1) no diff view for a file edit, just two blobs of raw
   JSON-shaped text.

A third, lower-cost gap is common and low-controversy across the surveyed tools and absent here:
no global command palette (Cmd/Ctrl+K) for cross-cutting navigation.

## What changes

Three additions to the conversation and shell surfaces, in `hub/ui` only — no backend schema
change, no new backend endpoint:

1. **Markdown rendering** for message-level conversation entries (operator input, agent text
   output, peer traffic) — fenced code, lists, emphasis, links, tables render as such. Raw
   fallback is unaffected for anything a renderer does not recognize (same visual result as today).
2. **Tool-call type formatting**: `WorkRow` looks up the tool name already carried in
   `payload.tool` and renders a per-tool icon and short label from the existing `Icon`
   (lucide-react) component, instead of one generic label for every tool. For the file-editing
   tools whose `payload.input` carries an old/new string pair, the expanded row renders a real
   diff instead of two raw text blobs.
3. **A command palette** (Cmd/Ctrl+K): a searchable overlay for switching conversation, opening an
   agent, opening a spec document, and opening a task, scoped to the current project.

## Out of scope, with reasons (per the survey's own ranking)

- **In-chat plan/todo list** (survey gap 4). Flagged in the survey itself as architecturally the
  most expensive item on the list — it needs a new turn-scoped data model, not a rendering change.
  Belongs in its own exploration and its own spec round, not folded in here where it would
  dominate review effort against two well-evidenced, low-risk changes.
- **Per-turn/per-conversation cost display** (survey gap 5). Not re-checked this pass against what
  `hub/hub/api/v1/accounting.py` actually scopes its numbers to — the survey flagged this as
  needing that check before estimating cost, and it was not done here for time. Left for a future
  item once that's confirmed cheap.
- **Cross-agent "all runs at a glance" grid** (survey gap 6). Medium cost, additive, not touching
  any surface this change touches — no reason to couple it here, and no evidence pass has scoped it.
- **Composer autonomy/spend-limit dial** (survey gap 7) — **resolved during this AUTHOR pass, not
  deferred**: checked against `ComposerModelControls.tsx`/`modelCatalog.ts` as the survey asked.
  AgentWeave already has a per-conversation `permission_mode` control
  (`PERMISSION_MODE_CONTROL`, `hub/ui/src/api/modelCatalog.ts:56`) rendered directly in the
  composer via the same `EnumControlPill` every other per-turn control uses — an in-composer
  autonomy dial, which is what Cline's comparison was actually asking for. There is no per-run
  spend-limit control, but that is a narrower, unconfirmed gap, not the finding the survey flagged
  as needing a look. Not a real gap; no task in this change addresses it.

## Impact

- Capability `agent-conversation-workspace`: two new requirements (markdown rendering; tool-call
  type/diff formatting), both additive to the existing "Conversation disclosures respond to the
  pointer" requirement's territory.
- Capability `hub-workspace-shell`: one new requirement (command palette).
- `hub/ui/package.json`: three new dependencies — `react-markdown` + `remark-gfm` + `remark-breaks`
  (markdown), `diff` (jsdiff, for the edit-tool diff view), `cmdk` (command palette). No new
  backend dependency. See `design.md` D1–D3 for why each was chosen over the alternatives
  considered.
- No database migration, no API route change, no change to `payload` shape or to what any runner
  sends — this reads data the Hub already records and never rendered.
