# Test guide — evidence is decided after the run that recorded it

## Agent-verifiable

1. **A mid-run decision is refused, and clears by itself.** Tasks 1.1-1.3: 409 `recording_run_live`
   while the run is registered, 200 once it is not. 1.1 and 1.2 fail on today's code.
2. **Nothing wedges on a crashed run.** 1.4: a `running` row the registry does not hold is decidable.
3. **Refusal order is unchanged for the other refusals.** 1.5.
4. **A same-turn re-record revises instead of refusing.** 1.7 fails today; 1.8 (different runs) keeps
   refusing; 1.9 (reworded requirement) makes a new row.
5. **The agent is not told to commit.** 1.10.
5a. **A second record in a new, dirty turn revises that turn's row.** 1.7b.
5b. **A merge failure after a decision does not 500 the decision (F426).** 1.14 — fails today (measured).
5c. **A revision counts as the latest recording.** 1.7: the revised row's `produced_at` moves, and
   `commit_for_task_review` picks it.
5d. **A refused agent is woken when the run ends (operator decision 2).** 1.15-1.16: one `evidence`
   entry, in the conversation it was refused in, in the refusing turn's workspace. 1.17's controls:
   nothing for the operator, for a row decided since, after a restart, or into an archived thread; two
   rows make one note. 1.18: both transports wake after the registry pop. 1.19: the origin persists
   and renders as `AgentWeave`.
6. **The live trials** (3.1, 3.2), with the 409 body and the wake note recorded verbatim.

## Human-only

1. Open a document whose requirement has evidence an agent is recording right now (the agent is
   mid-turn). Once `the-coverage-bar-takes-the-evidence-decision-it-asks-for` has shipped, the row
   should read as still being recorded, with its buttons held. Before that change ships there is no
   screen; nothing to check by eye.
2. After the turn ends, the same row offers Accept and Reject, and the commit it shows is the one the
   turn produced, not the one it started from.
3. Tell one agent to review another's work while the author is still mid-turn, and let the reviewer
   try to decide the evidence. In the reviewer's conversation you should see its refusal (it names
   the run and says stopping it would end it), then — once the author's turn ends — a short note from
   AgentWeave saying the piece can be decided now and which commit it names, followed by a new turn in
   which the reviewer decides it. The note should appear in the same conversation, once.
