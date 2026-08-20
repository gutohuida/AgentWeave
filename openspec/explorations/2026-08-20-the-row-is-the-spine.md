# Exploration — The row is the spine (2026-08-20)

**Status:** Explored with the operator, 2026-08-20. Supersedes four stubs written earlier the same
day (`adopting-documents-that-already-exist`, `the-spec-landing-page`,
`agents-starting-their-own-documents`, `who-implements-this-spec`) — they turned out to be one
problem, and holding them apart was hiding the shape.

Decisions the operator took during this session are marked **DECIDED**. Everything else is open.
Every claim below was checked against the code; `file:line` is given so the next reader can
re-check rather than trust.

---

## 1. The spine

A specification document has two halves: **a file on disk**, and **a row in `spec_documents`**. The
file is the document. The row is what lets the product do anything *with* it.

```
   spec/capabilities/agent-charter/spec.html        (34 of these, in git)
                    │
                    ├──── READ PATH ─────────────▶  browse · rail nav · open · render   ✅ WORKS
                    │     GET /specs is disk-driven
                    │     titles + kinds from spec/index.json
                    │
                    └──── needs a ROW ───────────▶  phase · requirements · coverage ·   ❌ BLOCKED
                                                    evidence · tasks · assignment
```

Everything the operator asked for in items 5, 9 and 11 lives on the right-hand side. **Adoption —
minting a row from a file that already exists — is the gate all three are behind.**

## 2. Three things the earlier framing got wrong

**The corpus is not invisible.** Handoff 0062's finding 17 and handoff 0063 both say the Spec tab
shows nothing. It isn't so. `SpecPage` and `SpecRailNav` call `useSpecList` → `GET /specs` →
`spec_documents.compute_state()` (`spec_documents.py:393-423`), which is **entirely disk-driven**:
it walks `spec/`, reads `spec/index.json` for titles and kinds, and returns all 34 documents. Rows
are merged in afterwards and contribute exactly two fields (`api/v1/spec.py:106-113`): `phase` and
`document_id`, both `null` without a row.

The row-less case was designed for, not overlooked — `hub/tests/test_spec_archive.py:125` states it
outright, and `specNavigation.ts:135,178` falls back to `deriveTitle(entry.path)` for display.

The accurate description is **readable but inert**. You can read the corpus. You cannot act on it.

**The blocker is a weld, not a missing capability.** `POST /documents` fuses two operations:

```
POST /documents  (api/v1/spec.py:1131-1153)
     │
     ├──▶ spec_lifecycle.create_document()       mints the ROW. pure database.
     │    spec_lifecycle.py:121-156              takes no workspace — cannot touch disk.
     │
     └──▶ spec_service.save_document(placeholder)  WRITES THE FILE.
          api/v1/spec.py:1141-1151                 "title": body.title or UNTITLED
                                                   renders over whatever is there.
```

The separation already exists one layer down. `create_document` is pure row-minting. **The route is
what welds the destructive half on**, and that weld is the only reason a corpus already on disk
cannot be brought in.

**The row *is* the filing.** `build_index` (`spec_documents.py:245-273`):

> *"Only documents that are both on disk and known to the Hub are filed."* A file with no row is
> reported as `unindexable_document` and never filed — *"the Hub has no title or kind for it, and
> guessing one would put an invented name into a file that outlives this machine."*

This is why `project-instructions` and `quiet-hours` sit at `unfiled` permanently: no row, so
reindex refuses to invent a title for them. Being in the corpus *means* having a row. That kills the
idea (mine, briefly) of using `unfiled` as an approval gate — see §5.

## 3. How much is already built

More than expected. Adoption composes existing parts rather than adding a subsystem:

| Piece | Where | What it does |
|---|---|---|
| `discover()` | `spec_documents.py:81` | walks `spec/`, every `.html`, path-safety validated, diagnostics per exclusion |
| `extract_payload()` | `spec_payload.py:297` | reads the embedded JSON block back out; returns `None` rather than guessing |
| `reindex_from_file()` | `spec_index.py:292-315` | reads a file, writes **database rows only** — verified read-only on disk |
| `POST /spec/reindex` | `api/v1/spec.py:1036` | rebuilds requirement index **and** `index.json` |

**All 34 corpus files carry a payload block** (`id="aw-spec-payload"`), verified 34/34.

`reindex_project` (`spec_index.py:318-331`) iterates `list_documents()` — **existing rows only**. It
is adoption's whole machinery, pointed at the wrong set. And `write_index` has exactly one caller,
the reindex route (`api/v1/spec.py:1076`), so nothing else files anything.

## 4. Item 5 — the landing page is a document, and that model holds

**DECIDED.** There is no landing screen and does not need to be one. Arriving at the Spec tab with
no document, `SpecPage.tsx:41-50` resolves the manifest `home` and opens it —
`spec/agentweave.html`, 343 lines, `kind: system-map`. The operator's *"the spec main page is weak"*
means **that document's content is thin**, not that a screen is missing.

What they want there: an overview of the project, and the path to every other feature and spec —
*"the main spec to understand the general gist of the features and navigate between the deep dive on
the other files."*

**DECIDED — two pieces, different in kind:**

```
  spec/agentweave.html
  ┌──────────────────────────────────────────────┐
  │  AUTHORED NARRATIVE                          │  operator's. prose. stale-tolerant.
  │  what this project is, the gist              │
  ├──────────────────────────────────────────────┤
  │  ◆ GENERATED MAP ◆                           │  from spec/index.json.
  │  capabilities, grouped by parent, linked     │  rebuilt on reindex.
  │  never hand-edited                           │  structurally cannot go stale.
  └──────────────────────────────────────────────┘
```

`spec/index.json` already holds `path`, `title`, `kind`, `status`, **`parent`** and `order` for all
33 filed documents — a maintained table of contents with hierarchy support **that nothing currently
renders**.

This is what makes the operator's *"each new spec created needs to reflect a little bit on the main
spec"* affordable: **the map maintains itself.** Had every document creation edited shared prose,
the result would be tone drift and write contention on one file.

**The other half — documents that link back — is a renderer gap.** `render_document`
(`spec_render.py:328`) takes payload, identifiers, phase and rigor. It knows **nothing about the
corpus**: no home, no parent, no siblings. Every document renders as a self-contained island. That
is structurally why there is no navigation, and it is what *"update how we generate specs"* means.

**Open:** is the narrative prompted for at document creation ("one line on how this fits the whole"),
or purely the operator's to maintain?

## 5. Item 9 — agents creating documents

**RECOMMENDED, NOT YET CONFIRMED.** Three options were considered:

| | gates the corpus | matches the ask | cost |
|---|---|---|---|
| **1. Agent creates directly** | already, at the write layer | ✅ "from an endpoint" | MCP tool + auth |
| 2. Request + operator accepts | yes | ✗ blocks the agent mid-flow | new card + queue |
| 3. Create into `unfiled` staging | **no — the gate is illusory** | ✅ | a new flag, to make it real |

**Option 3 was proposed and then withdrawn.** The tree the operator sees is disk-driven, so an
unfiled document is *already visible*; and any agent-created document needs a row (or
`save_document` cannot write its file), and a row gets filed on the next reindex. The "accept" step
does not exist. Manufacturing one means inventing a flag, which is a larger claim than the feature
earns.

**Option 1 is recommended because the thing worth protecting is already protected.**
`spec_service.save_document` (`spec_service.py:106`):

> *"A capability document is written only by the operator — never by an agent, whatever its run."*

The current-behaviour corpus — the 34 documents, the part with accumulated value — is unwritable by
agents one layer below whoever calls the endpoint. An agent that can create documents can only
produce change-specs and explorations, which is exactly what an agent should be able to start.

**One requirement this carries:** `kind` must be restricted **at creation**, not only at write.
`create_document` sets `phase=CURRENT` for `kind="capability"` (`spec_lifecycle.py:151`), so an
unrestricted tool would let an agent mint an empty capability document sitting in `current` that it
then could not fill in.

Keep `unfiled`/filing as the **arrangement** concept feeding §4's map. Do not repurpose it as a gate.

Against this stands the existing, deliberate rule (`mcp_server.py:905`): *"The document must already
exist: the operator starts an exploration, and you fill it in."* Relaxing it is a decision about who
the spec lifecycle belongs to, and it should be taken explicitly rather than routed around.

## 6. Item 11 — routing work by complexity, not by agent

The operator's original ask was a field naming the implementing agent. **They replaced it during
this session with something better.**

**DECIDED — complexity tiers, with a project-level mapping.**

```
  IN THE SPEC (durable)              IN THE PROJECT (moves freely)
  ─────────────────────              ─────────────────────────────
  task: "migrate the index"          high    ─┬─▶ runner "Deep work"
  complexity: high                             ├─▶ runner "Deep work (codex)"
                                               └─▶ ...
        │                            medium  ──▶ ...
        └──────────────┬─────────────low     ──▶ ...
                       ▼
              approval routes each task to a roster agent
              whose Agent.runner_id is in that tier's set
```

Writing `claude-opus-5` into a spec would couple a durable corpus to today's model lineup — Opus 6
ships and 34 documents are quietly wrong. The tier keeps the spec true; the mapping absorbs the
churn in one place.

**DECIDED — the mapping is a table in the project, operator-editable.**

**DECIDED — one-to-many.** A tier maps to *several* runners. This is what lets approval actually
distribute: three agents holding the `high` tier means three tasks can start at once. It is also the
parallelism mechanism (§7).

**Point it at runners, not model strings.** `Runner` is *"reusable execution capability: which CLI,
which model"* (`models.py:302-330`) — a complexity tier is a statement about required execution
capability, so this is a reference rather than a translation. Matching becomes a foreign key on
`Agent.runner_id` instead of string comparison; deleting a runner breaks the mapping visibly instead
of leaving it pointing at a dead name; and `Runner.flags` can carry **effort**, which is often the
cheaper way to buy "harder" than a bigger model is.

**What is missing is one hard-coded line.** Approval **already materialises tasks** —
`spec_tasks.materialise()` (`spec_tasks.py:89`), called from `api/v1/spec.py:1253`. It resolves
requirements, links them, dedupes against hand-made tasks, respects an owning `Loop`, and preserves
unresolvable names as free text. Then, at `spec_tasks.py:192`:

```python
assignee=None,
assigner=None,
```

Auto-assignment is not a subsystem to build. It is a value with no source.

**Also missing: the payload has nowhere to put any of this.** `spec_payload.Task` (`:98-108`) is
`key`, `title`, `description`, `requirements`. No complexity, no dependencies.

**Model choice is a spend decision.** An agent writing "this needs Opus 5" is an agent committing
the operator's money — which is why the operator's instinct to put a model-selection step in the
exploration is right. There is precedent for the guard: `decide_evidence` already refuses to let an
agent decide evidence it produced (`mcp_server.py:1127`).

**Open — routing:**

1. No roster agent holds the mapped tier — refuse approval, or create the task unassigned with a
   stated reason?
2. Several hold it — round-robin, least-loaded, or ask?
3. `Agent.runner_id` is nullable; an unbound agent has no model. Invisible to routing?
4. `agent_budget` (8, `api/v1/agents.py:1377`) caps the roster and therefore caps parallelism.
5. Does assignment **start** work, or only fill in a name? Approving a document and having eight
   agents wake up is either exactly right or alarming.
6. What are the tiers? `high/medium/low` is the obvious three; a tier could map to **(model, effort)**
   rather than a model alone.

## 7. Parallel work

**DECIDED — parallelism comes from more agents, not from one agent running several conversations.**

The scheduler forbids the latter anyway. `turn_scheduler.py:42`:

```python
if running.scalar_one_or_none() is not None:
    return ScheduleResult(waiting_reason="agent is already running")
```

and it then selects a **single** conversation's entries (`turn_scheduler.py:63`). An agent is a
single-threaded worker with several mailboxes.

More decisively, there is **nothing to gain** from changing that. `Conversation.provider_session_id`
(`models.py:416`) puts the provider session on the **conversation** — *"AgentWeave-owned durable
conversation, independent of provider session identity."* One agent across three conversations is
three independent sessions sharing **no context**; it is three agents wearing one name tag, with the
name tag being precisely what makes it untrackable. Canonical context is assembled per *run*, so
three agents cost no more context than three conversations would.

**The framing that falls out: the agent is the identity; the conversation is the worker thread.** An
agent does not "know" things — its conversations do. Spawning agents for parallelism is the model
working as designed, not a workaround.

**DECIDED — parallelism is the operator's choice.** *"He could be using a restricted token plan and
need to do things one at a time."* A project setting — **max concurrent runs, default 1** — beside
the budgets that already exist. Opt in; never discover it.

### Dependencies in the spec

**Wanted:** the spec should say which tasks can run in parallel and what the dependency tree is, and
agents should be instructed to produce it.

This is small, because `key` is already *"a stable handle for this task, unique within the
document"*:

```python
key: str            # exists
depends_on: [str]   # keys of sibling tasks. the DAG, for free.
complexity: str     # the tier from §6
```

Anything with no unmet dependency can start now. Two things ride along: the `Field(description=...)`
strings in `spec_payload.py` **are** the agent-facing instructions (*"One concrete unit of work, not
'build the whole thing'"*), so dependencies get taught the same way; and `materialise()` can enter
dependent tasks as `blocked` rather than `pending`, so the board shows the wave structure instead of
twenty tasks all claiming to be ready.

### The budgets — the operator's worry was right, the named budget was not

| | what it is | drains under parallel work? |
|---|---|---|
| `hop_budget` (6) | max **depth** of a delegation chain (`inbound_queue.py:91`) | **no** — a depth limit, not a pool |
| `turn_delivery_cap` (10) | entries batched into one turn — **already scoped to one conversation** | no |
| `agent_budget` (8) | roster size | it is the ceiling on parallelism |
| `token_budget` | project-wide consumable pool | **yes — this is the one** |

`token_budget` already behaves well: `turn_scheduler.py:69` blocks **autonomous** turns when
exhausted but lets operator-initiated ones through, so the operator's own work is never starved by
their agents' spending. No change proposed here; recorded so the next reader does not re-derive it.

## 8. The model catalog is code, and that is the real bottleneck

The tier mapping makes model churn cheap — but only the *mapping* half.

```
  Opus 6 ships:
   1. add ModelDescriptor to model_catalog.py:136   ◀── CODE CHANGE + Hub release
   2. point a Runner at it                              operator UI, seconds
   3. update the tier mapping                           operator UI, seconds
   4. 34 spec documents                                 untouched — this is the win
```

Step 1 is the bottleneck. `api/v1/runners.py:24` refuses a model the catalog does not declare:
*"Runner management offers catalog models, not free-typed text."* So a new model cannot be used
until someone ships a Hub release — in a product whose value is orchestrating frontier models.

The system half-anticipated this: an already-stored unrecognised model is **left alone**, and
`RunnerResponse` carries a flag for *"model is set but the catalog does not declare it"*. The
display path for an unknown model exists; only create/patch refuses one.

**DECIDED — the refresh is a button backed by the existing worker, not a scheduled job.**
`hub/hub/worker.py`:

> *"One-shot, out-of-band model invocations owned by the Hub. A worker reads one
> deterministically-assembled prompt and returns one schema-validated answer."*

and, load-bearing:

> *"**No `Run` row is recorded, deliberately** — a worker run recorded under an agent's name makes
> that agent look busy and stalls its queue until the worker returns."*

Costs land in `worker_invocations`; `conversation_titles.py` is the proto-worker it generalises;
checkpoints already use it. So: **button → worker → schema-validated model list → proposed catalog
entries → operator accepts.** No roster slot, no queue interference.

**Open — and worth a spike before designing around it:** can a worker reach the internet? It builds
`claude … -p <prompt>` and `codex exec --skip-git-repo-check --json` (`worker.py:131,133`) with **no
tool flags at all**. A catalog refresh is worthless without current information. If it cannot, the
fallbacks are sound: the Hub fetches a feed and the worker only normalizes it, or the worker parses
release notes the operator pastes in.

**Open:** an agent that can update the catalog can expand what it is allowed to spend money on. That
`allow_agent_jobs` defaults to `False` suggests this caution is already native. Propose-and-accept
is the likely answer — which is `D-a13`'s shape for the **third** time in this session (agent
requests a task; agent requests a document; worker proposes a catalog entry). That recurrence is
probably telling us to build it once, generically.

## 9. The carve-up

Ordered by dependency, not by appetite.

| # | Change | Why here |
|---|---|---|
| **1** | **Document adoption** | The gate. Splits the weld: mint a row from an existing file without writing it. Everything else waits on this. |
| 2 | **Spec landing page** | Narrative + generated map from `index.json`; give `render_document` corpus context so documents link back. |
| 3 | **Agent-created documents** | MCP tool + run-credential auth + `kind` restriction at creation. Small. |
| 4 | **Tiers, dependencies, routing** | Payload fields (`complexity`, `depends_on`), the tier→runners table, DAG-aware `materialise`, max-concurrent-runs. The largest. |
| 5 | **Catalog as data + refresh worker** | Independent of all the above, and carries its own governance question. |

**Adoption's own rules — DECIDED:** *"It should look at the file but it should compare with the
database. But it should trust what we have on the file."*

Worth naming what that overturns, because it is deliberate: `content_digest` currently treats an
externally-edited file as **a conflict to report and never silently resolve**. The operator's rule
keeps the reporting and drops the never-resolve. So adoption adopts from the file **and states in
its response where the row disagreed**. Silent trust would be a different rule than the one given.

**Still open for adoption:**

- A file with **no payload block** — refuse, or derive a minimal row from the `aw-spec-*` meta tags?
  `extract_payload` deliberately does not guess. (Academic for the 34; the rule outlives them.)
- What `phase` an adopted document lands in. A file can claim any `aw-spec-status`, and the row
  exists precisely so phase does not live where the gated party writes it. "Trust the file" was
  decided for *content* — whether it extends to *phase* was not asked.
- One document at a time, or a directory sweep? The corpus wants the sweep; §5's agent case wants
  the single.
- Whether `content_digest` is set from the file as found — which asserts "this file is as the Hub
  would have written it", possibly not byte-true for a converted corpus.

## 10. Not covered here

Three of the operator's twelve keep their own stubs, untouched by this exploration:
`2026-08-20-showing-the-reasoning-chain.md` (item 1),
`2026-08-20-the-theme-does-not-survive-a-restart.md` (item 3),
`2026-08-20-how-long-an-open-document-should-follow-you.md` (item 7).

`2026-08-20-an-agent-messaging-its-other-conversation.md` (item 10) is touched only in passing: the
operator asked whether an agent asked to test something can reply into the exact conversation it was
asked from. It can — `send_message` takes `conversation_id` (`mcp_server.py:180`), and no self-send
guard was found. That stub still owns the question.
