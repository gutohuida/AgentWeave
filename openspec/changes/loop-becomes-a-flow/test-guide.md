# User test guide — a loop becomes a flow

Task 12.1. What an operator does, what they should see, and what it looks like when it goes wrong.

The suite proves the routing: a firing staffs every task it can, a finished task is offered to
somebody other than its author, a reviewer is spawned into a checkout of the work, and a chain of
A → review → B runs with no operator action. What it cannot prove is any of the six judgements in
group 11 — whether the result is *legible*. Three agents working is either a picture of a machine
doing what you asked or a wall of activity you cannot read, and the same rows produce both.

**Lead with the first check below.** A flow that behaves differently from a loop when it has one
agent is the failure that would undermine confidence in everything else here (task 12.3), and it is
the cheapest thing to falsify.

## Before you start

- The trial Hub on port **8010**, started **from `hub/`** so the source package is what runs:

  ```bash
  cd hub
  DATABASE_URL="sqlite+aiosqlite:///$HOME/.agentweave/hub/profiles/beta/agentweave.db" \
    py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1
  ```

  **Not `agentweave --port 8010`.** The console script is the *installed* `agentweave-hub`, whose
  bundled migrations lag this branch.

- **Three agents on the roster, each with a runner bound.** This is the one setup cost, and it is
  the difference between exercising this change and re-testing loops. The walkthrough uses
  `builder`, `critic` and `auditor`. An agent with no runner is deliberately not eligible — the
  flow will not select one, because selecting it would turn a staffing question into a launch
  failure a step later.

- **A git repository as the project workspace.** A review turn checks out the commit under review,
  so a project that is not a repo cannot have its work reviewed; the flow says so rather than
  guessing.

- Nothing else to configure. There is no width setting, no concurrency cap, and nothing to put back
  afterwards. That is deliberate — see "Why there is no dial" at the end.

## 1. A flow with one agent is a loop (start here)

Create an ordinary loop with `builder` as its agent and two independent tasks on its queue, and
temporarily archive `critic` and `auditor` so that `builder` is the only eligible agent.

Watch two or three firings. **Everything should read exactly as it did before this change:** one
task claimed per firing, one run per firing in the job's history, one current item on the card, one
agent's name, and consecutive firings collapsed into a single row in the conversation list.

If any of that reads differently, stop — the default agent has stopped being a default and become
something else, and the rest of this guide is not worth running yet.

## 2. A firing staffs everything it can

Un-archive `critic` and `auditor` and give the flow three independent tasks — no dependencies
between them.

On the next tick you should see **three turns start at once**: three rows in the job's history for
one firing, three conversations, and the loop's card listing all three tasks with the agent working
each one beside it.

Two things worth checking rather than assuming:

- **The card names who has what.** "Three tasks in progress" is not the same information as three
  lines each naming a task and an agent. The first tells you a lot is happening; the second tells
  you what is happening.
- **Three rows for one tick is correct, not a bug.** Each agent's turn succeeds or fails on its
  own, so each has its own row. A single row could not say that two agents finished and one failed.

Now add a fourth task while only three agents exist. It should **stay untouched** — still `pending`,
still unassigned, no row, no notice. Running out of agents is the bound working, not a fault, and
the next firing considers it again.

## 3. Dependencies still order the work

Give the flow two tasks where B depends on A, with all three agents free.

Only A should start. B must not be staffed alongside it however many agents are idle — the width
comes from the graph, and the graph says B waits. When A is approved, B starts on the next tick.

If B starts alongside A, the parallelism has stopped respecting the ordering you decomposed the work
into, which is worse than having no parallelism.

## 4. The handover, which is the point of the change

Let `builder` finish a task — take it to `completed` with evidence naming a commit.

On the next tick the flow should staff **somebody else** to review it. Nobody sent a message,
nobody was asked to hand anything over, and `builder` did nothing except finish.

Check three things, in this order:

1. **The reviewer is not the author.** `builder` must not be offered its own finished work, on any
   firing, ever. If it is, author/reviewer separation has a hole and the review means nothing.
2. **The reviewer is looking at the work.** Open the reviewer's workspace during its turn. The
   author's changes must be *in it* — the reviewer works in a checkout of the commit under review,
   not in its own working copy where unmerged work does not exist. This is the check that matters
   most and the one most likely to be skipped: a reviewer who cannot see the work will ask the
   author what changed, and a review conducted by asking the author is not a review.
3. **The reviewer arrives briefed.** Read what it was given. The prior agent's checkpoint should
   read as something written *for somebody else* — naming the file, the task and the decision in
   full. If it reads as notes-to-self ("fixed it, see the thing above"), the instruction agents get
   when writing checkpoints has not taken, and every handover in the flow inherits the shorthand.

**Review comes before new work.** A flow with finished work waiting and untouched work pending will
review first. That is intended: work waiting on a second pair of eyes is closer to done than work
not yet begun, and letting it wait is how a queue accumulates a tail of unreviewed work.

## 5. The three staffing outcomes, and telling them apart

This is task 12.2, and it is the part where a working flow and a stuck one look most alike.

| What you see | What it means | What to do |
|---|---|---|
| A turn running, agent named | The step is staffed and working | Nothing |
| Nothing new this tick, no notice | Every agent is busy, or none is free for this step | Nothing — the next tick picks it up |
| **A notice saying the step could not be staffed** | Nobody *can* take it | Add an agent, free one, or fix a reviewer's name in the document |

Only the third asks anything of you, and it is the only one that raises a notice. That asymmetry is
deliberate: a flow with more ready work than agents is in the second state on almost every tick, and
a notice for that would bury the one that needs you.

Produce the third state deliberately: archive every agent except the one that finished a task. The
notice should read as **the flow needing somebody**, not as the flow having failed. If it reads like
breakage you will restart something that needed no restarting.

Produce the second state too: give the flow more ready tasks than you have agents. Nothing should be
recorded at all — no rows, no notices, no growing history. A tick that does nothing should cost
nothing.

## 6. What it cost

Run a flow three agents wide for a while, then look at the project's usage.

You should be able to answer "what did that cost" without reconstructing it from the runs. Three
agents spend three times as fast as one, and the flow will not stop until its stop condition fires —
so this is the check that decides whether you can leave one running unattended.

## Why there is no dial

There is no maximum-concurrency setting and no width configuration, and that is a decision rather
than an omission. Width is not a policy you set afterwards; it is the shape of the decomposition you
already approved. You start parallelism at spec time by declaring independent work, and you stop it
by declaring an order. A cap on top of that would let you contradict your own spec from a settings
page — and at a value of one it would make review structurally unreachable.

What *does* bound a flow is what bounds a loop: its stop condition, the project's token budget, and
the agents you have.

## When something is wrong

| Symptom | Likely cause |
|---|---|
| One task claimed per firing, several agents idle | The other agents have no runner bound, are archived, or already hold active work |
| A finished task never reviewed | Nobody else is eligible, or the task has no recorded completer — one written straight into `completed`, rather than reaching it through the app, is offered to nobody |
| A reviewer asking the author what changed | It is in the wrong workspace; check its working directory against the commit under review |
| The flow reviews before starting new work | Intended — see the note in section 4 |
| A card showing one task while three agents are working | The board and the firing have parted company; that agreement is a shipped test and a failure here is a real defect |
