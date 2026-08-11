# Parked phase guidance

**This directory is reference material. Nothing loads it, nothing seeds it, and no code path reads
it.** It is not a charter directory. The Hub seeds charters from `hub/hub/data/charters/` only, and
that glob cannot reach here.

## What this is

`2026-08-11-charter-set-reshape` removed six charters and cut the procedural bulk out of a seventh.
Some of what it removed was wrong and was deleted. Some of it was genuinely useful guidance that was
merely in the wrong place — text about how to investigate before deciding, what makes a requirement
testable, how to hold context across a long piece of work. That text is here.

## The requirement it is waiting on

`openspec/specs/agent-charter/spec.md` — **"A charter names an accountability, not an activity"**:

> A seeded charter SHALL describe what its holder is answerable for. It SHALL NOT be defined by the
> activity its holder performs, by the technology its holder works in, or by the phase of work it
> occurs in.

That is why this text was cut rather than kept. It describes what an agent is *doing*, which is a
phase's concern, and phase guidance does not exist yet. Design decision **D4** of this change records
the choice: parking beats deleting because recoverable is not the same as findable — nobody greps a
deleted file they do not know existed.

When the change that builds phase guidance arrives, this is its source material. It travels into
`openspec/changes/archive/` with this change, so the path stays stable.

## What is here

| File | Was | Cut because |
|---|---|---|
| `explorer.md` | a seeded charter | Investigating is an activity, not an accountability |
| `implementer.md` | a seeded charter | Implementing is an activity; `developer` carries the accountability |
| `context_keeper.md` | a seeded charter | Holding context is an activity, and largely one the Hub now performs |
| `spec-skill-routing.md` | `spec.md` §"Which skill for which step" | Routes to six `aw-spec-*` skills that nothing installs |
| `spec-inventory-rules.md` | `spec.md` §"On session start" item 2 and related | A Hub-owned project has no `spec/` tree; also carries a false claim about Hub discovery, flagged inline |
| `spec-manifest-duties.md` | `spec.md` §`spec/index.json` duties | The manifest is written by a CLI path the project cannot reach |

The three charter files are byte-identical copies of the seeds as they stood at this change's start.
The three `spec-*.md` files are verbatim excerpts under a provenance header.

## What was deleted rather than parked, and why

Not everything removed is worth keeping, and pretending otherwise would make this directory a
dumping ground:

- **`coordinator`, `model_router`, `project_manager`** — prose asking a model to guarantee what the
  transition machine and the model catalogue now guarantee in code (D3). There is nothing here to
  recover; a second unenforced authority is worse than none.
- **`architect`, `qa_engineer`, `technical_writer`, and the six `*_dev`/`*_engineer` variants** —
  folded into `tech_lead`, `verifier`, and `developer` respectively (D1, D2). The accountability
  survives in the surviving charter; only near-duplicate text was lost.
- **`spec.md`'s self-enforced approval gate** ("no implementation begins until `aw-spec-status`
  flips to `approved`") — the gate exists, but it belongs to the task transition service
  (`2026-08-10-task-transition-machine`, archived). An agent is subject to it, not its administrator.
  Reinstating this text anywhere would recreate the defect.
- **`spec.md`'s "You Are NOT Responsible For" list** — it deferred to roles that need not exist
  (`Project Manager`, `Coordinator`), which is the absent-participant defect this change closes.

Git history holds all of it if a future reader disagrees with one of these calls.
