# Design

## D1 — Detect in the observation path, not the approval path

The approval path (`mcp_server._decide`, `codex_appserver.decide_approval`) runs only in the two
approver postures and is the *wrong* place twice over: under full access it is not called at all, and
under `manual` the call it would report is one the operator deliberately allowed. The observation
path is the transcript builder, and it runs in every posture because that is how the run is rendered
at all.

Concretely, for Claude, `runner_parsing.parse_claude_line` walks each `assistant` message's content
blocks and, for `tool_use`, has `block.get("input", {})` — the full structured input, `file_path`
included (`hub/hub/runner_parsing.py:264-272`). For Codex, `codex_appserver` builds the same events
from `fileChange` items carrying `changes` (`hub/hub/codex_appserver.py:449-459`).

**Consequence for the two out-of-scope vectors.** Both are properties of this layer, not oversights.
A `Bash`/`shell` call's structured input is `{"command": "..."}` with no path argument, and a symlink
inside the workspace reports a path that is genuinely inside. Neither is reachable from a check on
structured input, which is why the label is *a file tool wrote outside the workspace* and not
anything broader.

## D2 — The parser extracts paths; the caller classifies them

The classification needs three things at once: the tool's structured input, the run's workspace, and
the project root. The parser has the first and must not acquire the other two — it is a pure
line-in/events-out function with no session, no run and no filesystem, and both providers share it.

It also cannot be done *downstream* of `tool_use_event`. That constructor redacts, stringifies and
truncates the input into `payload["input"]` (`hub/hub/runner_events.py:134-155`, 8 KiB cap), so by
the time an event exists the structured `file_path` may be gone, mangled or cut in half. Recovering
it by re-parsing the payload string would be a guess with a truncation bug waiting in it.

So: `ParsedLine` gains a field carrying the **write paths** the line's tool calls named — tool name,
call id, and the raw path string, nothing else. `_flush_line` in `_execute_run`
(`hub/hub/api/v1/agent_trigger.py:1877`) already has `work_dir`, `run_id`, `project_id` and `agent`
in scope, and does the classifying.

Not the whole tool input on `ParsedLine`: that would duplicate what the event already carries and
invite a second consumer to grow a second opinion about what an input means.

## D3 — Which tools count, and why only writes

Only tools whose call *is* a write: Claude's `Write`, `Edit`, `MultiEdit`, `NotebookEdit`; Codex's
`apply_patch`. Not `Read`, `Glob`, `Grep` or `LS`. The finding is about work landing where nothing
will attribute it, and a read leaves nothing behind. Recording reads would also make the record
enormous and unreadable — an agent reads outside its workspace constantly and correctly (the
project's own source, its dependencies, the standard library).

This deliberately differs from `_decide`, which checks *every* tool including reads. That is right
there and wrong here: refusing a read is a safety posture the operator chose, whereas recording a
read is noise in a record whose entire purpose is to be short enough to be read.

## D4 — Classify with the vocabulary already required: kind and name

`workspace-isolation` already requires that every API response describing a checkout says *which
kind* of workspace it is and what it belongs to, as two fields rather than a name alone — because a
task id is not an oddly-named agent. The record of an outside write reuses exactly that, since it is
answering the same question about a different subject.

The layout is entirely derivable from pure helpers in `worktrees.py`, with no database and no git:

| Path is under | kind | name |
|---|---|---|
| `<root>/.agentweave/worktrees/<agent>` (`worktree_path`) | `agent` | the agent |
| `<root>/.agentweave/tasks/<task-id>` (`task_worktree_path`) | `task` | the task id |
| `<root>/.agentweave/reviews/<agent>` (`review_path`) | `review` | the reviewing agent |
| the project root, none of the above | `project` | the project's directory |
| nothing in the project | `outside` | — |

The comparison is on `os.path.realpath` + `os.path.commonpath` with `normcase`, the same construction
`_decide` uses and for the same reason: `commonpath` compares components, so `/work-other` does not
read as inside `/work`, and both sides being real paths collapses `..` before the comparison.

**The boundary compared against is the run's own recorded one.** `AW_WORKSPACE_DIR`,
`Run.workspace_dir` and `_execute_run`'s `work_dir` are all `effective_work_dir`
(`agent_trigger.py:1023`, `:1095`, `:1146`) — one value written to three places. The detector must use
that same value and not recompute a workspace from the agent's name, or the product acquires a second
boundary that can disagree with the first, which `agent-run-sandboxing` already forbids in the
enforcement case: *"A boundary that is described in one place and enforced from another can disagree,
and the agent is given no way to tell which is real."*

Where `work_dir` is absent or unresolvable, nothing is recorded and that is stated. This is the one
place this change deliberately does **not** copy `_decide`, which refuses on an unestablished
boundary. Refusing is right for a gate; for an observer, "I could not tell" must not be written down
as "it wrote outside", because a false entry in this record accuses an agent of laundering work.

## D5 — Where the record lives: a column on `Run`, plus the existing activity event

Two consumers with different needs, and one authoritative fact.

**The fact: a nullable JSON column on `Run`.** F71's footprinting reads per run — `recorded_workspace_dir(session, run_id)` is already a one-scalar select on `Run` — and a sibling read of the same row costs nothing. `EventLog` has no `run_id` column (`hub/hub/db/models.py:1006-1027`); a run id lives inside its JSON `data`, so making footprinting read it would be an unindexed JSON scan of the project's entire activity history to answer a question about one run.

Nullable with no backfill, on migration `0096`'s own precedent for `workspace_dir` and `0043`'s for
`snapshot_commit_sha`: `NULL` means *not observed*, which is exactly what is true of every run that
predates the detector. A backfilled empty list would claim those runs were watched and found clean.
Distinguish "no writes escaped" (`[]`) from "nobody was looking" (`NULL`) — the difference is the
whole value of the record.

**The operator's notice: `persist_event(..., severity="warn")`**, following `turn_produced_nothing`
(`hub/hub/run_divergence.py:622-635`) exactly — an activity entry naming the run, the agent, the tool,
the path and the destination workspace. That is this codebase's shipped answer to "record it and
surface it to the operator", and it needs no new surface to be visible.

Two writes, not one record in two places: the column is the durable fact that later reads consult,
the event is the notification. `agent_trigger` states the same separation of itself — *"Event rows are
observability"*.

**Bounded.** A run can write outside many times. The column stores at most N entries (proposed: 20)
plus a total count, and the event fires once per distinct destination workspace per run rather than
once per call — an agent that writes forty files into the operator's checkout is one fact told forty
times, and forty warn rows would be the noise `note_turn_that_produced_nothing` explicitly refuses to
create.

**Not a new table.** Decided (D3 in the run's `decisions_for_user`), and the shape does not need one:
this is a property of a run, read only with its run, never joined and never queried across runs.

## D6 — Part (1) is a specification change, not a code change

`Run.workspace_dir` already records where the run started; nothing writes anything else into it. What
this change adds is a requirement of record saying that is *all* it records, so the next reader cannot
do what F71's footprinting did and read containment into it. The model's own comment gets the same
sentence.

The one place the current wording is actively misleading is `requirement_evidence.footprint_root`'s
docstring — *"The directory whose HEAD is the work this evidence is about"* — which is true only when
nothing escaped. Part (3) is what makes it true again, by making the exception visible rather than by
weakening the claim.

## D7 — Part (3): annotate the evidence, do not move the footprint

Where a run wrote outside its workspace, the footprint taken at `workspace_dir` describes a tree that
is missing some of the run's work. Three options were considered:

1. **Footprint the other tree instead.** No. There may be several, one of them may be the operator's
   checkout sitting on an unrelated branch, and picking one would be the "silently describes a tree
   other than the one named" failure the shipped requirement already names as worse than absent
   evidence.
2. **Refuse the evidence.** No. The operator's accepted risk is that the work lands and they find out.
   Refusing evidence would turn an observation into a gate, which is exactly the containment this
   change is forbidden to build, arriving through the evidence door.
3. **Say so on the footprint.** Yes. The footprint still describes what it describes; what changes is
   that it stops implying completeness it cannot have.

`capture_footprint` and `record` both already resolve per-run state through
`recorded_workspace_dir(session, run_id)`; the annotation is read at the same point, from the same
row, and applied by the single `_apply_footprint` mapping so capture and re-capture cannot come to
disagree about what a footprint means.

## D8 — Codex is specified, not driven

`codex_appserver.py` emits `tool_use_event` for `fileChange` with `input_data={"changes": [...]}`, a
shape different from Claude's `file_path`. The requirement is provider-neutral and the extractor
covers both, but the operator's decision of 2026-08-29 stands: **Codex is undrivable**, so the Codex
half is verified by unit test against recorded item shapes only, and the change says so rather than
claiming a live drive it did not do. Round 2 should confirm the exact `changes` element shape before
implementation — it is read here from `_file_change_summary`'s caller, not from a live transcript.

## Open questions for rounds 2 and 3

- Does `parse_codex_line`'s `fileChange` `changes` element actually carry a usable path key, and what
  is it called? Read from a real Codex item, not from the summariser.
- Is there any path by which `work_dir` differs from `AW_WORKSPACE_DIR` for the same run — a review
  checkout, a resumed run, the app-server path — which would make the detector and `_decide` compare
  against two different boundaries?
- `MultiEdit` and `NotebookEdit`: which key holds the path, and can one call name more than one file?
- What does the detection record when a path is relative but resolves outside via `..`? (It should be
  caught by realpath before comparison — assert it rather than assume it.)
- Does anything today read `Run.workspace_dir` and treat it as a containment guarantee besides
  footprinting?
