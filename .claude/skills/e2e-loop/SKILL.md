---
name: e2e-loop
description: Drive AgentWeave end to end as a real operator would — a live Hub, real agents, real runs — and report what breaks at the seams. Establishes test scope from the user before looking at what was built, so the test is not shaped by the builder's assumptions. Use when the user says "test the whole flow", "test this end to end", "drive the product", "e2e test", "does the loop actually work", "test what we just shipped", or after a change that touches how agents, specs, tasks or runs fit together. Finds defects unit tests structurally cannot: every serious finding lives between two features, not inside one.
---

Drive the product the way a user does, and report what the seams do.

This is not a test suite and does not replace one. `pytest hub/tests/` had 1693 passing tests on
the day this skill was written, and the first real run of the loop found ten defects — including a
tool no agent could call, and an agent that could write code but never execute it. **Both were
invisible to every test in the repository, because both live between features rather than inside
one.** That is what this is for.

## The rule that governs everything here

**This repository must never acquire an AgentWeave session.** No `agentweave.yml`, no
`.agentweave/`, no `spec/` at the repo root. Every test project is created *outside* the
repository (`~/Documents/<name>` by default). See `CLAUDE.md` — this is the one rule that, if
broken, leaves test output looking like project state.

## Step 1 — Establish scope before looking at anything

**Ask the user what to test, in their own words, first.** Do not read `git log`, the openspec
change in flight, or the session's own work before asking.

The reason is not politeness. A tester who starts from what was just built tests *that*, and
inherits the builder's model of what matters — including its blind spots. The most valuable
finding in the first run of this skill came from a question the operator was asked and *did not
answer*, which no one would have thought to test for.

Ask plainly: **"What should this run exercise?"** If they have already said, use that.

**Then reconcile, and only then.** Once you have their answer, look at what the session actually
touched — recent commits, the change in flight, modified files — and come back with:

> You asked for X. This session also touched Y. Include it?

That preserves an uncontaminated scope while still catching what they'd have forgotten. Never
silently widen the scope you were given.

## Step 2 — Derive the operator gates for *this* scope

**Do not assume the gates are the specification ones.** The scope decides where a human is
genuinely required. A spec run stops for the interview, close-exploration, propose and approve. A
permissions run stops at an approval card. A checkpoint run stops somewhere else entirely, and a
run testing agent messaging may need no stop at all.

So, having settled scope: **work out which surfaces inside it actually require an operator**, say
what you found, and confirm. Ask the user how much to drive unattended — they may want a long
autonomous run, or a checkpoint after every phase. Honour standing directives over anything here.

## Step 3 — Prepare, and check the Hub is really on your code

```bash
curl -s http://127.0.0.1:8010/health          # {"status":"ok"}
```

A Hub running an older build is the single most expensive way to waste an hour: you will attribute
its behaviour to code you changed. If anything under `hub/` changed since it started, restart it
(see Reference) and confirm health again.

Then, with the harness at `e2e.py` in this skill's directory:

```bash
python e2e.py setup <project-name>                       # fresh project, outside the repo
python e2e.py agent <project> <name> <charter> <cli>     # e.g. architect "Spec Author" codex
```

Prefer **two runners** when the scope allows — a Claude agent and a Codex agent. The first run
found a defect that only affected Claude, and would have reported the product healthy if it had
used one runner.

## Step 4 — Drive it, and hold to these

Each of these produced a finding on the first run. They are the method, not decoration.

1. **Use the real surface. Never simulate a step.** If something has no API, that absence *is* the
   finding — write it down and continue. Do not have the harness paper over it. (This is how "no
   integration step exists" surfaced.)
2. **Play the operator honestly, and leave something unanswered.** Answer as a real user would:
   decisively, in prose, with actual constraints. Then *deliberately let one question go
   unanswered.* A tester who answers everything never discovers which questions silently evaporate.
3. **Watch the seams.** Between exploring and proposing. Between an approved document and a task.
   Between a completed task and a reviewed one. Between one agent and the next. The defects are
   there, not inside a phase.
4. **Read what the agent actually said.** The transcript is evidence. On the first run an agent
   reported it could not run tests and the described tool surface said otherwise — the agent was
   right. Do not dismiss an agent's account of its own failure; verify it.
5. **Follow peer-triggered work, not just what you triggered.** Runs started by an agent messaging
   another take a different path through the code than runs started from the composer, and that is
   where posture and continuity get lost.

## Step 5 — Verify independently

**Never accept "the tests pass" as evidence.** Run them yourself. Then go further: recompute a
result by hand and compare. On the first run the settlement arithmetic was checked to the cent
against the specification's stated rounding rule — which is the only reason "correct" could be
claimed at all.

Check the database, not just the chat: task transitions, document events, conversation records.
An agent's summary of what it did is a claim; the rows are the fact.

## Step 6 — Vary one axis

Change one environmental thing and re-run the verification. Encoding, locale, working directory,
a different runner.

The first run's tests passed 99/99 and failed 9 under `PYTHONIOENCODING=utf-8`. Both agents shared
one machine, so a two-agent review was structurally incapable of noticing. **Any review where the
author and reviewer share an environment is blind to this whole class**, and varying one axis is
the cheapest way to see it.

## Step 7 — Record it

Write findings to `openspec/explorations/<date>-<subject>.md`, **ranked by what each cost**, not by
where they were found. For each one:

- what happens, in a sentence
- the evidence — a transcript quote, a database row, a command and its real output
- whether it is one defect or a symptom of a design gap
- whether an existing planned change already covers it

That last point matters: the first run rediscovered two entries from an existing roadmap
(`openspec/explorations/2026-08-10-specification-and-surface-program-roadmap.md`) from the outside.
Check the roadmap and the archived changes before proposing anything new — you may be finding
confirmation rather than news.

Also record **what held**. A gate that correctly refused something is a result, and the next
session needs to know it was exercised.

## Step 8 — Clean up

```bash
python e2e.py clean <project-id>      # removes the project's rows and its directory
```

Remove any credentials the run minted. Leave a project in place only when you say so explicitly and
why — a stray test project is indistinguishable from a real one a week later.

## Reference — this machine

- **Restart the Hub so it survives session teardown:**
  ```
  Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}
  ```
  Find the live PID with `Get-NetTCPConnection -LocalPort 8010 -State Listen`.
- **Interpreter:** `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`pytest hub/tests/ tests/` together fails collection** — run them separately.
- **Auth:** `Authorization: Bearer <AW_BOOTSTRAP_API_KEY from hub/.env>`; the harness reads it.
- **A run's permission posture** comes from `overrides: {"permission_mode": ...}` on the trigger —
  `workspace` lets an agent execute inside its own worktree, `acceptEdits` does not. The harness
  exposes this as `--perm`.
- **Agent worktrees** are per *agent* (not per conversation), at `.agentweave/worktrees/<agent>` on
  branch `agentweave/<agent>`, created lazily at first trigger. Code an agent writes is **there**,
  not on master.
- **Printing agent replies through a cp1252 console** crashes on a sketch containing `→`; the
  harness reconfigures stdout to UTF-8.

## The harness

`e2e.py`, in this skill's directory. Every command goes through the Hub's real HTTP surface with
real credentials.

```
setup <name>                                    fresh project, outside the repo
agent <project> <name> <charter> <cli> [model]  register and bind runner + charter
doc-new <project> [title]                       create a document; the Hub mints the name
turn <project> <agent> <msg> [--doc P] [--task T] [--perm MODE] [--fresh]
watch <run-id> [minutes]                        wait, then dump the whole turn
answer <project> <agent> [choice]               answer an open ask_user batch
close|propose <project> <path>                  operator gates
phase <project> <path> <to> [reason]            exploring | proposed | approved
tasks <project>                                 the board
task-set <project> <task-id> <status>           move a task
state <project>                                 documents, events, runs, tasks
clean <project>                                 remove the project and its rows
```

Extend it when the scope needs something it lacks — but if a step has no API to call, that is
Step 4 rule 1, and it belongs in the findings.
