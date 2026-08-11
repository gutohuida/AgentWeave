# Design — Charter set re-shape (B0)

## Context

A charter is text the Hub inlines into an agent's turn. That single fact decides everything below:
a charter is not a description of a role that a reader may take or leave, it is an instruction a
model will act on. `openspec/specs/agent-charter/spec.md:77-87` already states the standard —
describe only what the runtime provides — and `hub/tests/test_agent_facing_text.py` already enforces
two of its three clauses. The starter set fails all three anyway, most widely on the clause with no
test behind it.

Two problems are tangled here and it is worth separating them, because only one is urgent:

1. **Honesty.** Charters point at skills, files, mechanisms and participants that do not exist. This
   actively misleads a running agent, and has: the test file's own docstring records the operator's
   session that produced "an agent that read files it could not find."
2. **Shape.** The set is the deleted role subsystem renamed. This wastes an operator's attention and
   misrepresents what the product is for, but it does not break a run.

Fixing (1) alone was the original narrow B0. The operator chose to fix both, because rewriting 21
charters for honesty and then deleting 15 of them shortly after is two passes over the same text.

Direction comes from `openspec/explorations/2026-08-10-charters-phases-and-the-spec-on-ramp.md` §1,
which is agreed direction rather than approved requirement, and is what this change converts into
requirements.

## Goals / Non-Goals

**Goals:**

- No seeded charter names a participant, file, command, or mechanism that a fresh project lacks.
- The set is decided by one stated test — accountability, not activity — so a future addition has a
  criterion to meet rather than a precedent to follow.
- The starter set demonstrates a non-software separation of duties.
- Removed activity content survives for the change that builds phase guidance.
- The absent-participant clause becomes enforceable, not merely stated.

**Non-Goals:**

- Building phase guidance, migrating existing projects, reinstating the `aw-spec-*` skills, or
  touching the charter API, UI, or schema. See the proposal's Non-Goals.

## Decisions

### D1 — The set is decided by the accountability test, and the test is written down

**A charter answers "what am I accountable for?" A phase answers "what am I doing right now?"**

Applied, this sorts the 21 mechanically rather than by taste:

| Verdict | Charters | Why |
|---|---|---|
| **Accountability — keep** | `code_reviewer`, `verifier`, `guardian`, `security_engineer`, `tech_lead`, `spec` | Each is a boundary someone is answerable at |
| **Same accountability, different subject** | the six `*_dev` / `*_engineer`; `architect`→`tech_lead`; `qa_engineer`→`verifier`; `technical_writer`→`developer` | Differ by what they work on, which is scope |
| **Activity — belongs to a phase** | `explorer`, `implementer`, `context_keeper`, the bulk of `spec` | Describe doing, not answering for |
| **Coordination-as-prose — remove** | `coordinator`, `model_router`, `project_manager` | Asks a model to guarantee what code now guarantees |

Result: **21 → 9.** Six kept, `developer` added, `underwriter` and `underwriting_approver` added.

*Rejected: cutting to the four pure accountabilities.* It reads well as a principle and fails as a
starter set — an operator creating their first agent would find nothing that says "build the thing",
which is the overwhelmingly common case, and would write one themselves. A starter set exists to be
used, not to be exemplary.

*Rejected: keeping all 21 and only repairing the text.* The honesty pass has to rewrite every file
anyway; rewriting fifteen files in order to delete them later is the expensive ordering.

### D2 — Software specialisation is scope, not identity

`backend_dev` and `frontend_dev` are answerable for the same thing — that the code they wrote works.
Nothing in either charter's *responsibility* differs; what differs is the subject matter, and the
subject matter of a particular agent is a property of that agent's assignment, not of a shared
behaviour contract. Six charters that differ only in their examples produce six near-duplicate texts
to maintain and six wrong answers to "which one do I pick?"

One `developer` charter carries an explicit scope line the operator fills in. That also fixes a
defect the variants had structurally: `backend_dev` disclaimed responsibility for infrastructure and
`devops_engineer` for business logic, so a project with one developer agent had a charter telling it
half its work was somebody else's.

*Rejected: keeping `fullstack_dev` as the collapsed one.* Its name asserts breadth rather than
taking it from the assignment, and it carries the same "not responsible for" disclaimers.

### D3 — Coordination charters go, because the guarantee moved into code

`coordinator`, `model_router` and `project_manager` ask a model, in prose, to route work, pick
models, and track progress. Two of those now have real implementations — the transition machine
(`2026-08-10-task-transition-machine`, archived) and the model catalogue. A prose instruction beside
a code guarantee is strictly worse than either alone: it is unenforced, it can disagree with the
enforced version, and its presence suggests to the operator that assigning it does something.

`coordinator` is also the largest single source of absent-file citations
(`.agentweave/shared/plan-[task-id].md`).

*Rejected: rewriting them to describe the code's behaviour.* That is documentation, and a charter is
not documentation — it is instruction injected into a turn. An agent does not need to be told how the
transition service works in order to be subject to it.

### D4 — Removed activity content is parked in the change, not deleted and not left seeding

`explorer`, `implementer`, `context_keeper` and the procedural bulk of `spec` contain genuinely
useful guidance — how to investigate before deciding, what makes a requirement testable — that is
destined for phase guidance. Phase guidance does not exist yet.

Three options, and the middle one is chosen deliberately:

- *Leave them seeding until phase guidance exists.* Rejected: they stay wrong in the meantime, and
  "temporary" is how the current 21 got here.
- **Park the text under `openspec/changes/charter-set-reshape/parked-phase-guidance/`.** Chosen. The
  change carries its own leftovers, and archiving carries them with it, so the change that builds
  phase guidance has the source at a findable path rather than in a diff.
- *Delete and rely on git history.* Rejected: recoverable is not the same as findable. Nobody greps
  a deleted file they do not know existed.

The parked files are reference material, not seeds — nothing loads that directory, and the tasks
assert it.

### D5 — Underwriting is the non-software example, and it ships as a pair

One non-software charter would demonstrate nothing. The claim being supported is that AgentWeave
serves domains with **separation of duties**, and a separation needs two sides: `underwriter`
assesses and prices the risk, `underwriting_approver` accepts it on the institution's behalf above a
threshold. Neither may perform the other's step, and that constraint is the entire content of the
charters — which is exactly what makes them a better demonstration of what a charter is *for* than
any of the software ones.

This is also the case that answers "are charters vestigial once phases exist?" One capable model can
perform every activity in a dev workflow, so software makes charters look redundant. It cannot be
both the underwriter and the approver, because the separation is the control.

*Rejected: a single generic `domain_expert`.* It demonstrates the opposite of the point — that a
charter is a topic label.

*Rejected: adding legal, finance and editorial too.* Each additional pair is more for a new operator
to read past, and one worked example carries the argument. The operator picked one.

### D6 — The absent-participant clause gets a scenario and a test, keyed to the roster

The clause has been in the spec since the charter capability shipped and 16 charters break it,
because `test_agent_facing_text.py` checks a needle list of removed *files and commands*. The gap is
structural: files and commands are a closed set you can enumerate, and roster participants are not.

The test asserts on the shape the defect takes rather than on a list of role names: a seeded charter
must not instruct the agent to *address* a named party — the pattern is an escalation or hand-off
directive naming a title. Concretely, the surviving charters name no other charter's title in an
instruction to contact, escalate to, hand off to, or ask.

Where a charter genuinely needs to escalate, the target is the operator via `ask_user`, which always
exists. That is the honest escalation path in a Hub-owned project, and it is what the four kept
accountability charters already partly do.

*Rejected: asserting against the manifest's own titles.* It would pass the moment someone removed a
charter while leaving the reference, which is precisely today's bug — 16 charters cite a Tech Lead
that a project need never contain.

### D7 — The spec charter keeps its judgment and sheds its procedure

What survives in `spec` is the part that is genuinely an accountability and genuinely durable: the
spec captures WHAT and WHY, not HOW; requirements are measurable assertions, not "the system is
fast"; slice vertically by capability; a stale spec is worse than none; a passing suite does not
prove a faithful rebuild; ambiguity goes to the operator rather than being guessed.

What goes: the six skill citations, the `spec/` path inventory, the `spec/index.json` manifest
duties, the false Hub-discovery claim, and the self-enforced approval gate. Every one of those
describes a mechanism the project does not currently have, and the last one describes a mechanism
that exists but is not the agent's to enforce.

This is what forces the `aw-spec-workflow` delta. That capability's "The spec role routes instead of
duplicating procedures" requirement *mandates* the routing being removed. Leaving the spec untouched
while changing the charter would leave a shipped requirement asserting behaviour the code contradicts
— the same class of defect this change exists to close, one level up.

### D8 — Existing projects are left entirely alone

Seeding is once-per-project and this change does not alter that. A live project keeps all 21 charters,
including ones the operator has since edited. No migration, no backfill, no reconciliation prompt.

The asymmetry is deliberate and worth stating so a later session does not "finish the job": the
defect is real for existing projects too, but their charter rows are operator-owned data. Silently
rewriting text an operator may have authored is worse than leaving a stale seed they can edit. If
adopting the new set is ever wanted, it is an operator-initiated action with a UI, which is a
different change.

## Risks / Trade-offs

- **An operator upgrading sees no improvement** → their charters are theirs; the change is about what
  a *fresh* project is given. Called out in D8 rather than papered over, and the user test guide
  checks a fresh project explicitly, because testing on Testbed would show nothing.
- **Collapsing six variants loses useful domain hints** (`ml_engineer` said things about training runs
  that `developer` will not) → the scope line is where that goes, authored per agent. The hints were
  worth less than they look: they were generic enough to apply to any project and therefore to none.
- **The absent-participant test is heuristic and can misfire** → it runs only over the nine seeded
  files, which this change also authors, so a false positive is fixed by rewording a sentence rather
  than by weakening the test. Preferred to no assertion at all on the clause 16 charters broke.
- **Parked text is never picked up** → it is referenced from the change that parks it and travels
  into the archive with it. If phase guidance is never built, the loss is guidance that was already
  wrong in place.
- **`underwriting_approver` reads as odd in a software project** → that is the demonstration working.
  A starter set of nine where two are visibly not about code says what the product is for faster than
  any documentation, and an operator who does not want them deletes two rows.
- **Fewer charters means an operator writes their own sooner** → intended. The set should be a
  starting point that runs out, not a catalogue that pretends to be complete.
