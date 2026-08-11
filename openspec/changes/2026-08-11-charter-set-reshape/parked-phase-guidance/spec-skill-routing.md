# Parked: the spec charter's skill routing table

> Cut verbatim from `hub/hub/data/charters/spec.md` (lines 34–36, 38–47, 61 of the pre-change file)
> by `2026-08-11-charter-set-reshape`, task 2.6. Reference material only — nothing loads this file.
>
> **Why it was cut:** it routes to six `aw-spec-*` skills that nothing installs. The templates exist
> at `src/agentweave/templates/skills/*.md`, but no Python reads that directory — the reduction to
> five CLI commands removed whatever placed them. An agent following this table looks for skills
> nobody shipped it.
>
> **What it is waiting on:** a phase-guidance mechanism, plus a decision on whether the `aw-spec-*`
> workflow returns at all (the proposal's Non-Goals defer that to B2/B5). If it does return, this is
> the routing it had.

---

## From "On session start"

3. Use the aw-spec skills below for procedure — each bundles the authoring/manifest reference
   docs it needs (`html-spec-conventions.md`, `spec-manifest-conventions.md`) next to itself.
   Read those from inside the skill, not from this guide.

## Which skill for which step

- **Investigate:** `aw-spec-explore` (product framing) / `aw-spec-technical-explore` (codebase grounding)
- **Author or update a spec:** `aw-spec-propose` — generates the self-contained HTML spec and
  maintains its `spec/index.json` entry in the same pass
- **Implement:** `aw-spec-apply` — refuses to run on an unapproved spec
- **Complete a change:** `aw-spec-archive` — verifies approval and task completion, moves the
  change, updates its manifest entry
- **Hub reports manifest drift:** `aw-spec-reindex` — deterministic mechanical repair
  (title/kind/status refresh, unfiled documents); asks before touching anything semantic
  (parent, home, a missing-file removal)

## From "When blocked"

- Missing domain knowledge → use `aw-spec-explore` to ground yourself in the codebase first
