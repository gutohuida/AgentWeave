# The transition model agents are told

**2026-09-14, day window, I-1 brief 6 of 11.** This is an improvement brief, not a proposal: there
is no change directory and no tasks. Source: `spec-queue/observations/2026-09-14-LoopEngine.md`,
`## Improvements` item 6, `### Architect` item 4, `#### dev` item 5 and `#### tester` item 2.

## What we saw

Agents kept trying edges the lifecycle does not have, and learned each one from a refusal.
- **`dev`** tried `in_progress → under_review` three times, which was its idea of handing work in,
  plus `pending → completed` once and `pending → under_review` once. Each cost a retry.
- **The Architect** got seven *"Cannot move a task from 'completed' to …"* refusals: five to
  `approved`, one to `rejected` and one to `revision_needed`. Each ended *"From 'completed' the
  available transitions are: under_review."*
- **`tester`** went to approve `task-bb06b8c3c708` at 20:45 and found it still `in_progress`,
  because `dev`'s turn had ended without completing it. It moved the task to `completed` itself,
  and so became its author. The approval was then refused: *"agent 'tester' recorded the task's move
  to 'completed', and approving, rejecting or requesting revision of work requires a different
  actor … Starting a new run does not make you a different actor."*
  (`hub/hub/task_transition_service.py:367-372`). It saved a private note never to complete a task
  it reviews.

**The lifecycle is not told to them anywhere, except as refusals.**
- The graph lives in `hub/hub/task_transitions.py:101-153`, with the run/operator split per edge.
  Its refusal (`:381-399`) names the edges available from where you are, which is why each misstep
  cost only one retry.
- The `update_task` tool lists the eight statuses an agent may name, and says nothing about which
  follow which or who may take them (`hub/hub/mcp_server.py:306-319`).
- Review turns get the one edge they need, *"The task is `under_review`: set it to `approved` … or
  `revision_needed`"* (`hub/hub/api/v1/agents.py:1641-1646`).
- No briefing for other turns, and no starter charter, states:
  - that an author ends at `completed`, and the flow stages review from there;
  - that whoever records `completed` cannot also give the verdict;
  - that `completed` cannot be sent back except through review.

## What would change

Every turn that can move a task would carry a short, generated statement of the edges *this* run
may take from the task's current status. It would say who may take each one, and add the two rules
agents actually tripped on:
- the author's last move is `completed`;
- the actor who records `completed` cannot approve, reject, or return the work.

The text would be rendered from the transition table, not written by hand, so it cannot drift from
what the Hub enforces. The same statement would go into the `update_task` description, so the MCP
and HTTP channels agree.

## Why it matters

Each wrong edge is cheap alone and adds up across a team. On LoopEngine that was about a dozen
refused calls, one verdict made impossible by a well-meant `completed`, and a private ledger of
notes teaching agents what the product never told them (improvement 8). A reviewer who knows that
completing a task disqualifies them from judging it would have messaged `dev` instead. That is one
approval that would have landed without the Architect.

## Rough cost — a code-read estimate

- **Files:**
  - `hub/hub/task_transitions.py`: a renderer over the table that already exists, one function;
  - the canonical-context builder in `hub/hub/api/v1/agents.py` and the scheduler's flow
    briefings. Both channels must agree, which is the F45/F140 lesson, so a test should assert they
    render the same statement;
  - the `update_task` description in `hub/hub/mcp_server.py`, **which F354 keeps out today**. The
    briefing half stands alone without it.
- **Capabilities:** `openspec/specs/task-lifecycle-governance` (*"Task status moves only along
  declared transitions"*, *"An agent cannot approve the work it produced"*) and
  `agent-context-onboarding` for what a turn is told.
- **Migration, API shape, UI:** none.
- **Prompt size:** a few lines per turn, which is small against the 41–45 k every session already
  starts at.

## Risks and open questions

- **Telling agents the edges invites them to walk the graph for its own sake.** It must be framed as
  "how your work reaches review", not as a menu.
- **The `tester` case needs more than wording.** A reviewer who finds the author's work still
  `in_progress` has no good move today: completing it disqualifies them, and it is not theirs to
  complete. Should the briefing say "send it back to its author", or should an ended turn with
  recorded evidence and no `completed` be surfaced? That second question belongs to
  `turn-outcome-visibility` and is out of this brief.
- **Overlap with F357**, the review briefing that omits the evidence gate. F357 fixes the review
  turn's sentence and this brief covers every other turn. R1 should read f357's diff so the two
  statements do not contradict each other.

## The decision, in one line

Approve a spec loop, after f357 is built, for *a turn is told the transitions it may take, rendered
from the table the Hub enforces*. The briefing half can be built without `mcp_server.py`.
