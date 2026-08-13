# A gate that only evidence opens

Roadmap **B4** — *rigor and completion gates*. Technical design source:
`openspec/explorations/2026-08-03-specification-authority-technical.md`, Child 3. Authority model:
`openspec/explorations/2026-08-10-coordinator-terms-and-format.md` §1.1. Depends on **B3**
(`2026-08-13-a-requirement-knows-its-work`) for the coverage query, and on **B1** (shipped) for the
transition service the gate lands in.

## Why

**Nothing has ever refused a task for being unverified.**

`gate_policy: {"rigor": ...}` round-trips through save and render today and is read by **nothing** —
it appears only in three test files. The field was laid down and never built on.

What that costs was visible in the 2026-08-13 end-to-end run. Six tasks went `completed` →
`under_review` → `approved`, and the transition machine did its job: it refused a reviewer's attempt
to jump `completed → approved`, forcing the work through review. But that is a check on the *shape*
of the move, not on whether the work was any good. **At no point did anything ask whether the
requirements the task served were verified**, because nothing could.

The predecessor mechanism was worse than absent. From the coordinator analysis:

> *"Enforcing the approval gate: no implementation begins on a change spec until the user approves"*
> — **it is a charter instructing an agent to enforce a gate on itself**, … to enforce a gate that
> is honour-system. It will improvise.

Two things changed that make this buildable now. **B1 shipped** a transition service that every
status write already goes through. **B3 supplies** a single coverage computation and real
task↔requirement links. B4 is the join: the gate has somewhere to live and something to ask.

## What Changes

- **Rigor becomes real.** A document declares `sketch`, `contract` or `gate` in `aw-spec-rigor`
  metadata, visible in the file, defaulting to `sketch`. The Hub owns the transitions, writes them
  compare-and-swap, and records each in an append-only `spec_rigor_events`.
- **Rigor is the operator's alone.** An agent SHALL NOT promote or demote it. This is the whole
  change: a gate an agent can lower is a gate that opens itself. *"A project must be able to say
  'this one is a sketch, don't gate it.' An agent must never be able to say that about its own
  work."*
- **Promotion is refused while the document is broken** — unresolved identifiers, duplicate
  references or parse errors. Rigor is a claim about enforceability, and a document that cannot be
  read cannot be enforced.
- **Demotion changes enforcement only.** Links, revisions, evidence and reviews survive it, so
  lowering rigor to get unblocked and raising it again does not erase what was already established.
- **The completion gate lands in the transition service**, not beside it: resolve every requirement
  the task links; select those whose document rigor is `gate`; compute state with **B3's single
  coverage query**; refuse the move into `approved` when any is not verified; return a typed
  response naming the requirement identifiers and the reason for each.
- **Every route asks the same question.** Operator UI, agent HTTP actions, MCP and jobs all call the
  one service. **No route may assign `Task.status` directly** — that rule already exists and this
  change depends on it holding.
- **Each transition records the policy that governed it** — the policy digest in force at the
  moment of the decision. A gate that passed last month must remain explicable after the policy has
  been edited, and the policy being operator-editable is exactly what makes that a live risk.

## Resolving the question B3 deferred

**`verified` means the same thing at every rigor: accepted evidence against the current digest.**
Rigor changes what *happens* about that state — nothing, reported, or refused — never what it
means.

The alternative, letting `contract` be satisfied by merely recorded evidence, was considered and
rejected. It would mean promoting a document from `contract` to `gate` silently un-verifies
requirements that were verified a moment earlier, and that a coverage count means different things
on two documents in the same project. A word that shifts meaning by context is worse than a strict
one, and with a tester agent able to accept evidence (B3), acceptance is not the bottleneck it
would have been.

What rigor *does* change:

| rigor | coverage | task completion |
|---|---|---|
| `sketch` | reported | never blocked |
| `contract` | reported, and drift surfaced | never blocked |
| `gate` | reported | **refused into `approved` while any linked requirement is unverified** |

## Where the gate fires, and why not earlier

The gate refuses the move into **`approved`**, not into `completed`.

`completed` is an agent saying "I have finished writing." `approved` is the system recording that
the work is good, and it is the terminal state. Refusing `completed` would deadlock the ordinary
flow: evidence is accepted after review, and review happens after completion, so a task could never
reach the step that produces the acceptance it is being blocked for.

## Capabilities

### Modified Capabilities

- `spec-document-authority`: a document SHALL carry a rigor level that only the operator can change.
- `task-lifecycle-governance`: approval SHALL be refused while a linked `gate`-rigor requirement is
  unverified, through the same service every status write already uses.

## Impact

**Behaviour** — a project can declare that a document is binding and have that mean something. The
demonstrable outcome, from the design source: *identical task completion succeeds for a sketch or a
contract and is refused for an unsatisfied gate, then succeeds after independent evidence
acceptance.*

**Schema** — `spec_rigor_events`; a policy-digest column on the transition record. Rigor itself
lives in the document, not a column.

**Risk** — this is the first change that can *stop* an operator's work. Every refusal must name the
requirement and say what would satisfy it; a gate that refuses without explaining is worse than no
gate, because it cannot be acted on and will be switched off.

## Non-Goals

- **Not making strictness a setting.** The enforcement *mechanism* is immutable in code: that the
  transition graph exists, that a reviewer may not be the author, that a `gate` requirement needs
  accepted evidence, and that every status write goes through one service. Only the *policy* —
  which rigor a document carries — is editable, and only by the operator. *"If strictness is a
  setting, the guarantee is the setting's default, and defaults are not guarantees."*
- **Not changing the transition graph.** B1's edges are unchanged; this adds a precondition to one
  of them.
- **Not the authoring workspace** (B5) or **approval gates in the conversation** (B7). B7 needs
  stable gate-decision identities, which this creates.
- **Not gating on integration.** B3 reports `verified, not integrated`; whether *that* should refuse
  approval is a real question and belongs with whoever owns the integration step, which nothing
  currently does.
