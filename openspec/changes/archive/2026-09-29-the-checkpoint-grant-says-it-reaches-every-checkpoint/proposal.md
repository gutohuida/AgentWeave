# Proposal — the checkpoint grant says it reaches every checkpoint

**Round 1, 2026-09-24** (bundle B2, decision D11). Finding: **F235 (C)**, re-verified against HEAD
`ce086b6`: the hint is unchanged (`git log -S "Still bounded by each checkpoint"` last touches
`cb4ce21`), and `visibility` still has no writer. Bundle B8's change
`a-checkpoint-is-handed-over-once-and-says-where-it-went` names F235 as B2's and does not carry it
(its proposal, *Out of scope*). **Nothing here is implemented yet.**

## Why

The operator grants an agent *Read other agents' checkpoints* with a checkbox whose hint says:
*"Summaries of where their conversations got to. **Still bounded by each checkpoint's own
visibility.**"* (`hub/ui/src/components/agents/AgentSettingsControls.tsx:417`). No such bound can
exist:

- `Checkpoint.visibility` has no writer. The two creators take it as a parameter defaulting to
  `"project"` and no caller passes it (`checkpoints.py:425`, `checkpoint_generation.py:506`); no
  route and no request body carries it. The model's own comment records this, dated 2026-09-20:
  *"DEAD … `granted` has no writer, and could not be observed if it had one"*
  (`db/models.py:1653-1665`).
- Migration `0097` rewrote every stored `private` to `project` (`0097_checkpoint_visibility_default.py`),
  because every one of them was the absent default, not a choice.
- So `may_read_checkpoint`'s visibility half (`checkpoint_access.py:48`) answers *yes* for every
  checkpoint that exists, and the grant is **all-or-nothing across the project**. F235 drove it: a
  peer granted read listed and read an author's checkpoint from a conversation it had never been in.

The hint tells the operator the grant is narrower than it is, which is the wrong direction for an
access statement. The spec says the same thing the hint does, as a MAY nothing implements:
*"A checkpoint MAY additionally restrict itself, in which case access requires both the reader's
grant and the checkpoint's own visibility"* (`conversation-checkpoint/spec.md:255-256`).

Decision D11 (recommended, `spec-queue/tracks/B2.md`): the grant **is** all-or-nothing; say so, and
remove the concept that pretends otherwise.

## What Changes

- The hint says what the grant reaches: *"Summaries of where their conversations got to, from every
  conversation in this project."*
- `conversation-checkpoint`'s requirement loses the MAY and states the grant's reach.
- `may_read_checkpoint` drops its visibility half; the module docstring stops saying
  *capability ∩ visibility*.
- `CheckpointSummary.visibility` leaves the API response (`api/v1/checkpoints.py:37`, `:58`) and the
  UI type (`hub/ui/src/api/checkpoints.ts:14`). No UI code reads it.
- `create_checkpoint` and `generate_checkpoint` lose the unused `visibility` parameter.
- **The column is dropped** in a new migration, with `CHECKPOINT_VISIBILITIES` and the
  `ck_checkpoints_visibility` check. This is the last task group; stopping before it leaves a complete
  change with an inert column (design D3).

## Capabilities

### Modified Capabilities

- `conversation-checkpoint`: *Reading a checkpoint and recalling raw observations are separate
  permissions* (the MAY paragraph replaced; one scenario added).

## Impact

- `hub/ui/src/components/agents/AgentSettingsControls.tsx`, `hub/ui/src/api/checkpoints.ts`, a UI
  bundle refresh.
- `hub/hub/checkpoint_access.py`, `hub/hub/api/v1/checkpoints.py`, `hub/hub/checkpoints.py`,
  `hub/hub/checkpoint_generation.py`, `hub/hub/db/models.py`, a new migration, and the migration head
  assertions (`hub/tests/test_migrations.py`, `hub/tests/test_project_persistence.py`).
- **A migration reaches the operator's real database** on their next `:8000` restart
  (`.claude/rules/db-migrations.md`). It drops a column every row of which reads `project`.
- Routes changed: every checkpoint route that answers `CheckpointSummary` loses one field. No new call
  that can raise.
- Sequencing with B8: both change the `checkpoints` table (B8 adds `cut_over_to_conversation_id`).
  Migration numbers are assigned at IMPL, in landing order.
