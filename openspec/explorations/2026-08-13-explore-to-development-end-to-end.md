# Explore → spec → tasks → build → review, driven end to end

**Date:** 2026-08-13 · **Hub:** local, `:8010` · **Project:** `aw-e2e` (`proj-471e281a`)
**Agents:** `architect` (Codex, Spec Author) · `builder` (Claude, Developer) · `reviewer` (Codex, Code
Reviewer) · **27 runs**, 34 task transitions, 17 spec-document events.

The first run of the *whole* loop rather than one phase of it. `spec_loop.py` covered exploring;
this covered everything after it, which is where the unexamined seams were.

**The product built:** a flatmate expense-splitter CLI — `init`, `expense`, `correct`, `repay`,
`settle`, `balance`. **99 tests, passing.** Verified independently, not on the agents' say-so:
balances and the settlement transfers were recomputed by hand and match.

## What the loop actually did

| Step | How | Turns |
|---|---|---|
| Exploration interview | prose, grounded in the repo, stopped for answers | 3 |
| Document written | `submit_spec_document`, kept in `exploring` while questions were open | — |
| Close / propose / approve | operator only; no agent-facing route exists | 3 API calls |
| Spec → task board | agent called `create_task` ×6 | 1 |
| Build | one run bound per task, moved to `in_progress` on bind | 11 |
| Review | different agent, ran the tests itself, moved `completed → under_review → approved` | 8 |
| Extension (`balance`) | reopen → interview → submit → approve → build | 5 |

**Three interview rounds to a proposal-ready document.** Not endless. The agent stopped and asked
rather than guessing, and the questions were ones a person genuinely had to answer (what "minimal
transfers" means; who absorbs the rounding cent).

## What works, and is worth keeping

- **The approval gate is real.** `propose` before the operator closes exploration is refused
  (`explore_not_closed`). An approved document refuses further writes. There is no agent-facing
  phase route at all — not a rule, an absence.
- **The transition machine refused a shortcut.** The reviewer's first `update_task` failed:
  `completed → approved` is not an edge, so it went through `under_review`. The history cannot say
  work was approved without being reviewed.
- **Author/reviewer separation held**, and the reviewer independently re-ran the suite rather than
  trusting the builder.
- **Requirement identifiers are stable across an extension.** FR-1…FR-13 survived the reopen; the
  new requirement minted FR-14 from the high-water mark. Two withdrawn requirements (FR-5, FR-7)
  were never reissued.
- **`rename_spec_document` was used unprompted**, in the first turn, once the interview established
  the subject. `indigo-basilisk` → `shared-flatmate-expense-command-line-tool`.
- **Open questions are structural**, not just prose: five were recorded in the payload and all five
  closed before approval.

## Findings

Ordered by how much they cost.

### F1 — A building agent cannot read the specification it is implementing

`spec/` is **untracked** in the project repo (`?? spec/`). Agent worktrees are git worktrees, so
they contain tracked files only. The builder's worktree has no `spec/` directory at all.

The turn context makes this worse by looking sufficient: it states the document's **path and
phase**, and then says *"the operator is viewing `spec/changes/…/spec.html`"* — a path the agent
cannot open. It never carries the document's **content**. That block was written for the *authoring*
case; there is no implementing case.

The builder said so itself, unprompted:

> *"I don't have filesystem or MCP-resource access to the live `spec.html` … I built to the FR-14
> wording and acceptance criteria already captured verbatim on the task."*

So **the task's copied requirement text is the de facto contract at build time**, and the approved
document is decorative once implementation starts. Drift between them is undetectable.

### F2 — A peer-triggered run silently loses the operator's permission posture

Every trigger without a `conversation_id` opens a **new conversation**, and runtime overrides live
on the conversation.

| conversation | agent | overrides |
|---|---|---|
| `conv-1ab659d3` | builder (operator composer) | `{"permission_mode": "workspace"}` |
| `conv-3c7a302c` | builder (peer message) | **`None`** |

The operator chooses "Workspace only", the builder hands work to the reviewer, the reviewer messages
back — and the resulting run has a **different posture than the operator chose**, with nothing said.
This is the concrete damage behind the previously-recorded open question about conversation reuse; it
is not merely a continuity nicety.

### F3 — The default Claude posture can write code but never run it

`DEFAULT_CLAUDE_PERMISSION_MODE = "acceptEdits"` accepts edits and still prompts for `Bash` — and
headless there is nothing to answer the prompt. Observed twice, both times the builder honestly
reported it:

> *"every `python`/`py` invocation in this session … is blocked with 'This command requires
> approval', and there's no interactive user available to grant it … this should be treated as
> unverified-by-execution."*

Same agent, same code, `permission_mode: workspace`: **14/14 tests ran and passed.**

The rationale in `runner_commands.py` says `acceptEdits` was chosen over `manual` so a run "can do
work". Running the tests *is* the work. And it is **runner-dependent**: the Codex reviewer executed
freely throughout, so whether an agent can verify its own output depends on which CLI it is bound
to — not on anything the operator chose.

Combined with F2: an agent reached by a peer message reverts to a posture in which it cannot verify,
while still being asked to.

### F4 — Nothing integrates the work

`master` contains `README.md`. Every line of the product lives on `agentweave/builder`, in commits
titled **"Auto-snapshot: builder's turn"** — no task id, no requirement id. Six approved tasks and
99 passing tests, and none of it is on the main branch. "Approved" does not mean "in the product",
and no step in the lifecycle says so.

`.pyc` files are committed; no `.gitignore` is seeded.

### F5 — The document does not know it was implemented

The approved spec still says, in its own evidence section:

> *"No implementation exists to validate against the specified behaviors."*
> *"Acceptance criteria are proposed coverage … not tests observed passing."*

Both are now false. Nothing feeds implementation back into the document, so a reader of the
specification cannot tell whether it describes a plan or a shipped thing.

### F6 — A question asked only in prose can vanish

The agent asked, in round two, whether an expense needs a **description and a purchase date**. I
never answered it. It was not recorded in `open_questions`, not carried into a requirement, and not
declared a non-goal — it simply disappeared. The shipped ledger has no description and no date.

The structural `open_questions` list is a real ledger; the prose around it is not. The interview
being conversational is right, but only the questions the agent chose to formalise survive.

### F7 — Retired requirement identifiers are forgotten one save later

`read_identity` returns only `requirements` and `high_water`; it never reads the stored `retired`
map back. `retained()` therefore computes retirement from the *live* previous map alone, so the
record covers only the immediately preceding submission. Observed: `{FR-5, FR-7}` retired after the
v1 approval, then **`retired: {}`** after the next save.

Reuse is still prevented — minting reads `high_water` — but the docstring's stated purpose ("so a
later change can offer 'was this a rename?'") does not hold.

### F8 — Peer acknowledgement burns runs

`run-e7ec6dac` exists solely to say *"Acknowledged. This independently matches my review run."*
Builder and reviewer ping-ponged acknowledgements, each one a scheduled run with a real cost. Of 27
runs, several carried no work.

### F9 — Rename moves the path but not the title

After `rename_spec_document`, `SpecDocument.title` still held the operator's opening sentence while
the path held the real subject. The title only caught up on the next `submit_spec_document`. The
agent had already told the operator it had "renamed the specification to …", which was half true.

### F10 — The delivered tests were environment-fragile, and the review could not catch it

`python -m unittest discover -s tests` → **99 passing**. With `PYTHONIOENCODING=utf-8` → **9
failures**: the CLI tests read subprocess output without pinning an encoding, so `€10.00` arrives as
`â‚¬10.00`.

Not a regression, and the builder's "99/99" was true where it ran. But builder and reviewer share
one machine and one console encoding, so a two-agent review is blind to exactly this class of
defect. Independent verification meant re-running the same command in the same environment.

## On the questions this was run to answer

**Is the spec good?** Yes, on the evidence. 12 requirements, 14 acceptance criteria in
given/when/then, two named algorithms, **15 explicit non-goals**, and the decisions that were
genuinely mine are recorded as mine — including "guaranteeing the mathematically fewest possible
transfers" as a *non-goal*, because I chose reproducibility over minimality. The implementation
matches it: I recomputed the balances and transfers by hand.

**Are we specifying forever?** No. Three rounds to approval, one round for an extension. The
pressure runs the other way — see F1: the risk is not over-specifying, it is that the document
stops mattering the moment building starts.

**Against outside practice.** The industry consensus lands where this product already is: the spec
is the unit of work handed to an agent, and the failure mode to design against is *drift* — plausible
code that solves the wrong problem. Two points of divergence worth weighing:

- **Acceptance criteria format.** The document uses given/when/then, which the sources recommend for
  behaviour that maps to tests, with EARS held in reserve for the cases where GWT feels forced. This
  is the right default; nothing here needs changing.
- **The stated golden rule is "the minimum specification rigor that removes ambiguity"**, and the
  named anti-pattern is specs that drift toward pseudo-code. This document does not — it names
  behaviour, not implementation, and its evidence section says so explicitly.

The gap outside practice does *not* cover, and which F1/F4/F5 all point at, is the **return path**:
every published workflow describes spec → code. None of them says how the code gets back to the
spec, or how an approved document learns it was built.

## What else this cycle should track

Missing today, in rough priority:

1. **Spec ⇄ task linkage as data.** `task.requirements` is free text (`"FR-11 — deterministic-
   settlement"`). Nothing can answer "which requirements have no task?" or "which approved
   requirement changed after its task was approved?" — even though `requirement_digests` are already
   recorded for exactly that and are read by nothing.
2. **Implementation state on the document.** A phase after `approved` — or a recorded link from
   requirement to the commit/test that satisfies it — so F5 cannot happen.
3. **Integration.** Whatever ends a task's life should say where the code went.
4. **Cost and time per requirement.** 27 runs happened; the per-run cost is visible in the transcript
   text and nowhere queryable.
5. **Which environment a verification ran in** (F10). "Tests passed" without that is weaker evidence
   than it looks.

## Reproducing

`testbed/scratch/e2e.py` (gitignored) drives all of it over the real HTTP surface — setup, agents,
document, turns, phase control, tasks, state. Nothing in it is simulated; where a step has no API,
that absence is a finding above rather than something the harness worked around.
