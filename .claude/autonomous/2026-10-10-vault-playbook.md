# Vault loop, 2026-10-10 — build contradictions, then spec and build reports

Operator, 2026-10-10 morning: loop until 15:00 on "the slices of the new work we determined" — the
knowledge vault roadmap `spec/changes/the-knowledge-vault-and-its-manager-roadmap/spec.json`
(`spdoc-7c75066d6403`). Slices 1–3 are done. This loop builds slice 4 (**contradictions**), closes it,
then specs and builds slice 5 (**reports**). At the end the driver runs a close-out briefing that
is published as a Claude Doc (see `closeout` in the STATE file); you do not write it yourself.

State `.claude/autonomous/STATE-vault.json`, log `.claude/autonomous/2026-10-10-vault-log.md`
(newest entry at the bottom; find it with `grep -n '^## '`).

## Read before the first contradictions item

- `.claude/handoffs/handoff-0190-2026-10-09-2203-contradictions-approved-build-next.md`,
  "Current state" — the fixed design, restated so the build needs no re-reading, and "Next steps"
  2–5. Read the handoff from disk; it is untracked.
- `spec/changes/sources-that-disagree-are-pointed-out/spec.json` (`spdoc-bcbc9be56864`, Tier 2) —
  FR-1..FR-9, acceptance criteria, design D1–D8.
- `scripts/drive/d1017_contradictions.py` — the acceptance drive, committed failing at check 1. It
  is the definition of done for the slice.
- `.claude/handoffs/DEAD-ENDS.md`, the 2026-10-09 blocks (vitest worktree junction, `schema_version`
  in `author_change.py` payloads, `py -3.11 -m ruff/black`).

## How to work

- One queue item per firing, sized to finish. Tests first at the seam the item names; `py -3.11`
  only; `black --target-version py311`; ruff and black over CI's paths before committing.
- UI items: vitest first, then the component, then `npm run build` in `hub/ui` and
  `py -3.11 scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together.
- Drives: scratch Hubs on free ports (8110+), from source, under `testbed/`; every real agent turn
  binds `claude-haiku-4-5`; never leave a job enabled. `.claude/loops/night-window.md` "Driving" is
  the reference.
- Spec documents are written through the trial Hub `:8010` (`proj-d85a82bf4216`) with
  `scripts/drive/author_change.py` (payload needs `"schema_version": 1`), never by editing
  `spec/` files. If `:8010` is down, start it from `hub/` from source per
  `.claude/reference/hubs.md`; restarting `:8010` is allowed. It writes into this checkout, which is
  on the loop branch — that is intended.
- **Design questions the operator would normally answer** (operator, 2026-10-10: "pick and
  record"): take the recommended option, build it, and add an `OPEN` row to
  `spec-queue/DECISIONS.md` with id `vault-1010-<n>`, worded "Taken by the loop: … Rejected: … Confirm
  or reverse." — the format of the `night-1010-*` rows. List the id in `decisions_for_user`.
- CI: the driver puts its verdict at the top of your prompt; a red branch is that firing's work.
- **Time:** the stop is 15:00. Do not start an item you cannot finish and commit by then; if that is
  every remaining item, log why and set `next_action` to null (the close-out briefing then runs).
- Findings found on the way go to `scripts/drive/FINDINGS.md` (next free F-number), not into the
  change. Metrics: when a change closes, append its row to `spec-queue/METRICS.md`.

## Limits

Everything in the STATE file's `limits`. In particular: never touch `:8000`; no merge to master
(the operator merges after reading the briefing); stage explicit paths.
