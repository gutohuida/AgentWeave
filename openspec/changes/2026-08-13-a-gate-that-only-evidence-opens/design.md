# Design — A gate that only evidence opens

Sources: `2026-08-03-specification-authority-technical.md` (Child 3, "Rigor and gate enforcement"),
and `2026-08-10-coordinator-terms-and-format.md` §1.1 for the authority split. This freezes the
mechanism and records what the end-to-end run added.

## D1. Two layers, and the boundary between them is the point

The word "immutable" carries two different jobs here, and collapsing them is the failure this design
is built against.

**The mechanism is immutable in code.** Not configuration, not editable at runtime, not switchable
per project:

- that the transition graph exists and is the only way status moves;
- that a reviewer identity may not equal an author identity;
- that a `gate`-rigor requirement needs accepted evidence;
- that every status write goes through one service.

**The policy is operator-editable and agent-immutable.** Which rigor a document carries; which
evidence kinds satisfy it.

> *"If strictness is a setting, the guarantee is the setting's default, and defaults are not
> guarantees."*

**And the audit property applies over both:** each transition records the policy digest that
governed it. Without that, a gate that passed last month cannot be explained today — and the policy
being operator-editable is precisely what makes that a live risk rather than a theoretical one.

## D2. An agent cannot touch rigor

The load-bearing rule. An agent may not promote and may not demote.

Demotion is the dangerous direction and the easy one to overlook. If an agent blocked by a gate can
lower the document to `contract`, the gate is decorative — it becomes a speed bump the blocked party
removes. Promotion is refused for a quieter reason: an agent that could raise rigor could block
another agent's work, which is a decision about how the project is run.

This mirrors `spec-document-authority`'s existing rule that approval is the operator's and no agent
can express it — and, as there, it is enforced by **there being no argument and no route**, not by
instructing agents not to try. That distinction is the entire lesson of the charter-enforced gate
this replaces: *"a charter instructing an agent to enforce a gate on itself."*

## D3. Rigor lives in the document; its history lives in the Hub

`aw-spec-rigor` metadata in the HTML, visible to anyone reading the file, defaulting to `sketch`.
Consistent with the operator's 2026-08-10 decision that the document is authoritative, and with how
phase is already handled: the file states it, and the Hub owns the transitions that change it.

Writes are **compare-and-swap** against the document's current content digest — the machinery
`spec_lifecycle.divergence` already provides — so a rigor change cannot silently land on a document
that was edited underneath it.

`spec_rigor_events` is append-only: from, to, actor, reason, time, and the digest current at the
moment. No update, no delete, the same shape as `TaskTransition` and `SpecDocumentEvent`.

**Rigor is not phase.** A `gate` document can still be `exploring`, and an `approved` document can
still be a `sketch`. Phase asks "has the operator agreed to this?"; rigor asks "what happens to work
that ignores it?" The design source says so explicitly — *"rigor is not a replacement for change
approval"* — and conflating them would make every approved document enforcing, which is exactly the
barrier-heavy product the direction document rules out.

## D4. Promotion refuses a broken document; demotion keeps everything

**Promotion** to `contract` or `gate` is refused while identifiers are unresolved, references are
duplicated, or the document does not parse. Rigor is a claim about enforceability; a document that
cannot be read cannot be enforced, and promoting one would create a gate whose failures are
diagnostics rather than judgements.

**Demotion** changes enforcement only. Links, revisions, evidence and reviews all survive. Lowering
rigor to unblock something urgent, then raising it again, must not destroy the record — otherwise
the demotion is a laundering step.

## D5. The gate is a precondition on one edge

In the transition service, on the move into `approved`:

1. resolve every requirement the task links (B3);
2. select those whose document rigor is `gate`;
3. compute coverage with **B3's single query** — the same one the document badge and the project
   total call;
4. refuse when any selected requirement is not `verified`;
5. return a typed failure naming each requirement identifier and its reason.

**Step 3 matters more than it looks.** If the gate computed its own answer, a task could be refused
while the document beside it showed everything green, and no one would be able to say which was
lying. One query, or two truths.

**Why `approved` and not `completed`.** `completed` is an agent reporting it has finished writing;
`approved` records that the work is good, and is terminal. Evidence is accepted after review, and
review follows completion — so refusing `completed` would deadlock the ordinary path: the task could
never reach the step that produces the acceptance it is blocked for.

**Why not a separate gate service.** The design source is explicit: the gate belongs *in* B1's
transition service, not beside it. A second enforcement point is a second thing to bypass, and the
rule that no route may assign `Task.status` directly is what makes one point sufficient.

## D6. A refusal has to be actionable

This is the first change that can stop an operator's work, so the failure response is part of the
feature rather than an error path.

A refusal names, per requirement: the identifier, its current coverage state, and what would change
it — no linked evidence, evidence awaiting review, evidence stale against a reworded statement. "The
gate refused" without that is unactionable, and an unactionable gate gets switched off, which is a
worse outcome than never having built it.

The operator retains an explicit way through: demote the document, which is recorded, attributed and
visible — as opposed to a hidden override, which would be the same act without the record.

## D7. `verified` does not vary by rigor

Resolving the question B3 deferred: **accepted evidence against the current digest, at every rigor.**

The alternative — `contract` satisfied by recorded evidence, `gate` requiring accepted — was
rejected because promoting a document would then silently un-verify requirements that were verified
a moment before, and a coverage count would mean different things on two documents in one project. A
word whose meaning shifts with context is worse than a strict one.

The cost that made this look unattractive in the source document has since been removed: B3 lets a
tester agent accept evidence, so acceptance is no longer necessarily an operator bottleneck.

## D8. What this deliberately does not do

- **Does not gate on integration.** B3 reports `verified, not integrated` for evidence sitting on an
  unmerged agent branch. Whether that should refuse approval is a real question — and it belongs
  with whoever owns the integration step, which is currently nobody. Gating on it now would block
  every approval in the product as it stands today.
- **Does not touch the transition graph.** One edge gains a precondition; no edge is added or
  removed.
- **Does not put decisions in the conversation.** B7, and it needs the stable gate-decision identity
  this creates.
