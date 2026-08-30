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

**Corrected in round 2: the carrier is `RunEvent`, not `ParsedLine`.** Round 1 put the field on
`ParsedLine` (`runner_parsing.py:51`) and classified it in `_flush_line`. That reaches one of the
three transports this product has, and round 2 found it by walking each of them:

| Transport | Builds events via | Reaches `_flush_line`? |
|---|---|---|
| Claude (PTY) | `parse_claude_line` -> `ParsedLine` | yes (`agent_trigger.py:1890`) |
| Codex `exec` (pipe) | `parse_codex_line` -> `ParsedLine`, `file_change` branch at `runner_parsing.py:486-499` | yes, same line |
| Codex `app-server` | `codex_appserver.map_item_to_events` -> `List[RunEvent]`, `fileChange` branch at `codex_appserver.py:448-459` | **no** |

`_execute_run` hands the app-server case straight to `_execute_codex_appserver_run`
(`agent_trigger.py:1738-1755`) and returns; that function's event sink is `_on_event`
(`agent_trigger.py:2474`), which never touches `ParsedLine`. So a field on `ParsedLine` cannot reach
it — and `run_turn`'s callback contract is `Callable[[RunEvent], Awaitable[None]]`
(`codex_appserver.py:916`), so there is no side channel either. `_on_event` receives only the event,
whose `payload["input"]` is the redacted, stringified, 8 KiB-truncated blob D2 has just finished
ruling out.

`RunEvent` is the one object all three transports produce and both sinks consume, and it is a
four-field dataclass (`runner_events.py:111-115`). It gains

```python
write_paths: Tuple[WrittenPath, ...] = ()
```

populated inside `tool_use_event` itself, from the structured `input_data` it is handed *before* it
redacts and truncates. One population site, three transports, and the field is never persisted —
`record_agent_output` stores `event.kind` and `event.payload` only (`agent_trigger.py:2480-2489`), so
this stays a transport-internal carrier and adds nothing to the stored payload.

`ParsedLine` is then left alone entirely, and both sinks classify identically: `_flush_line`
(`agent_trigger.py:1880`) and `_on_event` (`agent_trigger.py:2474`) each already have `work_dir`,
`run_id`, `project_id` and `agent` in scope, for the same reason.

Not the whole tool input on the event: that would duplicate what the payload already carries and
invite a second consumer to grow a second opinion about what an input means.

## D3 — Which tools count, and why only writes

Only tools whose call *is* a write: Claude's `Write`, `Edit`, `MultiEdit`, `NotebookEdit`; Codex's
`apply_patch`. Not `Read`, `Glob`, `Grep` or `LS`. The finding is about work landing where nothing
will attribute it, and a read leaves nothing behind. Recording reads would also make the record
enormous and unreadable — an agent reads outside its workspace constantly and correctly (the
project's own source, its dependencies, the standard library).

**Round 2: the list already exists in the product, twice, and must not become a third.**
`runner_commands.py:210` disallows exactly `Edit,Write,NotebookEdit` for a read-only agent — the
product's own statement of which Claude tools write — and `mcp_server.py:858` holds
`_PATH_KEYS = ("file_path", "path", "notebook_path")`, its statement of where a path lives. Round 1's
list added `MultiEdit`, which nothing else in this codebase recognises. Adding it is harmless in
isolation (an unknown tool extracts nothing) but a third, unreconciled list is precisely the
"two opinions about one thing" this design refuses for the boundary.

`mcp_server.py` may import **only** stdlib plus fastmcp, so it cannot import `workspace_writes.py`
and the lists cannot literally be one object. The codebase's shipped answer to exactly this is
restate-and-assert: `OPERATOR_POSTURE` is restated in `mcp_server.py` and
`test_permission_approver.py` asserts the two agree; `test_mcp_server_stdio_surface.py:95` asserts
import and spawn agree about the tool surface. `workspace_writes.py` follows it — it holds the list,
and a test asserts that every tool it calls a writer appears in `runner_commands`'s disallowed set
and that its path keys are a subset of `_PATH_KEYS`.

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
claiming a live drive it did not do.

**Round 2 answered the shape question, from a second source rather than the summariser.** The element
is a dict with a `path` key: `{"path": "a.py", "diff": "..."}`. The corroboration is
`approval_subject`'s `paths` extraction and its test (`hub/tests/test_permission_approver.py:588-604`),
which came out of **F107** — a defect found against a live Codex item, where the Hub held the item and
showed the operator the string "a file change" anyway. That is an independent reader of the same
shape, written from a real transcript rather than from `_file_change_summary`. Its malformed-input
cases are worth copying verbatim: `None`, `{}`, `{"changes": "not-a-list"}` and
`{"changes": [{"path": 1}, {}, None]}` must all extract nothing and must not raise.

Note also that the two Codex transports spell the item type differently — `parse_codex_line` reads
`file_change` (`runner_parsing.py:486`), `map_item_to_events` reads `fileChange`
(`codex_appserver.py:448`) — which is why D2's correction routes both through `tool_use_event` rather
than through either item mapper.

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

## D9 — This change records an *allowed* action, and `agent-run-sandboxing` already says not to

Found in round 2, in the capability this change adds to. The shipped requirement *A refusal is
recorded wherever it is decided* (`openspec/specs/agent-run-sandboxing/spec.md:321`) contains:

> Only refusals SHALL be recorded. An allowed action is the ordinary case, and an event per allowed
> action buries the refusals among them.

D5 emits `persist_event(..., severity="warn")` for a write that was **allowed** — approved by the
operator under `manual`, or never checked at all under full access. Round 1 wrote two ADDED
requirements into this file and never cited the sentence next door that constrains what may be
recorded in it.

It is not fatal, and the requirement is not wrong. Its own fourth scenario reads *"Allowed actions
are not recorded **as refusals**"*, so the scenario is already narrower than the prose, and the
argument the prose gives — burying the refusals — is about volume, which D5 already bounds to once
per destination per run. But in this corpus the SHALL sentence is normative and the scenario is
evidence rather than a limit on it; leaving the prose unqualified would ship a change whose own
notification breaches a requirement in the file it ships into.

So the change carries a **MODIFIED** delta for that requirement, narrowing the sentence to
"recorded *as refusals*" and stating the conditions an allowed action must meet to be recorded at
all — not ordinary, not presented as a refusal, bounded. That is the narrowest edit that makes the
corpus true, and it does not weaken the original: the volume argument survives as a constraint
rather than being deleted.

This is the same failure shape round 2 of the F14 loop found — a change breaching a shipped
requirement it did not think it was near — and it is why the round exists.

## D10 — Two columns, one migration, and the numbers

Head is `0099` (`hub/hub/migrations/versions/0099_question_wait_window.py`). The head assertions to
bump are `hub/tests/test_migrations.py:39` (`HEAD_REVISION = "0099"`) and
`hub/tests/test_project_persistence.py:227` (`assert version == "0099"`).

Round 1's tasks asked for a migration at 4.2 and another at 5.2, which would be `0100` and `0101`
and two head bumps in sequence for one change. Both columns are added by this change, neither is
readable without the other, and a half-applied pair means an annotated footprint with nothing to
annotate from. One migration, `0100`, adds both.

## D11 — `_apply_footprint` maps a `Footprint`, which is git state

Round 1's task 5.2 said to carry the outside-writes fact "through `_apply_footprint`". That function
(`requirement_evidence.py:362`) takes `taken: Footprint` — a value built by `capture_footprint` from
git alone — and writes its fields onto the row. The outside-writes fact is database state read from
`Run`, not git state, so putting it on `Footprint` would make a git-derived value carry something
git cannot derive, and `restamp_run_footprints` (`:845`, calling `_apply_footprint` at `:921`) would
then have to fabricate it.

`_apply_footprint` gains an explicit parameter instead, defaulting to "not observed", and both call
sites (`:423` and `:921`) pass what they read from the run. The "one place maps a footprint onto a
row" property the function's docstring is about survives, which is the point of routing through it
at all.

## Round 2 corrections, 2026-08-30

Recorded rather than silently applied, in the order they were found.

1. **The carrier was wrong and the Codex half unreachable.** `ParsedLine` -> `RunEvent`; the
   app-server transport never reaches `_flush_line`, and `parse_codex_line`'s own `file_change`
   branch — the Codex transport that *does* — was named by no task at all. See D2.
2. **A shipped requirement in this very capability is breached.** *Only refusals SHALL be recorded.*
   A MODIFIED delta now narrows it. See D9.
3. **The write-tool list already exists twice in the product** and round 1 proposed a third that
   disagrees with both (`MultiEdit`). See D3.
4. **D8's open question is answered**, from F107's live-derived reader rather than the summariser:
   `{"path": ..., "diff": ...}`. See D8.
5. **One migration, not two**, and the head is `0099` with two assertions to bump. See D10.
6. **`_apply_footprint` cannot carry the fact on `Footprint`.** See D11.
7. **Line-number corrections.** `_flush_line` is at `agent_trigger.py:1880`, not `1877` (cited three
   times); `_apply_footprint` is at `requirement_evidence.py:362`, not `365`; the Codex `fileChange`
   branch is `codex_appserver.py:448-459`, not `449-459`.

### What round 2 re-derived and did *not* overturn

8. **Round 1's premise correction is itself right.** `DEFAULT_CLAUDE_PERMISSION_MODE =
   WORKSPACE_PERMISSION_MODE` (`runner_commands.py:66`), applied at `:220`, with
   `DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER = "acceptEdits"` (`:73`) as the fallback where no
   Hub tool server is configured. The comment at `:56-65` records the same history the correction
   reconstructed, independently. Nothing to overturn.
9. **`work_dir` cannot differ from `AW_WORKSPACE_DIR` for a run.** Checked rather than assumed, and
   it survives. `_execute_run` has exactly one caller (`agent_trigger.py:1138`); `effective_work_dir`
   is assigned on four mutually exclusive branches (the explicit `work_dir` case at `:809`, the
   review checkout at `:824`, the isolated worktree at `:889`, and the non-isolated fallback) and is
   then written to all of `Run.workspace_dir` (`:1095`), `AW_WORKSPACE_DIR` (`:1023`) and
   `_execute_run(work_dir=...)` (`:1146`). A review turn is one of those branches rather than an
   exception to them: a review run's workspace *is* the detached review checkout, so a reviewer
   writing into its own agent worktree is correctly recorded as a write outside its workspace. That
   is right, and it deserves an explicit test rather than being discovered as a surprise.
10. **`EventLog` has no `run_id` column** — re-checked at `db/models.py:1005-1028`. D5's argument for
    the column over the event stream stands.

### For round 3

- The MODIFIED delta in D9 is the piece most worth attacking: is narrowing the shipped sentence the
  right call, or should this change emit no operator notification at all and live only on the run
  row? Round 2 chose to narrow, because a record the operator never sees is not the record F115
  asked for — but that is a judgement, not a derivation.
- `tool_use_event` is called by every transport for **every** tool, not only writers. Confirm the
  extractor returns on the tool name before it looks at anything else, so the overwhelming majority
  of calls pay nothing.
- Does anything else construct a `RunEvent` of kind `tool_use` without going through
  `tool_use_event`? If so, D2's "one population site" claim is false and round 3 should say so.
