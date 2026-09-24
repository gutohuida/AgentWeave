# Proposal — a checkpoint is handed over once, and says where it went

**Round 1, 2026-09-24** (bundle B8, spec track S2); **verified by R2 and R3 the same day**. Findings: **F293 (B)** and **F294 (B)**, both
filed 2026-09-06 (day D-2) by an independent drive of F126's guard (`3142a91`). Both were
**re-measured on HEAD `404c7d5`** against `cut_over` itself (design *Measured in R1*). One change
answers both, because the column F293 needs is the thing F294's claim has to be written into.
**Nothing here is implemented yet.**

## Why

A cutover closes a conversation and opens its successor, handing it the checkpoint as a queued
entry (`hub/hub/checkpoint_cutover.py:63-200`). Nothing records that a checkpoint was handed over.
The only guard against a second handover is a **proxy**: `cut_over` refuses when the predecessor's
`lifecycle == "archived"` (`checkpoint_cutover.py:97-103`). The proxy fails in two ways.

**F293: following the refusal's own advice mints the duplicate.** The refusal ends *"if it was
archived by hand, unarchive it first"* (`:101-102`). `unarchive` is *"Always permitted"*
(`hub/hub/conversations.py:479-482`, route `hub/hub/api/v1/agent_chat.py:623-635`) and sets
`lifecycle = "open"`, which erases the proxy. The next press on the same spent checkpoint opens a
second successor and delivers the same checkpoint again. That delivery is a whole billed turn
spent rediscovering finished work (F126's measured outcome). Re-measured in R1: two `handoff`
successors of one predecessor.

**F294: two presses at the same instant both succeed.** `cut_over` reads `lifecycle` at `:97` and
writes it at `:144`, then commits at `:145`. Between the two it awaits `archivable` (`:105`), and
nothing serialises the window. There is no row claim, no uniqueness constraint and no lock.
`take_checkpoint` does hold one (`_checkpoint_claims`, `hub/hub/api/v1/checkpoints.py:27-28,
167-186`), but it guards only the cheaper half of the pair. Re-measured in R1 with a barrier: two
sessions, one checkpoint, two successors.

**The ledger has asked for this column three times.** F126 recommended it as shape (2) on
2026-08-30. The night of 2026-09-06 shipped shape (1) instead, because a migration fails the day
window's repair carve-out. F293 asked for it again the same day. F294 then showed that the column
alone races just as the lifecycle guard does. Design *History* says why none of the three landed.

## What Changes

- **`Checkpoint.cut_over_to_conversation_id`**, a new nullable column. It is set in the same
  transaction that creates the successor. The checkpoint row then answers *"where did this
  checkpoint go"*, which today can only be reconstructed by parsing queue-entry text.
- **A row claim.** The column is written by a compare-and-set `UPDATE … WHERE id = :id AND
  cut_over_to_conversation_id IS NULL`, and the rowcount is checked. When the second of two
  simultaneous presses finds the row already claimed, it rolls back, and neither its successor nor
  its queue entry survives.
- **A database-enforced "handed over at most once".** A partial unique index on
  `checkpoints(conversation_id) WHERE cut_over_to_conversation_id IS NOT NULL`. A conversation's
  line of work can then be continued by only one successor. That holds when two *different*
  checkpoints of the same conversation are cut over, in sequence (after an unarchive) or at the same
  instant (the automatic trigger racing an operator's press). The claim alone does not cover that
  case.
- **Refusals name where the work went.** A spent checkpoint, or a conversation already handed over,
  is refused with the successor's id. The *"unarchive it first"* advice is kept only for a
  conversation that was archived by hand and never handed over, where it is now true.
- **Migration `0106`** (the number is provisional: two other changes also name `0106`, so it is renumbered at IMPL): add the column, backfill it from delivered checkpoint entries, and create
  the index. Guarded for a missing table. The backfill is exact (design D5). The operator's real
  database holds zero cutovers (read-only, 2026-09-24), so on that database it writes nothing.
- **The automatic trigger stops at a conversation it can no longer hand over** (design D6, added
  by R3, amended by the operator 2026-09-24). A reopened conversation that was already handed
  over gets no notes request, no `due` warning and no generated checkpoint: the billed steps. The
  free final warning to a dismissed conversation still fires. Without this, D2's refusal would
  cost one billed generation per turn there.
- **`CheckpointSummary` gains `cut_over_to_conversation_id`**, so the operator routes that list and
  read checkpoints report it. No UI change is made here.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-conversation-handoff`: one ADDED requirement, *"A conversation is handed over at most once,
  and its checkpoint records where it went"*. No requirement in `openspec/specs/` governs cutover
  refusals today (F126's fix note). The existing lineage requirement in `conversation-checkpoint`
  (*"Lineage is recorded and participation is derived"*: a lineage *"is linear"*) is upheld, not
  modified.
- `conversation-checkpoint`: one MODIFIED requirement, *"Crossing the threshold warns before it
  spends"* (operator review, 2026-09-24). It now exempts a reopened, handed-over conversation from
  the notes request, the `due` warning and generation, and keeps its final warning.

## Out of scope, and where it lives

- **The cutover banner's `trigger === 'context_pressure'` filter** (`AgentOutputPanel.tsx`, F126's
  *"Still open"* remainder). A checkpoint the operator generated is never offered a cutover. That
  is UI behaviour, and it is not carried here. The new field is what such a banner would read to
  stop offering a spent checkpoint.
- **Checkpoint visibility (F235)** belongs to bundle B2 (D11). It concerns the `visibility` read
  grant, not handover. B2 may add request fields to the same `CheckpointSummary`. That is a textual
  merge point, not a conflict.

## Impact

- `hub/hub/checkpoint_cutover.py` (`cut_over`), `hub/hub/db/models.py` (`Checkpoint`),
  `hub/hub/migrations/versions/0106_*.py`, `hub/hub/api/v1/checkpoints.py` (`CheckpointSummary`), `hub/hub/checkpoint_trigger.py` (`consider`: D6's decline, and the refusal branch's return value).
- The route `POST /projects/{p}/checkpoints/{id}/cutover` still answers 409 for every refusal. Only
  the detail text changes. `checkpoint_trigger.consider` still reports a refusal as
  `cutover_refused` on `checkpoint_ready`.
- Tests: `hub/tests/test_checkpoint_cutover.py`, `hub/tests/test_migrations.py` (head bump + 0106
  data tests), `hub/tests/test_project_persistence.py` (head bump).
- `scripts/drive/t_d2_cutover_guard.py` probe 1 asserts the old *"unarchive it first"* text on a
  spent checkpoint. Re-driving it after this change should flip exactly that check, plus the
  duplicate verdicts.
- **Reaches the operator's live database on their next `:8000` restart**: one nullable column and
  one partial index, with the backfill writing zero rows there.
