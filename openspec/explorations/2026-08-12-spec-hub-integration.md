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

**Second pass, later the same day — the apparatus is not merely unnecessary, it is already
unreachable.** Verified in code:

- `POST /project/specs/sync` and `POST /project/specs/reconcile` (`hub/hub/api/v1/spec.py`) are the
  only writers of `project_specs`. Their only callers are `HttpTransport.push_spec` and
  `reconcile_specs` (`src/agentweave/transport/http.py:555,576`), and **those two methods have no
  callers at all**. Their docstrings say "called at watchdog startup… plus manually via
  `agentweave spec push`" — the watchdog is deleted and that command is among the 51 removed.
- The live database holds 3 stale `project_specs` rows and **0** `project_spec_snapshots`.
- `ACTIVE_SOURCE_TTL_SECONDS` is documented against "normal watchdog polling."

So the specification surface reads from a cache that nothing in the shipped product can fill. This
is the concrete reason a user cannot author a spec today.

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

### 1.11 The new phase is the frame, and it settles the cache question

*"We have to take into consideration the whole new phase that agentweave is in. We removed the
watchdog and the hub doesn't operate as a separate docker entity. This might help us resolve some of
this questions."*

Then, on the resulting proposal to delete the push apparatus and read from the working directory:
*"Yes, this is good."*

Three independent reasons now support it, any one sufficient:

1. The cache's stated purpose — "so the UI can display them without filesystem access" — is void in
   **both** deployment modes. Native leaves `AW_WORKSPACE_ROOT` unset and imposes no containment
   restriction (`project_workspace.py:89`); Docker mounts a real root. Either way
   `ProjectWorkspace.resolve_relative` (`project_workspace.py:62-71`) already provides
   containment-checked, traversal-free reads. **There is no mode in which the Hub is blind.**
2. `project_spec_snapshots` exists for "possibly multiple machines syncing the same project." One
   local Hub, and a project bound to one canonical directory by `canonical_path_key` plus the
   `.agentweave/project.json` marker — the multi-source premise is gone by construction, not by
   preference.
3. The write path is dead and unreachable (see §0).

### 1.12 The skills' knowledge is preserved; technical exploration is dropped

*"There is a lot of knowledge on those skills. How do we preserve them? Their behavior is very
good… Maybe some tweaks and remove the technical explore but I want the same knowledge imputed."*

And, on the apply/archive/reindex skills: *"Read them just to be sure but I believe then can be all
automated."*

Two obligations, and they are not the same one. The knowledge must **land somewhere that reaches an
agent of either runner** — deleting the files is fine, losing what they encode is not. And the
disposition must be **auditable**, so that "did we drop something?" is answerable by reading a table
rather than by diffing a deleted directory. See §6.

### 1.13 The two superseded capabilities are removed, not rewritten

*"I feel like remove."*

`aw-spec-workflow` (10 requirements) and `spec-manifest-sync` (9) are removed from
`openspec/specs/`; `spec-chat-session` (5) survives and is extended.

The reasoning, agreed in conversation: a capability spec describes current behaviour, and after this
change no code implements those 19 requirements — a spec still named `aw-spec-workflow` but
describing a phase machine would be a document whose name misstates its own subject. Rewriting in
place would also read as evolution when this is replacement. The paper-trail argument for rewriting
was withdrawn: `changes/archive/` and git preserve the trail either way.

The decisive evidence is behavioural. `aw-spec-workflow`'s spec-role requirement was rewritten in the
**previous session**, during the charter reshape, to stop routing agents to mechanisms a project
lacks. That is a capability being patched to survive a product that moved out from under it.

**Removal is not forgetting.** Four of `spec-manifest-sync`'s requirements describe a *document tree*
rather than syncing, and any owner needs them. They carry forward into the new capability as
requirements:

- spec discovery covers every safe document
- home-document selection is explicit and resilient
- an invalid or absent index degrades visibly rather than silently
- state changes refresh subscribers (the SSE broadcast survives outright)

`aw-spec-workflow` is a clean kill — its subject is a delivery mechanism that cannot reach a Codex
agent, and two of its ten requirements describe technical exploration, dropped under §1.12.

**Sequencing constraint:** the removal lands in the **same change** as the new capability, never
ahead of it. Otherwise there is a window in which shipped behaviour is specified nowhere. This is the
one place where the "small verifiable commit first" pattern used for the charter harvest does not
apply.

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

The runner-agnostic delivery channel already exists: `agent_trigger.py:376-405` calls
`_render_hub_agent_context` and writes `.agentweave/context/<agent>.md` into the run's effective work
directory every turn, for both runners. It already carries a `### Open specification document`
section (`agents.py:1015`), so document awareness per turn shipped with `spec-chat-session`.

**Correction to the table above — the split as first written violates §1.8.** "How to interview" is
two different things, and only one of them is judgment:

| | belongs to | optional? |
|---|---|---|
| **The obligation to interview** — you may not reach `propose` with unresolved clarifications | the phase machine (code) | **no** — it is an exit condition |
| **Skill at interviewing** — what to probe, when a requirement is too vague to be testable | the charter | yes — degrades quality, not validity |

As the table originally read, the obligation landed in the optional charter, which is exactly what
§1.8 forbids. The phase block therefore needs a **minimum procedural floor** that holds against a
blank charter — roughly five code-owned lines: *you are exploring; ask before assuming; use
`ask_user` for anything that changes scope; ground claims in the codebase; you cannot propose until
the operator marks explore complete.* Not 216 lines of skill.

This reconciles with §1.8 in practice because charters are **seeded by default** — skipping one is
opt-out, not opt-in. The floor keeps a blank-charter run *valid*; the seeded charter makes it *good*.
One decision follows from this and should be made explicitly: a spec-phase run binds the spec charter
by default unless the operator overrides, so that "optional" means "you may remove it" rather than
"you must remember to add it."

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

### 2.9 The document lives on disk; the cache is deleted

Following §1.11. The Hub reads and writes documents through `ProjectWorkspace.resolve_relative`.

**Deleted:** `POST /project/specs/sync`, `POST /project/specs/reconcile`, the `project_specs` and
`project_spec_snapshots` tables, the drift/TTL machinery, and `HttpTransport.push_spec` /
`reconcile_specs`. Cost: one guarded migration, both head assertions bumped, and spec deltas.

**Kept:** manifest parsing and `validate_spec_path`. Reading from disk still needs path validation,
and the manifest is still the document index — it changes owner, not purpose.

### 2.10 The format contract travels as the tool's input schema

The question §1.9 leaves open is *how a model learns the format when no skill file installs*. The
answer falls out of the choice itself: `submit_spec_document`'s JSON Schema **is** the contract. MCP
delivers tool schemas to Claude and Codex alike, by protocol, every turn, with no skills directory
and no runner-specific path.

This replaces 713 lines of `html-spec-conventions.md` with a boundary the model cannot cross without
a field-level validation error. The model does not need to be *taught* the format; it needs to be
*shown the tool*.

### 2.11 The skills' self-checks become blocking validators

The highest-value content in the entire skill set is the step-7b self-check
(`aw-spec-propose.md:230-259`), and it is currently a polite request:

> *"Every requirement is referenced by at least one acceptance criterion **and** one task; every task
> references at least one requirement. Report both directions — an orphan in either direction is a
> real gap, not a formatting nit."*

That is an orphan-detection algorithm, and today we ask the model to run it on itself and report the
result — precisely the `unverifiable_claim` failure mode of §3.2. Every check in that block is
mechanical: anchors resolve, no duplicate IDs, non-goals non-empty, modal verb present, no unresolved
clarification markers. Moved into Hub validators they stop being advisory.

The general rule, and it is what makes §6 a promotion rather than a salvage operation: **knowledge
does not need preserving as text when it can be preserved as a constraint.**

---

## 3. Open — nobody has decided these

1. **What the reconciliation rules actually are — now a smaller question.** §1.3 fixes the *policy*
   — surface both, operator decides. §1.11 **deleted half the problem**: it was "N machines pushing,
   whose copy wins," and it is now one case — the Hub wrote the file, someone edited it in an editor,
   two versions, one operator. Still unspecified: per-file or per-requirement, what "keep mine" does
   to evidence already accepted against the Hub's version, and what happens to edits made while the
   operator is deciding. **Not a prerequisite** — store the digest from day one and defer the
   resolution UI.
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
5. **Carried, still binding — but cheaper than it was:** the format contract **must not be frozen**
   until traceability and gates have stated their requirements on it. Otherwise the schema ships
   unable to express what the gates need, and every existing document has to be migrated.

   §1.11 lowers the cost of being wrong. With no pusher, no portability goal (§1.1) and no external
   consumer, the Hub is the **only** reader and the **only** writer of the format — and a format with
   one reader is migratable by that reader. A wrong schema costs a Hub-side migration, not
   coordination across machines and CLI versions.

   **Proposed resolution, not yet ratified:** version the payload (`schema_version`) and freeze only
   the part that must be permanent — **requirement ID stability across schema versions**. Traceability
   and gates then extend the payload later without migrating documents. This satisfies item 5
   literally rather than deferring the first slice, which would otherwise be blocked by it, since the
   named first slice *is* the format contract.
6. **Carried:** the binding/advisory classification of the remaining AI judgment points — is an
   exploration complete enough to propose from; is this requirement testable as written; is an edit
   editorial or substantive.

   On the first of those, a **proposed** resolution: make the explore exit an explicit operator
   action in v1 — the operator says "done exploring." No model sits in the path, and it holds against
   a blank charter per §1.8. Ratification still needed.
7. **What happens to the two superseded capabilities.** `spec-manifest-sync` (9 requirements) is
   built on the push model, and one of them — "Spec synchronization remains backward compatible" — is
   compatibility with a client that no longer exists. `aw-spec-workflow` (10 requirements) describes
   authoring through the `aw-spec-*` skills, which §2.1 established a Codex agent can never invoke.
   `spec-chat-session` (5 requirements) **survives** — the composer, the conversation reuse, and the
   document-beside-chat layout are what the new design builds on.

   So the proposal is not "add spec↔Hub integration"; it is **replace two capabilities and extend a
   third**, which changes the shape of the change document and makes most deltas removals.

   **RESOLVED — see §1.13.** Removed, not rewritten, with four of `spec-manifest-sync`'s
   requirements carried forward into the new capability. Recorded here rather than deleted so that
   the question, and the fact that it was answered separately from §1.11's *"Yes, this is good"*,
   both stay visible.
8. **Where the disposition table in §6 is enforced.** The table records intent. Nothing yet checks
   that a destination was actually built — e.g. that the orphan validator of §2.11 exists. A test
   asserting each `V` row has a validator would make the harvest verifiable rather than asserted.

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

---

## 6. Disposition of the skill set

§1.12 requires that the skills' knowledge survive their files, and that the survival be auditable.
This table is that audit. Every section of every skill has a destination, including `X` with a stated
reason. "Did we drop something?" is answered by reading this table, not by diffing a deleted
directory. The files remain in git history regardless.

**Destinations:** **S** = `submit_spec_document` JSON schema · **V** = Hub validator · **P** = phase
block in the per-turn context (code-owned, non-optional) · **C** = charter `spec.md` (judgment,
optional per §1.8) · **R** = Hub renderer · **X** = deleted, superseded

**Scope: 1,802 lines.** Six skills (1,306) plus two references (796), less
`aw-spec-technical-explore.md` (300), removed entire per §1.12.

### `aw-spec-explore.md` (216 lines)

| content | → |
|---|---|
| Spec-Driven Mindset (18-31), The Stance (34-44), What To Explore (48-80), Visualizing (111-130), Guardrails (209-216) | **C** — ~120 lines, near-verbatim. This is the interviewing craft, and the reason §1.12 exists |
| "Explore mode is for thinking, not implementing" (10, 211) | **P** — and stronger than today: an `exploring` run can be permission-restricted, so it is enforced rather than requested |
| The `idea.md` template (144-184) | **S** — this *is* the explore-phase payload: `problem`, `users_workflows`, `goals`, `non_goals`, `emerging_requirements[]`, `codebase_context[]`, `evidence_limits`, `options[]`, `open_questions[]`, `risks[]`, `slice_boundary` |
| `find spec/changes` context probing (95-107) | **X** — the Hub knows its own documents |
| Routing to technical exploration (14, 89-91, 202) | **X** — removed per §1.12 |

### `aw-spec-propose.md` (321 lines)

| content | → |
|---|---|
| Principles 2,3,4,5,7,8,9,10,11,12 — testable + modal verbs, Given/When/Then, numbered algorithms, non-goals, producer/consumer split, task→requirement trace, non-normative labelling, clarification markers, evidence & limits, lifecycle | **S** — each becomes a required field or enum. A required non-empty `non_goals` array enforces principle 5 better than a sentence requesting it |
| Principles 1, 6, 13 — separate WHAT from HOW; justify non-obvious rules; decompose an epic into vertical slices | **C** — irreducible judgment |
| Step 7b structural checks (236-244) — anchors resolve, no duplicate IDs, offline, head metadata, task attributes, theme layers | **R** — the Hub emits the HTML, so most cannot fail by construction |
| Step 7b content checks (245-257) — orphans in both directions, modal verb present, algorithms not prose, non-goals non-empty, no unresolved clarifications | **V** — blocking, per §2.11 |
| Step 7b "rewrite anything unfalsifiable" (249-251) | **C** — a word list is a hint, not a gate |
| Step 8 approval gate (261-279), "never flip to approved without an explicit decision" | **P** + phase machine — the agent cannot flip status at all |
| Step 7a manifest update (219-228) | **X** — the Hub owns the index |
| Step 3 roles/quality config (118-137), reviewer warnings (208-217), team summary (296-298) | **X** — deleted subsystem. Intent survives as the roster plus §2.5's independence check, which is code |
| Step 7 HTML skeleton, inline style, section order (172-207) | **R** |
| Step 1b roadmap rows (81-95) — stable ID, intent, in/deferred boundary, dependencies, child link | **S** (`kind: "roadmap"`) + **C** (when one is warranted) |
| Step 3b "do not convert an implementation detail into a requirement without recording the rationale" (150-151) | **C** — the sharpest line in the set |
| Step 5 resolve ambiguity (158-162) | **P** + the existing `ask_user` |

### `aw-spec-apply.md` (189 lines)

| content | → |
|---|---|
| Step 2 approval gate by grep (33-51) | **X/P** — the agent currently greps its own permission slip. §4's "the approval gate is real" |
| Step 6.6 mark task done inside the HTML (126-129) | **X** — §2.2, status is derived |
| Step 3 cross-artifact consistency, mechanical half (67, 70) | **V** |
| Step 3 "an approved spec that disagrees with the system map is a re-approval, not a judgement call you make mid-implementation" (72-73) | **P** — a phase rule, not prose |
| Step 6.2 "derive requirement tests from the acceptance criteria and label them as proposed coverage rather than observed behavior" (113-116) | **C** + an evidence field. Serves `unverifiable_claim` directly |
| Step 6.5 "do not treat a green unit test as proof" (123-125) | **C** — already present in the seeded charter |
| Step 3 quality config (78-80), step 5 principal-owned tasks (100-106), step 7 delegation (140-152) | **X** — deleted subsystems and a deleted command |
| Step 4 progress display (82-96) | **R** — rendered from the task ledger |
| Pause conditions (133-138) | **P** + `ask_user` |

### `aw-spec-archive.md` (142 lines)

| content | → |
|---|---|
| Step 2 verify approved and every task done (30-58) | **V** + phase machine — §4's archive entry condition |
| "Tasks under review are not done" (60-66) | **V** — *stronger* than the original: the Hub owns the ledger, so this is computed, not grepped |
| Roadmap row completion rule (73-77) | **V** — precise and mechanical as written |
| Step 4 manifest path update (79-88), step 5 dated move (97-103), collision suffix (142) | **X** → Hub code, atomic per §4 |
| Evidence preservation, "do not represent the archive as a complete reconstruction guarantee" (68-71) | **C** — already present in the seeded charter |

### `aw-spec-reindex.md` (138 lines) — ~100% X, and the reason matters

The skill exists because the manifest could drift from the filesystem. Under §1.11 the Hub owns the
index and writes the documents, so a hand-move is the §1.3 reconciliation case, not routine repair.
Its own closing line instructs the agent to run `agentweave spec push` — a command that no longer
exists. The file is built entirely on the deleted architecture.

| content | → |
|---|---|
| Step 7 manifest validation (96-103) — unique safe paths, home resolves, acyclic parents, kind/status compatibility | **V** — transfers straight across |
| Step 4 "never silently discard a manifest entry you can't explain" (63-73) | already §1.3's policy |
| Everything else | **X** |

### References (796 lines)

| content | → |
|---|---|
| `html-spec-conventions.md` (713) | **R** — the single largest deletion, and pure win. §2.10 |
| `spec-manifest-conventions.md` (83) | **S** + **V** |

### Accounting

| destination | ~lines |
|---|---|
| **R** renderer | ~750 |
| **X** deleted with the architecture they served | ~640 |
| **C** charter | ~180 |
| **S** schema | ~120 |
| **V** validators | ~90 |
| **P** procedure floor | ~25 |

Roughly 180 of 1,802 lines survive as prose. Everything else becomes code, or dies with the
subsystem it addressed.

### Status: the charter harvest has shipped

Commit `2909137` — `hub/hub/data/charters/spec.md`, 88 → 157 lines, done ahead of the change per the
operator's *"2 - ok"*. The pre-existing charter already carried more than expected (vertical slicing,
what a passing suite proves, non-goals, testability), so the harvest was targeted: the interview
stance and ground, sketch guidance, non-obvious rules carrying their reason, producer/consumer
separation, the epic-versus-slice decision, the reverse-engineered-requirement warning, the
re-approval rule, and the proposed-versus-observed coverage label.

Verified against the four seeded-charter guards in `hub/tests/test_agent_facing_text.py` (43 passed):
names no uninstalled `aw-*` skill, cites no removed subsystem, addresses no roster title, defers to
no principal. Charter API/context/instructions/registration suites: 58 passed.

**Note for whoever implements the rest:** charters are copied into the database per project at seed
time, so this reaches **new projects only**. The three existing projects keep their own editable
copies — correct behaviour, but it means verifying the harvest requires a fresh project.

---

## 7. The program, and what change 1 must not foreclose

This design is four or five changes, not one. The order is a dependency order, not a ranking:
evidence links, task links, and gates all point *at requirement IDs*, and those do not exist until
the Hub mints them.

### The sequence

| # | one demonstrable outcome | in | deferred to | depends on |
|---|---|---|---|---|
| **1** | **You can author and approve a specification document in the Hub** | documents on disk; JSON in, HTML out; Hub-minted requirement IDs; `exploring → proposed → approved` enforced in code; the procedure floor; two capabilities removed, one added | everything below | — |
| **2** | **An approved specification becomes tasks on the board** | §1.4; the requirement→task link — the one missing row in §5 | assignment policy beyond an operator control | 1 |
| **3** | **Work links to requirements, and the gate is arithmetic** | §2.3 relevance-at-the-link; §2.4 rigor levels; §2.5 independence as a code check; evidence records | rejection vocabulary | 1, 2 |
| **4** | **You can see why work was rejected and how reviewers perform** | §1.6; §3.2 categories; §3.3 overturn rate and cost | — | 3 |
| **5** | **A hand-edit asks you which version to keep** | §1.3 mechanics; §3.1 | — | 1 (the digest) |

Each row is a vertical capability with an outcome the operator could watch working — not a layer.
That is the slicing rule this document's own §6 carries into the charter, applied to itself.

**Why 3–5 are not written now.** Their requirements depend on what using change 1 teaches: what the
rejection categories actually need to be, whether relevance-at-the-link is workable in practice, what
a hand-edit conflict looks like when it happens to a real document. Writing them today means
guessing, and a guess written in the voice of a requirement is indistinguishable from a decision —
the exact failure this document was restructured to prevent.

### The five forward commitments — requirements *in change 1*

The risk of a sequenced program is not forgetting the design; it is **foreclosing** it. These five are
load-bearing for later changes, cannot be reconstructed retroactively, and must therefore ship in
change 1 even though nothing in change 1 consumes them:

1. **Requirement IDs are stable** across schema versions and across rewording of the requirement
   text. Changes 2 and 3 both point at them; this is what umbrella task 14.1 exists for.
2. **The payload is versioned, and unknown fields survive a read/write round trip.** This is what
   lets change 3 add gate fields to documents authored before gates existed, and it is how §3.5's
   "do not freeze the contract" is satisfied without deferring change 1.
3. **The document digest is stored from the first write**, though nothing consumes it until change 5.
   §2.8.
4. **Every edit is recorded as an event** — actor, origin, run ID where one exists, and what changed.
   Changes 4 and 5 both read this history and **it cannot be backfilled**. §1.3.
5. **State transitions are append-only with actor attribution.** Change 4's telemetry has no other
   source.

A later change that finds one of these missing does not merely cost more work — it costs a migration
of every document already authored.
