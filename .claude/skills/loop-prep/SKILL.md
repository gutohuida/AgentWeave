---
name: loop-prep
description: Prepare for an unattended loop before starting it. Reads the recent handoffs, the openspec state and the working tree to work out where the project actually is, interviews the operator about intent, then finds the things that would stall the loop — unmade decisions, missing specs or explorations, an unready environment, a queue too vague to execute — and produces them up front. Ends by seeding STATE.json so the loop can start. Use when the user says "prepare for a loop", "get ready to run overnight", "loop prep", "what do we need before we start", or before invoking /autonomous-session on anything substantial.
---

Work out what would stall the loop, and remove it before the loop starts.

## Why this exists

An unattended loop cannot ask you anything. Every question it hits becomes one of three bad
outcomes: it guesses, it stalls, or it burns an iteration writing the question down. All three are
avoidable, because **the questions are almost always knowable in advance.**

Measured on this project:

- The overnight run of 2026-08-15 hit a decision mid-flight — whether a binding-conflict failure
  should requeue its input — that two existing test files exposed within minutes of the code
  landing. Nothing about it required the loop to be running to discover.
- Loop 9 inherited its test scope from a previous session's answers because the operator was
  asleep, which the `/e2e-loop` skill explicitly warns produces a test shaped by the builder's
  blind spots.
- The first driver iteration ran against a `STATE.json` whose `next_action` I had hand-written
  seconds earlier. It worked — but only because the task was trivial. A real queue was never
  prepared.

The cost of preparing is minutes. The cost of not preparing is an iteration, or a wrong turn you
find in the morning.

## Step 1 — Ask intent first, before reading anything

One question, in the operator's own words: **"What do you want this loop to have achieved by the
time you look at it?"**

Ask this *before* opening the handoff or the git log. A prepared brief that starts from what was
last built will propose more of the same, and inherit whatever that work assumed. Intent first
keeps the target uncontaminated.

If they have already said, use it. Do not re-ask.

**Then** ask two shaping questions:

- **How long, and stop when?** A two-hour loop and an overnight loop want different queue depths.
- **Is anything off limits** beyond the usual — a branch, a file, a service, a cost ceiling?

## Step 2 — Now read, and work out where the project actually is

Only after intent is fixed. Gather, in this order, and do not guess any of it:

```bash
cat .claude/handoffs/LATEST.md          # then read that file
git log --oneline -10
git status --short
ls openspec/changes/ | grep -v archive  # what is in flight
ls -t openspec/explorations/*.md | head -5
```

From the newest handoff, extract four things specifically:

1. **`## Next steps`** — the queue someone already thought about.
2. **`## Open questions for the user`** — these are stalls, pre-identified. They are the single
   highest-value input to this whole skill.
3. **`## Constraints and user directives`** — the loop must inherit these verbatim.
4. **`## Dead ends`** — so the loop does not pay twice for the same failure.

Then establish the **development phase**, because it decides what artifact is missing:

| Where the work is | What the loop needs to exist first |
|---|---|
| A problem is felt but not understood | an **exploration** — evidence gathered, ranked by cost |
| Understood but not designed | a **proposal + design** — with alternatives and their rejection reasons |
| Designed but not built | a **tasks.md** — split agent-verifiable from human-only, with a user test guide |
| Built but unproven | a **live environment** and a **verification plan** |
| Proven but not recorded | **archive ordering**, and the specs synced |

A loop asked to implement against a spec that does not exist will write the spec badly and then
implement it. That is the most common and most expensive form of unpreparedness.

## Step 3 — Hunt the stalls

This is the substance of the skill. Walk all five categories; each has produced a real stall here.

### 1. Decisions only the operator can make

Find them **before** the loop does. Look for: a design choice with two defensible answers; anything
touching safety, cost, or what ships; anything the handoff's open questions already names.

For each, do one of two things — never leave it implicit:

- **Decide it now**, with the operator, in one `AskUserQuestion`. Record the answer *and the
  rejected alternative with its reason*, or it will be re-proposed.
- **Pre-authorise a default**: "if you hit this, do X; the cost of X being wrong is Y." This is what
  lets a loop keep moving at 3am instead of parking.

### 2. Missing artifacts

Against the phase table above: does the thing the loop will act on actually exist? A named
exploration, a spec with the requirement it will implement, a `tasks.md` with an executable first
task. **Create what is missing now**, in this session, where you can ask questions.

### 3. An environment that is not ready

The loop cannot debug its own runway. Check, do not assume:

- Is the service running, and **on the current code**? A stale build is the most expensive
  failure mode there is — the loop attributes its behaviour to code you changed.
- Do the test projects, credentials and fixtures it needs exist?
- Does the suite pass **now**? A loop that starts on a red suite cannot tell its own breakage from
  the one it inherited.

### 4. Unstated constraints

Anything the operator would object to on seeing it, that is written nowhere. Ask directly rather
than inferring. These belong in `STATE.json`'s `limits`, verbatim.

### 5. A queue too vague to execute

Each item must survive this test: **could a stranger with no memory of this conversation do it?**
That is literally the next process. "Improve the error handling" fails. "In `x.py:120`, add the
guard described in design decision D4, and mutation-check it" passes.

## Step 4 — Produce the brief, and seed the loop

Write `.claude/autonomous/STATE.json` — the file `/autonomous-session` and the driver both read.
Every field earns its place:

- `branch` — the **fresh, dated** branch the loop will cut, e.g. `autonomous/2026-08-15-<topic>`.
  Never a reused fixed name: the last run's scratch would come with it.
- `parent_branch` and `parent_sha` — **the branch the operator is actually working on**, captured
  now. The loop must branch from there, not from `master` and not from a previous autonomous
  branch, or it works against a world the operator will not recognise. It is also the answer to the
  morning's first question, "what is this a diff against".
- `queue` — ordered, each item executable, each with an id.
- `current` and `next_action` — the first item, written for a stranger.
- `limits` — the constraints, quoted.
- `decisions_for_user` — **start it populated** with anything Step 3.1 could not settle. An empty
  array here after a real prep is usually a sign the hunt was not done.
- `stop_at`, `branch`, `purpose`.

Alongside it, state plainly:

- what was **created** this session so the loop would not have to (spec, exploration, fixture);
- what was **decided**, and what the rejected alternative was;
- what is **pre-authorised**, and the cost if the default is wrong;
- what is **still unknown**, and what the loop should do on hitting it.

Then say whether the loop is ready, and if it is not, say what is missing rather than starting it
anyway.

## Step 5 — Hand off to the loop

`/autonomous-session` takes it from here — it will read this `STATE.json` rather than asking again.
If the run is genuinely unattended, install the durable driver; a session-bound loop will not
survive the night, which is measured, not theoretical.

## What good preparation looks like

A loop that runs for hours and produces **no** `decisions_for_user` entries was either trivially
scoped or is guessing. A loop that produces one or two, each specific, is working correctly and
telling you where the real ambiguity was.

The aim is not to eliminate every unknown — it is to make sure the loop meets no unknown that you
could have resolved in thirty seconds while awake.

## Reference — this repository

- Handoffs are in `.claude/handoffs/`, newest named by `LATEST.md`. Read the newest, and follow
  `**Previous handoff:**` back one hop only if the next step needs it.
- In-flight work is `openspec/changes/<date>-<name>/`; findings are `openspec/explorations/`.
  Requirements use `### Requirement:` with `#### Scenario:` and MUST/SHALL language, and the
  validator reads **only the first physical line** for the modal.
- `npx openspec validate --changes --strict` before declaring an artifact ready.
- Start the Hub detached so it outlives the session, and confirm `/health` reports the code you
  think it is running.
- `pytest hub/tests/` is about seven minutes and exceeds the 600s command cap — run it in file
  chunks. `pytest hub/tests/ tests/` together fails collection.
- Never create `.agentweave/`, `agentweave.yml` or `spec/` at the repository root; test projects
  live outside the repo.
