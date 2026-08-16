# A corpus at scale

## Why this document exists

Written for N1 in the 2026-08-16 night run
(`.claude/autonomous/STATE.json`). The operator raised two related but
distinct worries in the same breath: what the spec corpus looks like once
there are many capabilities and many completed changes, and what the task
board looks like once tasks from all of them have piled up on it. This
document answers both, grounded in what exists in this repository today
(30 capability specs, 17 unarchived changes, 67 archived), not in the
abstract. It ends in recommendations concrete enough for N2 and N2b to
spec from, per its own brief — it does not implement anything.

## 1. What distinguishes a capability document from a change document

The operator has already ruled that capability documents sit outside the
exploring/proposed/approved machine (`STATE.json` `decisions_for_user`).
Reading `openspec/specs/spec-document-authority/spec.md` alongside a
change's delta at
`openspec/changes/archive/2026-08-14-what-the-product-actually-built/specs/task-lifecycle-governance/spec.md`
shows the distinction was already operating in the *filesystem*, just not
yet in the Hub's data model:

| | Capability document (`openspec/specs/<capability>/spec.md`) | Change document (`openspec/changes/<date>-<name>/`) |
|---|---|---|
| Answers | "What does this capability do today?" | "What is proposed to change, and why?" |
| Requirement form | `### Requirement: <statement>` — a complete, present-tense claim | `## ADDED/MODIFIED/REMOVED Requirements` — a diff against the capability's current state |
| Lifespan | Indefinite; edited in place forever | Finite; created, worked, archived |
| Owns tasks/evidence? | No — nothing points a `Task.spec_document_id` at a capability spec today, and nothing should: it is not a unit of decomposed work | Yes — this is what `spec-document-authority`'s "A declared task can state the name the board shows" requirement and `task-lifecycle-governance`'s "Approval creates the work its document declares" requirement are for |
| Read by | Someone asking "how does X work" | Someone asking "what changed and why", during the change's life, and an archaeologist afterward |

The Hub-side gap CLAUDE.md names is real: `SpecDocument.kind` is a free
`String(32)` defaulting to `'change-spec'` (`models.py:1537`) and has
never taken a second value. The distinction above already exists in prose
and in file layout; it does not yet exist as a value the database can
branch on. That is precisely the gap N2 closes by giving `kind='capability'`
a real second meaning, with no phase transitions available to it.

One more asymmetry worth naming for N2: a change document's requirements
are *deltas* (ADDED/MODIFIED/REMOVED against a named capability); a
capability document's requirements are *absolute*. A capability document
authored through the same structured-payload path as a change document
(`spec-document-authority`'s "The agent submits a structured payload and
the Hub renders the document" requirement) needs the payload schema to
know which shape it is rendering — this is a rendering concern, not a
phase concern, and belongs in the schema version's discriminator, not a
new phase value.

## 2. The folder tree at 30+ capabilities and hundreds of archived changes

Current counts, measured this session:

```
openspec/specs/            30 capability directories, one spec.md each (largest: task-lifecycle-governance, 863 lines)
openspec/changes/          17 unarchived + 67 archived = 84 change directories total
openspec/changes/archive/  67, flat, one level, named <date>-<slug>
```

`openspec/specs/` is already flat-by-capability and that scales fine on
its own — 30 directories in one listing is nothing, and nothing in this
exploration recommends restructuring it. The tree that will not survive
scale is `openspec/changes/archive/`: it is a **flat, undated-by-anything-
but-filename list**, and at 67 it is already past the point where a human
scans it productively. `ls openspec/changes/archive` today returns 67
lines in filename order, which is chronological only because the naming
convention is `<date>-<slug>` — an accident of discipline, not a structural
guarantee. Nothing indexes it by capability. Finding "what changed about
task lifecycle" means grepping 67 directory names for a slug that might
not mention "task" at all (`2026-08-13-a-requirement-knows-its-work` is
about task-lifecycle-governance; nothing in its name says so).

This is where the operator's acceptance criterion — "the spec should
still be useful" — actually bites, and where navigability, not tidiness,
is the fix. Two changes, both cheap, both Hub-side rather than filesystem
restructuring (moving 67 directories around is exactly the kind of
churn-for-tidiness the operator did not ask for):

1. **An index by capability, not a folder move.** The Hub already has
   `SpecDocument.path` and `kind` per document; a `capability` (or
   `capabilities: []`, since a change can touch more than one — see the
   `task-lifecycle-governance` archive example above, which lives inside
   `2026-08-14-what-the-product-actually-built` alongside deltas for two
   *other* capabities in the same change) field on the change's row lets
   a UI answer "show me every change that has touched
   `task-lifecycle-governance`" as a query, not a grep. The `specs/`
   subdirectory names inside a change's own folder already carry this
   information structurally (`ls` a change's `specs/` directory to see
   which capabilities it deltas) — the recommendation is to read that
   structure into the index at archive time (see §3), not to invent a new
   place to declare it.
2. **The archive folder itself does not need to be reorganized.** It is
   disk, not a UI; nobody browses it with `ls` once the Hub has an
   indexed, filterable view over the same data (SpecDocument rows carry
   `path`, so the file location is retrievable without walking a
   directory tree by hand). Recommend leaving `openspec/changes/archive/`
   flat. Reorganizing it into per-capability subdirectories buys nothing
   the index above does not already buy, and it breaks the one thing the
   flat structure gets for free today: a change that deltas three
   capabilities has no single "true" subdirectory to live in.

The corpus's actual scale risk is not the *folder tree* — it is the
**capability document's own length**. `task-lifecycle-governance/spec.md`
is 863 lines today after roughly a dozen changes have merged into it over
two and a half weeks. Extrapolated to the lifetime of a "big project", a
handful of high-traffic capabilities will become the ones nobody reads
end to end, which is the actual threat to "the spec should still be
useful" — not disk layout. This is a §3 problem (what merging does to a
capability document's *size and structure*, not just its truth), not a §2
one, and is called out there.

## 3. What happens to the corpus when a delta finishes executing

The operator has already ruled explicit authored merge over automatic
requirement migration (`STATE.json` `decisions_for_user`, rejecting
"the corpus becomes an accumulation rather than a document, and reads
like one"). The archived example read in this session shows what that
already looks like under openspec's convention: a change's `specs/`
subdirectory holds ADDED/MODIFIED/REMOVED deltas against named
capabilities, and `openspec-sync-specs`/`openspec-archive-change` fold
that delta into the capability's `spec.md` by hand (an authored step, not
generation). N2 is porting that convention — proven over 67 completed
merges — into the Hub's data model, not inventing a new one.

What the *authored* part must be, concretely, so N2 has something to
build rather than a restated principle:

- **An explicit merge action**, scoped to one change against one or more
  capabilities, that the operator (never an agent — see the archiving
  ruling below, which is the same authority question) drives: review the
  delta, edit it into the capability document's prose (not just append —
  the archived `task-lifecycle-governance` example above shows a delta
  can restate a requirement's surrounding rationale, not just add a new
  `###` block), and save.
- **A record that the merge happened**, linking the change's id to the
  capability document(s) it touched and the commit/evidence it merged.
  This is the field §2 recommends for the archive index — it is the same
  data, read twice for two different purposes (§2: "what touched this
  capability", §3: "what did this change's merge do").
- **Archiving the change document itself is a separate, later act** from
  merging its delta. A change can be merged into the corpus and still sit
  unarchived for a while (evidence still being gathered, tasks still
  closing) — collapsing "merged" and "archived" into one button would
  force the operator to choose between recording the capability's new
  truth promptly and closing the change document prematurely.

## 4. The task board at scale

This is the operator's open question and the one N2b acts on. Grounding,
verified this session:

- `Task.spec_document_id` exists today, is indexed, and is `nullable=True`
  (`hub/hub/db/models.py:641`) — most tasks today are unlinked, created
  directly rather than declared by a document, and that will stay true
  even at scale (ad hoc work does not go away because a spec corpus
  exists).
- `Task.spec_task_key` (`models.py:642`) is the declared-task correlation
  key, already used to make document re-approval idempotent
  (`task-lifecycle-governance`'s "Approval creates the work its document
  declares" requirement, read in this session).
- The board is **already filtered from outside itself**, proven working
  code, not a proposal: `taskFilterStore.activeTaskIds`
  (`hub/ui/src/store/taskFilterStore.ts`) is a Zustand store holding
  `string[] | null`; `SpecCoverageBar.tsx` calls `onOpenTasks(taskIds)`
  on a coverage row's task-count link; `App.tsx:352-355` wires that to
  `useTaskFilterStore.getState().setActiveTaskIds(taskIds)` and navigates
  to the Tasks tab; `TasksBoard.tsx` reads `activeTaskIds` and filters
  every column by `t.id` membership (verified at
  `TasksBoard.tsx:150-151` and `:237-238`), showing a "Showing N tasks
  linked from the &lt;document&gt;" banner when the filter is active.

That machinery generalizes almost exactly to "scope the board by spec
document" — it is a **new source of `taskIds`, not a new mechanism**.
Concretely, for N2b:

- **Recommended shape**: a spec document's page gains a "show its tasks
  on the board" affordance analogous to `SpecCoverageBar`'s existing one,
  querying tasks by `spec_document_id` (already indexed — no new query
  cost) and calling the same `setActiveTaskIds`. This reuses the exact
  code path already proven by the coverage-bar integration; it is a
  second caller of an existing store method plus one new query, not new
  UI machinery.
- **Cost**: one new API query (`GET /tasks?spec_document_id=...`, or
  reuse of an existing tasks-list endpoint with a filter param — needs
  checking against `hub/hub/api/v1/tasks.py`, out of scope for this
  exploration) plus one small UI affordance (a button/link on the spec
  document page). No schema change. This is deliberately the cheap end of
  what N2b could build, consistent with the operator's "I don't know" —
  it is a filter, not a new information architecture.
- **What pile-up actually means at scale**: the risk is not that the
  board *can't* be scoped — it already can, per above — it is that the
  **default, unscoped view** accumulates every task from every document
  ever declared, most of them long since completed and irrelevant to
  today's work. Scoping-on-demand (the mechanism above) does not fix
  that; it only helps once the operator already knows which document's
  tasks they want to see. The default view still needs an answer, which
  is where archiving (§5) does the actual pile-up prevention.

## 5. What archiving should do to a change's tasks

This is where §3's authorship question and §4's pile-up worry meet, and
it is the one place this exploration recommends a *behavior*, not just an
affordance, because leaving it unspecified is exactly what lets the pile-
up happen.

Recommendation: **archiving a change document retires its declared
tasks from the board's default view, not from existence.** Concretely:

- A task keeps `spec_document_id` pointing at its declaring document
  forever — archiving must not sever that link, or §4's "show this
  document's tasks" affordance breaks for archived documents, which is
  exactly when an operator is most likely to want it (auditing what a
  completed change actually did).
- The board's **default filter** (no explicit scope selected) excludes
  tasks whose declaring document is archived, *unless the task itself is
  still open* (not in a terminal status). A completed task from an
  archived change has no reason to occupy the default view; an open task
  from an archived change is a task someone still has to do, and hiding
  it because its originating document was tidied away would lose real
  work.
- This is a **view-level filter, not a task mutation**. Archiving does
  not change any task's `status`, `assignee`, or any other field — it
  only changes what the *default* board query returns. This keeps the
  operator-only archiving act (§1, and the binding ruling below) cheap
  and reversible: unarchiving a document (if that is ever a thing) is
  just a filter flipping back, not an undo of task mutations that never
  happened.

This composes directly with N2: whichever change ships the `archived`
phase value is the natural place to add the default-view exclusion,
since both touch the same query surface (a task list endpoint gaining an
"exclude tasks whose document is archived" clause). Per the coordination
note in N2b's own brief, this behavior is stated once here and should be
implemented by whichever of N2/N2b lands second, not duplicated.

## Recommendations, summarized for N2 and N2b

1. **N2**: `kind='capability'` documents render from an absolute-
   requirements schema (no ADDED/MODIFIED/REMOVED), distinct from
   `kind='change-spec'`'s delta schema — a rendering/schema concern, not
   a new phase.
2. **N2**: add a merge-record concept (change id → capability document
   id(s) it merged into, plus what merged) as part of the archive
   transition's data, not a separate feature — this is the same data §2
   wants for "what touched this capability" and §3 wants for "what did
   this merge do." Whether it is a new table or a column/JSON field on
   the existing archive event is an implementation choice for N2's
   design.md, not decided here.
3. **N2**: merging a change's delta into its capability document(s) is
   authored (operator reviews and edits), and is a distinct, possibly
   earlier act from archiving the change document itself.
4. **N2b**: build the "scope the board to one spec document's tasks"
   affordance by adding a second caller of the existing
   `taskFilterStore.setActiveTaskIds` mechanism (already proven by
   `SpecCoverageBar`) — no schema change, no new filtering mechanism.
5. **N2b** (or whichever of N2/N2b ships second, stated once): the
   board's default view excludes tasks whose declaring document is
   archived AND whose own status is terminal. Open tasks from archived
   documents remain visible by default; nothing is ever hidden from a
   document-scoped view.
6. **No folder reorganization.** `openspec/specs/` and
   `openspec/changes/archive/` both stay in their current flat shapes;
   navigability at scale is a Hub-side index/query problem (capability ↔
   change linkage, §2), not a filesystem problem.

None of this weakens or re-opens the operator's settled rulings: archiving
stays an operator act (§3, §5 assume it, do not re-derive it); the corpus
absorbs a change by explicit authored merge, never automatic requirement
migration (§3); capability documents stay outside the phase machine (§1).
