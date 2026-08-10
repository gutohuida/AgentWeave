# Exploration — How the spec agent authors, without skills

**Date:** 2026-08-10
**Supersedes:** `changes/2026-08-07-spec-execution-coordinator/` (retired; its unanswered questions
are carried forward in the last section of this document)
**Answers:** the operator's question of 2026-08-10 — *"The explore, propose, apply flow is really
good but how would we fit this inside AgentWeave without the skills? How would we make the agents
behave? Grill the user, then propose in a certain format that is acceptable by the spec feature."*

---

## The finding that decides it: skills are a Claude-only mechanism

AgentWeave is a multi-runner product. `hub/hub/runner_commands.py` wires two runners to a real spawn
path — `claude` and `codex`. `.claude/skills/` is read by Claude Code. **A Codex agent cannot invoke
`aw-spec-propose` under any circumstances.**

So "install the 24 skill templates" was never a complete answer. It would deliver the authoring flow
to half the product's agents and silently omit it for the other half — while the seeded `spec`
charter, which both runners receive, instructs all of them to use it.

**AgentWeave already has a runner-agnostic behaviour-delivery mechanism, and it is shipped.**
`hub/hub/api/v1/agent_trigger.py:333-360`:

```python
    # Build context from current Hub-owned state for every turn. Runners consume a file,
    # so materialize the canonical response inside the effective workspace immediately
    # before command construction; an edited charter is therefore visible on the next run.
    ...
    context_file = Path(effective_work_dir) / ".agentweave" / "context" / f"{agent}.md"
    context_file.write_text(rendered_context["context"], encoding="utf-8")
```

That file — roster, charter, project instructions, access-path guidance — is rebuilt every turn and
handed to `build_agent_command(context_file=...)` for **both** runners. It is operator-editable, it
is versioned in the database, and an edit takes effect on the next turn.

---

## A skill is three different things wearing one filename

`aw-spec-propose.md` is 252 lines; `references/html-spec-conventions.md` is 541. Reading them, the
content separates cleanly into three kinds, which is why "install or delete" is the wrong question —
**the three kinds belong in three different places in AgentWeave.**

| What's inside a skill | Where it belongs | Why there |
|---|---|---|
| **Procedure** — "first explore, then propose, then get approval, then apply" | **The coordinator's phase machine** (code) | A procedure the model is *asked* to follow is a suggestion. A procedure code drives is a guarantee. This is the coordinator's whole thesis, and the authoring flow is its first real use case |
| **Format contract** — what a valid spec document looks like | **A Hub parser that validates and refuses** | 541 lines of "please emit this shape" becomes a parse-or-reject boundary. The contract stops being prose the model may drift from and becomes something that fails loudly |
| **Judgment guidance** — how to interview, what makes a requirement testable, anti-patterns | **The charter** (already shipped, runner-agnostic, operator-editable) | This is exactly what charters are for, and `hub/hub/data/charters/spec.md` already carries a version of it |

**So the answer to roadmap [DECIDE #2] is neither of the two options it offered.** The skills are
**decomposed**: procedure into the coordinator, format into the parser, judgment into the charter.
The 24 template files are then deleted, because every useful thing in them has a better home — not
because the content was worthless, but because a markdown file in `.claude/skills/` is the wrong
container for all three of the things it currently holds.

---

## The flow, as a phase machine

The explore → propose → apply shape is worth keeping; the operator is right that it is good. Here it
is as something code owns rather than something a document requests.

| Phase | Entry condition | The agent's job | Exit condition (checked by code) |
|---|---|---|---|
| **Explore** | An operator or agent opens a spec conversation | Interview the operator. Ground in the codebase | No unresolved `[NEEDS CLARIFICATION]`; an exploration artifact exists |
| **Propose** | Explore satisfied | Emit a spec document in the validated format | Document parses; every requirement carries a stable ID; rigor is declared |
| **Approve** | Document parses | — (the agent does not act) | An **operator** decision is recorded. Never an agent's |
| **Apply** | Status is `approved` | Implement, linking work to requirement IDs | Tasks reach terminal states through the B1 transition machine; evidence attached |
| **Archive** | Gate satisfied for every `gate`-rigor requirement | Move the document, update the manifest | Archive write validated and atomic |

Two properties this has that a skill cannot:

1. **It works identically for a Codex agent and a Claude agent**, because the phase, its context, and
   its exit check live in the Hub, not in the runner's extension format.
2. **The approval gate is real.** Today `hub/hub/data/charters/spec.md:15` asks the agent to enforce
   the draft→approved gate on itself. Under a phase machine, `apply` has an entry condition the
   agent cannot satisfy by asserting it has been satisfied.

### "Grill the user" is already built

The explore phase's interview needs no new machinery. `ask_user` takes 1–4 structured questions,
blocks the run, and returns the answers; the operator steps through them above the composer. The
batched-questions change (`archive/2026-08-07-batched-operator-questions/`) shipped it.

The phase machine's contribution is the **exit condition** — the coordinator re-invokes the agent
until the explore phase's condition is met, rather than the agent deciding for itself that it has
asked enough. That is a bounded loop over an existing tool, not a new capability.

### Where a model is genuinely consulted

Per the retired change's own framing — *code decides the flow; at a point needing judgement it asks
a model a bounded question and applies its own rule to the answer.* Candidate points in this flow,
to be classified binding/advisory in the follow-up exploration:

- Is this exploration complete enough to propose from? (advisory — the operator ratifies by approving)
- Is this requirement testable as written? (advisory — a diagnostic on the document)
- Does this evidence actually demonstrate this requirement? (**binding, and the hard one** — this is
  where "if an AI can decide a gate's outcome, the determinism is theatre" bites)
- Is this document edit editorial or substantive? (advisory — the 2026-08-03 exploration already
  ruled that agents may propose the classification but not accept it)

---

## The format must be designed backwards from the features

The operator's framing — *"the spec itself should be created in a way that will augment the
AgentWeave spec and development experience"* — is the right constraint, and it has a sequencing
consequence.

The HTML contract is not a document-formatting preference. Every element in it exists because a
product feature needs it:

| Format element | Exists because |
|---|---|
| Stable project-global requirement IDs | Traceability (B3) needs something to link a task to that survives rewording and relocation |
| Semantic digest inputs | Evidence staleness (B3) needs to know when meaning changed |
| `aw-spec-rigor` | Gates (B4) need to know which requirements are enforced |
| `data-task-id` / `data-requirements` | Bidirectional navigation (B3) |
| Bounded structural profile | The parser must be able to refuse; "infer requirements from arbitrary HTML" was already rejected |

**Therefore the format contract cannot be finalised before B3 and B4 are designed.** It is written in
B2 but must be reviewed against B3/B4's needs before it is frozen — otherwise the parser ships a
contract that cannot express what the gates need, and every existing document has to be migrated.

This is a change to the roadmap's assumptions worth stating: **B2 freezes the parse contract, but
B3 and B4 must be designed far enough to state their requirements on it first.**

---

## Consequence for the roadmap

| Roadmap item | Change |
|---|---|
| **[DECIDE #2]** | Answered: **decompose, then delete.** Procedure → coordinator, format → parser, judgment → charter |
| **B0** (aw-spec honesty repair) | Grows slightly: rewrite the seeded `spec` charter to carry the judgment guidance directly and stop citing absent skills. Remove the false Hub-discovery claim and the self-enforced approval gate |
| **B6** (AI augmentation) | **Reframed, not re-ordered.** It is not a bolt-on; it is how the authoring flow works at all. It still comes after the machine exists, but it is release-blocking rather than optional |
| **B2** | Must not freeze the parse contract until B3/B4 have stated their requirements on it |
| New | A **phase machine** for the spec workflow, which is a second instance of B1's transition machine rather than a separate mechanism. Whether they share an implementation is a B1 design question |

---

## Carried forward from the retired change

`changes/2026-08-07-spec-execution-coordinator/` is retired, not archived — it never described
shipped behaviour, and an archived change reads as shipped. Its cluster-1 questions are answered in
`2026-08-10-coordinator-terms-and-format.md`. These remain **open and worth exploring**, and are the
next exploration to run:

- **Classify each AI decision point as binding or advisory** — the central question. Binding: the
  answer is an input to a rule code applies. Advisory: it is recorded rationale something else
  ratifies.
- **Answer shape for each binding point** — bounded and validatable, not free text. Determine whether
  the existing structured-output path suffices.
- **Behaviour when the model is unavailable, times out, or is self-inconsistent** — decided per
  decision point, not globally. Fail-closed blocks work; fail-open defeats the gate.
- **Reproducibility** — is the guarantee "the same transitions given the same decisions," or
  something stronger? Are decisions cached against their inputs?
- **Author/reviewer separation: separated on what identity?** Agent name, run, runner, or model. Two
  agents bound to the same runner and charter are not independent reviewers in any meaningful sense.
- **Echo-chamber protection** — what it means when the reviewer is a model of the same family as the
  author. Find what, if anything, implements it today.
- **Evidence kinds** — which can satisfy a gate alone. A gate satisfiable by a model asserting it is
  satisfied is not a gate.
- **Where the human sits** — which gates escalate to the operator, reusing the shipped questions and
  permissions machinery rather than inventing a second one.
