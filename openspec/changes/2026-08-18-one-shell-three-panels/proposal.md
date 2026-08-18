# One shell, three panels

## Why

**The right side of the screen has exactly one tenant, and the operator asked for three.**
`openspec/explorations/2026-08-18-the-side-panel-family.md`, written this session against code read
live (not inferred from the loop change's own text), measured it directly:
`hub/ui/src/components/agents/ConversationView.tsx` hosts `SpecDocumentPanel` and nothing else —
no tab strip, no plus button, no second slot. `SpecDocumentPanel` was never asked to coexist with
anything, so nothing in this codebase has ever had to answer "which panel is open," only "is *the*
panel open."

The operator's own words, in full:

> "We should have a button that opens the side panel (just like t3 does and other harnesses as
> well). On top we can click a plus sign and open something else... We could start with a file
> viewer/navigation of the repo of the project. A loop tab with loop information (with some loop
> animations and icons)... and the spec that we already have. This could solve also our explore
> button problem."

Three things are being asked for at once: a **container** (tabs, a plus affordance, resize), a
**second tenant** (a loop status screen — the governance half of `2026-08-18-a-loop-writes-its-own-
queue`, which produces the data this change's loop tab is the first UI consumer of), and a **third
tenant** (a file browser — new, and the first UI in this codebase that reads a project file's
content rather than only its path). The existing spec document panel is not being rewritten; it is
being asked to stop being the only thing that can live on the right.

**Why generalize rather than bolt a second mechanism beside the first.** Costed in full in the
exploration's §2: a second, independent tab-and-resize mechanism duplicates the breakpoint math
`ConversationView.tsx:34-35`'s own comment already names as a past mistake (the three-column
workspace), gives the operator two different things "open on the right" can mean, and — the sharper
objection — contradicts the operator's own framing. "Just like T3 does" names a reference with
**one** right panel and **one** plus button, not a spec panel with a second, unrelated panel beside
it. Generalizing is real, non-trivial work (`ConversationView.tsx`'s panel-hosting block has to
become shell-plus-registry rather than spec-specific) but it is the only shape that matches what was
asked for.

**Why this is governance, not decoration.** The operator framed the whole loop feature this way,
recorded in the loop change's own proposal: a loop an agent creates for itself is only acceptable if
the operator can see what it is doing. The loop tab is that visibility surface. It is not being
added because a status screen is a nice feature; it is the other half of a feature this repository
has already agreed to ship.

## What Changes

- **A panel shell replaces the spec-only hosting block in `ConversationView.tsx`.** The shell owns
  the tab strip, the plus affordance, and the resize/overlay breakpoint math that today serves only
  the spec panel. `SpecDocumentPanel` becomes the shell's `spec` tab content, unchanged internally —
  every feature it has today (breadcrumb, archived marker, phase/coverage bars, proposals panel, the
  sandboxed `SpecFrame` bridge, the outline rail) keeps working exactly as it does.
- **A small, literal descriptor array, not a plugin system.** Three entries — `spec`, `loop`,
  `files` — each declaring `id`, `title`, `icon`, and `singleton: true`. Reopening an already-open
  singleton refocuses it rather than creating a second instance; there is nothing a second `loop` tab
  could mean when a loop tab always shows the same job's summary.
- **A loop tab**, surfacing what `hub/hub/api/v1/jobs.py`'s `_batch_loop_summaries` already computes
  for the Jobs page's `LoopBlock` — purpose, queue counts, the claimed item, open questions, stop
  reason — on a conversation-scoped surface the Jobs page is not. Adds one genuinely new fact
  (whether an agent is running *right now*, for this loop's job) and consumes one event the loop
  change already produces but does not surface (`loop_queue_exhausted`).
- **A file tab**, backed by a new content-read endpoint. `GET /api/v1/workspace/paths` already lists
  every path a project's workspace contains (feeding the composer's `@path` trigger); nothing today
  returns a file's *bytes*. The new endpoint's allowlist is defined as "exactly what
  `list_workspace_paths` would return" — no second, independently-reasoned path-safety check — with
  a size bound reusing the Hub's existing 1 MiB inbound-body precedent rather than inventing a new
  number, and a binary/text decision using the same first-bytes-null-byte heuristic git itself uses
  to decide whether to diff a file as text.
- **Persistence splits by what is actually per-conversation.** Panel width stays the single global
  preference `specPreferences.ts` already persists — extended with two more fields, not replaced.
  Which panel is active, and whether the shell is open at all, becomes conversation-scoped
  destination state, the same ownership `ConversationView`'s existing `document` prop already has —
  a loop tab pinned open while looking at an unrelated conversation would be stale, misleading state,
  the same objection T3's own per-thread persistence answers.
- **The explore button is untouched.** Per `DEC-explore-button`, the panel is designed so it *can*
  subsume `ComposerSpecControl`'s three actions (start/stop exploring, open the picker, reopen an
  existing document) from the shell's own spec-tab header, but this change does not remove or change
  the composer control. Both paths reach the same state.
- **A load-bearing bug in the loop-summary query is fixed.** `_batch_loop_summaries`'s `current_task`
  candidate query filters `Task.status.in_(("in_progress", "blocked", "pending"))` — `"assigned"` is
  missing, while `checkpoints.py`'s `_LIVE_TASK_STATUSES` and `task_transitions.py`'s
  `ENTRY_STATUSES` both already treat it as live. Once `2026-08-18-a-loop-writes-its-own-queue`
  ships, a firing claims its task by setting exactly that status — so a freshly claimed task would
  silently vanish from both the Jobs page's existing card and this change's new loop tab until
  something else moves it along. Fixed here, one clause, because this change is the first thing that
  makes the gap visibly wrong to an operator rather than merely latent.

## Capabilities

### Added Capabilities

- `conversation-side-panel`: the panel shell, its registration contract, the loop tab and its data
  sources, the file tab and its new content-read endpoint, the persistence split, and the
  accessibility requirements (reduced motion, keyboard reachability) for all three.

### Modified Capabilities

- `spec-chat-session`: "A specification document opens beside a conversation" is restated as opening
  in the shell's `spec` tab rather than as the conversation's only possible right-hand occupant.
  Every guarantee the requirement already makes — closable, part of the addressed destination,
  survives a reload, an operator-owned resize boundary — is preserved; nothing about what the
  document panel does is loosened.

## Impact

**Behaviour** — a conversation that never opens any panel is unaffected. A conversation with a
document open today continues to show it, now inside a tab strip with two more (empty, until used)
tabs beside it. `_batch_loop_summaries`'s `current_task` field starts including a task in `assigned`
status, which — until the loop change ships — no code path can currently produce, so this fix is
inert on its own and load-bearing only once that change lands.

**API** — new `GET /api/v1/workspace/file?path=...`, project-scoped, resolving through the same
`project_workspace.resolve_project_workspace` boundary every other project-scoped route uses.
`_batch_loop_summaries`'s SQL gains one value in an existing `IN` clause; no schema change. No
existing endpoint's request or response shape changes.

**Migration** — none. The loop tab's live-ness check needs a job-scoped "is a run active" lookup;
design D6 states whether this needs new storage or is derivable from existing `Run`/`JobRun` rows.

**UI** — `ConversationView.tsx`'s panel-hosting block is rewritten as shell-plus-registry.
`SpecDocumentPanel`'s own internals are not rewritten, only re-hosted. Two new panel content
components (`LoopPanel`, `FilePanel`) are added.

## Non-Goals

- **Not multi-instance tabs.** All three panels are singletons this pass — no per-file tabs, no
  reopening a second loop view. `testbed/scratch/t3ref/` shows even T3 reserves multi-instance for
  exactly two of its six panel kinds; none of AgentWeave's three initial panels need it, and the
  operator asked to "start with a file viewer/navigation," not a multi-file-tab workflow.
- **Not a fourth panel, and not a plugin system.** The descriptor array is deliberately a fixed
  literal, matching what T3 itself does with six panel kinds — appropriate for three known panels,
  disproportionate as a fully dynamic registry would be for three.
- **Not removing the explore button.** Per `DEC-explore-button`, removing a shipped entry point is a
  taste call the operator should make while looking at the replacement, not something this change
  decides on its behalf.
- **Not fixing `run_task_binding.py`'s interaction with a loop-claimed task.** Whether a loop
  firing's run automatically transitions its claimed task from `assigned` to `in_progress` once
  bound — `run_task_binding.py:250-254`'s existing automatic-bind mechanism — was not verified to
  apply to a loop firing's binding path this session. This change fixes the *query* so an `assigned`
  task is visible where it previously was invisible; whether that state is typically momentary
  (superseded quickly by the automatic bind) or can persist is left open, named in design D6 rather
  than silently assumed either way.
- **Not spend bounds, not a fourth data source for "is this loop still healthy."** Out of scope,
  same as the loop change's own Non-Goals.
