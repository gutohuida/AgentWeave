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

**Round 3: that list is right and it is not sufficient.** The four values were re-checked and all
four are there — `_execute_run` takes `work_dir: Optional[str]` alongside `project_id`, `agent` and
`run_id` (`agent_trigger.py:1720-1740`), and so does `_execute_codex_appserver_run`
(`:2389-2406`). But D4 classifies against **two** roots, not one: it needs the project root as well,
to compute `worktree_path`, `task_worktree_path` and `review_path` and to tell `project` from
`outside`. `repo_root` occurs **nowhere** in either function — measured across `agent_trigger.py`
lines 1720-2274 and 2389-2752, zero occurrences. It is computed in the trigger body above and never
passed down.

So both functions take a new parameter. That is a small change and it is the right one: the
alternative — re-reading the project row from the database inside a per-event callback — would put a
query on every tool call of every run to answer a question that is constant for the run. Tasks 4.3
and 4.3b are written as though the project root were already in scope; they are corrected to pass it.

**Round 3 also confirms the one-population-site claim, with one boundary on it.** `kind="tool_use"`
is constructed in exactly one place in `hub/hub` — `runner_events.py:154`, inside `tool_use_event` —
so D2 holds for every event the Hub produces, and task 2.5c is answered rather than left conditional.
The boundary: `record_agent_output`'s own docstring says it mirrors `POST .../output`, an ingest
route that will accept a `tool_use` kind from a self-reporting agent the Hub did not spawn. Such a
row has no `RunEvent` behind it and no workspace to check it against, which is correct — it is not a
Hub-spawned run — but the claim is "one population site for the events the Hub produces", not "for
every `tool_use` row in the database".

Not the whole tool input on the event: that would duplicate what the payload already carries and
invite a second consumer to grow a second opinion about what an input means.

## D3 — Which tools count, and why only writes

Only tools whose call *is* a write: Claude's `Write`, `Edit`, `MultiEdit`, `NotebookEdit`; Codex's
`apply_patch`. Not `Read`, `Glob`, `Grep` or `LS`. The finding is about work landing where nothing
will attribute it, and a read leaves nothing behind. Recording reads would also make the record
enormous and unreadable — an agent reads outside its workspace constantly and correctly (the
project's own source, its dependencies, the standard library).

**Round 2 said the list exists twice and must not become a third. Round 3 measured it: it exists
three times, and round 2 reconciled against the wrong one.**

The third is `WRITING_TOOLS` in `hub/ui/src/components/agents/AgentTimeline.tsx:573`:

```ts
const WRITING_TOOLS = new Set(['Edit', 'MultiEdit', 'Write', 'NotebookEdit', 'apply_patch'])
```

That is the same *concept* this change needs — tools whose call is a write, across both providers —
and it is the timeline's basis for the "wrote to N files" summary an operator already reads. So
`MultiEdit` is not, as round 2 wrote, a tool "nothing else in this codebase recognises": it is
recognised here, at `AgentTimeline.tsx:558`, in `lib/editDiff.ts:20`, and in a test written against a
real `MultiEdit`-shaped payload (`hub/ui/src/__tests__/agentTimeline.test.tsx:801-827`). Round 2's
ground for dropping it is false, and it goes back in.

**`runner_commands.py:210` is not a statement of which tools write.** Read in place, the flag is
`restrict_spec_writes` and its own comment names its subject: F4/design D6, *which tools exist at
all* for a spec-authoring agent, applied unconditionally including under yolo. It is a permissions
decision about one kind of agent — Claude-only by construction, since it is a `--disallowedTools`
argument, so `apply_patch` can never appear in it. Round 2's proposed assertion, that every tool
`written_paths` calls a writer appears in that set, is therefore **false by construction for the
Codex half** and would have forced `MultiEdit` out for a reason that does not hold. (That
`restrict_spec_writes` omits `MultiEdit` while the UI counts it as a write is worth a finding of its
own — a spec-restricted agent may be able to write through it — but it is not this change's to fix,
and this change must not inherit the gap by treating that list as the definition.)

What survives from round 2 is the `_PATH_KEYS` half, and only for Claude. `mcp_server.py:858` holds
`_PATH_KEYS = ("file_path", "path", "notebook_path")`, and every Claude writer's declared path is one
of those, `MultiEdit` included — its input is `{file_path, edits: [...]}`, so the file it touches is
at the top level. Codex's `apply_patch` names its paths at `changes[].path`, a nested key `_PATH_KEYS`
does not contain and should not.

So the reconciliation is: `workspace_writes.py` holds the list; a test asserts it agrees with the
UI's `WRITING_TOOLS`, which is the same concept; and a second asserts its **Claude** path keys are a
subset of `_PATH_KEYS`. `mcp_server.py` may import only stdlib plus fastmcp, so restate-and-assert is
the shape available — the same one `test_permission_approver.py` uses for `OPERATOR_POSTURE` and
`test_mcp_server_stdio_surface.py:95` uses for the tool surface.

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
| `<root>/.agentweave/`, none of the above | `hub` | the Hub's own directory |
| the project root, none of the above | `project` | the project's directory |
| nothing in the project | `outside` | — |

**Round 3 added the `hub` row, and it is not cosmetic.** Rounds 1 and 2 folded everything under the
project root that is not a worktree into `project`, and then justified `project` as the mild
destination on the grounds that a write there *sits visibly*. That justification is exactly inverted
for `<root>/.agentweave/`. `repo_hygiene.EXCLUDE_PATTERNS` (`hub/hub/repo_hygiene.py:59-80`) lists
`.agentweave/worktrees/`, `.agentweave/reviews/`, `.agentweave/tasks/`, `.agentweave/logs/`,
`.agentweave/evidence/` and `.agentweave/context/`, and `seed_repo_excludes` writes them into the
repository's `info/exclude` on **every turn** — `resolve_agent_workspace` calls it as its first
statement (`worktrees.py:627`), before it does anything else. So the Hub itself has told git to hide
that subtree. A write into `<root>/.agentweave/evidence/` is a run writing into the Hub's own
record-keeping about runs, it appears in no `git status` anywhere, and under the round-1/round-2
table it would have been reported to the operator as the destination that "sits there visibly".

It also keeps the table honest about its own construction: three of those exclude patterns are the
same three directories the layout helpers name, and the remainder is precisely the residue this row
now claims. The classifier still derives the three from `worktree_path`/`task_worktree_path`/
`review_path` rather than from the exclude list — one source of truth for the layout — but the two
must not drift, and a test that walks `EXCLUDE_PATTERNS` and asserts every `.agentweave/` pattern
classifies as `agent`, `task`, `review` or `hub` and never as `project` is what keeps them together.

The comparison is on `os.path.realpath` + `os.path.commonpath` with `normcase`, the same construction
`_decide` uses and for the same reason: `commonpath` compares components, so `/work-other` does not
read as inside `/work`, and both sides being real paths collapses `..` before the comparison.

**Round 3: the construction is not complete without `_decide`'s first line, and rounds 1 and 2 both
omitted it.** `_decide` does not call `realpath` on the reported path. It joins first
(`mcp_server.py:901`):

```python
absolute = candidate if os.path.isabs(candidate) else os.path.join(root, candidate)
resolved = os.path.realpath(absolute)
```

Round 1's open question said the relative case "should be caught by realpath before comparison —
assert it rather than assume it", and round 2 left it unanswered. It is not caught by realpath.
`os.path.realpath` resolves a *relative* path against the calling **process's** working directory,
and the two call sites do not share one:

- `_decide` runs inside the **agent's own process** — it is the spawned `mcp_server.py`, whose cwd is
  the run's workspace. Its own comment relies on this in the shell branch: *"Relative paths are left
  alone: they resolve against the run's cwd, which is the workspace."* There, `realpath` alone would
  have been nearly right, and the join makes it exactly right.
- The detector runs inside the **Hub process**, whose cwd is wherever uvicorn was started and has
  nothing to do with any project. One Hub serves many projects; there is no cwd that could be
  correct.

So `os.path.join(workspace_dir, candidate)` is a named, load-bearing step, not an implementation
detail of the comparison. Without it the delta's scenario *A relative path that traverses outside is
caught* would resolve `../../x` against the Hub's launch directory and classify essentially at
random — usually `outside`, for the wrong reason, and on a Hub started inside a project, silently
`project`.

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

**Round 3: where the accumulated state lives, and when the column is written.** Neither round said,
and both of D5's own constraints need it — "at most 20 entries plus a total count" and "once per
distinct destination per run" are per-*run* facts, while the only sites that see the calls are
per-*event* callbacks that each open their own session (`_flush_line`'s `for event in parsed.events`
loop at `agent_trigger.py:1930-1945`, and `_on_event` at `:2474-2489`).

The precedent D5 cites points at the answer that is wrong here. `turn_produced_nothing` is emitted
from `evaluate_run_end` (`run_divergence.py:622-635`, reached at `:672`) — at the run boundary, once,
having read the whole run back. Flushing this column the same way would be the natural reading of
D5 as written, and it loses the entire record for a run that is killed, whose Hub is restarted, or
whose process dies — which is exactly the population of runs whose stray writes matter most. A record
that survives only tidy runs is not the record F115 asked for.

So: **accumulate in the enclosing closure, write on first sight of each destination.** The
accumulator is a `dict` keyed by destination — the same `nonlocal` shape `sequence` and
`accounting_sample` already use in both functions, and safe for the same reason, since each sink is
awaited serially within a run and only one of the two runs for any given run. When a destination is
seen for the first time, one transaction writes the `Run` column and emits the `persist_event`
together; every later write to a destination already recorded touches the closure only.

That gives, per run, at most one database write per distinct destination — a handful, and bounded by
the same 20 that bounds the column. A killed run keeps every destination it reached and the first
path into each, which is the whole of the operator-facing fact. What a killed run loses is the exact
per-destination call count, updated best-effort at the run boundary. That is the least valuable field
in the record and the only one it is safe to lose, and it makes the column and the activity event
consistent by construction rather than by two code paths agreeing to be.

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

## D9 — `Only refusals SHALL be recorded` does not say what round 2 read it as

Round 2 found the sentence, concluded that this change's operator notification breaches it, and
carried a MODIFIED delta to narrow it. Round 3 was asked to attack that judgement. The judgement
survives; **the argument for it does not, and the delta it produced was three times the size the
correct argument supports.**

### The premise is false, and the product disproves it

The sentence sits in the requirement *A refusal is recorded wherever it is decided*
(`openspec/specs/agent-run-sandboxing/spec.md:321`). Round 2 read it as a constraint on what the
system may record *at all*. Measured against the shipped Hub, that reading fails immediately.
`persist_event` is called 55 times across `hub/hub`, carrying **44 distinct event types**. Exactly
one of them — `permission_denied` — is a refusal. The other 43 record things that happened and were
allowed:

```
queue_entry_delivered   question_answered      task_created       job_fired
agent_heartbeat         run_interrupted        project_adopted    message_read
checkpoint_notes_submitted   conversation_titled    loop_stopped   context_warning
```

Under round 2's reading the Hub breaches its own shipped requirement forty-three ways, and has since
the requirement was written. A reading that convicts the entire activity log is not the reading.

Three further things agree. The requirement's **title** is about the refusal record. Every other
sentence in it is about the refusal record — what triggers one, that runtime-decided refusals are
covered too, that a refusal is recorded once, that the named action is readable. And its own fourth
scenario already says the narrow thing: *"Allowed actions are not recorded **as refusals**"*. Round 2
noticed that scenario and argued past it — *"in this corpus the SHALL sentence is normative and the
scenario is evidence rather than a limit on it"*. That inverts openspec's structure, in which the
scenarios are the requirement's testable content, and it needed to be true only because the prose had
been read out of its subject.

### So the answer to round 2's own question is: the choice was never forced

Round 2 posed the question for round 3 as narrow-the-sentence versus emit-no-notification-at-all, and
called its choice a judgement rather than a derivation. It was right that it was not a derivation, and
wrong about which branch needed defending. Nothing in the corpus ever forbade the notification, so
"live only on the run row" was never the price of compliance — it would have been a straight
downgrade of the change (a record the operator never sees does not answer F115) bought to satisfy a
requirement that does not object. The notification stays, for D5's own reasons.

### What the delta should be

Not nothing. The prose and its own scenario disagree by two words, and this change is the reader that
tripped over the gap — which is the ordinary case for a clarification. So the MODIFIED delta keeps
the two words, adds one sentence saying what the paragraph is about, and stops:

> Only refusals SHALL be recorded **as refusals**. … This constrains what the refusal record may
> contain; it is not a rule about every durable event the system keeps.

Removed from round 2's version, and why:

- **The paragraph legislating "an allowed action that is not ordinary".** It wrote this change's
  policy — rare, not presented as a refusal, bounded — into a requirement about refusals. That
  couples two capabilities through a sentence neither owns, makes the refusal requirement carry a
  general rule nothing enforces, and invites the next change to argue about its edges. This change's
  own ADDED requirement is where its policy belongs.
- **The scenario *An allowed action that is not ordinary may still be recorded*.** Same reason,
  and it has moved: `agent-run-sandboxing`'s ADDED requirement now carries *The record is not a
  refusal*, which pins the same fact where the fact lives.

### The shape this is an instance of

Round 2 was right that a change can breach a shipped requirement it did not think it was near, and
right to go looking. What it did on finding a candidate was edit the corpus to fit the change. The
cheaper move was available and was not made: read the sentence against the product, and see whether
the product already breaches it. If it does, the reading is wrong — not the product, and not the
requirement.

## D10 — Two columns, one migration, and the numbers

Head is `0100` (`hub/hub/migrations/versions/0100_loop_work_needs_evidence.py`). The head assertions
to bump are `hub/tests/test_migrations.py`'s `HEAD_REVISION = "0100"` and
`hub/tests/test_project_persistence.py:227` (`assert version == "0100"`).

Round 1's tasks asked for a migration at 4.2 and another at 5.2, which would be two migrations and
two head bumps in sequence for one change. Both columns are added by this change, neither is
readable without the other, and a half-applied pair means an annotated footprint with nothing to
annotate from. One migration, `0101`, adds both.

*Corrected 2026-09-02 (night N-7).* This section was written when `0099` was head and claimed
`0100` for this change. `a-loop-declares-whether-it-needs-evidence` has since landed
`0100_loop_work_needs_evidence.py`, so `0100` is taken and both head assertions already read it.
The number here is derived from the tree, not carried forward — re-derive it again if another
migration lands before this change is implemented.

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

## D12 — The detector is structurally silent for a run whose workspace is the project root

Found in round 3, and neither round had asked. `resolve_agent_workspace` returns `repo_root` itself
on three branches (`worktrees.py:607-636`): a **read-only agent**, a **project that is not a git
repository**, and a **machine with no git at all** — the last two being deliberate degradations the
module's docstring defends at length. `resolve_turn_workspace` routes through the same function
whenever `takes_task_workspace` is false (`:651-694`), and `agent_trigger.py:891` records the
consequence in its own words: `isolated_workspace = workspace if workspace != repo_root else None`.

For such a run, `effective_work_dir` **is** the project root. The detector's boundary is then the
entire project, so nothing inside it is ever an outside write — including a write into another
agent's worktree, which is the case this change calls the worst one and the case whose record
justifies naming a destination at all.

This is not a defect to fix here, and the fix is not to invent a narrower boundary for those runs:
the record would then disagree with `Run.workspace_dir`, `AW_WORKSPACE_DIR` and `_decide`, which is
the second-boundary failure D4 exists to prevent. The record is honest — that run's workspace really
is the root.

What must not stand is the **claim of coverage**. D5 makes `[]` mean *observed, nothing left the
workspace*, and for a root-workspace run that value is simultaneously true and the least informative
sentence the product could emit: the least confined run it has, reporting a clean sheet. The
requirement now says so explicitly rather than letting a reader infer confinement from an empty list,
and it is the same discipline as the label rule in D1 — a detector that reads as coverage where it
has none is worse than none.

Partially mitigating, and only partially: a read-only agent is spawned with
`--disallowedTools Edit,Write,NotebookEdit` (`runner_commands.py:210`), so most of its write tools do
not exist. `MultiEdit` is not in that list (see D3), and neither mitigation reaches the
non-repository or no-git branches, where the agent is a full writer standing at the project root.

## D13 — The cost objection to checking every tool call is already answered

Round 2 asked round 3 to confirm that `written_paths` returns on the tool name before touching the
input, since `tool_use_event` is called for every tool of every run. It should, and it is one
membership test to write — but the premise deserves correcting rather than satisfying. By the time
`written_paths` could be called, `tool_use_event` has *already* committed to the expensive work
unconditionally (`runner_events.py:142-143`):

```python
safe_input = redact_secrets(input_data)
input_text, input_truncated = _truncate_utf8(_stringify(safe_input), MAX_TOOL_RESULT_BYTES)
```

`redact_secrets` walks the whole structure and `_stringify` is `json.dumps(..., sort_keys=True)` over
it. A tuple-membership test on a short string is not measurable beside that, on any call. Keep the
early return because it makes the function read as what it is — writers only, everything else empty —
and drop performance as the reason for it. A design that defends a cheap thing with a cost argument
invites the next reader to relax it when the cost argument stops applying.

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
5. **One migration, not two**, and the head is `0100` with two assertions to bump. See D10.
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

## Round 3 corrections, 2026-08-30

An independent re-derivation against the code, not a re-read of round 2. Six corrections, in the
order they were found. The change is still not implemented.

1. **D9's premise is false and its delta was three times too big.** *"Only refusals SHALL be
   recorded"* constrains the refusal record, not every durable event — disproved by measuring the
   product: 44 distinct `persist_event` types, one of which is a refusal. Round 2's reading convicts
   the shipped Hub 43 times. The two-word clarification stays; the paragraph legislating "allowed
   actions that are not ordinary" and its scenario are removed from `agent-run-sandboxing`'s MODIFIED
   delta, and the fact they pinned now lives in this change's own ADDED requirement. See D9.
2. **D4 omitted the step its own scenario depends on.** `_decide` joins a relative path to the
   workspace *before* `realpath` (`mcp_server.py:901`); `realpath` alone resolves against the calling
   process's cwd, and the detector's process is the Hub, which has no cwd that could be right. Round
   1's open question assumed realpath would catch it; round 2 left the question open. See D4.
3. **`.agentweave/` is not "the project".** Rounds 1 and 2 classified it as `project` and justified
   that as the destination that "sits there visibly" — while the Hub seeds that exact subtree into
   the repository's ignore rules on every turn (`repo_hygiene.py:59-80`, called first thing in
   `resolve_agent_workspace`). A new `hub` kind, and the requirement no longer rests the `project`
   case on visibility. See D4.
4. **D3 reconciled against the wrong list.** The write-tool list exists three times, not twice; the
   third (`AgentTimeline.tsx:573`) is the one whose concept matches, it includes `MultiEdit`, and
   round 2's ground for dropping `MultiEdit` was false. `runner_commands.py:210` is
   `restrict_spec_writes`, a Claude-only permissions flag that cannot contain `apply_patch`, so round
   2's proposed assertion was false by construction for the Codex half. See D3.
5. **D5 specified bounds and dedup with no accumulator and no write point**, and the precedent it
   cites fires at the run boundary — losing the whole record for a killed run, the population whose
   stray writes matter most. Accumulate in the closure, write on first sight of each destination. See
   D5.
6. **The detector is structurally silent where the workspace is the project root** — read-only
   agents, non-repository projects, machines with no git. Not a defect to fix, but the empty record
   must not read as confinement. See D12.

### What round 3 re-derived and did *not* overturn

7. **D2's one-population-site claim holds.** `kind="tool_use"` is constructed once in `hub/hub`
   (`runner_events.py:154`). Task 2.5c is answered, not conditional. The one boundary: the
   `POST .../output` ingest route accepts a `tool_use` kind from an agent the Hub did not spawn, so
   the claim covers events the Hub produces. See D2.
8. **`write_paths` is never persisted.** `record_agent_output` takes `content`, `kind`, `payload`,
   `run_id`, `sequence` and the ids, and nothing else off the event. Re-checked at its definition.
9. **`work_dir` is genuinely in scope at both sinks** — `Optional[str]` on both `_execute_run` and
   `_execute_codex_appserver_run`. The list was right; it was incomplete, because D4 also needs the
   project root, which is in neither. See D2.
10. **The premise correction from round 1 survives a third reading.**
    `DEFAULT_CLAUDE_PERMISSION_MODE = WORKSPACE_PERMISSION_MODE` (`runner_commands.py:66`), with
    `acceptEdits` as the no-approver fallback (`:73`), and `_decide` really does refuse an outside
    path on realpath + commonpath + normcase (`mcp_server.py:864-916`).
11. **The cost objection to running the extractor on every tool call is moot** — `tool_use_event`
    already redacts and JSON-serialises every input unconditionally. Keep the early return; drop the
    argument. See D13.

### For implementation

- Task 1.4 is still the first thing to run and still the stop condition: if `_decide` does not refuse
  the absolute path under the default posture, the proposal's premise is wrong and nothing should be
  built on it. Three rounds have now read that code and none has executed it.
- D12 is the one open question this change deliberately leaves: whether a run whose workspace is the
  project root should get a boundary at all is a product question about the non-repository case, and
  it is not this change's to answer.
