# Design — one shell, many tabs

**Rewritten 2026-08-18 afternoon.** The previous D1–D9 were authored unattended; D1 (generalize
rather than bolt on) and D7 (the file endpoint's allowlist, size bound and binary detection) survived
the operator conversation intact and are restated below as D1 and D7 with their reasoning preserved.
Everything else changed. The old D6 is **withdrawn entirely** — see D6 below.

Decisions are grounded in code read on 2026-08-18 and in T3 Code's right-panel source recovered under
`testbed/scratch/t3ref/` (design reference only — patterns, never copied code, never committed).

## D1. Generalize the hosting block rather than bolt a second mechanism beside it

`ConversationView.tsx`'s panel-hosting block (`:150-291` — the `panel` JSX, the resize math, the
`Drawer` overlay) becomes shell-plus-tabs. `SpecDocumentPanel`'s props (`path`, `inventory`,
`onSelectPath`, `onClose`, …) become a tab's props, not the shell's.

**Rejected: a second, independent tab-and-resize mechanism beside the existing spec column.** It
would duplicate `DOCUMENT_COLUMN_BREAKPOINT`'s derived-not-written math — the exact class of bug
`ConversationView.tsx:34-35`'s own comment names as a past mistake, the three-column workspace — and
give the operator two different things "open on the right" can mean. It also contradicts the brief:
"just like T3 does" names a reference with **one** right panel.

## D2. The tab model: the strip holds what is open, the plus adds what is not

The first version specced a fixed literal strip of `spec`/`loop`/`files` **and** a plus affordance
that SHALL offer *"every registered panel... No registered panel SHALL be hidden or omitted."* With
three fixed singletons those are the same three items, so one of the two affordances did nothing.

**Decided: T3's model.** The strip contains open tabs, each closable; the plus affordance opens one
that is not open; exactly one tab's content is visible at a time. The operator: *"the whole panel is
dedicated to one tab at a time of displayed information."*

**Rejected: keep the fixed strip and drop the plus affordance.** The smaller change, and it makes the
strip a segmented control rather than tabs — which forecloses D3's drill-downs entirely, since a
fixed strip has nowhere to put a second document.

## D3. Index tabs and keyed detail tabs

T3 models a surface as a discriminated union whose `id` is a template literal
(`rightPanelStore.ts:27-47`): singletons take a fixed id (`"files"`, `"diff"`, `"agents"`),
multi-instance kinds take a keyed one (`file:${relativePath}`, `browser:${tabId}`).

```
  INDEX (fixed id, one instance)      DETAIL (keyed id, many instances)
  id: "specs"   ──── click ────▶      id: `spec:${documentId}`
  id: "files"   ──── click ────▶      id: `file:${relativePath}`
```

**Reopening an already-open keyed tab refocuses it and re-reveals its content**, never duplicating
it — T3 bumps a `revealRequestId` counter for this (`rightPanelStore.ts:295`), which is the right
shape because "open this file again" and "scroll to it again" are the same operator intent.

**Rejected: `singleton: true` on every panel** (the first version's model). It foreclosed exactly
what the operator asked for — *"clicking into one opens a new tab drilling down"* — and it was
justified by an argument that does not survive the drill-down: "there is nothing a second tab could
mean" is true only when a tab has no key.

**Rejected: a fully dynamic `registerPanel(descriptor, Component)` registry.** A fixed union is
exhaustively type-checkable in a way a runtime string key is not, and nothing on the horizon needs
runtime registration. Keyed multi-instance is not dynamic registration; the *kinds* stay literal.

## D4. Key by id wherever an id exists; only files key by path

`rename_spec_document` is an **agent-callable MCP tool**. A tab keyed `spec:<path>` dangles the moment
an agent renames a document that still exists — a tab pointing at nothing, for a live document.

| Tab | Key | Survives |
|---|---|---|
| `spec:<document_id>` | id | rename, phase change, archive |
| `file:<path>` | path | nothing — a file has no other identity |

T3 keys files by path because there is no alternative, not because path-keying is preferable. Copying
that choice for documents would import a constraint we do not have.

**Consequence:** only `file:` tabs can dangle, so reconciliation (D5) has exactly one class of
target — which is also why T3 has `reconcileFileSurfaces` and no equivalent for its singleton kinds.

**Rejected: key spec tabs by path for symmetry with files.** Symmetry with a workaround is not a
reason to adopt the workaround.

## D5. Persistence is per project, versioned, and reconciled

Three separate questions, three answers:

1. **Tab configuration — which tabs are open, which is active, whether the shell is open at all:**
   **per project.** The operator: *"Each project we might want to have different tabs
   configurations... when we reopen the side panel it loads what was being used (For that project)."*
2. **Panel width:** the single global value `specPreferences.ts` already persists. Nothing suggests
   the operator wants different widths per tab, and that store already resolved this question once.
3. **A "recently used" ordering for the plus menu:** not built. A short fixed list does not need it.

**Rejected: per-conversation tab state** (the first version's D4/D5). Its argument was that a stale
tab from another conversation is misleading. That argument is strongest for the loop tab — which is
no longer in this change, and which turned out to be *project*-scoped anyway, since a conversation has
no loop at all (loop change D20).

Persisting keyed tabs means persisting pointers to things that can stop existing, so the store needs
machinery the first version had none of. T3's is worth adopting whole
(`rightPanelStore.ts:49-51, 164, 237-248`):

- A **versioned** key with a real migration function. T3 is on storage version 9 because this shape
  changed nine times; starting unversioned guarantees a future silent breakage.
- **Reconciliation** of keyed tabs against what exists, T3's `reconcileFileSurfaces` shape.
- Two rules taken verbatim, both of which describe failures a naive implementation will have:
  *"A migration that dropped every surface must not reopen an empty panel"* — `isOpen` requires at
  least one surface — and when the dropped surface was the active one, fall back to the first
  survivor rather than rendering an open, empty panel.

## D6. Withdrawn — the live-ness lookup belongs to the loop change

The previous D6 specced *"a new, job-scoped live-ness lookup... keyed by the loop's `AIJob.id` via its
most recent `JobRun.conversation_id`."*

`2026-08-18-a-loop-writes-its-own-queue` D13, written about twenty minutes earlier by a different
firing, had already **rejected that exact shape by name**: *"Rejected: deriving 'is a firing running'
by joining `JobRun.conversation_id` to `Run.status == "running"` and leaving the column alone... it
keeps a lie in the table and obliges every future reader to know to join."* D13 decided instead that
`JobRun.status` should be able to state its own value, through **one helper both callers use**.

**Decided: withdrawn.** The loop change owns the data layer. With the loop panel also moving there
(D20 of that change), this change has no live-ness concern left at all.

## D7. The file content endpoint: allowlist, size bound, binary handling

*Retained from the first version — the operator conversation did not touch it, and its reasoning
still holds.*

**Allowlist.** `GET /api/v1/workspace/file` serves a `path` only if it is byte-for-byte a member of
what `list_workspace_paths` currently returns for the same project — not a second, independently
reasoned containment-and-traversal check. The same git-backed enumeration that decides what is
*visible* (respecting `.gitignore`, resolving through `project_workspace.resolve_project_workspace`)
decides what is *readable*, so the two cannot disagree about what a symlink or a `../` resolves to.

**Rejected: an independent resolve-and-check-prefix check.** The usual shape, rejected because
"independent" is the risk rather than the safety feature it sounds like: two sanitizers reasoned
about separately can each be correct and still disagree on an edge case. One list, checked by
membership, cannot disagree with itself.

**Size bound.** 1 MiB, reusing `hub/hub/config.py`'s existing `aw_max_body_size` default rather than
inventing a number. Over the bound the request is **refused, naming the size and the bound, never
silently truncated** — source code read in a viewer is expected to be complete, and a truncated file
reads as a whole one.

**Binary detection.** First 8,000 bytes checked for a NUL byte — git's own heuristic, chosen because
this endpoint is already git-backed for its allowlist, so the two answer the same question the same
way. A binary file is identified as binary rather than rendered as text.

**Rejected: extension or MIME-library detection.** Wrong for exactly the files an operator most wants
to open — extensionless config, a `Makefile`, a suffixless script — and a new dependency for a
question the existing git dependency already answers.

## D8. Opening a file replaces the tree; an index that is a glance does not

`openFile` (`rightPanelStore.ts:284-286`) filters every `kind === "files"` surface out before adding
the file surface: **in T3, opening a file closes the tree.**

**Decided: adopt it for files.** The tree is a launcher; in a ~360px column a tab spent on the thing
that only got you here is a tab wasted.

**Decided: do not generalize it.** The loops index in the loop change deliberately stays open when a
drill-down opens, because it is a governance glance — "what is running right now" — not navigation.
Both changes state the asymmetry so neither is later "corrected" into consistency with the other.

## D9. Reading a document is not attaching one

Today `ComposerSpecControl` fuses two facts: which document is **attached** to the conversation (what
an agent writes into during an explore turn, part of the addressed destination) and which document is
**displayed**. There is one slot, so a second document cannot be read at all.

**Decided: unfuse them.** The attachment keeps its meaning, its ownership and its place in the
destination. Displaying becomes `spec:<document_id>` tabs like anything else. **Closing a spec tab
does not detach the attached document** — closing a reader is not an edit to what the agent is
working on. The composer control is unchanged in this change.

**Rejected: make the attached document simply "the first spec tab."** It would make an act of
window-tidying change what an agent writes into, which is the failure this decision exists to
prevent.

## D10. Resize and overlay generalize by parameter, not by rewrite

`DOCUMENT_COLUMN_BREAKPOINT = CONVERSATION_MIN_WIDTH (380) + SPEC_DOC_MIN_WIDTH (360) +
DIVIDER_WIDTH (1) = 741px` is already *derived* from the two minimums so the breakpoint and the
layout cannot disagree (`ConversationView.tsx:34-38`). The shell computes the same expression from
whichever tab is active. Below it, the existing `Drawer` overlay behaviour applies unchanged,
including the reopen affordance left in the conversation column.

**No new numbers are invented here.** `spec` has a measured minimum; `files` does not, and this change
does not guess one — see D12.

## D11. Accessibility is stated, not inherited

- **Keyboard.** The tab strip and plus affordance are the first controls of their kind in this
  codebase, so nothing exists to inherit: every tab reachable by sequential focus, activatable with
  `Enter`/`Space`, arrow keys moving between tabs while the strip has focus (the ARIA `tablist`
  pattern), and closing a tab reachable by keyboard too.
- **Reduced motion.** `hub/ui/src/index.css:708-715` already collapses CSS `transition`/`animation`
  durations under `prefers-reduced-motion: reduce`, so a CSS-driven effect inherits it for free. A
  JS-driven one does not and needs its own `matchMedia` check — stated because the blanket rule
  silently fails to cover that implementation choice.

## D12. What this change deliberately does not answer

- **The `files` tab's minimum width**, and **tab-strip overflow** once more tabs are open than fit.
  T3 does one native `scrollIntoView` for the newly active tab and nothing else. Both need measuring
  against a real shell rather than guessing, and no number is stated here for either.
- **Whether the shell should subsume the explore button's actions.** D9 makes it possible; per
  `DEC-explore-button` the operator decides while looking at the working shell.
- **A download affordance for a binary file** the viewer refuses to render.
- **A capability-gating `disabledReason` on a tab kind.** No current kind needs one; the shape is
  named so adding it later is additive.
