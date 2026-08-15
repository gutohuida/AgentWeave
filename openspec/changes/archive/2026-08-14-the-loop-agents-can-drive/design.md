# Design — The loop agents can drive

## D1. Three evidence tools, not two, and `decide` rather than `accept`

`record_evidence`, `list_evidence`, `decide_evidence`.

**Listing is not optional.** `decide_evidence` takes an evidence id. Without a way to discover ids
an agent granted acceptance has nothing to act on, and the grant is decorative. The agent plane has
no `GET` today; the operator plane's (`spec.py:494-518`) is the model.

**`decide_evidence`, not `accept_evidence`.** The route is a decision and rejection is half of it. A
tool named `accept_` that takes `decision="rejected"` lies about what it does, and one that can only
accept makes rejection unreachable from the agent plane while HTTP allows it — a parity violation
against `agent-capability-plane`'s rule that the two surfaces offer the same operations.

`accepted` / `rejected` read oddly as imperative arguments. They are not "fixed" to `accept` /
`reject`: they must match `EVIDENCE_DECISIONS` and the `review_state` they produce, and a vocabulary
that changes between the argument and the result is worse than one that reads slightly stiffly.

## D2. `kind` stays a bare string; only `decision` earns a `Literal`

`EVIDENCE_KINDS` is open at the edges on purpose (`db/models.py:1814-1823`): *"Values outside this
list are accepted; the list is what the surfaces know how to label."* `EvidenceRecord.kind` is a
bare `str`.

Declaring a `Literal` in `mcp_server.py` would make the HTTP route wider than the tool, which
`openspec/specs/agent-capability-plane/spec.md:109-116` forbids — the same operations with the same
validation. `decision` is genuinely closed, so it gets an alias and a row in
`test_mcp_tool_schemas.py`.

## D3. The agent-facing evidence view keeps `actor`, and reuses the operator's view

`requirement_evidence.decide` refuses self-acceptance (`:370-379`) — an agent may not accept or
reject evidence it produced. An agent that cannot see who produced a row cannot tell which rows it
may decide, and discovers the rule by burning one 403 per row.

The view is `spec.py`'s `_evidence_view` / `_footprints_for`, imported rather than rewritten.
`agent_actions.py` already imports from sibling route modules. Two evidence views would eventually
disagree about `footprint`, and `footprint.branch` is exactly the field a reviewer needs to catch
the 2026-08-13 defect class by eye.

## D4. The acceptance grant is its own setting, not a third checkpoint grant

`can_accept_evidence` is shaped like `can_read_checkpoints` / `can_recall` — a boolean the operator
confers — so it reuses their validated apply loop. It does **not** join
`CHECKPOINT_GRANT_FIELDS`: that tuple's docstring says "the two access grants" and the UI union is a
literal pair, but more importantly accepting evidence is a governance capability, not a peer-context
read. Folding them tells the operator that authority over what ships is a kind of reading.

The column and its migration already exist (`0068`). Only the API, the response schema and the UI
are missing.

**Trap:** `AgentSummary` is built by hand at `agents.py:598`. A schema default of `False` silently
wins over the row unless that construction is edited too.

## D5. A granted agent is told it has the grant

`_render_hub_agent_context` already receives `agent_row`. A granted agent that is never told will
not go looking; an ungranted one that guesses gets a 403 mid-turn.

This is the `submit_spec_document` failure mode exactly — served, correct, and invisible. A
capability the agent does not know it has is one it does not have.

For the same reason `record_evidence`'s docstring states that evidence is what makes approval merge.
`NOTHING_TO_MERGE` is shown to the operator and never to the agent that could have prevented it.

## D6. The task's document is resolved before the context renders, and the binding stays where it is

The context renders at `agent_trigger.py:~405-430`; the task binds at `:549-590`. Deriving the
document where the task is bound is out of order by 120 lines.

So a **read-only** `resolve_bound_task` moves into `run_task_binding.py`, covering all three
branches (delegated → explicit → conversation-inherited), and is called once above the render. The
mutations — `rebind_conversation`, `bind_run_to_task`, `record_response_run` — do not move. The
comment at `:549` (*"staged here — before delivery, which is what commits"*) is load-bearing.

Safe because the mutations never feed back into the resolution: `rebind_conversation` runs only in
the if-branch, `binding_for_conversation` only reads in the else-branch.

`turn_scheduler.py:71-77` is **not** changed. Its `spec_document` is the operator's viewing
position and stays that; resolving a binding in two places would guarantee drift.

## D7. The task block is a different block, not the open-document block reworded

The existing block says *"The operator is viewing `X`… Treat it as context for what they ask, not as
an instruction to act on it."* That is exactly backwards for a task run, where the document **is**
the instruction.

> ### The specification this task implements
> - This turn is bound to `task-xxxx`, which implements `spec/foo.html`.
> - Read it with `read_spec_document('spec/foo.html')`. It is not in your working copy.
> - *(then the existing `SPEC_PHASE_DUTIES` line, which already reads correctly for `approved`)*

When both blocks would name the same path, only the task framing renders — it is the stronger claim.

**And the task-derived path does not go through `spec_turn_notice`** (`launchability.py:240-262`).
That prepends *"SPECIFICATION TURN — this overrides any other specification workflow you know"*,
which is authoring instruction. Handing it to an implementer tells it to write a document instead of
implement one.

## D8. `spec_document_id` is set when a task is created, not only when one is declared

`create_task_for_actor` never sets it, even when `body.spec_document` is supplied — that field only
disambiguates `requirement_ids` today. Left alone, D6/D7 reach tasks a document *declared* and no
others, so an agent that decomposes its own work gets nothing.

It also records the document the task's `requirement_ids` **agree on** when the caller passed no
`spec_document`, and records nothing when they disagree. This was raised to the operator as a
judgement call that could be narrowed to explicit `spec_document` only, and **kept** (2026-08-14):
a task whose links all point at one document should let its builder find the spec without asking,
and guessing across mixed links is the case worth refusing.

## D9. `decide_approval` stays pure; the caller reports

Its purity is a stated decision in its docstring and asserted by `test_codex_appserver.py`. The
refusal is reported by an optional callback on `run_turn`, invoked from the caller loop once the
decision is final.

Reported **only** on a decline, and **only** when the decline did not come from the operator path —
that one already emits through `permissions.py:113`, and double-emitting is worse than silence.

The JSON-RPC method is mapped to a readable label before it becomes `tool_name`: the timeline
renders *"{agent} refused {tool_name}"*, and a method name there reads as noise.

## D10. Ignore rules cover what the Hub's own commit would sweep in

`repo_hygiene.py` currently reasons that a Rust project does not want `__pycache__` ignored because
AgentWeave happens to be written in Python. That holds for a file the operator owns. It does not
hold here, because **`snapshot_worktree` uses `git add -A`** — the Hub is the writer. The list
covers what the Hub's own commit would otherwise sweep in, which is also the rule for what may be
added to it later.

`requirement_evidence.py:300` `SKIP_DIRECTORIES` already carries nearly this list; the two should
agree in content and the comment names which is canonical. They cannot share code — `repo_hygiene`
imports nothing from the Hub, by design, so `worktrees` can call it.

**This does not untrack anything.** Git ignores untracked paths only; a `.pyc` a previous snapshot
committed stays committed. Repairing that means the Hub rewriting the operator's index unasked,
which it must not do.

## D11. A declared task may state its own title

`spec_payload.Task` inherits `extra="allow"`, so a `title` key already round-trips today —
unvalidated, unused, and invisible. Making it a real optional field costs nothing and lets the
author say what the board should show.

`_title_from` stays as the fallback, but clips on a word boundary at a board-sized limit. Fixing
only the truncation would leave a clipped sentence as a title, which is a lesser version of the same
complaint.

Existing assertions in `test_spec_declared_tasks.py` require a short single-sentence description to
come through unchanged. Those are right and are not edited.

## D12. What this deliberately does not do

- **Does not reopen the interview backstop.** Operator decision, standing.
- **Does not carry permission posture from a triggering run to a triggered one.** The existing
  inheritance is per-agent and deliberate; the run's gap was that a refusal went unrecorded, which
  is D9.
- **Does not untrack already-committed artefacts** (D10).
- **Does not give the operator plane an evidence-listing change** — it already has one.
