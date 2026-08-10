# Exploration — Coordinator: the terms it rests on, and the format it would execute

**Date:** 2026-08-10
**Change:** `openspec/changes/2026-08-07-spec-execution-coordinator`
**Covers:** tasks 1.1–1.4 (cluster 1 of 3)
**Status:** answered with evidence. Cluster 2 (1.5–1.9) and cluster 3 (1.10–1.13) follow.

> Every claim below cites a file, a line, or a counter-example, per the exploration's own rule
> that *"a file path, a transcript, a worked example, or a counter-example is an answer; 'I think'
> is not."* Where I make a recommendation rather than report a finding, it is labelled
> **Recommendation** and carries its reasoning.

---

## Headline finding, established before any of the four questions

**The exploration asks which specification format the coordinator executes. The evidence is that
neither candidate format is executable today, and the shipped one is broken in a way nobody has
noticed because nothing exercises it.**

This is not a detail of task 1.4. It changes what the next change should be, so it belongs first.

### The shipped spec pipeline has no producer and no reader

| Link in the chain | Expected | Actual |
|---|---|---|
| Skills that author `spec/*.html` | `aw-spec-propose`, `-apply`, `-archive`, `-explore`, `-technical-explore`, `-reindex` | Present as templates in `src/agentweave/templates/skills/` (6 of 24 files). **Nothing installs them.** A search of `src/` for `.claude/skills`, `SKILL.md` returns no matches; the only reference in `hub/hub/` is `workspace_paths.py:3`, which *reads* a directory someone else was supposed to populate |
| Hub discovers `spec/**/*.html` | Live filesystem discovery | Does not exist. `hub/hub/api/v1/spec.py` has exactly four routes — `POST /specs/sync`, `GET /specs`, `GET /spec`, `POST /specs/reconcile` — all reading `ProjectSpec.content` from the database |
| Something writes those cache rows | The watchdog | Deleted. `openspec/explorations/2026-08-03-specification-authority-technical.md` already recorded this: *"the old watchdog was also the only production caller that discovered and pushed `spec/**/*.html`, and it has been removed"* |

### And the shipped charter instructs agents to use all of it

`hub/hub/data/charters/spec.md` is one of the 21 starter charters seeded into **every new project**
(`charters.json` lists `"spec": {"name": "Spec Author"}`; seeding runs from
`hub/hub/project_lifecycle.py`). It tells the agent, verbatim:

- line 34 — *"Use the aw-spec skills below for procedure"*, then names all six. **None are installed.**
- line 28–33 — *"The Hub discovers every safe `spec/**/*.html` file independently of
  `spec/index.json`, so a document missing from the manifest is still visible (reported as drift),
  not lost."* **The Hub does no such discovery.** There is no drift report and no file reader.
- line 15 — *"Enforcing the approval gate: no implementation begins on a change spec until the user
  explicitly approves it (`aw-spec-status` flips from `draft` to `approved`)"*. **Nothing enforces
  this.** It is a charter instructing an agent to enforce a gate on itself.

An agent bound to this charter is told to invoke tools that do not exist, against a discovery
mechanism that does not exist, to enforce a gate that is honour-system. It will improvise, and
whatever it improvises will look like the feature working.

### The capability spec describes a subsystem that was deleted

`openspec/specs/aw-spec-workflow/spec.md` is the shipped capability's spec. Two of its requirements
are stale against the code:

- *"### Requirement: The spec role routes instead of duplicating procedures"* — *"The packaged spec
  **role** SHALL contain identity, ownership boundaries…"* and *"The CLI **role** template and Hub
  packaged **role** MUST remain behaviorally equivalent."*
- The role subsystem was removed. `CLAUDE.md`: *"Deleted, and not to be recreated: … the role
  subsystem"*, and umbrella task 13.12 records the removal of `roles.py`, `roles.json`,
  `VALID_ROLE_IDS`, and `templates/roles/`.

So the capability spec asserts a scenario (*"WHEN tests load the CLI and Hub copies of the spec
role"*) that cannot be run.

**Consequence for the coordinator:** a coordinator is a machine that executes a specification. There
is currently no specification artifact in a user project for it to execute, no path by which one
gets authored, and no reader that would find one if it existed. Building the coordinator first would
be building the executor of an empty pipeline.

---

## 1.1 — What does "immutable" mean here?

The task offers three readings and asks for one. **The evidence says one reading cannot carry the
whole word, and that the interesting answer is where the boundary between them falls.**

| Reading | If taken alone |
|---|---|
| (a) not editable by the agents it governs, but editable by the operator | The operator can weaken any gate. That is correct for the *policy* — the operator is the principal — but if it also covers the enforcement machinery, "guarantee" degrades to "default" |
| (b) versioned and content-addressed; a run records which coordinator version governed it | Orthogonal to both others. It is an audit property, not an authority property. It makes a past decision explicable; it constrains nothing at the time of the decision |
| (c) shipped in code, not editable at runtime at all | Guarantees the most and permits the least. A project could not define its own gates. This collides directly with the direction document's organising constraint: *"Where a capability and a barrier conflict, the barrier loses"* |

**Recommendation: split the word across two layers, and record (b) over both.**

- **The enforcement mechanism is (c) — immutable in code.** The transition graph's *existence*, the
  rule that a reviewer identity may not equal an author identity, the rule that a `gate`-rigor
  requirement needs accepted evidence, and the rule that every status write goes through one
  service. These are not configuration. No project may switch them off, because they are what the
  word "guarantee" in the operator's statement refers to.
- **The policy the mechanism enforces is (a) — operator-editable, agent-immutable.** Which rigor a
  document carries, which evidence kinds satisfy which rigor, which decision points consult a
  model, how long to wait for the operator. A project must be able to say "this one is a sketch,
  don't gate it." An agent must never be able to say that about its own work.
- **(b) applies to both and is cheap.** Each transition record carries the coordinator version and
  the policy digest that governed it. Without this, a gate that passed last month cannot be
  explained today, and the policy being operator-editable is exactly what makes that a live risk.

The failure mode this split is designed against: a "configurable gate system" in which strictness is
a setting. If strictness is a setting, the guarantee is the setting's default, and defaults are not
guarantees.

---

## 1.2 — What exactly is guaranteed?

Each claim below must hold no matter what any model outputs, and each is falsifiable by a test. The
task's rule is applied strictly: a claim I could not state as a test is not in the list.

| # | Claim | How it is falsified |
|---|---|---|
| **G1** | No task reaches a status except by a transition the graph permits | Enumerate all ordered pairs of the 8 statuses; attempt each through the service; assert exactly the permitted set succeeds |
| **G2** | The identity that produced a task's work is not the identity that approves it | Same agent drives `in_progress → completed → approved`; the last transition is refused with a stated reason |
| **G3** | Every write to `Task.status` passes through the transition service | Static: grep for assignments to `.status` on a `Task`; assert exactly one call site. Dynamic: exercise REST, MCP, and the job path; assert each is refused identically on an illegal transition |
| **G4** | A `gate`-rigor requirement is never verified by a model's assertion alone | Attach only evidence of kind `agent_assertion`; assert the gate still refuses and names the requirement |
| **G5** | Every transition is recorded with its cause, append-only | Drive two transitions; assert two rows exist and the first is byte-identical to when it was written |
| **G6** | A model being unavailable, slow, or self-inconsistent never *advances* state | Stub the decision point to raise, to time out, and to return two different answers; assert no transition occurs in any of the three |
| **G7** | The coordinator version and policy digest that governed a transition are recorded and never rewritten | Change the policy; assert prior rows still carry the old digest |

G3 is the load-bearing one and is the cheapest to break. Today it is already false, which is the
subject of the next section.

**Note on G2's scope.** It says *identity*, deliberately, not *agent name*. Which identity — name,
run, runner, or model — is task 1.10 and is not decided here. G2 is stated so that 1.10's answer
plugs into it without restating the guarantee.

---

## 1.3 — What is the coordinator's unit of work?

**Three unrelated concepts exist today.**

1. **Hub `Task`** (`hub/hub/db/models.py`) — a row with `id`, `project_id`, `status`, `assignee`,
   `assigner`, `created_by_run_id`, `updated_by_run_id`, and four untyped JSON blobs
   (`requirements`, `acceptance_criteria`, `deliverables`, `notes`).
2. **An openspec `tasks.md` checkbox** — a line of markdown in this repository's own contributor
   workflow. No identity, no attribution, no concurrency control.
3. **An aw-spec HTML task element** — `data-task-id`, `data-status`, `data-requirements`, per
   `src/agentweave/templates/skills/references/html-spec-conventions.md`. Authored by a skill that
   is not installed.

**Recommendation: the Hub `Task` is the unit. The other two are projections of it, never peers.**

The reasoning is an authority argument, and it is the mirror image of one the 2026-08-03 exploration
already made and accepted. That document concluded that the *file* owns requirement meaning and the
database must not become a second document authority. The symmetric claim is that the *database*
owns work and evidence, and a text file must not become a second workflow authority. Its own
authority table already says so — `Task lifecycle | Hub task ledger | rendered beside requirements`.

Concretely, a markdown checkbox cannot be the unit because it has no identity to attribute a
transition to, no way to record who reviewed it, and no way to refuse a concurrent write. Every
guarantee in 1.2 would be unenforceable against it.

**What this makes real:** requirement ↔ task is a link record, not a JSON blob.
`Task.requirements` is `Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)` and
`TaskUpdate` cannot even modify it (`hub/hub/schemas/tasks.py:87-94` — no `requirements` field), so
today a task's stated requirements are write-once at creation and unreferenced by anything.

### The self-approval hole, stated precisely

`hub/hub/api/v1/tasks.py:183-184`:

```python
    if body.status is not None:
        task.status = body.status
```

A direct assignment. The only validation upstream is set membership
(`hub/hub/schemas/tasks.py:106-111`), so `pending → approved` in one call is valid input at every
layer. `hub/hub/mcp_server.py`'s `update_task(task_id, status)` reaches the same write, so an agent
can approve its own work in a single tool call.

**A finding the proposal did not have:** attribution exists but is *overwritten*.
`update_task_for_actor` sets `task.updated_by_run_id = updated_by_run_id` on every call
(`tasks.py:194`). It is a single mutable column, not a history. So even with run-bound credentials
already shipped, the schema **cannot today distinguish the run that moved a task to `completed` from
the run that moved it to `approved`** — the second overwrites the first. Author/reviewer separation
therefore needs an append-only transition record before it can be enforced at all; it is not a
matter of adding a check to the existing columns. This is G5 and it is a prerequisite of G2, not a
sibling of it.

---

## 1.4 — Which spec format does it execute?

Restating the two candidates against the evidence in the headline section:

- **openspec markdown** is this repository's contributor workflow. It is deliberately not a product
  runtime — `CLAUDE.md` is explicit that the `aw-*` workflow is *"a feature AgentWeave ships to its
  users"* and that openspec is what this repo uses on itself. Making the coordinator execute
  openspec would ship this repo's internal process as the product.
- **aw-spec HTML** is the product's format and is the right answer on intent — but per the headline
  section it currently has no installed producer, no file reader, a stale capability spec, and a
  seeded charter that describes three mechanisms that do not exist.

**Recommendation: the coordinator executes an internal representation, populated from the product's
aw-spec HTML — and it is not the next change.**

- **Not the product format directly.** The coordinator should depend on parsed
  documents/requirements with stable identifiers, not on HTML. The 2026-08-03 exploration already
  designed this layer (`spec_documents`, `spec_requirements`, `spec_requirement_revisions`, with
  Crockford-base32 project-global IDs and a semantic digest). The coordinator consumes that index.
- **Not openspec.** Same representation could later be fed by a markdown parser if this repo ever
  wants to dogfood, but that is not a 1.0 concern and must not shape the design.
- **Not next.** The prerequisite the 2026-08-03 exploration named — *"the local multi-project
  successor must provide … a canonical absolute working directory on every project"* — **has since
  shipped** (`2026-08-04-2026-08-03-local-multi-project-workspace` is archived; `ProjectWorkspace`
  is the required path resolver per `CLAUDE.md`). That document's closing instruction was:

  > *"Do not propose the full specification program next. Propose the local multi-project workspace
  > first… After it is approved and implemented, create a shallow specification-program roadmap and
  > propose child 1, 'portable specification authority and identity'."*

  Both preconditions are now met. **Child 1 is unblocked and is the actual next change.**

---

## Early answer to 1.16 (should this be one change or several?)

1.16 asks this at the end. The cluster-1 evidence answers it now, and the answer changes what
happens next, so deferring it would waste the finding.

**It is several changes, and the coordinator is not the first of them.** The 2026-08-03 exploration
already proposed a four-child decomposition that this change substantially re-derives:

| 2026-08-03 child | Coordinator section that duplicates it |
|---|---|
| Child 1 — portable authority and identity | 1.4's internal representation |
| Child 2 — traceability, evidence, and drift | §3 placeholder (gates and evidence), 1.12 |
| Child 3 — rigor and completion gates | §2 and §3 placeholders, 1.2's G4 |
| Child 4 — authoring workspace | umbrella section 14 |

Two changes, written four days apart, are planning the same territory with different vocabulary.
That should be reconciled before either is implemented.

**Recommended sequence, revised:**

0. **Repair the shipped pipeline's honesty** — small and urgent, independent of everything else.
   Either install the packaged skills or stop the seeded charter claiming they exist; correct the
   charter's false statement about Hub discovery; mark the two stale `aw-spec-workflow`
   requirements. Today a new project ships an agent instructed to use six absent tools.
1. **State-machine enforcement + append-only transition records** — the 2026-08-03 decomposition
   does *not* contain this, and it is the one piece of the coordinator that is valuable entirely on
   its own: it closes the self-approval hole. It needs no specification format, no evidence model,
   and no AI. Guarantees G1, G2, G3, G5, G7.
2. **Child 1 — portable authority and identity.**
3. **Child 2 — traceability and evidence.** Guarantee G4 becomes meaningful here.
4. **Child 3 — rigor and completion gates.**
5. **AI augmentation** — last, and only over a machine that already exists. This is the proposal's
   own stated design intent: *"augmenting a machine that does not yet exist is the failure mode this
   change is designed against."*

Step 1 is the correction to the coordinator's current framing: it leads with the AI question, but
the piece with the highest value-to-risk ratio has no AI in it at all.

---

## Open questions raised by this cluster

1. **Does the operator want the packaged skills installed, or removed?** 24 templates ship in the
   wheel and nothing renders them. Handoff 0023 open question 6 raised this; it is now blocking,
   because the seeded `spec` charter depends on six of them.
2. **Does the 2026-08-07 coordinator change survive as its own change,** or is it re-cut as
   "state-machine enforcement" (step 1) plus deltas onto the 2026-08-03 children? My reading is the
   latter, but it retires a change the operator approved four days ago.
3. **Is `aw-spec` HTML still the product's spec format at all?** Every consumer of it is dead. If
   the answer is "yes, and we repair it," child 1 is large. If "no, we re-cut it as markdown to
   match what agents actually author well," that is a different and possibly smaller change. This
   should be decided before child 1 is proposed, not inside it.

## Not covered by this cluster

1.5–1.9 (enumerating and bounding the AI decision points) and 1.10–1.13 (governance identity,
echo-chamber protection, evidence kinds, where the human sits). Cluster 3's 1.10 has a partial
answer above — the append-only transition record is its prerequisite — but the identity question
itself is untouched.
