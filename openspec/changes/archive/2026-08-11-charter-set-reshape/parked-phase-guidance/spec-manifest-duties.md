# Parked: the spec charter's `spec/index.json` manifest duties

> Cut verbatim from `hub/hub/data/charters/spec.md` (lines 10–11, 45–47, 75–76 of the pre-change
> file) by `2026-08-11-charter-set-reshape`, task 2.6. Reference material only — nothing loads this
> file.
>
> **Why it was cut:** `spec/index.json` is written by `src/agentweave/spec_manifest.py`, reachable
> only from the `aw-spec-*` skills that no longer install. A charter cannot make an agent accountable
> for a manifest the project has no way to produce.
>
> **What it is waiting on:** the same spec on-ramp decision as `spec-inventory-rules.md`. The durable
> judgment here is the last item — do not guess a manifest's semantic fields, and do not discard an
> entry for a missing file without evidence. That rule holds for any manifest, not just this one.

---

## From "You Are Responsible For"

- Keeping `spec/index.json` (the document manifest — home document, parent/order relationships)
  accurate as you create, move, or archive documents

## From "Which skill for which step"

- **Hub reports manifest drift:** `aw-spec-reindex` — deterministic mechanical repair
  (title/kind/status refresh, unfiled documents); asks before touching anything semantic
  (parent, home, a missing-file removal)

## From "Anti-Patterns"

- Guessing a manifest's semantic fields (`parent`, `home`) or discarding an entry for a missing
  file without evidence — ask, or leave it as reported drift
