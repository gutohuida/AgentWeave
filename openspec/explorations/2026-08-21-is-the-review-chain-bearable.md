# Exploration — Is the review chain bearable? (2026-08-21)

**Status:** OPEN, and deliberately so. Carries `task-dependencies` **11.4**, waived when that
change was archived: *"I'll need to use more to decide."*

11.4 is described in its own change as **the change's main risk, and only real use answers it.**
This note exists so that question survives the archive.

## The question

Walk a three-deep chain with two agents. Is the review cost *per wave* acceptable — or would you
route around it in real work?

## The one data point so far

2026-08-21, `proj-5e960453`, board "Batch the loop board dependency gate". Asked to start a gated
task, `builder` did not stall:

```
18:59:35  builder  measure    → in_progress
19:03:09  builder  measure, inventory → completed
19:06:56  speccer  both → under_review
19:06:59  speccer  both → approved     →  next layer ungated
```

Roughly **seven minutes**, unattended, for one wave of two tasks across two agents.

And the review was real, which matters for the cost question — a rubber stamp would be cheap and
worthless. `speccer` checked both against the source, caught that `task_transition_service.py:236`
imports the gate under an alias (so a literal grep misses it), and stated what it had *not*
verified: *"I didn't re-run your scratch test, but read jobs.py:190-198 directly."*

## Why that is not an answer

- One wave, not a chain. The question is about **sustained** cost over three or four layers.
- Two tasks in the wave, both small and both investigative.
- Nobody was waiting. Seven minutes unattended reads differently from seven minutes blocked.
- No rejection happened. The expensive case is a review that sends work back.

## What would answer it

Run a real decomposition through to the terminal layer and count: wall-clock per wave, how often a
review rejects, and whether the operator ends up approving without reading. That last one is the
failure mode — a chain that is *tolerable* only because the reviews stopped being real.
