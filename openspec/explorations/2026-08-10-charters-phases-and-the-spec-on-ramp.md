# Exploration — Charters, phases, and how a spec ever gets started

**Date:** 2026-08-10
**Mode:** explore session, captured after the fact
**Follows:** `2026-08-10-authoring-flow-without-skills.md`
**Scope:** what a charter is for once procedure moves to a phase machine; what separates an agent
from a conversation; how spec mode coexists with runner-native plan mode; and the discoverability
problem underneath all of it.

> Conclusions here are **agreed direction, not approved requirements.** They constrain B0, B2, B5
> and A1 and should be re-read when each is proposed.

---

## 1. Charter is accountability; phase is activity

The skills decomposition (procedure → phase machine, format → parser, judgment → charter) cuts the
charter too. Applied to `hub/hub/data/charters/spec.md`, almost nothing left is about *who you are*
— "don't write 'the system is fast'" is good advice for anyone in the propose phase.

The temptation was to conclude charters are vestigial. **That is wrong**, and the counter-example
is decisive: an *underwriter* and an *approver* are not two activities, they are two
accountabilities, and the separation between them is the entire point. That is guarantee G2 with a
business meaning rather than a software one.

> **A charter answers "what am I accountable for?" A phase answers "what am I doing right now?"**

Software misleads here: one capable model can perform every *activity* in a dev workflow, so
charters look redundant. In a domain with real separation of duties they are the product.

### What gets injected, and from where

```
  canonical context for a turn
  ══════════════════════════════════════════════
    roster ─────────────── project
    project instructions ─ project
    charter ────────────── AGENT     (accountability, scope)
    phase guidance ─────── DOCUMENT  ★ (how to do this activity)
    document context ───── DOCUMENT  ★ (what I am working on)

                      ★ = does not exist today
```

### The 21 starter charters are the deleted role subsystem under a new name

`charters.json` ships: tech_lead, architect, backend_dev, frontend_dev, fullstack_dev, qa_engineer,
devops_engineer, security_engineer, data_engineer, ml_engineer, technical_writer, code_reviewer,
project_manager, coordinator, model_router, explorer, implementer, verifier, guardian,
context_keeper, spec.

`charters/spec.md` is formatted as a role guide ("You Are Responsible For / You Are NOT
Responsible For") and **escalates to a "Tech Lead"** (lines 62, 83) that exists only if the
operator happened to create one — the same honesty defect as the six absent skills.

Sorted by the accountability test:

| Kind | Charters | Disposition |
|---|---|---|
| **Accountability** — a real review boundary | `code_reviewer`, `verifier`, `guardian`, `security_engineer` | Keep |
| **Activity** — belongs to a phase | `explorer`, `implementer`, `context_keeper`, most of `spec` | Move to phase guidance |
| **Same job, different tech** | the six `*_dev` / `*_engineer` variants | Collapse to one with scope |
| **Coordination-as-prose** | `coordinator`, `model_router`, `project_manager` | **These are the coordinator being built in code.** A charter asking a model to coordinate is the "guarantee is vibes" shape |

**And there is not one non-software charter.** If AgentWeave is for underwriting too, the starter
set should demonstrate it. Two or three domain charters would support that claim better than six
flavours of developer.

**Consequence for B0:** the repair is not "stop citing absent skills." It is *cut the set, re-shape
what remains to accountability, and add a non-software example.*

---

## 2. A conversation never becomes an agent

Asked directly: if charters thin out, what still separates an agent from a thread? The answer does
not depend on charters at all.

| | Agent | Conversation |
|---|---|---|
| Addressable (`send_message`) | yes | no |
| Own worktree | yes | no — shares the agent's |
| Distinct identity for author ≠ reviewer | yes | no — same identity |
| Runs concurrently with a sibling | yes | no — same queue |

> **An agent is a unit of concurrency, isolation, and accountability. A conversation is a unit of
> context.**

So one Opus agent, speccing in thread 1 and implementing in thread 2, is sound — **when the
operator is the reviewer**, which the phase machine already requires (approval is never an agent's
decision). A second agent is needed for parallelism or for agent-reviews-agent, not for competence.

Note for the still-open 1.10: two agents sharing a runner and charter are not independent reviewers
in any meaningful sense.

---

## 3. Spec mode and plan mode are different altitudes; ship both

**Plan mode is not currently available in AgentWeave.** `model_catalog.py`'s `permission_mode`
control offers `acceptEdits`, `workspace`, `manual`, `bypassPermissions`. Claude's
`--permission-mode plan` is not exposed.

```
  PLAN                                SPEC
  ────                                ────
  "what am I about to do?"            "what should this system do?"
  ephemeral, lives in the turn        durable, outlives the conversation
  about actions                       about behaviour
  per-run posture                     document-level phase
  runner-native, free                 ours: traced, gated
```

They are not rivals — plan is used *inside* the apply phase. They must not look like the same
control:

- **Permissions pill** gains `plan` as one more `ControlValue`. Per-run, ephemeral.
- **Phase** is shown near the document, not in the composer's posture row.

Suppressing a runner-native feature would make AgentWeave feel like it is fighting the CLI beneath
it, and arrivals from Claude Code would read the absence as a missing feature.

---

## 4. Phase belongs to the document, not the thread

The original framing — a thread that is "a spec thread" — created a detection problem with no
solution. *Promote* requires the human to classify; *infer* requires the machine to. Both fail,
because "add SSO login" is a spec conversation or a just-do-it conversation depending on what the
user wants to happen next, which is not in the text.

**Resolved by moving the phase onto the document.** A thread is in a phase because a document is
open in it.

```
  BOTTOM-UP                          TOP-DOWN
  ordinary thread                    a change document exists
    │ "I want this written down"       │ coordinator opens a thread
    ▼                                  ▼
  "create a spec from this"  ───▶  thread bound to a document
                                     phase = the document's phase
```

Neither path detects anything. The bottom-up trigger is a **want** ("I'd like an artifact"), not a
classification ("this is of type spec"). The bottom-up action is already a planned requirement —
umbrella §14.13, *"grow from conversation."*

Two consequences:

- The phase control is a **status readout**, not a mode switch. No document, no phase, no nagging.
- **`origin` may be the wrong axis for A1.** If phase comes from the document, the interesting
  field is *which document this thread is bound to* — a link, not an enum. Reinforces A1 option
  (B): reuse the agent's conversation and do not produce `origin="spec"` yet.

---

## 5. Where explore lives: nowhere new

Explore findings are not homeless — `Conversation` and its message history are durable. The problem
is that a transcript is not a usable input to the propose phase.

`submit_checkpoint_notes` → `Checkpoint` / `CheckpointNote` already distils a conversation into
structured notes, and **no live agent has ever called it** (handoff 0023). The propose phase should
consume that distillation rather than the raw transcript. No new artifact type; a shipped,
never-exercised capability gets its first real user.

---

## 6. The discoverability problem, unsolved but narrowed

The risk, stated plainly: 50 conversations, 0 specs, "I don't see why this is better than T3." At
the moment of typing there is no cost to skipping the spec and no visible benefit to writing one;
the payoff arrives weeks later. A button loses to that.

The checkpoint warning solved the same shape — the user will not remember — **without asking anyone
to notice anything**: it watches a measurable non-semantic signal (context %) and interrupts at a
threshold. Available analogues today: turn count, tokens spent, task completion. Not yet available:
`files_changed` (never observed non-empty), repeat-visit counts.

But the analogy breaks where it matters: checkpointing prevents **loss** (urgent, self-evident);
a spec offers **future value** (trivially dismissed forever) — and dismiss-forever was a real enough
problem for the urgent case to require its own change.

Three shapes, and the direction chosen:

1. **Interrupt** (checkpoint-shaped) — reuses shipped machinery; nags; barrier.
2. **Ambient** (coverage-shaped) — no interruption; easy to ignore; 0/0 reads as fine.
3. **Inversion** — every thread starts in explore. **Chosen direction**, because explore is
   indistinguishable from ordinary conversation. Nothing about a typo fix changes; no document
   exists; no ceremony. The only real decision is **explore → propose**, when an artifact
   materialises — and at that point the agent has material and can offer a *draft* rather than
   homework.

(2) becomes the safety net rather than the mechanism.

**Residual, unsolved:** the agent still decides when to offer. That is advisory and low-stakes —
worst case a declined draft — and is one of the decision points the retired coordinator's
exploration must classify. Whether "explore" is even the right name for the default state of every
conversation is also open; it may simply be "no phase," with propose the first real one.

---

## 7. Parked: the steward agent

An operator-configured agent, triggered by **AgentWeave events** rather than cron — on handoff, on
thread creation, on a spec moving to done, on archive — with broad read access to the Hub's data and
metadata, which helps with decisions and reaches the operator through notifications.

**Why it is safe:** it has *no authority*. It reads and reports; it cannot approve, transition, or
write. That is the governance-safe use of a model, and the exact inverse of the
"a gate decided by AI is theatre" problem.

**What exists:** `AIJob` (cron → agent → message, with `create_job` / `run_job` / `toggle_job` /
`delete_job` on MCP) and an event substrate (`EventLog`, `persist_event`, `sse_manager.broadcast`
emitting `task_created`, `task_updated`, checkpoint and session events). The missing piece is only
the **event → agent** binding; cron → agent is done.

**Why not now:** its value is proportional to the structured data available to read. Today the MCP
surface exposes tasks, messages, questions and jobs — no accounting, runs, conversations, coverage,
or specs. Its most valuable report, spec coverage, requires B2 and B3. Built today it is a cron job
that says "you have 3 open tasks," which the task board already shows.

**Two consequences to carry forward:**

1. **B6 splits.** *Advisory in-flow* (a coordinator consulting a model at a gate) is high-risk and
   blocked on the binding/advisory classification. *Advisory out-of-flow* (the steward) has no
   authority, needs no governance design, and can ship as soon as there is data worth reading —
   potentially well before B6.
2. **B3's read tools should be designed for an out-of-flow reader too**, not only for agents
   mid-turn. Different access pattern; easy to foreclose by accident.

---

## Open, carried forward

- Is "explore" a phase, or just the absence of one?
- Should the propose offer come from the agent mid-turn, or from the machine at a threshold? Very
  different failure modes when the model is wrong.
- How many charters, and which non-software domains does the starter set demonstrate?
- Everything in the final section of `2026-08-10-authoring-flow-without-skills.md` — the
  binding/advisory classification and the governance questions — remains untouched.
