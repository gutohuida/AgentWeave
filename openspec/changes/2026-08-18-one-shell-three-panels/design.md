# Design — one shell, three panels

Every decision below either restates what `openspec/explorations/2026-08-18-the-side-panel-family.md`
already settled as a position (cited, not re-derived) or resolves something that exploration left as
a recommendation or an open question, argued fresh with a rejected alternative recorded so it does
not resurface.

## D1. Generalize the hosting block, rather than bolt a second mechanism beside it

Already argued and costed in the exploration's §2, restated here as the decision this change acts
on rather than re-litigated: `ConversationView.tsx`'s panel-hosting block (`:150-291` — the `panel`
JSX, the resize math, the `Drawer` overlay) becomes shell-plus-registry. `SpecDocumentPanel`'s props
(`path`, `inventory`, `onSelectPath`, `onClose`, …) become the `spec` tab's props, not the shell's;
`ConversationView`'s `document` destination field becomes "which document the `spec` tab is pointed
at," not deleted.

**Rejected: a second, independent tab-and-resize mechanism beside the existing spec column.** The
exploration's cost table (§2) is not repeated here in full; the sharpest line from it is enough to
record: it would duplicate `DOCUMENT_COLUMN_BREAKPOINT`'s derived-not-written math and now has two
things that could disagree about what "open on the right" means, plus it directly contradicts "just
like T3 does" — T3 has one right panel, not two competing ones.

## D2. The panel descriptor: what a panel declares, and what happens on a second open

A small, literal array — one entry per kind, matching what even T3 itself does for six panel kinds
(exploration §3 item 1: no dynamic registry exists there either, just a fixed literal union
hand-kept in sync across a store, two switch statements, and the plus-menu's item list):

```ts
interface PanelDescriptor {
  id: 'spec' | 'loop' | 'files'
  title: string
  icon: string   // an Icon component name
  singleton: true
}
```

**Reopening an already-open singleton refocuses it, never duplicates it.** There is nothing a second
`loop` tab could mean — it always shows the same job's summary — and a second `files` tab reopening
the same tree-plus-preview singleton is equally meaningless before this pass adds per-file tabs
(Non-Goals). This matches T3's own `upsertSurface` pattern (exploration §3 item 3).

**What is deliberately excluded from the descriptor:**

- **A capability-gating predicate** (T3's `SURFACE_DISABLED_REASONS` — its `diff` panel needs a git
  repo, its `preview` panel needs desktop). None of AgentWeave's three panels have an environmental
  precondition: `spec` always exists per-project, `loop` always shows whatever loops exist (including
  "none yet" as a legible empty state, not a disabled tab), `files` always has a workspace root once
  a project is registered. Adding an optional `disabledReason` now, for three panels that never use
  it, is exactly the premature generality this codebase's own conventions (the `spec_document_id`/
  `loop_id` "deliberately not a ForeignKey" comments the loop change cites repeatedly) argue against.
- **Which React component renders a given id's content.** Config-shaped registration metadata and a
  non-serializable component reference do not belong in the same array `PanelPlusMenu` iterates to
  render icon+label pairs. Component association stays a separate, code-level `switch` (or lookup
  object) keyed by the same `id`.

**Rejected: a fully dynamic registry (`registerPanel(descriptor, Component)`) callable from
anywhere.** Considered because it would look more "extensible." Rejected: three known panels do not
need runtime registration, a static array is exhaustively type-checkable in a way a runtime registry
is not (the union `'spec' | 'loop' | 'files'` catches a typo at compile time; a string key registered
at runtime does not), and nothing in the operator's brief or the exploration names a fourth panel on
the horizon that would justify the extra indirection now.

## D3. `SpecDocumentPanel`'s migration is inside this change, not a prerequisite

The exploration flagged this as something Q8 had to settle rather than assume (§2's "cost of
generalizing" paragraph). Two shapes:

| | Migrate inside this change | A separate prerequisite change first |
|---|---|---|
| What the loop/file panels are built against | The shell's final contract | `SpecDocumentPanel`'s current one-off shape, then re-plumbed once the shell lands |
| Risk of drift | One change, one review pass | Two changes, second one can silently assume the first's shell shape without re-checking it |
| Operator review load | One PR touching the hosting block once | Two PRs, the second only meaningful in light of the first |

**Decided: migrate inside this change.** Building the loop and file panels against
`SpecDocumentPanel`'s current, spec-specific prop shape and then re-plumbing them once a real shell
exists is strictly more work than building all three against the shell's contract from the start —
exactly what the exploration's §2 "cost of generalizing" paragraph already recommended sequencing
first. `SpecDocumentPanel`'s own internals (breadcrumb, phase/coverage bars, the `SpecFrame` bridge,
the outline rail) are moved, not rewritten — this is a hosting change, not a rebuild of a component
that already works.

**Rejected: land the shell with only the spec tab, add loop/files in follow-up changes.** Considered
as a way to reduce this change's surface area. Rejected because the operator's brief and the
exploration both treat the loop tab specifically as the governance payoff for a feature
(`2026-08-18-a-loop-writes-its-own-queue`) already speced and awaiting review — shipping a shell with
one tab and calling the governance story done would misrepresent what was asked for. This change
specs all three; `tasks.md` may still sequence their *implementation* in whatever order makes review
easiest, but the spec does not stage the panels themselves.

## D4. Persistence: three questions, three different answers, not one blanket rule

Restating the exploration's §5 position as the decision, because it already argued each of the three
independently and none of the three arguments changed on review:

1. **Panel width** — a single global `localStorage` value, extending `specPreferences.ts`'s existing
   `conversationWidth` key rather than inventing a second model. No evidence the operator wants a
   loop tab and a spec tab remembered at different widths.
2. **Which panel is active, and whether the shell is open** — per-conversation, following the same
   ownership `ConversationView`'s existing `document` prop already has (destination/URL-shaped
   state, owned by the caller, surviving a reload because the destination itself does). A loop tab
   left open while looking at an unrelated conversation would show that *other* conversation's loop
   — or nothing, if that conversation has none — which is worse than closed: it looks like an answer
   and is not one.
3. **The set of tabs ever opened** ("recently used" ordering in the plus menu) — not built. Three
   items is not enough for ordering to solve a problem the operator has.

**Rejected: make "which panel is active" global too, matching width.** The natural-seeming
consistency move. Rejected specifically because width and "which panel" fail differently when wrong:
a wrong *width* is a minor resize; a wrong *active panel* is a governance surface showing the wrong
loop's status without saying whose it actually is — the exact failure mode the operator's own
"visibility" framing exists to prevent.

## D5. What "which panel is active" actually is: a destination field, not a new store

Concretely, `ConversationView`'s `document: string | null` prop is joined by `activePanel: 'spec' |
'loop' | 'files' | null` and `panelOpen: boolean`, owned and threaded exactly the way `document` and
`onOpenDocument` already are — the caller (whatever resolves the current conversation's destination)
owns all three, and a reload restores all three together. Opening the file or loop tab does not
require a document to be open; `document` stays meaningful only for the `spec` tab specifically
(which document, if any, that tab shows).

**Rejected: fold `activePanel`/`panelOpen` into `document` by making `document` a discriminated
union instead of three fields.** Would need every existing caller of `document`/`onOpenDocument` —
the destination-routing code, not just `ConversationView` — updated to the new shape in this same
change, for a saving that is purely cosmetic (three fields versus one union field with three cases).
Three independent fields is a strictly smaller diff against working code.

## D6. The loop tab's live-ness gate, and the `"assigned"` query fix

Two separate problems the exploration's §6.2 raised, resolved separately because they have different
shapes.

**The query fix.** `_batch_loop_summaries`'s `current_task` candidates query
(`hub/hub/api/v1/jobs.py:122-124`) filters `Task.status.in_(("in_progress", "blocked", "pending"))`.
`checkpoints.py`'s `_LIVE_TASK_STATUSES` (`:43-49`) and `task_transitions.py`'s `ENTRY_STATUSES`
(`:94`) both already include `"assigned"`. **Decided: add `"assigned"` to the `IN` clause, in this
change.** One word, and it is the query this change's own loop tab depends on to show a freshly
claimed task correctly — the Jobs page's existing `LoopBlock` benefits identically, as a side effect
of fixing the shared query rather than a second, separate fix.

*A genuinely open question this change does not resolve*: `run_task_binding.py:250-254` already
moves a task from an entry status to `in_progress` automatically the moment a run binds to it
("The agent is never asked, so it cannot forget"), which raises whether `"assigned"` is typically a
momentary state for a loop-claimed task rather than one that persists long enough to be worth
querying for. Whether a loop firing's run actually goes through that binding path — which depends on
`InboundQueueEntry`-based binding the loop change's own `design.md` D3 does not describe using — was
not verified this session. **Decided: fix the query regardless.** Even if `"assigned"` turns out to
be momentary in practice, a query that cannot represent a real, reachable status is a latent bug
independent of how often it is hit — the same standard the loop change's own commit-ordering fix
(Q2/Q3 of this session's queue) applied to a rare-but-real path. If a future session confirms
`"assigned"` never survives long enough to be observed, that is a finding about `run_task_binding.py`
and the loop change's D3, not a reason to leave this query wrong.

**Rejected: make the loop change's D3 claim step also set `in_progress` directly, skip `"assigned"`
entirely.** This is the loop change's own design surface, already closed and reviewed
(`2026-08-18-a-loop-writes-its-own-queue/design.md` D3), not this change's to reopen. Folding claim
and start into one transition is a legitimate alternative but it is a decision about *how a firing
claims work*, which belongs in that change if it is revisited, not smuggled in here as a side effect
of a UI change.

**The live-ness gate — a genuinely new lookup, not a query fix.** `_batch_loop_summaries` has no
notion of "is a run active right now" at all; it summarizes task/queue state. Handoff 0055's decision
2 (cited in the exploration, §6.2) already rejected gating a live-ness indicator on the polled
`agent.status` roster field — it hides the indicator the moment an agent's turn produces any text,
which is wrong, since an agent legitimately keeps working after speaking. `AgentTimeline.tsx`'s
existing gate, `runVisiblyActive = isRunning && !lastRunSettled` (`:104`), is scoped to one agent's
current conversation. The loop tab needs the equivalent answer scoped to *the loop's job's current
run*, which is a different scope than any existing call site uses.

**Decided: a new, job-scoped live-ness lookup**, reusing lifecycle events plus the streamed status
line exactly as `AgentTimeline`'s does (`useSSE` + the same event types), but keyed by the loop's
`AIJob.id` via its most recent `JobRun.conversation_id` rather than by agent. No new storage — `Run`
and `JobRun` rows already exist; this is a new read path over them, not a new column.

**Rejected: reuse `AgentTimeline`'s hook directly, pointed at the loop's agent instead of the open
conversation's agent.** Rejected: `AgentTimeline`'s gate answers "is *this agent*, in *this
conversation*, visibly active" — pointing it at a different conversation than the one currently open
would require threading a conversation id the hook was not built to take as a variable input, and an
agent can be simultaneously idle in the open conversation and running a loop firing in a different
one. The loop tab's question is about the *job's* current run, not about whichever agent happens to
own the conversation the operator is looking at — conflating the two would make the indicator lie
whenever they diverge, which is exactly the scenario a loop makes routine (a background firing while
the operator is in an unrelated conversation with the same agent).

## D7. The file panel's content-read endpoint: allowlist, size bound, binary handling

**Allowlist.** `GET /api/v1/workspace/file` accepts a `path` query parameter and SHALL serve it only
if `path` is byte-for-byte a member of what `list_workspace_paths(workspace.root)` currently returns
for the same project — not a second, independently-reasoned containment-and-traversal check. This is
the exploration's §7 recommendation, decided here rather than merely repeated: the same git-backed
enumeration that already decides what is *visible* (respecting `.gitignore`, refusing anything
outside the project's registered working directory via `project_workspace.resolve_project_workspace`)
also decides what is *readable*, so the two cannot silently disagree about what a symlink escape or a
`../` traversal attempt resolves to.

**Rejected: a second path-safety check (e.g., resolve-and-check-prefix) independent of
`list_workspace_paths`.** This is the more common shape for a file-serving endpoint, and was
rejected specifically because "independent" is the risk, not the safety feature it sounds like — two
sanitizers reasoned about separately can each be individually correct and still disagree on an edge
case (a symlink `list_workspace_paths`' git-based enumeration excludes but a raw filesystem check
would resolve through). One list, checked by membership, cannot disagree with itself.

**Size bound.** 1 MiB (`1_048_576` bytes), reusing `hub/hub/config.py`'s existing
`aw_max_body_size` default rather than inventing a new number — the same bound the Hub already
applies to what it accepts *inbound* is reused for what this endpoint now serves *outbound*. A file
over the bound SHALL be refused with a response naming the size and the bound, not silently
truncated — unlike a checkpoint's briefing text (design D5 of the loop change, truncated on purpose
because a checkpoint is already understood to be a bounded summary), source code read in a viewer is
expected to be complete; a silently truncated file reads as the whole file and is not.

**Rejected: truncate to the bound and serve the prefix, matching the briefing's own truncation
pattern.** Rejected because the two cases are not equivalent: a checkpoint's consumer (a future
firing) benefits from *some* context over none, and truncation there is explicitly reasoned as
acceptable degradation (loop change design D5). A file viewer's consumer (the operator, deciding
whether to trust or act on what they are reading) is actively harmed by silently-partial code that
looks complete.

**Binary detection.** Read the first 8,000 bytes and check for a NUL byte — the same heuristic git
itself uses (`core.autocrlf`/diff machinery) to decide whether to treat a file as text, chosen
specifically because this endpoint is already git-backed for its allowlist (D7 above) and inheriting
git's own definition of "binary" keeps the two checks answering the same question the same way,
rather than the file panel disagreeing with `git diff` about what counts as text. A binary file's
response names that it is binary and is not rendered inline; whether the panel later offers a
download affordance for it is left to `tasks.md`'s implementation sequencing, not a spec requirement
this change states.

**Rejected: use the file extension (or a MIME-type library) to decide text vs. binary.** Rejected:
extension-based detection is wrong for exactly the files an operator is most likely to want to view —
extensionless config, a `Makefile`, a script with no suffix — and a MIME-type library is a new
dependency for a decision the codebase's own git dependency (already required for
`list_workspace_paths` to function at all) already answers for free.

## D8. Motion — reserved for the one indicator that would otherwise be missed

The operator asked for "some loop animations and icons... explore ui/ux practices." Per the
exploration's §3 item 7 (T3's own agents panel avoids animating live-updating rows "so completion
state changes never yank rows out from under the user") and §6.3, the standard held here is **"what
does not animating this cost the operator," not "what would look good."**

- **Active-now indicator (D6's live-ness gate) — the one place motion earns its keep.** A CSS-driven
  pulse or equivalent, only while the gate is true. "Is something happening right now" is exactly the
  state a static icon under-communicates; a colour alone does not say "ongoing" the way movement does.
- **Queue progress bar** — no new animation; reuses whatever CSS transition `SpecCoverageBar` already
  gives a width change for free on data update, matching that component's existing visual language
  rather than inventing a second progress-bar style.
- **Stop-reason / terminal-state badge** — static, deliberately, matching T3's own reasoning for its
  agents panel: a completed or stopped state should not visually "yank" once it settles.

**Rejected: animate tab switches, panel open/close, or queue-count changes.** T3's own reference
implementation does none of this (exploration §3 item 7: hover-only colour transitions on the resize
handle, one native `scrollIntoView` for the newly active tab, otherwise no motion at all). Adding
motion AgentWeave's own reference does not use would not be "exploring ui/ux practice," it would be
decoration the brief did not ask for.

**Accessibility.** `hub/ui/src/index.css:708-715` already collapses every CSS `transition`/
`animation` duration to near-zero under `prefers-reduced-motion: reduce` — a CSS-driven pulse
inherits this for free. If implementation chooses a JS-driven approach instead (the codebase's own
precedent, `AgentTimeline`'s elapsed-seconds ticker, uses `requestAnimationFrame` for its *number*,
not for motion), it needs its own `matchMedia` check — stated as a requirement rather than left
implicit, because the blanket CSS rule silently does not cover a JS-driven implementation choice.

**Keyboard reachability.** The tab strip and the plus affordance are interactive controls with no
existing precedent to inherit from (nothing like them exists in this codebase today) — stated as its
own requirement: every tab is reachable and activatable via keyboard (`Tab`/`Shift+Tab` to reach,
`Enter`/`Space` to activate, arrow keys to move between tabs while the strip has focus, matching the
ARIA `tablist` pattern), and the plus affordance's menu is keyboard-navigable the same way any other
menu in this codebase already is (no new pattern invented for this one control).

## D9. What this leaves for a future change, named rather than assumed away

Mirroring the loop change's own D9 practice:

- **Whether `"assigned"` is a momentary or persisting state for a loop-claimed task** (D6) — the
  query fix lands regardless; whether it is ever load-bearing in practice for longer than an instant
  is unverified.
- **Multi-instance file tabs** — explicitly out of scope (Non-Goals), named here so a future session
  proposing it knows this change considered and rejected it for this pass, not that it was never
  considered.
- **A disabled-with-reason predicate on a panel descriptor** — deliberately excluded (D2) because no
  current panel needs one; the shape is named so adding it later is additive, not a rework.
- **Whether the panel shell can subsume the explore button's three actions** — designed to be
  possible (D1, per `DEC-explore-button`), not built. A future change makes the shell's spec-tab
  header actually expose start/stop-exploring and reopen, once the operator has seen this shell in
  use and has an opinion on whether that consolidation reads as better or as two ways to do the same
  thing.
- **File download for a binary file the viewer refuses to render inline** (D7) — named, not speced.
