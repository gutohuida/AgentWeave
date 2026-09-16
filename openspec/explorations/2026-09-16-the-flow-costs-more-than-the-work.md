# The flow costs more than the work

**Written 2026-09-16 by an interactive session, at the operator's instruction, after measuring the
live `:8000` Hub's `turn_usage` table read-only (`mode=ro`).** Exploration only: no change
directory, no spec edit, nothing decided here.

The operator's framing: *"The way we have the flow today is spending a lot of tokens and the
conversations between agents feel inefficient... My biggest problem is not that it got stuck, that
was a bug and we can solve it, but that it spent a lot of my token budget and it did not finish the
work or not even close."*

This file answers that with numbers rather than argument, because the aggregate spend was already
known and the *mechanism* was not. **One of the results below contradicts the intuitive version of
the argument**, and that contradiction is the most useful thing in the file.

---

## 1. Method, so this is reproducible and its blind spots are visible

Read-only against the operator's real Hub database
(`~/.agentweave/hub/data/agentweave.db`, `file:...?mode=ro`), project `LoopEngine`
(`proj-03b9c6a6c37a`), the run window 2026-09-12 20:39 to 2026-09-16 19:00. Tables: `turn_usage`,
`runs`, `tasks`. Nothing was written, no process was restarted.

`turn_usage` records one row per Hub-owned run, carrying the runner's own reported token counts and
its `api_equivalent_usd_micros`. A "turn" here is one run — which internally is *many* provider API
calls, each re-sending the conversation. That is why per-turn input counts exceed any context
window.

**Blind spots this measurement has, stated up front:**

- **64 of 274 measured rows carry a NULL model and zero tokens** (23%). The runner reported no
  usage for them. They are skewed toward same-agent continuation turns, which means every
  continuation total below is *understated*. Averages are computed over measured rows only, so the
  averages are sound; the totals attributed to continuations are not.
- **3 runs have no measured usage at all** (`status='unavailable'`).
- **82 of 277 runs carry no `task_id`** and are excluded from every per-task trace below. They cost
  **$73.58 (26% of the budget)** — coordination that never attached to a unit of work.
- **LoopEngine was parked on the F352 staffing gate partway through.** The 23 never-started tasks
  are therefore **not** evidence that cost caused incompletion. Do not read them that way; that is
  a separate bug with its own finding.
- Costs are the provider's own figures as reported by the runner, not a re-priced model. They mix
  Opus and Sonnet, and §5 controls for that.

---

## 2. The headline: the work is 0.77% of the spend

274 measured turns, 2026-09-12 to 2026-09-16:

```
                 turns      input tok    cache-read    output tok    $ API-equiv
  dev              97      321,479,354   316,709,317    1,710,891      114.21
  Architect        96       49,427,707    46,644,347    1,174,616       81.36
  tester           62       81,110,949    79,062,911      640,358       76.05
  dev_2            19       28,825,499    28,247,199      215,648       10.13
  ------------------------------------------------------------------------------
  TOTAL           274      480,843,509   470,663,774    3,741,513      281.75
```

**Output tokens are 3,741,513 of 484,585,022 total — 0.77%.** For every token of reasoning or code
produced, **128 tokens of context were read**.

Task outcomes over the same window: 48 tasks, **10 approved**, 12 completed-but-unapproved, 23
pending, 1 rejected, 1 under review. **$28 per approved task.**

## 3. Caching is not the problem, and this refutes the obvious hypothesis

The intuitive story — *an agent's context goes cold between turns, so it re-reads everything and the
cache is wasted* — is measurably **not** what happened.

```
  input_tokens        480,843,509
  cache_read_tokens   470,663,774    97.9%  <-- cache hits
  cache_write_tokens   10,171,881     2.1%  <-- cold-start re-priming
  uncached                 ~7,854     0.0%
```

**The cache hit rate was 97.9%.** Cold-start re-priming cost 2.1% of all input. A fresh agent
starting cold pays roughly 37k tokens to re-prime — noise against a 481M-token bill.

**Consequence for design: this cannot be fixed with better caching, longer TTLs, or session reuse.**
Caching is already working almost perfectly. The bill is the *volume* of cached reads, which is
(number of API calls) x (context size), and only the topology moves that product.

## 4. Where the topology shows up

**Coordination and review, which write no product code, took 158 of 274 turns (58%) and $157 of
$282 (56%).** dev and dev_2 — the agents that actually changed the repository — took 44%.

**More than half the spend is cascade.** Runs carry a `turn_depth`; depth 0 is operator- or
scheduler-initiated, anything deeper was triggered by another turn:

```
  depth=0   101 runs   $136.77        depth=4    35 runs   $ 40.45
  depth=1    25 runs   $ 19.04        depth=5    29 runs   $ 15.06
  depth=2    32 runs   $ 43.85        depth=6    22 runs   $ 11.44
  depth=3    33 runs   $ 15.14
```

176 of 277 runs are cascade turns, worth **$145 (52%)**, reaching six levels deep.

**Failed runs are not the waste.** 72 runs failed, costing $3.66 total. That hypothesis is dead;
failures die cheap and early.

**The Architect is a relay, and every relay hop is a full LLM turn.** Counting agent-to-agent
transitions *within* a single task, 95 of 167 (57%) are handoffs, and the Architect sits in the
middle of almost all of them:

```
  tester    -> Architect   19        Architect -> dev_2        6
  dev       -> Architect   18        dev_2     -> Architect    5
  Architect -> tester      18        dev_2     -> dev          2
  Architect -> dev         10        dev       -> dev_2        2
  dev       -> tester       9
  tester    -> dev          6
```

`dev -> tester` happens directly 9 times and *through the Architect* 18+18 times. A one-hop handoff
is being billed as two LLM turns.

**The traces make it visible.** Per-task agent sequences, D=dev, d=dev_2, T=tester, A=Architect:

```
  $32.21  22t  completed   DDTADAADDDATADDDTTTTTT   Rule checks, blocking or warning
  $21.29  14t  completed   DDDTADATDTATTT           Failure backoff and cutoff
  $16.70  12t  completed   TATATATATATA             Unscheduled loops and hard rules
  $15.90   7t  approved    DDTATAT                  Missed windows
  $ 8.24   8t  approved    DATADATA                 Iteration records and machine-only files
  $ 7.87  31t  completed   DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD   Keep the machine awake
```

`TATATATATATA` is twelve turns and $16.70 on a task the implementer never touched.

---

## 5. The controlled result, and the one that contradicts the simple story

The naive cut says a turn following a handoff costs $1.24 against $0.40 for a turn where the same
agent continues. That comparison is confounded by model mix, so it was controlled two ways.

**Control 1 — hold the model constant.** Within Sonnet, the result *reverses*:

```
  model             kind        n      avg input   avg output   $/turn
  claude-sonnet-5   handoff    23      4,232,201       19,261     1.92
  claude-sonnet-5   same       13      7,098,753       37,488     2.10   <-- BIGGER
  claude-opus-5     handoff    66      1,115,719        9,807     1.12
  claude-opus-5     same        5        135,678        1,302     0.16   (n too small)
```

**A single owner that simply keeps going does not stay cheap.** Its context grows until each turn
averages 7.1M input tokens. The 31-turn `DDDD...` task is this failure mode, and one dev turn in the
corpus reached **31,074,806 input tokens** in a single run. Continuous ownership without a reset
degrades into a runaway.

**Control 2 — hold the agent, role and model constant.** Restricting to dev turns only, and asking
only whether the task changed hands since dev last had it:

```
  dev resuming its OWN work        n=52    avg input 1,742,245    $0.52 / turn
  dev resuming AFTER a handoff     n=18    avg input 4,663,161    $2.19 / turn
```

**Same agent, same role, same model. A dev turn that picks a task back up after someone else touched
it reads 2.7x more and costs 4.2x more.** That is the re-derivation cost, isolated.

### What the two controls mean together

They are not in tension; they name two different failure modes, and the current flow has both.

```
  HANDOFF       ownership changes  +  context resets   ->  pays re-derivation   (4.2x)
  GRINDING      ownership stays    +  context grows    ->  pays context bloat   (7.1M/turn)

  ITERATION     ownership stays    +  context resets   ->  pays neither
```

**The iteration boundary is a context reset that is not a change of ownership.** That is the whole
idea, stated precisely, and it is what distinguishes it both from today's design and from "just use
one big agent" — which the Sonnet row above shows is its own trap. The operator's instinct that the
*iteration* is the unit, not the agent, is the load-bearing half.

---

## 6. What the agents actually did

Cost tells you the flow is expensive; it does not tell you what the roles *were*. Profiling every
`tool_use` row (4,827 of them) by agent answers that, and it produced the two most surprising
results in this file.

```
  dev (2467 calls)          tester (1190 calls)       Architect (764 calls)
    708  Bash                217  PowerShell            154  Grep
    447  Read                212  Read                   95  Bash
    386  Grep                159  Grep                   80  Read
    373  Edit                134  Bash                   78  send_message
     79  Write               102  Edit                   73  PowerShell
     71  record_evidence      61  Write                  47  ToolSearch
     64  get_task             60  decide_evidence        45  update_task
     56  update_task          58  send_message           33  get_task
     39  send_message         51  list_evidence          26  Write
     36  submit_checkpoint    49  get_task               20  Edit
                                                         18  create_task
```

**Correction to this file's own first pass.** An initial classification of Edit/Write targets
reported that dev touched product code only 3 times. That was wrong: it treated everything under
`.agentweave/` as scratch, when `.agentweave/tasks/<task-id>/src` **is** the product source — agents
work in a per-task worktree. The directory shapes actually written to, across all agents:

```
  192  LoopEngine/.agentweave/tasks/task-<ID>/src        <-- product source
  174  LoopEngine/.agentweave/tasks/task-<ID>/test
   84  ~/.claude/projects/...-LoopEngine/memory          <-- see below
   46  LoopEngine/.agentweave/tasks/task-<ID>
   31  LoopEngine/.agentweave/worktrees/dev/src
```

### 6a. Writes are not single-threaded — the tester is a second developer

**The tester edited `engine.js`, LoopEngine's core product source, 31 times, plus `server.js` 3
times** — 34 writes into a task worktree's `src/`, on top of 12 into `test/`.

This is the precise condition Cognition names as what breaks multi-agent systems: *writes must stay
single-threaded and additional agents must contribute intelligence rather than actions.* AgentWeave
has **four writers**. The role labelled "tester" is not a reviewer that reports defects — it is a
second implementer, invoked in a cold context, doing the first implementer's job after paying the
4.2x re-derivation toll measured in §5.

This strengthens the operator's proposal rather than complicating it. "Get rid of the tester" is not
removing a safeguard; much of what that role does is *implementation that is happening in the most
expensive possible place*. What must survive is narrower and cheaper than the role: the tester also
made **60 `decide_evidence` and 51 `list_evidence` calls**, which is genuine adjudication and is
what `reviewer_is_not_the_author` and the evidence gate depend on. That part is read-only, belongs
at the end of a task, and costs almost nothing.

So the recommendation sharpens from *collapse the tester* to **split it**: return the writing to the
owner's loop, keep the adjudication as a read-only end-of-task gate.

### 6b. The agents already built the checkpoint the architecture never gave them

**The tester wrote 60 files into Claude Code's own memory directory** — outside the Hub, invisible to
it — across 16 distinct files:

```
   22x MEMORY.md                        3x  fr70-missing-state-pending.md
   10x sandbox-shell-quirks.md          3x  review-watchlist-missed-windows.md
    3x d8d4b-rule-checks-review.md      3x  partial-evidence-gated-tasks.md
    3x c6548-failure-backoff-review.md  2x  fr31-review-gate.md
    3x approve-needs-reassign.md        1x  dont-complete-tasks-you-review.md
```

Those names are per-task review state (`d8d4b-...-review.md` is task `task-d8d4b03d722b`), pending
findings, and — in `dont-complete-tasks-you-review.md` — **a rule about its own role that it kept
forgetting between cold starts.**

Nobody designed this. The agent invented a private checkpoint store because the architecture kept
destroying its context and gave it no durable place to stand. It is the strongest available evidence
for the checkpoint half of the proposed shape: the need is real enough that an agent built a worse
version of it by hand, out of band, where the Hub cannot read it, review it, or show it to the
operator — while the Hub's own checkpoint tools sat available and nearly unused:

```
  submit_checkpoint_notes    dev 36    Architect 2    tester 1    dev_2 0   = 39 writes
  list_checkpoints           dev  1    Architect 1    tester 2    dev_2 0   =  4
  read_checkpoint                      Architect 1                          =  1 READ
```

**Checkpoints were written 39 times and read once, in the entire corpus.** The mechanism the
proposed shape depends on already exists, is already being written to, and is being read by nobody —
because nothing in the flow makes the next turn start from it. That is a strong signal that the
gap is not missing machinery but a missing *contract*: no turn is required to begin from the last
checkpoint, so every turn begins from the repository instead, and pays §5's re-derivation toll.

### 6c. The tester's findings were real, and they were experiments rather than opinions

All 59 of the tester's messages were read (192 messages in the project, 245,000 characters in total —
about 61k tokens, which is 0.013% of the bill; **the messages are not the cost, they are the fuse
that detonates a re-deriving turn**). Five representative findings, quoted in substance:

- **A DNS-rebinding hole reached `main` with its evidence already rejected.** *"A DNS-rebound page
  gets same-origin GETs with no Origin header, `originAllowed()` allows a missing Origin, and Host
  is never checked. So `GET /` hands the page the token, and `GET /api/projects` returns data. I
  reproduced this at `a212df9`, and main's `src/`, `bin/` and `public/` are byte-identical to that
  commit."* It also corrected the task's own review note, which claimed the Origin check *"correctly
  survives DNS rebinding"*, and flagged the process bug behind it: an approval merged while a
  requirement's evidence was rejected.
- **A route guard that trusted a self-declared label, found by mutation.** *"It checks `route.kind`,
  which the author of the route writes, so a data route labelled 'static' gets through... `{ GET
  '/api/leaky', gated:false, kind:'static', handler:handleProjects }`: 11/11 pass, and the route
  serves project data with no token."* With a concrete fix: assert the handler by identity, not the
  label.
- **A state-persistence gap on `main`, found with a virtual-clock probe.** `closedWindow` was held in
  memory while its siblings `barredWindow` and `lateRunConsidered` were persisted, so a restart
  inside the same window started a second run. Demonstrated by stopping Engine A and starting
  Engine B: *"starts go from 1 to 2."*
- **A test asserting the opposite of its own criterion**, plus an FR-33 regression measured at
  *"0 starts on your branch and 15 on main."*
- **A rework that was never committed.** *"Your fix never got committed... your turn was cut off, so
  the Hub's end-of-turn auto-commit probably never ran."* It then refused three evidence rows that
  pointed at a commit not containing the work, *"because accepting them could let an approval merge
  the known-bad commit."*

**Verdict on open question 1: the tester earned its $76 in findings.** These are reproducible,
commit-pinned, mutation-driven results, several of them catching defects already on `main` and one
catching a governance failure in the approval path itself. **What it did not earn is its place in
the topology** — every one of those findings cost a cold-context re-derivation first.

### 6d. The tester was never the read-only critic the literature warns about

The concern that a judge-only agent burns tokens to produce worse results is about agents that
*read code and opine*. That is not what this one did. Classifying every measured tester turn by
whether it executed or wrote anything:

```
                                    n     avg input     $/turn    total
  RAN things (exec or write)       42     1,898,949      1.77     $74.42
  READ ONLY (no exec, no write)     5       259,391      0.31     $ 1.57
```

**42 of 47 measured tester turns ran something.** Across all agents the split is 154 grounded
($257.02) against 43 read-only ($24.22).

**This neither confirms nor refutes the concern, and should not be cited as if it did.** There is no
population of *thorough read-only reviews* in this corpus to compare against — the 5 read-only turns
are short status checks, not deep code readings. What the corpus does establish is that the tester's
value came from **execution**, which is exactly the condition under which the self-correction
literature says critique works at all (Huang et al.).

**The design consequence is direct: do not build a gate that reads a diff and passes judgement.
Build a gate that runs things.** A judgement needs the whole codebase in context; a probe run needs
the probe.

### 6e. The keystone: the acceptance criteria are already the probe definitions

This is where the part of the product that works meets the part that costs.

**Of 50 tasks, 18 carry acceptance criteria and 0 carry requirements.** The criteria that do exist
are already very close to executable:

> *"A test sends `GET /` and `GET /api/projects` with `Host: evil.example:<port>`, no Origin, and a
> valid token, and asserts both are refused."*

> *"With the health route temporarily made to refuse, the single-instance tests fail within their
> timeout rather than hanging, and no loopengine process is left running."*

The second is a **mutation-test specification**: it names the mutation and the expected outcome. It
is the same technique the tester independently reinvented in §6c's route-guard finding, at a cost of
roughly 1.9M input tokens of re-derivation per turn.

**The tester spent its context re-deriving the codebase in order to invent probes that the
acceptance criteria had already described.** A gate handed executable criteria does not need to
understand the code — which is why it can be cheap, and why it can run at the end of a task rather
than in the middle of every attempt.

That also answers *when* verification happens, and it is not "the tester evaluates the code":

```
  ITERATION N  (owner: implement, run tests, fix -- one context)
        |
        |  emits: diff + test output + checkpoint
        v
  GATE  run the task's acceptance criteria as executable checks
        + the adversarial mutations they imply
        needs: the criteria, the diff, a shell.   NOT the codebase.
        |
        +-- all pass --> adjudicate evidence (read-only) --> MERGE
        +-- any fail --> verdict into the checkpoint --> ITERATION N+1
                         (same owner, fresh context, reads the verdict)
```

Which makes the 18-of-50 number the most actionable defect in this file: **the cheap gate is
unavailable on 64% of tasks because nothing required the criteria to exist.**

### 6f. One corpus, and no generalization check is possible

The live Hub's other project (`proj-06d090fb`, "huida") has **0 runs and 0 tasks**. The trial Hub's
database holds 26 runs worth $0.63, all from drive-test agents (`mcpagent`, `httpagent`), not a
development corpus. **Every number in this file therefore comes from LoopEngine alone** — one
project, one four-day window, one roster of four agents. That limitation cannot be measured away
from here; it can only be reduced by running a second project.

## 7. What the outside evidence says

- **[Why Do Multi-Agent LLM Systems Fail? (Cemri et al., Berkeley, arXiv:2503.13657)](https://arxiv.org/abs/2503.13657)**
  — 1600+ annotated traces across 7 frameworks; 14 failure modes in 3 clusters, two of which are
  *inter-agent misalignment* and *task verification*. Finding: multi-agent systems show minimal
  gains over single agents on popular benchmarks.
- **[Cognition, "Don't Build Multi-Agents"](https://cognition.com/blog/dont-build-multi-agents)** —
  decision-making disperses and context fails to transfer; recommends a single-threaded linear agent
  with continuous context.
- **[Cognition, "Multi-Agents: What's Actually Working"](https://cognition.com/blog/multi-agents-working)**
  (their revised position, and the most directly useful) — multi-agent works **when writes stay
  single-threaded and additional agents contribute intelligence rather than actions**. One main loop
  carries state; subagents are stateless workers with narrow scope; read-only subagents are the
  safest pattern.
- **[LLMs Cannot Self-Correct Reasoning Yet (Huang et al., arXiv:2310.01798)](https://arxiv.org/abs/2310.01798)**
  — self-correction *degrades* performance without a ground-truth signal, but works when the
  feedback is **code execution results**. This is the load-bearing citation: an implementer running
  its own tests stands on solid ground; a critic agent that only opines does not.
- **[Anthropic, "How we built our multi-agent research system"](https://www.anthropic.com/engineering/built-multi-agent-research-system)**
  — orchestrator-worker beat single-agent by ~90% **at 15x the tokens**, with token usage explaining
  ~80% of performance variance; and their own caveat that this suits *parallel research strands* and
  is **less effective for tightly interdependent work such as coding**.
- **[Agentless (OpenAutoCoder)](https://github.com/OpenAutoCoder/Agentless)** — a fixed
  localize/repair/validate pipeline with no agent loop beat SWE-agent (50.8% vs 33.6%) at lower cost
  per issue. Structure beat autonomy.

## 8. How Claude Code's subagents differ, since the topologies look alike

```
  AGENTWEAVE TODAY                      CLAUDE CODE SUBAGENTS
  ================                      =====================

      Architect                               main loop
      /   |   \                              /    |    \
   dev <-> tester <-> dev_2              child  child  child
      \_______________/                     |      |      |
                                         report report report

  * peer graph, several writers          * tree, exactly ONE writer
  * durable identities, sessions grow    * stateless, one-shot workers
  * A messages B, B replies to A         * no child-to-child, ever
  * handoff = transfer of OWNERSHIP      * no conversation back, only a
                                           final report
                                         * delegation = CONTEXT COMPRESSION
```

The economics are the point. A Claude Code subagent may burn 200k tokens reading files and return a
2k report; **the parent pays for that reading exactly once and never again**, because the child's
context is discarded. It is not collaboration, it is buying compression.

AgentWeave's messaging inverts this. When dev hands to tester, tester pays to re-read what dev
already read; when it comes back, dev pays a third time — measured at 2.7x the reading and 4.2x the
cost in §5. Context is not compressed, it is **duplicated per hop**.

Note also *what* Claude Code delegates: overwhelmingly read-only search and exploration. Which is
where Cognition independently landed.

## 9. The shape this suggests

Nothing here is proposed; this is the shape the evidence points at, for a later change to argue
properly.

```
   TASK  (generated from the spec -- this layer is NOT in scope and stays as-is)
     |
     v
  +--------------------------------------------------------------+
  |  ITERATION N            one owner - one context - bounded     |
  |                                                               |
  |    read brief --> implement --> RUN TESTS --> fix --+         |
  |         ^                                           |         |
  |         +-------------------------------------------+         |
  |              the loop stays INSIDE one context                |
  |                                                               |
  |    ends on:  tests green  |  budget exhausted  |  blocked     |
  |    emits:    CHECKPOINT (diff, test output, what remains,     |
  |              what was learned that is not in the code)        |
  +--------------------------------------------------------------+
       | green                              | not green
       v                                    v
   GATE: read-only advisor              ITERATION N+1
   writes a VERDICT into the            fresh context, same owner role,
   checkpoint; never takes              reads the checkpoint, not a
   ownership of the task                transcript
       |
       v
     MERGE
```

Four properties, each traceable to a measurement above:

1. **The baton never moves backwards** — only forward, or around the same loop. (§5, control 2:
   4.2x on the return leg.)
2. **The handoff medium is a checkpoint artifact, not a conversation.** AgentWeave already has this
   machinery — `hub/hub/checkpoints.py`, `checkpoint_generation.py`, `checkpoint_handover.py`,
   `submit_checkpoint_notes` — and the flow does not lean on it.
3. **Every iteration is bounded.** A 31M-token turn must be structurally impossible; budget
   exhaustion is a normal exit that still emits a checkpoint. (§5, control 1.)
4. **Verification changes frequency, not existence.** Today it fires per *attempt*, N times, each
   costing a full re-derivation. Move it to fire per *task*, once, at the gate, as an advisor
   returning a verdict rather than a peer taking the baton.

**And the separate, cheaper win:** the Architect spent 96 LLM turns and $81 routing work. Dispatch,
staffing and sequencing are deterministic; the Hub already holds the task graph and already has
`create_flow`, `create_loop` and the scheduler. **Orchestration should be code, not a model.** This
is ~29% of the budget and is independent of whether the iteration loop is adopted.

## 10. What would falsify this, and the honest counter-arguments

- **Author bias is real and this weakens a real defence.** An implementer that writes both the code
  and the tests can write a test that passes. This repo has already built machinery specifically for
  that (`reviewer_is_not_the_author`, the evidence and requirement gates). The answer is to keep an
  independent check and change its *frequency*, not to delete it. Any proposal that quietly drops it
  should be rejected.
- **The tester's critiques were load-bearing — answered, in §6c.** All 59 messages were read. The
  findings are real, reproducible and commit-pinned, and several caught defects already on `main`
  including a DNS-rebinding hole and an approval that merged over rejected evidence. **Any proposal
  that removes this capability rather than relocating it should be rejected.** What §6e shows is
  that the capability does not require the topology: the findings came from probes and mutations,
  and the acceptance criteria already describe those probes.
- **One corpus.** Every number here is LoopEngine, four days, four agents. The only other projects
  available hold 0 and 26 runs (§6f). Nothing here has been shown to generalize, and the honest way
  to fix that is a second project, not more analysis of this one.
- **One project, one window, one runner mix.** 274 turns from LoopEngine only. The AgentWeave
  project (`proj-06d090fb`) was not analysed, and no other harness was.
- **The 23 unstarted tasks are the F352 staffing bug, not the cost.** Any argument that leans on
  them to claim "the flow could not finish the work" is unsound.
- **The `TATATATATATA` traces may encode a real bug** (a dispatch loop) rather than a design flaw.
  Not investigated. If so, its fix is small and separate.

## 11. Open questions for the operator

1. ~~**Did the tester earn its $76?**~~ **Answered** (§6a, §6c, §6d). In findings, yes — they are
   real, reproducible and caught defects on `main`. In topology, no — it paid a cold-context
   re-derivation for each one, and wrote product source 34 times while doing it. The capability
   relocates; it does not disappear.
2. **Is the Architect making judgements, or routing?** 96 turns. If routing, it is code. Sampling
   its outputs would settle it.
3. **Scope:** does this become one change (collapse verification), several (full topology rework),
   or first a circuit breaker alone?
4. **Does the spec-to-task layer stay untouched?** This file assumes yes — it is the part the
   operator said works, and it sits above the boundary being discussed.

## 12. The decision, in one line

Approving this means a spec loop on a named day for **one** of these, in the order the measurements
now recommend:

1. **Acceptance criteria become mandatory and executable** (§6e). Today 18 of 50 tasks carry them,
   and nothing runs them. This is the cheapest change, it is additive, it breaks nothing, and every
   other item below depends on it — a gate with no criteria to run is just another code reader.
2. **The per-iteration budget plus a mandatory checkpoint on exhaustion** (§5, control 1). Makes the
   31M-token turn structurally impossible and gives the next iteration something to start from.
   Independent of everything else.
3. **Split the tester** (§6a, §6c): writing returns to the owner's loop; adjudication becomes a
   read-only end-of-task gate that runs the criteria from item 1.
4. **Move orchestration out of the Architect and into the scheduler** (§4). Largest single saving
   (~29%), largest blast radius, and it should go last because items 1-3 change what there is to
   orchestrate.
