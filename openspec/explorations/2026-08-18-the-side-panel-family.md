# The right side of the screen has one tenant. It needs a landlord.

> **⚠ Its recommendations are superseded.** Read
> `openspec/explorations/2026-08-18-the-side-panel-with-the-operator.md` first. That session put this
> document's recommendations to the operator and **six were overturned**: all-singleton panels,
> per-conversation persistence, a fixed strip of three, a conversation-scoped loop tab, spec as a
> permanent special case, and the panel-side live-ness lookup. §11's numbered recommendations in
> particular should not be acted on.
>
> **The research below is still good** — the T3 study (§3), the survey of what exists today (§1), and
> the code findings (§6.2, §7) were all confirmed and reused. Only the conclusions moved.

**Status:** exploration. Decides nothing that is the operator's, and records what already exists so
the spec (Q8) does not re-derive it. Written 2026-08-18 by an unattended firing — no operator was
present to converse with, so this is written as analysis with recommendations named explicitly as
recommendations, not decisions. Code claims name the file and line they came from and were read this
session, not inferred from `2026-08-18-loops-as-an-agent-tool.md` or its change.

**The brief, in the operator's words:**

> "We should have a button that opens the side panel (just like t3 does and other harnesses as well).
> On top we can click a plus sign and open something else... We could start with a file
> viewer/navigation of the repo of the project. A loop tab with loop information (with some loop
> animations and icons)... and the spec that we already have. This could solve also our explore
> button problem."

Three things are being asked for at once: a **container** (tabs, a plus button, resize), a **second
tenant** (a loop status screen — new, and named as the governance half of the loop feature), and a
**third tenant** (a file browser — new). The spec document panel is not asked to change; it is asked
to stop being the only thing that can live on the right.

---

## 1. What already occupies the right side today

`hub/ui/src/components/agents/ConversationView.tsx` hosts exactly one thing beside a conversation: a
`SpecDocumentPanel`, opened by setting `document` (a path) on the conversation's destination state.
There is no tab strip, no plus button, no second slot. The mechanics, precisely:

- **Layout.** `DOCUMENT_COLUMN_BREAKPOINT = CONVERSATION_MIN_WIDTH (380) + SPEC_DOC_MIN_WIDTH (360) +
  DIVIDER_WIDTH (1) = 741px` (`ConversationView.tsx:37-38`). Above it, the conversation and the
  document sit side by side as two flex columns with a `PaneResizer` between them, and the
  conversation's width is what is dragged and persisted — the document takes whatever is left
  (`ConversationView.tsx:216-266`). Below it, the document becomes a `Drawer` overlay from the right,
  fixed at `SPEC_DOC_MIN_WIDTH` (`ConversationView.tsx:282-291`), with a small "reopen" affordance
  left behind in the conversation column (`:224-233`) since the overlay can be dismissed without
  losing the document. This is a push layout that degrades to an overlay, not two separate designs —
  the breakpoint is *derived from* the two minimums, "so changing either minimum cannot leave the
  breakpoint and the layout disagreeing" (`ConversationView.tsx:34-35`, citing a past mistake by
  name: the three-column workspace).
- **Persistence.** `hub/ui/src/components/spec/specPreferences.ts` persists exactly one number,
  `conversationWidth`, to `localStorage['aw.spec.presentation.v1']` — **global**, not per-conversation
  and not per-project. Every conversation that opens a document shares the same remembered width.
  Whether a document is open at all, and which one, is **not** persisted here — it lives in the
  conversation's own destination state (a URL-shaped concern the panel's props already treat as
  external: `path`, `onSelectPath`, `onClose` are all owned by the caller). `chatCollapsed` and
  `libraryMode` existed on an earlier three-column version of this file and are called out, in the
  comment at the top, as deleted along with the surfaces that read them — a a working precedent for
  *not* over-persisting.
- **The panel itself.** `SpecDocumentPanel.tsx` is not a generic container; it is a full-featured,
  single-purpose reader: a breadcrumb that reopens the document picker, an archived-marker, a
  refresh/close pair, `SpecPhaseBar`, `SpecCoverageBar`, `SpecProposalsPanel`,
  `SpecDocumentTasksLink`, a drift-diagnostics banner, the sandboxed `SpecFrame` iframe with its own
  bridge protocol (`specBridge.ts` — postMessage, versioned, bounded, no `allow-same-origin`), and an
  on-page outline rail. None of this is generic panel chrome; all of it is spec-document behavior
  that a registry must leave untouched.

**Conclusion: there is no panel registry today, because there has only ever been one panel.**
`SpecDocumentPanel` was never asked to coexist with anything, so it never grew the concept of
"another tab." Q7 has to design that concept from nothing, not extract it from something half-built.

## 2. Generalize, or bolt a second one-off beside it? — a position, with costs

**Position: generalize.** A thin **panel shell** owns the tab strip, the plus menu, the resize/overlay
breakpoint math, and which panel is active; `SpecDocumentPanel` becomes the `spec` panel's *content*,
registered like any other, with every one of the features in §1 untouched inside it. The alternative —
a second, independent tab-and-resize mechanism sitting next to the existing spec column — was
costed and rejected:

| | Generalize (one shell, N contents) | Bolt on (spec panel + separate tab sheet) |
|---|---|---|
| Breakpoint/overlay logic | Written once, reused | Duplicated, and now has to agree with the first — the exact class of bug `ConversationView.tsx:34-35`'s comment already names as a past mistake |
| What "open on the right" means | One concept | Two concepts, and the operator has to learn which one a given button opens |
| Resize/persistence | One store, one width preference (or a small, deliberate per-panel set — see §4) | Two independent width preferences to keep from fighting over the same screen edge |
| Migration cost | `SpecDocumentPanel`'s props (`path`, `inventory`, `onSelectPath`, …) become one panel's props instead of the shell's; `ConversationView.tsx`'s `document` state becomes "which tab is the spec tab pointed at," not deleted | None — but only because nothing new is asked to share space with the old |
| Governance framing | One place the operator learns to check for "what is open and why" | Contradicts the operator's own framing (governance *and visibility* — a second, unrelated mechanism for visibility is friction, not visibility) |

The bolt-on option is not merely more code; it directly contradicts what the operator asked for —
"just like T3 does," where the whole point of the T3 reference is **one** right panel with **one**
plus button, not a spec panel with a second panel beside it.

**Cost of generalizing, stated plainly:** `ConversationView.tsx`'s panel-hosting block (`:150-291`,
the `panel` JSX, the resize math, the `Drawer`) has to be rewritten as shell-plus-registry rather than
spec-specific. This is real, non-trivial work — moving working code, not writing net-new — and is
exactly the kind of thing Q8's `tasks.md` should sequence first, before either new panel exists, so
the file/loop panels are built against the shell's final contract rather than against
`SpecDocumentPanel`'s current one-off shape.

## 3. The T3 study — patterns, not code

`testbed/scratch/t3ref/` holds T3 Code's right-panel system, recovered from shipped sourcemaps. Read
in the stated order (`rightPanelLayout.ts`, `rightPanelStore.ts`, `RightPanelTabs.tsx`,
`RightPanelSheet.tsx`, `preview/RightPanelResizeHandle.tsx`, `chat/PanelLayoutControls.tsx`,
`files/FileBrowserPanel.tsx`, `files/FilePreviewPanel.tsx`, `files/fileTreeDragMention.ts`,
`AgentsPanel.tsx`, plus `preview/PreviewPanelShell.tsx` as the actual resize consumer). Findings,
patterns only — no code quoted:

1. **No dynamic registry exists even in T3.** Panel *kinds* are a fixed literal union
   (`diff`/`files`/`file`/`preview`/`terminal`/`agents`), hand-kept in sync across the store's
   discriminated union, two icon/title switch statements, and the plus-menu's item list. This matters
   for §2: AgentWeave does not need to out-engineer T3 with a fully pluggable descriptor system for
   three known panel kinds — a **small, explicit array of panel descriptors** (§4) is already a step
   *more* structured than T3's own approach, appropriate because AgentWeave is building this fresh
   rather than retrofitting, and disproportionate as a fully dynamic plugin system would be.
2. **Open-tab state is per-conversation-thread**, a single persisted store keyed by thread id, with a
   versioned migration function repairing stale shapes on load. Width, separately, is **not** part of
   that store — it is a second, independent localStorage key. T3 splits "what's open" from "how wide"
   into two persistence concerns; AgentWeave's existing `specPreferences.ts` already made the same
   split (width only, nothing about open/closed) by omission, without ever having to hold "what's
   open" at all. See §4 for what AgentWeave should do with the open-tab half, which is genuinely new.
3. **The plus menu is a fixed, always-rendered list** (five items), not filtered by what's already
   open — reopening a singleton just refocuses it. Unavailable items render disabled with a reason
   tooltip rather than being hidden. This directly answers a question the brief left implicit: the
   plus button does not need "smart" filtering logic; a disabled-with-reason state is simpler and
   more honest than hiding capability the operator might otherwise wonder about.
4. **Resize is push-by-default, overlay-only-when-narrow**, with the same shape AgentWeave's spec
   panel already independently arrived at: a fixed min width, a viewport-fraction max, and a
   dedicated overlay component (T3's `RightPanelSheet`, AgentWeave's `Drawer`) swapped in below a
   breakpoint rather than resized. AgentWeave does not need to adopt anything new here — it already
   built the T3 pattern once, for one panel; §2's generalization reuses it rather than replacing it.
5. **Multi-instance is the exception, not the default.** `diff`/`files`/`agents` are singletons keyed
   by a fixed id; only `preview` (browser tabs) and `file` (one tab per open file, keyed by path) are
   multi-instance, and multi-instance costs real complexity — a second keying scheme, drag-to-mention
   wiring, a "reveal again" signal for reopening an already-open file. **Recommendation: none of
   AgentWeave's three panels need multi-instance for this pass.** The file panel should be one
   singleton tab with an internal tree+preview split (§6), not one tab per opened file — the operator
   asked to "start with a file viewer/navigation," not with T3's fuller multi-file-tab workflow, and
   the added complexity buys nothing the brief asked for. Named as a recommendation, not a decision.
6. **The file tree hands a file to the composer two ways**: a context-menu "Add to chat" that calls
   the composer's imperative insert handle directly, and native HTML5 drag-and-drop carrying a custom
   MIME-typed mention string. AgentWeave already has the receiving half of the first pattern —
   `composerTrigger.ts`/`NewConversationSurface.tsx`'s `@path` trigger already turns a path into a
   composer mention today, fed by the workspace-paths endpoint (§6.1) — so a file panel's "insert
   into composer" action is *reusing* an existing mention format, not inventing one.
7. **Animation is almost entirely absent.** Hover-only colour transitions on the resize handle, no
   transition on open/close/switch, one native `scrollIntoView` for the newly active tab. T3's own
   agents panel explicitly avoids animating live-updating rows "so completion state changes never yank
   rows out from under the user" — chosen for legibility, not decoration. This directly informs §7.

## 4. What a panel declares to register

A small, literal array of descriptors — one entry per kind, not a plugin system:

```
{ id: 'spec' | 'files' | 'loop', title: string, icon: string (Icon name), singleton: true }
```

`singleton: true` for all three initial panels (§3 item 5). What happens when a singleton is opened
again: **refocus, don't duplicate** — matches T3's `upsertSurface` pattern and is the only sane
behavior for a fixed-id tab (there is nothing a second "loop" tab could mean if a loop tab always
shows the same job's summary). Component association (which React component renders a given id's
content) stays a separate, code-level switch — not part of the descriptor — because the descriptor is
config-shaped, static UI/UX and registration metadata; the component is not serializable and does not
belong in the same array `PanelPlusMenu` iterates to render icon+label pairs.

**What is deliberately not in the descriptor:** a capability-gating predicate like T3's
`SURFACE_DISABLED_REASONS` (diff needs a git repo, browser needs desktop). None of AgentWeave's three
initial panels have an environmental precondition — spec always exists per-project, loop always shows
whatever loops exist (including "none yet"), files always has a workspace root once a project is
registered. If a future panel needs one, the descriptor gains an optional `disabledReason: () =>
string | null` then; adding it speculatively now for three panels that don't need it is exactly the
kind of premature generality this codebase's own conventions argue against.

## 5. Persistence — split by what's actually per-conversation

Three questions, each with a different right answer, not one blanket "global/per-conversation/
per-project" choice:

- **Panel *width*.** Follow `specPreferences.ts`'s existing, working choice: one global
  `localStorage` value, shared across every conversation. There is no evidence the operator wants a
  loop tab and a spec tab remembered at different widths, and `specPreferences.ts` already resolved
  the equivalent question once (§1) — reusing that answer for a new field on the same store is
  cheaper and more consistent than inventing a second model that disagrees with the first for no
  stated reason.
- **Which panel is *active*, and whether the shell is open at all.** **Recommendation:
  per-conversation**, not global. T3's own reasoning (§3 item 2) applies directly here: a loop tab
  pinned open while looking at an unrelated conversation is a stale, actively misleading state — the
  governance value of the loop tab is "what is *this* conversation's agent doing," and that answer
  changes conversation to conversation. The existing `document` state that decides *which spec path*
  is open is already threaded through as conversation/destination state today (`ConversationView`'s
  own `document` prop, owned by the caller) — extending that same ownership to "which panel tab is
  active" is a smaller change than inventing a new persistence layer, and keeps the same actor
  (whatever already decides which conversation is open) responsible for both.
- **The *set* of tabs a user has ever opened** (so the plus menu can default to "recently used" or
  similar) — **not recommended for this pass.** T3 does not need this because its plus menu is a
  fixed, always-fully-rendered list (§3 item 3); AgentWeave's three-panel menu is small enough that
  "recently used" ordering would be solving a problem three items do not have. Flagged so a future
  session does not invent it unasked.

## 6. The loop panel, in detail — the governance half

This is what the operator asked for by name, so each element states its data source rather than being
described only in prose.

### 6.1 What already answers "what is a loop doing"

`hub/hub/api/v1/jobs.py:98`'s `_batch_loop_summaries` already computes, in four fixed queries (not
one-per-job), everything `LoopSummary` needs for a **job-list card** view, and this is already
rendered today — `hub/ui/src/components/jobs/JobCard.tsx`'s `LoopBlock` (`:88-172`) shows purpose,
an Active/Stopped badge, per-status queue counts (clickable through to the Tasks tab, reusing the
mechanism `SpecDocumentTasksLink` proved), the current/claimed task, and an open-questions count. **A
version of the loop panel already exists on the Jobs page.** The side-panel's loop tab is not
inventing this data; it is bringing an existing, working summary into a surface reachable from the
conversation the loop's own firings write to, which the Jobs page is not scoped to. Q8 should treat
`LoopSummary`/`_batch_loop_summaries`/`LoopBlock` as the starting contract to adapt, not a green field.

### 6.2 What the operator asked for that does not exist yet

- **"Is an agent running right now."** `_batch_loop_summaries` has no notion of this at all — it
  summarizes task/queue state, not live run state. Per handoff 0055 decision 2, live-ness must be
  gated on lifecycle events plus the streamed status line (`AgentTimeline.tsx`'s
  `runVisiblyActive = isRunning && !lastRunSettled`, `:104` — the polled `agent.status` field alone
  was rejected there for hiding the indicator whenever text appears, which is wrong because an agent
  legitimately keeps working after speaking). The loop panel needs the same gate, scoped to the
  loop's job rather than to whichever agent conversation happens to be open — meaning it needs the
  *job's* current run, not the agent's roster-wide status, which is a genuinely new lookup
  (`JobRun` rows already carry `conversation_id`; whether the loop tab can reuse `AgentTimeline`'s
  existing gate logic against that run, or needs its own, is a design question for Q8, not answered
  here).
- **"Next trigger."** `AIJob.next_run` already exists and is already computed at job creation
  (`jobs.py:203-210`, `croniter`) — this one is just wiring, not new data.
- **D6's telemetry** (`openspec/changes/2026-08-18-a-loop-writes-its-own-queue/design.md`, "Empty
  queue with an unanswered request"): a new `loop_queue_exhausted` event, broadcast alongside the
  existing `loop_stopped`, payload `{job_id, loop_id, pending_request}`. This is **produced by that
  change, not this one** — its own D9 says so explicitly ("This change produces the data; it produces
  no UI"). The loop panel is the first UI consumer named for it. Consuming it is exactly the existing
  `useSSE` + React Query invalidation pattern (§7), not a new transport.
- **D3's claimed-item concept** (same change): a firing claims the queue's current item
  deterministically by setting `Task.status = "assigned"` before working it. **This exposes a live
  data-source bug, found this session, that Q8 must account for:** `_batch_loop_summaries`'s
  `current_task` query (`jobs.py:122-124`) filters `Task.status.in_(("in_progress", "blocked",
  "pending"))` — **`"assigned"` is not in that list.** `hub/hub/checkpoints.py`'s own
  `_LIVE_TASK_STATUSES` (`:43-49`) and `task_transitions.py`'s `ENTRY_STATUSES` (`:94`) both already
  treat `"assigned"` as live/in-flight work, so this is not a case where `"assigned"` is obscure — two
  other modules in the same codebase already know about it and this one does not. **Consequence, once
  the loop-writes-its-own-queue change ships:** the moment a firing claims a task (sets it to
  `"assigned"`), that task silently disappears from every `current_task` field — the Jobs page card
  *and* the future loop panel — until something moves it to `"in_progress"`, which nothing in D3's own
  design says happens automatically. **This needs a fix somewhere before the loop panel can show a
  freshly claimed task correctly** — either `_batch_loop_summaries`'s candidates query gains
  `"assigned"` to its `IN` clause (the minimal fix, one word), or D3's claim step immediately also sets
  `"in_progress"` (folding claim and start into one transition, a design choice `2026-08-18-a-loop-
  writes-its-own-queue` did not make and should not be assumed here). Recorded here rather than
  silently worked around, because it was found while researching the panel, not the loop change, and
  the loop change is already merged into its own openspec change with a closed design.md.

### 6.3 UI/UX for the loop tab, and what each element must communicate

The operator asked for "some loop animations and icons ... explore ui/ux practices." Per §3 item 7,
T3's own practice is to animate almost nothing and reserve motion for things that would otherwise be
missed — **the standard to hold each proposed animation to is "what does not animating this cost the
operator," not "what would look good."**

- **Active-now indicator** (§6.2): a live pulse or similar *only* while `runVisiblyActive` is true for
  the loop's current run — this is the one place motion earns its keep, because "is something
  happening right now" is exactly the kind of state a static icon under-communicates (a colour alone
  does not say "ongoing" the way a subtle pulse does). Must respect `prefers-reduced-motion` — already
  a blanket rule at `hub/ui/src/index.css:708-715` collapsing every `transition`/`animation` duration
  to near-zero, so a **CSS-driven** pulse (transition/animation properties) inherits this for free; a
  JS-driven one (e.g. a `requestAnimationFrame` loop, which `AgentTimeline.tsx`'s own elapsed-seconds
  ticker already uses for its number, not its motion) would not, and needs its own `matchMedia` check
  if any such approach is chosen.
- **Queue progress** (done/total from `LoopSummary.queue`): no animation needed beyond what CSS width
  transitions already give a progress bar for free on data change — this is not a case needing new
  motion design, `SpecCoverageBar` already establishes the visual language for a coverage-style bar in
  this codebase and should be the pattern reused, not reinvented.
- **Stop-reason / terminal state**: a static badge (T3's own agents panel avoids animating completion
  states specifically "so they never yank rows out from under the user," §3 item 7) — recommend
  against any transition here, for the same reason T3 gives.
- **Icons**: `Icon` component only (`hub/ui/src/components/common/Icon.tsx`), CLAUDE.md's standing
  rule against a second icon system. No new icon names were confirmed to exist for "loop"/"queue"/
  "claimed task" specifically — Q8 should audit the current icon map before assuming one exists.

### 6.4 Live updates

`useSSE` (`hub/ui/src/hooks/useSSE.ts`) plus React Query cache invalidation on the relevant event
types (`job_run_failed`, `loop_stopped`, the new `loop_queue_exhausted`, task-status events) — not
polling. This is already the established pattern for every other live surface in the Hub UI
(`AgentTimeline`, `JobCard`'s existing `LoopBlock`); the loop tab has no reason to deviate from it.

## 7. The file panel — a real gap, not a UI-only build

Unlike the loop panel, the file panel's **backend surface is half-missing**, not merely un-surfaced.

- **What exists:** `GET /api/v1/workspace/paths` (`hub/hub/api/v1/workspace.py`, backed by
  `hub/hub/workspace_paths.py`'s `list_workspace_paths`) already returns a flat, sorted,
  `.gitignore`-respecting list of every tracked-or-untracked-but-not-ignored path under a project's
  registered working directory, resolved through `project_workspace.resolve_project_workspace` (the
  same project-boundary function `CLAUDE.md`'s "Local multi-project boundary" section names as
  mandatory). This already feeds the composer's `@path` trigger (`composerTrigger.ts`), so a
  client-side tree-building function is not new work either — `hub/ui/src/components/spec/
  specNavigation.ts`'s `buildPathTree` (`:320-364`) already turns a flat path list into a directory
  tree with exactly the shared-prefix-collapsing logic a file browser needs, for the spec inventory —
  worth reusing or adapting rather than re-deriving for the file panel.
- **What does not exist:** any endpoint that returns a file's **content**. A file *viewer* (the
  brief's own word, not just "navigation") needs one. This is new, security-relevant surface, not
  wiring:
  - It must resolve through the same `project_workspace.resolve_project_workspace` boundary every
    other project-scoped route uses — never a second, ad hoc path-join.
  - It must refuse to serve anything `list_workspace_paths` itself would not return — i.e., the
    content endpoint's allowlist should be "is this exact string, byte-for-byte, a path
    `list_workspace_paths` currently returns," not a permissive existence-and-containment check
    reimplemented from scratch. This closes path traversal and symlink-escape by construction (the
    same git-backed enumeration already decides what is visible) rather than by a second, independent
    sanitizer that could disagree with the first.
  - It must decide what happens for a binary file, an oversized file, and a file outside any
    reasonable size to render inline — none of this is answered by anything read this session, because
    nothing like it exists yet. Q8 has to settle bounds, not just wire a route.
  - "Insert into composer" reuses the existing `@path` mention format (§3 item 6) rather than
    inventing a second one — the file panel's tree and the composer's trigger should agree on what a
    mention looks like, since an operator dragging or clicking a path from one place should produce
    the exact text the other already knows how to render.

## 8. The explore button — current behavior, before proposing anything

Per `DEC-explore-button`: design so the panel *can* subsume it, do not remove it this pass. Current
behavior, read from `ComposerSpecControl.tsx` rather than assumed:

- **No document open:** the control is a **toggle**, deliberately modeled after "plan mode" per the
  operator's own comparison recorded in the component's docstring (`:44-51`) — pressing it arms
  exploration; the document is created on the first message sent, not on press. `armed` state exists
  only until that first message, "seconds," per the docstring.
- **A document open:** the control becomes a **label + close pair** — `Spec: <title>` opens the
  picker (`onOpenPicker`), and a separate close button (`onStopExploring`) detaches (never deletes)
  the document from the conversation.
- **A distinct, adjacent control** (`onOpenExisting`, rendered only when no document is open and not
  armed) reopens a document the conversation isn't currently attached to — added specifically because
  conflating it with "start exploration" left no way back into a document after closing it
  mid-work (component comment, `:95-98`).

**How the panel *can* subsume this without removing it:** opening the spec tab already needs "which
document" state (§1); today that state is *only* reachable through the composer control. Once the
panel shell owns a `spec` tab, the same three actions (start/stop exploring, open picker, reopen
existing) become things the panel's own header can *also* expose — the composer control stays exactly
as it is, and the panel becomes a second, equally valid way to reach the same actions, not a
replacement. This is a recommendation for Q8 to make concrete with the shell's actual props, not a
decision — the operator has not seen a mockup of either surface doing this yet.

## 9. Responsive behavior at the narrowest supported window

No new number needed — the existing breakpoint math (§1, `DOCUMENT_COLUMN_BREAKPOINT`) already
generalizes: the shell computes its own `shellMinWidth` from whichever panel is active (each panel
declares its own minimum, following `SPEC_DOC_MIN_WIDTH`'s precedent — `files` and `loop` need their
own measured minimums, not a guess, before Q8 states one), and the same
`conversationMax`/overlay-below-breakpoint logic that already exists for the spec panel applies
unchanged. This is not new design; it is the existing `ConversationView.tsx` breakpoint logic
parameterized by "whichever panel is active" instead of hardcoded to the spec panel's own minimum.

## 10. What this exploration did not verify

- **Nothing was driven live.** No panel shell exists to click through; every conclusion above is read
  from code and from T3's reference source, not observed in a browser.
- **File content size/type bounds** (§7) were not researched against what the Hub already does
  elsewhere for large content (e.g. how agent output logs handle a large file, if at all) — worth
  checking before Q8 states a number.
- **Whether `AgentTimeline`'s `runVisiblyActive` gate can be reused directly for a job-scoped (not
  agent-conversation-scoped) live-ness check, or needs its own implementation** (§6.2) — read the
  gate's logic, did not verify it generalizes past its current single call site.
- **Icon availability for loop-specific concepts** (§6.3) — the icon map was not fully enumerated,
  only spot-checked.

## 11. Recommendations, named as recommendations, for the operator to accept or redirect

1. Generalize the right side into a panel shell + small descriptor array (§2, §4), migrating
   `SpecDocumentPanel` to be the `spec` panel's content rather than rewriting it.
2. All three initial panels are singletons; no multi-instance file tabs this pass (§3 item 5).
3. Panel width stays a single global preference (extends `specPreferences.ts`); which panel is active
   and whether the shell is open becomes per-conversation state (§5).
4. Fix the `"assigned"` status gap in `_batch_loop_summaries` (§6.2) before or alongside building the
   loop panel — it is a real, already-shippable-adjacent bug, not a design question.
5. The file content endpoint's allowlist should be defined in terms of `list_workspace_paths`'s own
   output, not a second path-safety implementation (§7).
6. Motion is reserved for the active-now indicator only; everything else in the loop panel is static
   by the same reasoning T3 already applied to its own agents panel (§6.3).
