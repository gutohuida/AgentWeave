# Exploration — a harness, or tools for harnesses?

**Date:** 2026-09-07
**Status:** Pure exploration. No proposal, no decision, nothing here is committed work.
**Origin:** The operator, 2026-09-07 — *"Claude just released intermessages on its harness, there
are a ton of new harnesses coming out almost every day. We have the deep seek one, pydantic new one.
What I want to know honestly is: Should we keep p[u]rsuing a harness? Or take what we did here …
and build tools to su[pp]ort those harnesses. Like a visual tool that we can see the loops
executing, where we're at in the loops etc. … The handoff/resume but with a database so we can
track that… tracking data from harnesses in order to improve."*

**Reads against:** `2026-09-06-what-could-leave-agentweave-and-become-its-own-tool.md`,
`2026-09-07-what-is-actually-separable.md`, `2026-09-07-an-overseer-for-any-harness.md`, and the two
sibling prototypes those loops produced (`../continuity-kit`, `../witness`).

**Method.** Seven live web searches and two page fetches against the 2026 market on 2026-09-07,
plus a re-read of the three explorations above and the state of both prototypes. **What was not
done:** nothing named below was installed, run, or verified beyond its own documentation and one
comparison article. The competitor claims in Part 1 are marketing read at face value. That is a
weaker instrument than this repository normally accepts, and Part 5 says what would strengthen it.

---

## Part 1 — the market, measured on 2026-09-07

### The harness field is nine deep and converging

`winder.ai/ai-agent-harness-comparison` compares nine: Claude Code, Codex, OpenCode, Qwen Code,
DeepSeek Harness, Goose, Zed Agent, OpenHands, Pydantic AI Harness. Its own summary judgement is the
one that matters here: **"the harnesses look more like each other than their underlying models do."**
It describes fragmentation with emerging standardisation, driven by three open standards — MCP
(tools), `AGENTS.md` (instructions), and the Agent Client Protocol.

| Harness | The relevant fact |
|---|---|
| **DeepSeek Harness** (`dsh`) | Open-sourced 2026-08-13, MIT, ~453K lines. Everything is a plugin — models, tools, skills, sessions, sandboxes, storage, **loops, scheduling, and the UI**. Drives Claude Code and Codex *as sub-agents*. Ships a local web app, a headless command, and a Python SDK. **95,386 GitHub stars in two days.** |
| **Pydantic AI Harness** | Shipped with the breaking v2.0.0 on 2026-06-23. Every extension point collapses into one primitive, `capability`; 50+ documented (checked 2026-08-19). Includes a complete terminal coding agent. Assumes the agent lives inside a Python service you already have. |
| **Claude Code** | The "intermessages" the operator refers to: `thinking.display` accepts a third value, `"updates"` (beta) — reasoning returns an empty thinking field and the short progress updates written between tool calls come back as text, at most one thinking block before a tool call. |

**Agent Client Protocol** is the standard to watch: created by Zed, released 2025-08, now **v1
stable**, adopted by JetBrains, Google, GitHub and 25+ agents, public registry co-launched with
JetBrains 2026-01, SDKs in TypeScript, Python, Rust, Java and Kotlin. The stated analogy is LSP. Any
tool that wants to sit between an editor/UI and an arbitrary agent has a standard door now, and it
is not one we would define.

### The loop-with-a-dashboard already exists, MIT-licensed and stable

**`agentloop.tools` — AgentLoop, v1.2.0 stable, MIT, local-first, Node 18+/Git, no install.**

Its architecture, from its own page: a planner defines objectives in a goal file; fresh AI workers
build with clean context each cycle; **independent critics** evaluate against user-defined standards
in a `GUIDELINES.md`; evidence carries forward to the next iteration until standards are met. Its
dashboard shows a cycle timeline with **PASS/FAIL/CONTINUE verdicts**, critic notes, elapsed time and
tool calls per cycle, **cost**, **file handoffs**, and cancellation. Backends are Codex and Claude
Code, coordinated over MCP. It claims to detect defects "that passing tests miss." Roadmap: two-way
agent questions and research loops.

Read that against `.claude/loops/` and the round discipline: goal file ≈ `STATE.json` +
`DIRECTION.md`; fresh worker per cycle ≈ a fresh headless process per iteration; independent critics
against written standards ≈ R2/R3; evidence carried forward ≈ the evidence contract; two-way agent
questions ≈ `ask_user`. **This is substantially the mechanism this repository built, productised by
someone else, already stable, and given away.**

It is not alone. `agentsroom.dev` spawns each harness as a real local CLI process behind one
dashboard. Anthropic's own **Claude Code Agent View** (research preview, 2026-05) is a single
terminal screen over all sessions, with icons for alive / terminated / **sleeping between
iterations**. Marc Nuri's *AI Coding Agent Dashboard* coordinates Claude Code across machines and
names context percentage the most actionable metric. `manishiitg/coding-agent-loop` (AgentWorks)
calls itself "the open-source control plane for running, measuring, and improving AI agent workflows
across your company," with pause-for-approval and a consolidated health/cost/goal dashboard.

### Harness observability is a funded category

At least fourteen entrants appear across four comparison articles: Braintrust, LangSmith, Arize
Phoenix/AX, Helicone, Galileo, Maxim, Datadog LLM Observability, Latitude, Comet, Confident AI,
Monte Carlo and others. They already do session-grouped causal traces, nested multi-agent traces,
cost and latency, evals on production traffic, and dataset-building from failures. The category's
own framing is close to ours: *"multi-turn failures are invisible at the individual call level and
only visible in full-session causal traces."* Latitude closes issue → opened PR by connecting to a
coding agent over MCP.

---

## Part 2 — what this repository already established, and what it overturned

The 2026-09-06 exploration recommended extracting (1) the checkpoint/cutover engine and (2) the
day/night loop, and recommended *against* extracting handoff/resume/DEAD-ENDS on **market** grounds.

The 2026-09-07 verification pass read the named modules in full and **falsified seven of its
claims**. The three that bear on the operator's question:

- **The checkpoint engine is ~13% portable** of the 4,567-line stack that makes a checkpoint happen
  — 11 of 44 tables — and `grade_probe` (`checkpoint_generation.py:376-403`) cannot survive
  extraction: strip the Hub tables and it compares empty set to empty set and passes everything,
  degenerating into precisely the LLM-judge design its own docstring names as inferior.
- **"The loop wraps any CLI agent" is false as shipped** — `run-iteration.ps1:23-24` is
  `[ValidateSet("claude","codex")]`.
- **The loop's value is not software.** 879 lines of PowerShell against 1,047 lines of markdown, and
  every behavioural rule lives in the markdown. Nothing in any script enforces "this window does not
  implement."

And its sharpest observation, which decides most of Part 3: **the 09-06 document recommended
extracting the two mechanisms with the least production evidence and recommended against the one
with the most.** Context continuity here is carried by 112 numbered handoffs and a `DEAD-ENDS.md`
compiled from 1,387 dead-end bullets across 193 handoffs, proven daily for five weeks. The Hub's
checkpoint engine is the same idea rebuilt server-side, carrying none of that record.

Its separability ranking, smallest dependency footprint first: **(1)** handoff + resume +
DEAD-ENDS, 728 lines of markdown, zero code dependencies; (2) the two review-page checkers, 199
lines; (3) `checkpoint_policy.py`, 242 lines; (4) `spec_lifecycle.py`, 390 lines, two tables.

---

## Part 3 — the operator's three ideas, checked against both

### "A visual tool where we can see the loops executing, where we're at in the loop"

**Occupied, by an MIT incumbent that is stable.** AgentLoop's dashboard is a feature-for-feature
match for the described tool, and three other products cover adjacent ground including one from
Anthropic. Building this means competing with a v1.2.0 give-away for a feature whose only confirmed
user is us.

The honest residue: none of them was verified by running it, and none of them appears to do the one
thing our loop does that they do not describe — the **three-actor FILL/DECIDE/FIX asymmetry with a
human decision compressed into a single artifact between two windows that structurally cannot do
each other's job**. AgentLoop's critics are automated; ours is a person reading one page in the
evening. Whether that difference is worth a product is genuinely open. It is not obviously worth
one.

### "Handoff/resume but with a database so we can track it"

**This is the one to push back on, and the repository's own measurement is the reason.**

The file version is 728 lines of markdown with zero code dependencies, and `continuity-kit`'s README
states the property plainly: *"a file contract plus a checker, not a service. No server, no
database, no network, no MCP. That is deliberate: a file contract is the cheapest surface a harness
can integrate with, and the one least likely to be blocked by a company policy."* For an operator
whose own employer bans MCP servers, that last clause is not a footnote.

The database version **already exists** — it is the Hub's checkpoint/cutover engine — and it is the
13%-portable, 11-table, unextractable one with no production record. Adding a database to the
continuity kit is not an upgrade; it is walking from the artifact with five weeks of evidence toward
the one that has none, and buying back the exact coupling that makes the Hub's version impossible to
lift out.

If tracking is the goal, the cheap form is a checker over the file chain — which `continuity-kit`
already has, and which was driven against the reference chain and **failed it 308 times**, i.e. the
checker demonstrably works.

### "Tracking data from harnesses in order to improve"

**This is `witness`, and it is the only one of the three with a defensible wedge — narrower than
"an overseer."** Against fourteen funded observability tools, two measured properties survive:

1. **Retroactive.** The harness's own on-disk transcript covers sessions that ran *before the tool
   existed*. Every OTel path requires flags set before spawn — and Copilot CLI's file exporter needs
   `COPILOT_OTEL_FILE_EXPORTER_PATH` set before spawn, so its file surface is neither passive nor
   retroactive.
2. **Unredacted, and honest about what it cannot see.** Content is off by default on every harness
   surveyed, behind five separate flags in Claude Code. The transcript is not. And the completeness
   statement — *state per surface and per model what you cannot see* — came out of measuring that
   reasoning text is present for Haiku (407/1,022 blocks) and absent for Opus (0/8,572) and Sonnet
   (0/5,094). No incumbent reports that.

Bounded by: a measured 29-day retention window with a hard cliff (2,084 files / 1.09 GB, oldest
2026-08-09, while ≥51 earlier sessions are evidenced by committed handoffs); cost is unobservable on
the only implemented surface (`total_cost_usd` appears in 0 files); and only Claude Code's format is
mapped. Blocked on `OV-1`, which is a data-policy decision only the operator can make, and which is
time-sensitive because the corpus rolls off.

---

## Part 4 — recommendation

**Stop pursuing the harness as a product; keep it as the instrument. Do not start a new product to
replace it. Ship the one thing that is already built and already proven.**

1. **Retire the harness ambition, explicitly.** Not because AgentWeave is weak — it produced every
   piece of evidence in this document — but because the differentiators are being standardised into
   MCP, `AGENTS.md` and ACP, and a solo operator cannot out-ship a 453K-line MIT runtime that took
   95k stars in two days. Keeping AgentWeave as a private instrument costs nothing and loses nothing.
2. **Ship `continuity-kit` as-is.** Highest evidence, lowest dependency, already built and driven,
   unblockable by policy. MIT it, give it a remote, stop there. **No database.**
3. **Hold `witness` at propose-then-shelve** until `OV-1` is answered, and if it proceeds, scope it
   to the two defensible properties above rather than to "an overseer."
4. **Do not build the loop dashboard.** Drive AgentLoop for an hour first (see Part 5). If it is as
   deep as it reads, the correct move is to use it, not rebuild it.
5. **The asset nobody else can clone is the failure record.** `FINDINGS.md` at ~295 entries,
   `DEAD-ENDS.md` at 1,241 unique facts, 112 handoffs, and a round discipline that has found a real
   defect on five-plus consecutive outings. The 09-06 exploration named this itself and then did not
   follow it: *"measure the failure, then mechanize the fix … may be the most portable idea here,
   more than any single artifact."* That is a writeup or a talk, not a product — and it is the only
   thing here a funded competitor cannot answer by shipping features.

**The objection that outranks all five,** carried over from `what-is-actually-separable` and still
true tonight: the pipeline is oversupplied at the proposing end and starved at the building end —
three unarchived changes totalling ~91 tasks with **zero implemented**, six open severity-A findings
(five with no proposal), `DECISIONS.md` R-1…R-3 open a week, two changes in tonight's `APPROVALS.md`
with no verdict token, and six `OV-` decisions from the overseer loop. The FIX window builds about
one change a night. **Every option in this document except (2) adds to the proposing half.**

---

## Part 5 — what would make this exploration wrong

- **The competitor claims are unverified.** AgentLoop, AgentsRoom, Agent View and AgentWorks were
  read, not run. One hour driving AgentLoop against a real repository would either confirm Part 3's
  first verdict or overturn it. That is the single highest-value follow-up here and it is cheap.
- Star counts and adoption figures are reported by third-party articles, not counted.
- The Claude Code `thinking.display: "updates"` detail comes from a changelog aggregator, not from
  Anthropic's own documentation read directly.
- The harness-telemetry rows this builds on are already labelled `NOT CONFIRMED` for Copilot CLI's
  env vars and event schema and for Codex's, in `2026-09-07-an-overseer-for-any-harness.md`.
- If ACP turns out to be the integration surface for a tool layer, none of Part 3 was analysed
  against it. That is a gap, not a finding.

## Open questions for the operator

1. Does `continuity-kit` get a public remote, and under what name? It is four commits from done and
   the only thing here with no downside.
2. Is `OV-1` answerable this week? If not, `witness` should be shelved rather than left open, and
   the transcript corpus keeps rolling off while it waits.
3. Is the FILL/DECIDE/FIX asymmetry — a human decision between two windows that cannot do each
   other's job — worth defending as a product claim, or is it just how *you* like to work?
4. Given the building bottleneck: does anything new start before the ~91 queued tasks and six
   severity-A findings are drawn down?

## Read alongside this

- `openspec/explorations/2026-09-07-what-is-actually-separable.md` — the measured separability
  ranking and the seven falsified claims.
- `openspec/explorations/2026-09-07-an-overseer-for-any-harness.md` — the harness-telemetry survey
  and the three enforcement levers.
- `openspec/explorations/2026-09-06-what-could-leave-agentweave-and-become-its-own-tool.md` — the
  first pass, useful mainly as the thing the second pass corrected.
- `C:\Users\huida\Documents\projects\continuity-kit` — the P1 prototype, 7 commits, no remote.
- `C:\Users\huida\Documents\projects\witness` — the overseer loop's product, 4 commits, no remote,
  six operator decisions outstanding.

---

# Correction pass — 2026-09-07, later the same evening

A verification round re-derived every code-checkable claim above against the tree at `15ce482`.
The market half of Part 1 is still unverified and this pass did not touch it — only the claims
that name a file, a line, or a count in this repository.

## What held

`run-iteration.ps1:23-24` is the `ValidateSet`, exactly. `grade_probe` is at
`checkpoint_generation.py:376-403`, exactly. The "LLM judge" attribution is real
(`checkpoint_generation.py:12`). 44 tables. `checkpoint_policy.py` 242 lines, `spec_lifecycle.py`
390, the two checkers 94 + 105 = 199. The 728-line figure decomposes correctly as 341 + 127 + 260
and was right when measured — it is 824 today, because `DEAD-ENDS.md` grew to 356 in the session
that wrote this document.

## What was wrong

- **"Three unarchived changes totalling ~91 tasks with zero implemented" — it is four changes and
  127 tasks.** The missed one is `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`, 35
  tasks, which merged to master at `2b4dce4` *in this same session, before this document was
  committed at `35bffdc`*. Two boxes are ticked and neither is implementation (an R2 answer; a
  pre-change baseline measurement). **The objection this document calls decisive was understated.**
- **"`DEAD-ENDS.md` at 1,241 unique facts" — the file holds 91 bullets under 15 topic headings.**
  1,241 is the count of deduped bullets *harvested from handoffs as input*, stated in DEAD-ENDS.md's
  own header. Part 4 recommendation #5 restates the input volume as the artifact's size, overstating
  the crown asset by 13×.
- **"112 handoffs" and "193 handoffs" both appear here.** 113 exist on disk; 76 were ever tracked in
  git. 193 is not reproducible and most likely counted across the seven worktrees since deleted.
- **"Failed it 308 times" is pinned to a superseded commit.** That number is continuity-kit
  `608d4cf`, whose own message says exactly 308. Two later commits added rules; the same reference
  chain now yields **499 findings across 8 rules**. The conclusion — the checker works — is
  unaffected.
- "879 lines of PowerShell" is 877 across the four `.ps1` files.

## What was missed

### C1 — the loop-dashboard verdict was drawn against the wrong artifact

Part 3 compares AgentLoop's dashboard to `.claude/loops/`, the *scripts*, and concludes "do not
build it." But the Hub **already ships one**: `hub/hub/api/v1/loops.py` (list / detail / archive /
`control`), a `LoopSummary` carrying label, agent, purpose, stop condition, ending state, queue
counts, stop reason, open questions and firing history, and on the front end `api/loops.ts`,
`LoopsIndexTab.tsx`, `LoopFiringGroup.tsx`, `loopCounts.ts`, plus `AccountingPanel` for cost and
`QualityHealthPanel`.

**Recommendation #4 therefore answers a question nobody was going to act on.** The live question is
the delta between what already ships and what AgentLoop describes — and this document never asks it.

### C2 — the agent-agnosticism test has already run in this repo, and failed

`.agents/skills/` is a second, non-Claude skill tree of 37 skills. Of every skill present in both
trees, **exactly two have drifted: `handoff` (173 differing lines) and `resume` (107)** — precisely
the two nominated here as the most portable, zero-dependency, ship-as-is artifact. Every other
shared skill is byte-identical.

Those copies are 268/118 lines against 341/127, they are gitignored (`.gitignore:129`), and they
contain **zero mentions of `DEAD-ENDS.md`** — they predate the 2026-09-04 ledger entirely. On the
one non-Claude surface this repository maintains, the ledger does not exist.

continuity-kit's README documents the *shipped-template* fork (336 vs 341, 11 lines) and misses this
one, which is 15× larger and drops the ledger.
`what-is-actually-separable.md:135` says a port "would be a good first test of whether the contract
is really portable" — that test has been running in-tree since 2026-09-04 and its result was on disk
the whole time. The shipped templates themselves are healthy: `resume.md` is byte-identical to the
live skill, `handoff.md` differs on 11 lines and does carry the ledger.

This is the finding that bites recommendation #2. It does not overturn "ship continuity-kit" — it
prices it.

### C3 — the `ValidateSet` is not the binding constraint

`run-iteration.ps1` also accepts `-AgentExecutable`, which bypasses the PATH lookup entirely
(lines 50-55). What actually pins the loop to two agents is the hardcoded two-branch invocation at
**lines 245-258**: `claude` gets `-p … --permission-mode bypassPermissions`, `codex` gets
`exec --ephemeral --cd … --sandbox`. Relaxing the `ValidateSet` — the obvious reading of the
citation above — yields a run that invokes a third agent with Claude's flags. Cite 245-258.

### C4 — `grade_probe`'s degeneration is mis-described, and is worse than described

Stripping the Hub tables does not make it "compare empty set to empty set and pass everything."
`expected` goes empty; `reported` does not. A reader that correctly names files lands entirely in
`invented` (line 399) and the probe returns `failed`. The degenerate grader **passes only a reader
that reports nothing and fails every reader that works** — an inversion, not a no-op — and it does
not become an LLM judge, it becomes a vacuous one. The conclusion (unextractable) survives; the
stated mechanism does not.

## Net effect on Part 4

| # | Recommendation | After this pass |
|---|---|---|
| 1 | Retire the harness ambition | Unchanged |
| 2 | Ship `continuity-kit` as-is, no database | Stands, but C2 prices it — one drifted port already exists in-tree |
| 3 | Hold `witness` pending `OV-1` | Unchanged |
| 4 | Do not build the loop dashboard | **Rewrite.** C1: it is already built. The question is the delta, not the build |
| 5 | The failure record is the uncopyable asset | Stands; the headline number is 13× too large |

The overriding objection — oversupplied at the proposing end, starved at the building end — is
**confirmed and stronger**: four changes, 127 tasks, two ticked, neither an implementation.
