# Exploration — How the spec and the Hub integrate

**Date:** 2026-08-12
**Builds on:** `2026-08-10-authoring-flow-without-skills.md`,
`2026-08-10-charters-phases-and-the-spec-on-ramp.md`,
`2026-08-03-specification-authority-technical.md`
**Answers:** the operator's question of 2026-08-12 — *"the spec is generated in such a way that the
Hub can read the html and generate tasks, and the status of a task also updates the spec… what else
can the spec relate to the hub?"* — and their follow-up, *"how do I start an explore phase?"*

---

## Read this section first: what is decided and what is not

A decision in an earlier exploration was written as **"Resolved by…"** and read, three sessions
later, as something the operator had ratified. It had not been. That document contains no operator
attribution anywhere, and its own open-questions list still asked the very question the "resolution"
appeared to close. The operator caught it — *"I'm not sure I made that call. Could've been
hallucinated or buried in something else"* — and they were right.

**So this document separates three things that must never again be conflated:**

| Section | Means |
|---|---|
| **§1 Operator decisions** | The operator said this. Binding. Do not re-litigate |
| **§2 Proposed and agreed** | The agent proposed it, the operator agreed in conversation. Binding but derived — if the reasoning turns out wrong, it is reopenable |
| **§3 Open** | Nobody has decided. Do not treat any of it as settled |

Anything not in §1 or §2 is not decided, however confidently it is written.

---

## 0. What just became possible

`2026-08-03-specification-authority-technical.md` declared the specification program **not
implementable**, for one stated reason: `Project` had no working directory, so the Hub could not
resolve a project's files, and the only component that had ever discovered `spec/**/*.html` — the
watchdog — had been deleted.

**That prerequisite has shipped.** `ProjectWorkspace`, `Project.working_directory`, and
directory-backed project identity are live. The Hub can read and write a registered project's files
directly. The stated blocker is gone, and with it the entire push/snapshot/drift-reconciliation
apparatus that existed only because the Hub was blind to the filesystem.

---

## 1. Operator decisions

### 1.1 The HTML format stays, and the Hub is how you use it

*"I want to keep using the html format of the specs."*

*"It should be usable by the hub. If someone is opening from outside it's the wrong path. We make it
everything in the hub."*

The second half is load-bearing: portability outside the Hub is **not** a goal. That single decision
resolves the task-status question in §2.2.

### 1.2 Users do not hand-edit spec files

*"User's shouldn't edit the spec file directly they should use AI. If they edit in a file editor then
it should have reconciliation rules."*

*"Since it's HTML we can maybe use field that the user can interact with, button, combo boxes, etc…
edits where we allow them so the hub still in control a see all the edits made."*

The document is a **surface**, not a text file the operator maintains. Interaction happens through
controls the Hub renders and handles. Hand-editing is the exceptional path, not the normal one.

### 1.3 Every edit is traceable, and the Hub never silently wins a conflict

*"Edits (via hub or AI) should be traceable. And edit event via json of the spec or via the hub user
piloted should be tracked. If someone for some reason hand edits a file this should be the decision
of the user. If the hub can detect in a way (a hash maybe?) It should come back to the user and the
user decides which to keep."*

Two rules, and the second is the sharp one:

- Every edit is an **event** — actor (operator or agent), origin (Hub control or JSON submission),
  run ID where one exists, and what changed.
- On a detected external edit the Hub **surfaces both versions and waits**. It does not
  auto-reconcile. Auto-merging a manual edit is how text is lost without anyone noticing.

### 1.4 The spec creates tasks

*"The spec creates tasks if all the requirements are met. For that the hub for example assigning a
agent to the task. We can have a drop down or ai edit it."*

The document is a task **source**; the Hub imports. Agent assignment is an operator control or an
agent action, not something buried in the document's text.

### 1.5 Review is adversarial and independent

*"I want more like an adversarial position from testers where they trust nothing that's why a
different agent should review."*

Independence is the mechanism, not a recommendation. See §2.5 — it is checkable in code, and this
project already states the rule in prose in two charters while enforcing it in none.

### 1.6 Rejections carry reasons, and reasons are measurement

*"I want agents to be able to put a reason why a task was rejected if a bug was found etc. So I can
measure how the models and workers are performing after the fact. How many times a task was
rejected, why etc."*

Rejection stops being a status and becomes **telemetry**. Reviewer performance is tracked too —
*"Reviewer performance should be tracked as well."*

### 1.7 The operator does not review everything, but some things are theirs alone

*"I don't want to review every little thing. AI is here to assist me. But there are some things that
can only be approved by the user."*

This is what rigor levels are for (§2.4).

### 1.8 The spec charter is good practice, not required

*"Not necessarily I want to use the charter for spec. Is good practice but I can skip it."*

**Consequence, and it is a real constraint:** nothing load-bearing may live in the charter. The phase
machine's exit conditions and the format validation must work against a blank charter. The charter
makes output *better*; it must never be what makes output *valid*. This is the opposite of today,
where `hub/hub/data/charters/spec.md` was the only thing carrying the procedure.

### 1.9 JSON in, HTML out

*"yeah json in html is a good change."*

The agent emits structured JSON; the Hub renders the HTML. See §2.6.

### 1.10 Abandoned explore documents are acceptable

*"Acceptable is as you mentioned. Information, even on ideas for the future."*

An abandoned exploration is an **idea backlog entry**, not litter. Implies the spec tree must
distinguish dormant explorations from the active working set — a filter, not a problem.

---

## 2. Proposed and agreed

### 2.1 Skills are decomposed, not installed — and this corrects advice given earlier today

The agent initially proposed "restore skill installation" to fix the operator's complaint that they
could no longer author a spec. **That advice was wrong**, and
`2026-08-10-authoring-flow-without-skills.md` already says why:

> `.claude/skills/` is read by Claude Code. **A Codex agent cannot invoke `aw-spec-propose` under
> any circumstances.**

Installing the skills delivers the authoring flow to half the product's agents while the seeded
charter instructs all of them to use it.

A skill file is three things wearing one filename, and each belongs somewhere different:

| What is inside | Where it goes | Why |
|---|---|---|
| **Procedure** — explore, then propose, then approve, then apply | the **phase machine** (code) | a procedure the model is *asked* to follow is a suggestion; one code drives is a guarantee |
| **Format contract** — what a valid document is | **schema validation** (code) | 541 lines of "please emit this shape" becomes a boundary that fails loudly |
| **Judgment** — how to interview, what makes a requirement testable | the **charter** (optional, per §1.8) | runner-agnostic, operator-editable, already shipped |

The runner-agnostic delivery channel already exists: `agent_trigger.py:333-360` writes
`.agentweave/context/<agent>.md` every turn and hands it to both runners.

### 2.2 Task status is derived, not written back

The HTML contract has `data-status="pending|done"`, which `/aw-spec-apply` used to flip. Under §1.1
that is wrong: the Hub task ledger is the authority, and the document *renders* status beside the
requirement rather than storing a second copy of it.

Write-back's only real argument was portability — a file you can open anywhere and see the truth.
§1.1 removed that argument. What remains is one authority per fact, no write contention with an
operator, and no git churn on every transition.

### 2.3 Relevance is judged once, at the link; the gate itself stays deterministic

The hard question is *"does this evidence actually demonstrate this requirement?"* — flagged in the
prior exploration as **binding**, with the warning that *"if an AI can decide a gate's outcome, the
determinism is theatre."*

Three deciders, each failing differently: code can verify a linked test ran and passed but not that
it is *about* the requirement; an AI can judge aboutness but wants to be helpful and can be argued
into anything — especially by the system that produced the evidence; the operator is authoritative
but is the bottleneck the feature exists to remove.

**Resolution: split the gate.**

- **Relevance** — "is this evidence about FR-7?" — is asked **once, when the link is made**. An agent
  proposes it; a human (or, per §2.4, an independent agent) accepts. It becomes a durable, attributed
  record.
- **Mechanical** — "did accepted evidence run and pass?" — is asked at **every** evaluation, by code
  alone.

The judgment does not disappear; it moves out of the gate and into the link. After that the gate is
arithmetic and no model sits in the path.

The AI stays useful and never authoritative: it proposes links, flags weak evidence ("this test mocks
the clock, so it may not demonstrate a timeout"), and detects staleness.

### 2.4 Rigor decides who may accept

| Rigor | Who may accept evidence | Operator sees |
|---|---|---|
| `sketch` | nobody — evidence is informational | nothing |
| `contract` | an **independent** agent (§2.5), attributed and reversible | a summary |
| `gate` | **operator only** | the decision |

This is the dial that satisfies §1.7. Most requirements never reach the operator.

### 2.5 Independence is a code check, not a request

```
   accept(evidence E, requirement R) requires:
     E.produced_by_run.agent     ≠  acceptance_run.agent
     E.produced_by_run.conversation ≠ acceptance_run.conversation
```

The rule is already stated in prose in two shipped charters and enforced in neither —
`code_reviewer` ("do not merge/approve your own work") and `verifier` (the echo-chamber check).

**It is also exactly the control the underwriting pair demonstrates.** `underwriting_approver`: *"A
referral you wrote yourself is not one you may approve."* That pair shipped in
`2026-08-11-charter-set-reshape` as a demonstration that a charter can carry a real constraint rather
than a topic label. Software turns out to need the identical rule, which is the argument for D5
landing better than expected.

### 2.6 JSON in, HTML out — and why not the two obvious alternatives

```
   1. AGENT WRITES HTML          2. GRANULAR TOOLS             3. JSON PAYLOAD
   ──────────────────────        ─────────────────             ───────────────
   Write("spec.html", …)         add_requirement() × 40        submit_spec_document({…})
   Hub parses → accept/refuse    Hub assembles                 Hub renders

   no new tools                  cannot emit invalid HTML      one call
   541-line contract in every    ~40 round trips               cannot emit invalid HTML
     model's context, forever    prose sections awkward        schema error is precise
   drift: tags, escaping,        chatty and slow               prose = markdown strings
     anchors, meta                                               inside the payload
   retry loop burns tokens
```

Option 2 is the one that is too complex — the operator was right to push back on it. **Option 3 is
the answer.** Models emit JSON far more reliably than 200-line HTML with anchors and `data-`
attributes; structured output is a first-class model capability; and a JSON schema is both shorter to
state and machine-enforceable, where prose is neither.

The complexity does not vanish, it **moves**: option 1 pays it in every model's context on every turn
forever; option 3 pays it once, in tested Hub code.

**The agent does not supply requirement IDs — the Hub mints them.** That is how they stay stable
across rewording, which is what umbrella task 14.1 exists for. An agent inventing its own IDs
reintroduces the drift the identifiers were meant to remove.

### 2.7 Explore starts by creating an empty document

The prior exploration's position — *phase belongs to the document, not the thread* — has a hole:
**explore precedes the document**, so it is the one phase that cannot take its phase from one. That
is why starting felt undefined.

Its argument is also narrower than it reads. It demolishes *retroactive classification* ("is this
existing thread a spec thread?"), which is genuinely undecidable. It never addresses **prospective
declaration** — the operator saying up front "I want to explore an idea," which is intent, not
classification.

**Resolution: an entry point that creates an empty document in `exploring` state.** It can look like
a pill and behave like a button. Phase still always comes from a document, because the document now
exists from the first moment.

Why not a mode pill on the conversation:

| | Pill | Document created at start |
|---|---|---|
| what holds the phase | the conversation | the document |
| subject of "propose" | **ambiguous — propose what?** | the document |
| two explorations at once | two conversations, two pills | two documents |
| return tomorrow | is the pill still on? | open it; phase is its state |
| end of explore | transcript, then a separate "make a document" step | already there, filled in |
| composer collision | sits beside Permissions, which is *per-run*; phase is not | lives near the document |

The decisive row is the second. With a pill, every later transition — approve *what*, apply *what* —
inherits the same missing referent.

A bottom-up path complements it: the agent offers *"this sounds like it should be written down"*
mid-conversation (umbrella 14.13, "grow from conversation"). Both paths create the document; after
that everything is uniform.

### 2.8 One digest, two jobs

```
   Hub writes the document ──▶ stores digest
              │
     ┌────────┴────────┐
     ▼                 ▼
   file digest        requirement text digest
   differs            changed
   → hand-edit        → accepted evidence goes STALE,
     detected (§1.3)     not silently still valid
```

The same primitive that detects an external edit also detects that a requirement's *meaning* moved
out from under evidence accepted against the old wording.

---

## 3. Open — nobody has decided these

1. **What the reconciliation rules actually are.** §1.3 fixes the *policy* — surface both, operator
   decides. The mechanics are unspecified: per-file or per-requirement, what "keep mine" does to
   evidence already accepted against the Hub's version, and what happens to edits made while the
   operator is deciding.
2. **The rejection category vocabulary.** Sketched, unratified: `requirement_not_met`, `defect`,
   `evidence_insufficient`, `regression`, `scope_creep`, `convention_violation`,
   `unverifiable_claim`. The last is the one worth counting on its own — a model that reports success
   without running anything fails differently from one that writes buggy code, and today those look
   identical in a status column.
3. **Reviewer metrics beyond counts.** Rejection rate alone rewards a reviewer that rejects
   everything. **Overturn rate** — rejections later reversed — is what keeps it honest. Also: reviews
   with no category, and cost per review.
4. **Does the spec phase machine share an implementation with B1's task transition machine?** Both
   are guarded state machines with append-only audit and actor attribution. They differ in that task
   transitions are mostly "someone decided" while phase transitions have **computed** entry
   conditions. They must talk regardless, since `apply`'s exit condition is a statement about task
   statuses. **This is an implementation-structure question, not a product one — it blocks nothing.**
5. **Carried, still binding:** the format contract **must not be frozen** until traceability and
   gates have stated their requirements on it. Otherwise the schema ships unable to express what the
   gates need, and every existing document has to be migrated.
6. **Carried:** the binding/advisory classification of the remaining AI judgment points — is an
   exploration complete enough to propose from; is this requirement testable as written; is an edit
   editorial or substantive.

---

## 4. The flow, with everything above applied

| Phase | Entry | The agent's job | Exit, checked by code |
|---|---|---|---|
| **Explore** | operator creates a document, or the agent offers mid-conversation (§2.7) | interview via `ask_user`; ground in the codebase | no unresolved clarifications; distilled notes exist |
| **Propose** | explore satisfied | emit the JSON payload (§2.6) | schema validates; Hub mints IDs; rigor declared per requirement |
| **Approve** | document valid | **nothing — the agent does not act** | an operator decision is recorded |
| **Apply** | status approved | implement; work links to requirement IDs | tasks reach terminal states via B1; evidence attached and accepted per §2.4 |
| **Archive** | every `gate` requirement satisfied | move the document, update the manifest | archive write validated and atomic |

Two properties a skill could never have: it works identically for a Codex agent and a Claude agent,
because the phase, its context and its exit check live in the Hub; and **the approval gate is real** —
`apply` has an entry condition the agent cannot satisfy by asserting it has been satisfied.

---

## 5. What a requirement can relate to

Most of these links already exist and are simply not connected to a requirement.

| Relation | Substrate | State |
|---|---|---|
| requirement → task | `data-requirements`, `Task` | `Task.requirements` is free-form JSON; needs real IDs |
| task → run | `run-task-binding` | **shipped** |
| run → conversation | `blocked-and-conversation-binding` | **shipped** |
| run → cost | `usage-accounting` | **shipped** |
| task → transition history | `task_transitions`, append-only, with actor and run | **shipped**; needs a `reason` (§1.6) |
| agent → charter/runner | roster | **shipped** |
| requirement → evidence, review, gate decision | append-only Hub records | not built |

The chain **requirement → task → run → conversation → cost** is the valuable one, and four of its
five links already exist. Only the first is missing.
