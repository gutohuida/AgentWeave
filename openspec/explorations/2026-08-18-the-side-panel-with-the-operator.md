# The side panel, designed with the operator

**Status:** exploration. **Supersedes the recommendations** in
`openspec/explorations/2026-08-18-the-side-panel-family.md` — not its research, which is sound and
still worth reading for the T3 study and the code survey, but its *conclusions*, six of which the
operator overturned in this session.

That earlier exploration says so about itself, in its own opening: it was written by an unattended
firing, *"no operator was present to converse with, so this is written as analysis with
recommendations named explicitly as recommendations, not decisions."* This document is that
conversation finally happening. Where the two disagree, this one is the decision and that one is the
research it was decided against.

Written 2026-08-18 14:45–15:30 in an interactive session. Every code claim below was read this
session and names its file and line.

---

## 0. What the operator overturned, in one table

| The unattended exploration recommended | The operator decided |
|---|---|
| All three panels are singletons; no multi-instance (§3 item 5, §11.2) | **Index tab → keyed detail tabs.** Multi-instance is the point, not the exception |
| Which panel is active is **per-conversation** destination state (§5, §11.3) | **Per-project.** Reopen the panel and it restores that project's tabs |
| A fixed strip of three panels, plus a plus menu offering the same three (§4) | **The strip holds only open tabs.** The plus adds one that isn't there |
| The loop tab shows "the conversation's loop" (§6) | **Project-wide, with a loop picker.** A conversation has no loop |
| The spec panel stays the one conversation-attached special case (§8) | **Spec joins the pattern.** Read one document while attached to another |
| A panel-side, job-scoped live-ness lookup (§6.2, and the change's D6) | **Deleted.** The loop change's D13 already owns this and rejected that shape by name |

And one thing neither document had at all, raised by the operator from the philosophy rather than
from the code: **nothing should be deletable.** See §5.

---

## 1. The loop tab is project-wide, because a conversation has no loop

The unattended change specced the loop tab as showing *"the loop bound to the conversation's job."*
No such binding exists.

- `Conversation` (`hub/hub/db/models.py:369-405`) carries `project_id` and `agent`. There is no
  `job_id` and no `loop_id`.
- The only link runs the other way: `JobRun.conversation_id` (`models.py:1194`), documented as
  *"what this firing actually used."*
- `scheduler.py:337-343` — when `session_mode` is `"new"`, which is the default, **every firing
  creates a fresh conversation.**

So a loop that fires twenty times scatters across twenty conversations, and the conversation the
operator is actually sitting in — an ordinary operator↔agent thread, `origin="operator"` — has no
loop at all.

```
   THE OPERATOR'S CONVERSATION            THE LOOP
   ┌──────────────────────┐               ┌──────────────┐
   │ conv-a1b2            │               │ job-7f3      │
   │ origin: "operator"   │               └──────┬───────┘
   │  "not part of a loop"│                      │ fires
   └──────────────────────┘            ┌─────────┼─────────┬─────────┐
                                       ▼         ▼         ▼         ▼
                                   conv-c3   conv-d4   conv-e5   conv-f6
```

This is not an incidental gap that a future data model change might close. The loop change's own
decision — continuity is re-derived from durable state, never from a resumed conversation
(`2026-08-18-a-loop-writes-its-own-queue` D4, and the operator's reasoning that a loop exists partly
for *"context management since it's not a single unstopped session with more and more polluted
context"*) — **guarantees** `session_mode` stays `"new"` for loops. The fan-out is the design, not a
defect.

**Decided: the loop surface is project-wide.** The operator picks which loop to look at.

> "It's a project wide interest. The loop tab I can chose which loop I want to see."

**A gap this exposes:** `LoopSummary` (`hub/hub/schemas/jobs.py:70-81`) carries `id`, `purpose`,
stop state, queue counts and `open_questions` — **no name.** The label rendered on the Jobs page
today is the *job's* name (`JobCard.tsx:197`), and `purpose` is free text defaulting to `""`. A loop
picker needs a label; `LoopSummary` cannot currently supply one.

## 2. The strip holds open tabs; the plus adds

The unattended spec contained a contradiction: a *"fixed, literal registration list — `spec`, `loop`,
`files`"* rendered as the strip, **and** a plus affordance that *"SHALL present every registered
panel... No registered panel SHALL be hidden or omitted."* With three fixed singletons, the plus menu
always offers exactly the three tabs already on screen. One of the two affordances is dead weight.

**Decided: T3's model.** The operator:

> "We shouldn't show all of them at all times. We add with the plus sign like t3... On the side panel
> we have only one tab active is just like a tab from a browser so to speak. The plus just adds
> another tab with information and we click to navigate between the tabs but the whole panel is
> dedicated to one tab at a time of displayed information."

## 3. Index → detail, with keyed ids

T3's store (`testbed/scratch/t3ref/src/rightPanelStore.ts:27-47`) models a surface as a
discriminated union whose `id` is a template literal — singletons take a fixed id, drill-downs take a
keyed one:

```
  INDEX TAB (fixed id)                DETAIL TAB (keyed id, multi-instance)
  id: "files"      ──── click ────▶   id: `file:${relativePath}`
  id: "loops"      ──── click ────▶   id: `loop:${loopId}`
  id: "specs"      ──── click ────▶   id: `spec:${documentId}`
```

Reopening an already-open keyed tab does not duplicate it: T3 bumps a `revealRequestId` counter
(`rightPanelStore.ts:295`) so the panel re-reveals or re-scrolls instead. That is the correct
behaviour for us too and costs nothing to adopt.

### 3.1 Key by id wherever an id exists

`rename_spec_document` is an **agent-callable MCP tool**. A tab keyed `spec:<path>` dangles the
moment an agent renames the document — pointing at nothing, for a document that still exists. T3 keys
files by path because a file has no identity other than its path; that reasoning does not transfer to
loops or spec documents, which have real ids.

| Tab | Key | Survives |
|---|---|---|
| `loop:<loop_id>` | id | rename, stop, complete, archive |
| `spec:<document_id>` | id | rename, phase change, archive |
| `file:<path>` | path | nothing else available — needs reconciliation |

**Only `file:` tabs can dangle**, which is exactly the case T3 already solves with
`reconcileFileSurfaces` (`rightPanelStore.ts:79`).

### 3.2 Opening a file replaces the tree; the loops index stays

`openFile` (`rightPanelStore.ts:284-286`) filters every `kind === "files"` surface out before adding
the `file:` surface. In T3, **opening a file closes the tree tab.** The tree is a launcher, not a
destination — and in a narrow column a tab spent on the thing that only got you here is a tab wasted.

The operator accepted this for files and rejected it for loops:

> "You're right about the file tree... Opening files behave like t3, loops behave like we described."

The asymmetry is principled: a file tree is pure navigation, while a loops **index** is itself the
governance glance — "what is running right now" — and is worth keeping open beside a drill-down.

## 4. Persistence is per project, and the shell needs a migration

T3 persists per thread (`byThreadKey`, keyed by `scopedThreadKey(ref)`). **We deliberately diverge:
per project.**

> "Each project we might want to have different tabs configurations... when we reopen the side panel
> it loads what was being used (For that project)."

Panel **width** stays what `hub/ui/src/components/spec/specPreferences.ts` already persists — one
global value — since nothing suggests the operator wants different widths per tab.

Persisting keyed tabs means persisting pointers to things that can stop existing, so the shell needs
machinery the unattended spec had none of. T3's is worth copying whole
(`rightPanelStore.ts:49-51, 164, 237-248`):

- A **versioned** storage key with a real migration function — T3 is on storage version 9 because
  this shape genuinely changed nine times.
- **Reconciliation** of keyed tabs against what exists (`reconcileFileSurfaces`,
  `reconcileBrowserSurfaces`).
- Two rules worth taking verbatim: *"A migration that dropped every surface must not reopen an empty
  panel"* — `isOpen` requires `surfaces.length > 0` — and if the dropped surface was the active one,
  fall back to the first survivor rather than rendering an open empty panel.

## 5. Nothing is deletable — the philosophy applied

The operator, unprompted by anything in either document:

> "Loops should never be deleted. We need the information is tracking. Don't forget about the
> philosophy. Governance and traceability. We shouldn't lose information."

**This is currently false in shipped code:**

- `Loop.job_id` is `ForeignKey("ai_jobs.id", ondelete="CASCADE")` (`models.py:1208-1210`).
- `DELETE /api/v1/jobs/{job_id}` exists (`hub/hub/api/v1/jobs.py:482`).
- `delete_job` is one of the agent-callable MCP tools (`hub/hub/mcp_server.py:533`).

So one call — available to an agent — destroys a loop's row, its purpose, its stop reason, its
stopped-at, by cascade, silently.

**The irony worth recording:** the loop change's own D14 forbids reassigning `Task.loop_id` after
creation, reasoning that *"reassigning a task between loops would make a loop's queue history unable
to answer what work it was ever given."* It bolts the window while the door stands open. The
archival decision belongs in that change because that change already argues for exactly this
principle.

**Specs already got this right** and are the model to copy: `ARCHIVED = "archived"`, *"There is no
transition out of `archived`"*, and *"only the operator can archive a document"*
(`hub/hub/spec_lifecycle.py:31, 49, 241`).

**Decided:** nothing is deletable — loops **or** plain jobs. Everything archives.

## 6. Complete and archived are two different axes

The operator's sharpest correction, and better than the single-lifecycle model both documents assumed:

> "The loop can be marked as complete. The archivability is just to clean the UI."

```
   LIFECYCLE — what happened                 VISIBILITY — housekeeping
   running ──┬──▶ complete  (queue drained)  ──▶  archived
             └──▶ stopped   (stop_at, operator,   operator only
                             queue exhausted)     hides from lists
                                                  destroys nothing
```

Two consequences fall straight out:

1. **You cannot archive a running loop.** Archiving one would hide unattended work that is still
   firing — the precise governance failure the whole feature exists to prevent. This also replaces a
   clumsier rule considered earlier in the session ("archiving must force `enabled = False`"):
   requiring stopped-or-complete first makes that unnecessary, because `AIJob.enabled` is already
   false by then. `enabled` is the *only* gate on firing (`scheduler.py:153, 227, 275`), so getting
   this wrong means an archived loop keeps running.
2. **`complete` must be a real state value.** `Loop.stop_reason` is `Text, nullable`
   (`models.py:1226`) and `scheduler.py:102` writes the English string `"loop queue is empty"`. A
   loops index that wants to show *"4 complete · 1 stopped early · 2 running"*, or filter on it,
   cannot string-match prose. `stop_reason` stays as the human explanation beside the value.

## 7. `delete_job` becomes `archive_job`, and always asks

If nothing is deletable, the agent-callable `delete_job` has no valid target. The operator:

> "Agent can archive only with the explicit direction from the user. So the mcp endpoint becomes
> archive."

**The existing gate does not provide "explicit direction."** `_require_agent_job_allowance`
(`jobs.py:21-40`) checks `project.allow_agent_jobs` — a standing, project-level boolean. Once on, an
agent may call job mutations unattended indefinitely. The endpoint's own error message treats the two
as alternatives: *"requires operator approval **or** an enabled allowance."*

**Decided: `archive_job` always produces an approval card, independent of the run's permission
posture.** The standing allowance grants the *capability*; the card supplies the *direction*. This
makes `archive_job` the first MCP tool with an always-confirm rule — a precedent set deliberately
rather than inherited from `create_job` by copy-paste.

Archiving a **loop** stays operator-only regardless, mirroring `spec_lifecycle.py:241`.

## 8. The spec tab joins the pattern, unfusing two things

Today one control means two things at once. The composer's `Spec: <title>` pill
(`ComposerSpecControl.tsx`) simultaneously says *"this document is attached to this conversation"* —
what the agent writes into during an explore turn — and *"this document is what the right side
shows."* There is exactly one document slot, so you cannot read one document while attached to
another.

> "It would be nice to navigate other specs while we have one spec attached."

**Decided:** `specs` index (today's modal picker) plus `spec:<document_id>` detail tabs. The composer
pill keeps its meaning unchanged — which document the agent writes into — and reading becomes tabs
like everything else. **Closing the spec tab does not detach the document.**

This also makes the shell provable on its own: a `specs` index and two `spec:<document_id>` tabs open
at once, while the composer still names the attached document, exercises every mechanic in the shell
without a loop or a file endpoint existing yet.

**Archived documents:** archived is terminal and the document still exists, so its tab survives and
shows the archived marker `SpecDocumentPanel` already renders. Consistent with §5 — nothing is lost.

## 9. Two changes contradicted each other, and the loop change wins

Written twenty minutes apart by different unattended firings:

- **Loop change D13** (`design.md:366-374`) — *"`JobRun.status` is `"fired"` or `"failed"` — there is
  no value for a firing in progress... D11's rule needs this fact, and so does the loop panel's 'is
  an agent working right now' (`2026-08-18-one-shell-three-panels`). It should be **one helper both
  callers use**, not two joins."* And explicitly: *"**Rejected:** deriving 'is a firing running' by
  joining `JobRun.conversation_id` to `Run.status == "running"` and leaving the column alone... it
  keeps a lie in the table."*
- **Panel change D6** — *"a new, job-scoped live-ness lookup... keyed by the loop's `AIJob.id` via its
  most recent `JobRun.conversation_id`."*

Panel D6 chose precisely the approach loop D13 rejected by name. **The loop change wins** — it owns
the data layer, and a `JobRun.status` that cannot state its own value is a defect independent of who
reads it. Panel D6 is deleted; the loop tab consumes D13's helper.

## 10. Scope: the work splits, and the panel change is a rewrite

The operator's call — *"2 and 4 can be this spec"*:

```
  LOOP CHANGE  (2026-08-18-a-loop-writes-its-own-queue)   ← absorbs
  ├─ loop + job archival, complete-as-a-state, archive_job     (§5, §6, §7)
  ├─ loops index tab + loop:<loop_id> detail tabs              (§1, §3)
  ├─ panel D6 deleted in favour of D13's single helper          (§9)
  └─ _batch_loop_summaries missing "assigned" — fixed beside its cause (D3)

  PANEL CHANGE  (2026-08-18-one-shell-three-panels)       ← rewritten as
  ├─ the shell: keyed tabs, plus menu, per-project store,
  │   versioned migration, reconciliation, resize/overlay      (§2, §3, §4)
  ├─ specs index + spec:<document_id> tabs; SpecDocumentPanel re-hosted (§8)
  └─ files tree + file:<path> tabs + the content endpoint
```

The dependency **inverts**: the panel change used to depend on the loop change's data; now the loop
change depends on the panel change's shell. Clean either way — the panel change owns the container,
the loop change owns its tenant's content, and the panel change stays provable alone via specs.

The panel change is a **rewrite, not an amendment**: its descriptor model, its persistence decision,
its D6, and four of its Non-Goals are contradicted rather than merely thinned by the above.

## 11. Open, and deliberately not invented

- **The file panel's minimum width**, and **tab-strip overflow behaviour** in a narrow column. The
  existing spec says each panel declares "its own measured minimum" and no measurement exists for
  any panel but `spec` (`SPEC_DOC_MIN_WIDTH = 360`). A tree plus an inline preview at 360px was never
  evaluated, and with keyed multi-instance tabs the strip can now hold more tabs than fit. T3 does one
  native `scrollIntoView` for the newly active tab and nothing else. Not invented here.
- **Whether a plain job's `archive_job` is agent-callable at all**, versus operator-only like a
  loop's. §7 settles that archiving a loop is operator-only and that the agent path always asks; it
  does not settle whether an agent should be able to archive a bare job even with a card.
- **File content size and type bounds** — carried over unresolved from the earlier exploration §10.
- **Whether the loops index should show archived loops behind a filter**, or hide them entirely.

## 12. What this session did not verify

- **Nothing was driven live.** No shell exists; every conclusion is read from code and from T3's
  recovered source, not observed in a browser. This remains true across three consecutive sessions.
- **The `"assigned"` fix a firing reported making** to `_batch_loop_summaries` was not independently
  verified here either, carried forward from handoff 0056.
- **Whether `run_task_binding.py:250-254` moves a loop-claimed task off `assigned` automatically** —
  still open, as the panel change's own D6 admitted.
