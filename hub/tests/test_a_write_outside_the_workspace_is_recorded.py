"""F115: a file tool writes outside the run's workspace and nothing anywhere says so.

A run executes in a directory the Hub chose for it -- an agent's own checkout under
`.agentweave/worktrees/<agent>`, a task's checkout, a review checkout, or the project root. A
`Write` naming an absolute path somewhere else is a write the product has no record of: the path
survives only inside the tool call's stringified `input` blob, alongside every other argument of
every other call, and nothing distinguishes "wrote into its own workspace" from "wrote into a
second agent's workspace" from "wrote into a directory outside the project".

**This file is the reproduction, and it is written to become the gate on the fix.** Every test
here passed against unmodified code first -- that is what makes the change's behaviour claim a
measurement rather than an inference from reading the source. Tests 1.1, 1.2 and 1.3 are written
to flip in phase 4: the parsed event will carry the paths structurally, the run will carry the
record, and the cross-worktree case will name the *other* agent's workspace by kind and name.

Test 1.4 is not written to flip, and is not really a test of this change at all -- it is the
change's **premise**, pinned. F115 says that "in the posture an operator is most likely to be
running, nothing shows the path and nothing constrains it", and round 1 of the proposal
contradicted that from reading `mcp_server._decide`: the default posture for a non-yolo Claude run
is `workspace`, which routes every call through the approver, which refuses a path outside
`AW_WORKSPACE_DIR`. Rounds 2 and 3 both inherited that correction without executing it, and
`design.md`'s own *For implementation* section says so. Everything this change claims about
*where* the gap is rests on that refusal being real, so it is asserted here rather than argued in
a document. The gap is not that the default posture is blind; it is that an outside-the-workspace
write leaves no trace in any posture where it is possible.
"""

import json
import os
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, List

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput, Conversation, EventLog, Run
from hub.mcp_server import _decide
from hub.model_catalog import WORKSPACE_PERMISSION_MODE
from hub.output_recording import record_agent_output
from hub.runner_commands import DEFAULT_CLAUDE_PERMISSION_MODE
from hub.runner_events import RunEvent
from hub.runner_parsing import parse_claude_line
from hub.worktrees import worktree_path

PROJECT = "proj-test"
WRITER = "f115-writer"
NEIGHBOUR = "f115-neighbour"
SESSION = "sess-f115"

#: Every key `tool_use_event` puts in a `tool_use` payload today (`runner_events.py:145-153`).
#: Asserted as a set rather than by picking at individual keys: what 1.1 is measuring is that
#: *nothing* in the record says where the path pointed, and only an exhaustive comparison says
#: that. Phase 2 adds `write_paths` to `RunEvent`, not to this payload -- the field is never
#: persisted -- so this set is expected to survive the fix unchanged.
TOOL_USE_PAYLOAD_KEYS = {
    "version",
    "call_id",
    "tool",
    "category",
    "input",
    "summary",
    "truncated",
}


@dataclass(frozen=True)
class Layout:
    """One project, two agent checkouts under it, and one directory outside it entirely.

    The three destinations F115 cannot tell apart. `.agentweave/worktrees/<agent>` is
    `worktrees.worktree_path`'s real layout, not an invented one, so the paths below are the
    shapes the classifier in phase 3 will have to recognise.
    """

    root: Path
    workspace: Path
    neighbour: Path
    stray: Path

    @property
    def inside_file(self) -> Path:
        return self.workspace / "note.txt"

    @property
    def neighbour_file(self) -> Path:
        return self.neighbour / "note.txt"

    @property
    def stray_file(self) -> Path:
        return self.stray / "drive-note.txt"


@pytest.fixture()
def layout(tmp_path) -> Layout:
    root = tmp_path / "project"
    workspace = worktree_path(root, WRITER)
    neighbour = worktree_path(root, NEIGHBOUR)
    stray = tmp_path / "elsewhere"
    for directory in (workspace, neighbour, stray):
        directory.mkdir(parents=True)
    return Layout(root=root, workspace=workspace, neighbour=neighbour, stray=stray)


def write_call_line(path: Path, *, call_id: str = "call_w1") -> str:
    """One `assistant` line of Claude's `stream-json`, carrying a `Write` at *path*.

    The shape `test_runner_parsing.py`'s `CLAUDE_TOOL_USE_LINE` uses, with a `Write` in place of
    its `Bash` and an absolute `file_path` -- which is what F115 reproduced live, on
    `run-72de0f5c6898`.
    """
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "id": "msg_01f115",
                "model": "claude-haiku-4-5-20251001",
                "content": [
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": "Write",
                        "input": {
                            "file_path": str(path),
                            "content": "left behind by a run nothing was watching\n",
                        },
                    }
                ],
            },
            "session_id": SESSION,
        }
    )


async def seed_run(run_id: str, agent: str, workspace: Path) -> None:
    """A run the Hub owns, executing in *workspace* -- `Run.workspace_dir` as spawn writes it."""
    async with async_session_factory() as db:
        db.add(Conversation(id=f"conv-{run_id}", project_id=PROJECT, agent=agent, lifecycle="open"))
        db.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent=agent,
                conversation_id=f"conv-{run_id}",
                session_id=SESSION,
                status="running",
                workspace_dir=str(workspace),
            )
        )
        await db.commit()


async def record_turn(run_id: str, agent: str, line: str) -> None:
    """Mirror `_flush_line`'s per-event loop (`agent_trigger.py:1981-1996`).

    Parse, then one `record_agent_output` per event with an incrementing sequence. That call is
    the *only* per-event write on that path -- the surrounding block writes nothing else unless
    the line binds a provider session or conflicts with one, and this line does neither -- so a
    turn reproduced here records exactly what a spawned turn records.
    """
    parsed = parse_claude_line(line)
    # `_flush_line` carries `sequence` as a `nonlocal` across lines; one line is one call here, so
    # `enumerate` from 1 produces the identical values without the mutable counter.
    for sequence, event in enumerate(parsed.events, start=1):
        async with async_session_factory() as db:
            await record_agent_output(
                db,
                PROJECT,
                agent,
                content=event.content,
                session_id=SESSION,
                conversation_id=f"conv-{run_id}",
                kind=event.kind,
                payload=event.payload,
                run_id=run_id,
                sequence=sequence,
            )


async def outputs_for(run_id: str) -> List[AgentOutput]:
    async with async_session_factory() as db:
        result = await db.execute(
            select(AgentOutput).where(AgentOutput.run_id == run_id).order_by(AgentOutput.sequence)
        )
        return list(result.scalars())


async def all_events() -> List[EventLog]:
    async with async_session_factory() as db:
        result = await db.execute(select(EventLog).order_by(EventLog.timestamp))
        return list(result.scalars())


def flatten_slashes(text: str) -> str:
    """Collapse every run of backslashes to one forward slash.

    A Windows path is stored at two different escaping depths in the same row: `payload["input"]`
    is itself a JSON document, so the path inside it already carries `\\\\`, and dumping the
    payload to search it escapes those again. Rather than guess the depth at each call site --
    which is how the first draft of this file managed to assert that a path present in the
    database was absent -- both sides of every comparison are flattened. A POSIX path is
    unaffected.
    """
    return re.sub(r"\\+", "/", text)


def mentions(value: Any, path: Path) -> bool:
    """Does *value* name *path* anywhere inside it, at any depth and any escaping?"""
    return flatten_slashes(str(path)) in flatten_slashes(json.dumps(value, ensure_ascii=False))


# --- 1.1 The parse side ------------------------------------------------------------------------


def test_the_parsed_event_says_nothing_about_where_the_write_went(layout):
    """1.1 -- what `parse_claude_line` knows about a write. **Half-flipped by phase 2b.**

    As written in phase 1 this asserted two separate things: that the path survives only as text
    inside `payload["input"]`, and that nothing structural carries it -- `RunEvent` had four
    fields and none was about paths. Phase 2b (2026-09-04) falsified the second, deliberately and
    on the rehearsed schedule: `write_paths` now arrives on the event, populated inside
    `tool_use_event` *before* the redact and the 8 KiB truncation.

    The flip is recorded here rather than in phase 4 because **task 4.7 does not cover it** --
    4.7 flips tasks 1.2 and 1.3, the record-side pair, and 1.1 is the parse side. Checked rather
    than assumed when the field landed.

    What survives unfixed, and is what this test now measures:

    * The **payload** -- the only part `record_agent_output` persists -- is byte-for-byte what it
      was. The destination is still a substring of a stringified argument dump, indistinguishable
      from a `pattern` argument or a URL, and still nothing says it was outside anything.
    * `write_paths` reaches nobody. It is carried on an in-process event that is written to the
      database as `kind` and `payload` only, so it survives exactly as long as the function call
      that consumes it -- and phase 2 adds no consumer. That is the gap phases 3 and 4 close, and
      until they do, F115 stands with the field in place.
    """
    parsed = parse_claude_line(write_call_line(layout.stray_file))

    assert len(parsed.events) == 1
    event = parsed.events[0]
    assert event.kind == "tool_use"
    assert event.payload["tool"] == "Write"

    # The path is in the payload -- but only as text inside the argument dump.
    blob = event.payload["input"]
    assert isinstance(blob, str)
    assert json.loads(blob)["file_path"] == str(layout.stray_file)

    # Phase 2b: it is now *also* carried structurally. Asserted here, not merely noted, so this
    # test states the tree it is running against rather than the tree it was written against.
    assert {field.name for field in fields(RunEvent)} == {
        "kind",
        "content",
        "payload",
        "call_id",
        "write_paths",
    }
    assert event.write_paths == (str(layout.stray_file),)

    # And that changes nothing about what is *stored*: the payload has not grown a key, so the
    # structured path cannot reach any reader of the row. Exhaustive, because "nothing says" is
    # not provable by checking the keys one happens to think of.
    assert set(event.payload) == TOOL_USE_PAYLOAD_KEYS
    assert event.content == "Called Write"
    assert event.payload["summary"] == "Called Write"
    assert event.payload["category"] == "tool"


# --- 1.2 The record side -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_run_records_nothing_about_an_outside_write(app, layout):
    """1.2 -- the same call against a run whose workspace is known, and still nothing.

    The run's `workspace_dir` is its own agent checkout and the write lands outside the project
    entirely, so every value needed to notice is on the row. Today the turn produces one
    `AgentOutput` and no event at all: the path exists exactly once in the database, inside the
    blob 1.1 measured.

    Phase 4 flips this -- `Run.outside_workspace_writes`, and one `agent_wrote_outside_workspace`
    event per distinct destination.
    """
    run_id = "run-f115-outside"
    await seed_run(run_id, WRITER, layout.workspace)
    await record_turn(run_id, WRITER, write_call_line(layout.stray_file))

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        # This was `not hasattr(...)` -- deliberately stronger than `is None`, because when 1.2
        # was written there was no column at all. Migration `0101` added it (night N-17) and
        # turned this line red without anything noticing, since that iteration ran only the
        # migration and column-enumerating suites. Narrowed to `is None` on 2026-09-04 rather
        # than deleted: `NULL` is the column's own word for *not observed*, so the reproduction
        # still says exactly what it said -- nothing watched this turn. **Task 4.7 owns the real
        # flip**, which asserts the record exists and is driven through the sink rather than
        # through this file's hand-rolled mirror of it.
        assert run.outside_workspace_writes is None

    rows = await outputs_for(run_id)
    assert [row.kind for row in rows] == ["tool_use"]

    events = await all_events()
    assert [event.event_type for event in events] == []

    # The one appearance of the destination anywhere the operator's product can read.
    appearances = [row.id for row in rows if mentions(row.payload, layout.stray_file)]
    assert appearances == [rows[0].id]
    assert not any(mentions(event.data, layout.stray_file) for event in events)


# --- 1.3 The cross-worktree shape --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_write_into_another_agents_workspace_looks_identical(app, layout):
    """1.3 -- the case whose whole meaning is the destination, and the destination is what is lost.

    A stray file in a temp directory is untidy. A write into
    `.agentweave/worktrees/<other-agent>` is work appearing on another agent's branch, under
    another agent's identity, attributed to them by every snapshot commit that follows --
    proposal.md's "launders work through the wrong identity". The product's record of the two is
    the same record.

    Asserted by normalisation rather than by listing fields: both turns are recorded, the
    destination path is replaced by a placeholder in each, and what is left must be
    byte-identical. That is what "nothing distinguishes them" means, and it fails the moment phase
    4 gives either one a record the other does not have.
    """
    stray_run, neighbour_run = "run-f115-stray", "run-f115-neighbour"
    await seed_run(stray_run, WRITER, layout.workspace)
    await seed_run(neighbour_run, WRITER, layout.workspace)
    await record_turn(stray_run, WRITER, write_call_line(layout.stray_file))
    await record_turn(neighbour_run, WRITER, write_call_line(layout.neighbour_file))

    def normalised(rows: List[AgentOutput], destination: Path) -> str:
        dumped = json.dumps(
            [{"kind": row.kind, "content": row.content, "payload": row.payload} for row in rows],
            sort_keys=True,
            ensure_ascii=False,
        )
        return flatten_slashes(dumped).replace(flatten_slashes(str(destination)), "<DESTINATION>")

    stray_rows = await outputs_for(stray_run)
    neighbour_rows = await outputs_for(neighbour_run)
    assert mentions(stray_rows[0].payload, layout.stray_file)
    assert mentions(neighbour_rows[0].payload, layout.neighbour_file)
    assert normalised(stray_rows, layout.stray_file) == normalised(
        neighbour_rows, layout.neighbour_file
    )

    # And neither run says anything about a workspace it does not own. Narrowed from
    # `not hasattr(...)` to `is None` on 2026-09-04 for the reason given in 1.2 above.
    for run_id in (stray_run, neighbour_run):
        async with async_session_factory() as db:
            assert (await db.get(Run, run_id)).outside_workspace_writes is None
    assert [event.event_type for event in await all_events()] == []
    assert NEIGHBOUR not in normalised(neighbour_rows, layout.neighbour_file)


# --- 1.4 The premise, not a behaviour this change changes --------------------------------------


def test_the_default_posture_refuses_the_same_path(layout, monkeypatch):
    """1.4 -- the stop condition. If this fails, the proposal's round-1 correction is wrong.

    `DEFAULT_CLAUDE_PERMISSION_MODE` is `workspace` (`runner_commands.py:66`), the posture in
    which the Hub itself answers `--permission-prompt-tool` through
    `mcp_server.approve_tool_call`, and `_decide` compares each declared path argument against
    `AW_WORKSPACE_DIR` on `realpath` + `commonpath` + `normcase`. So the write F115 reproduced
    *is* refused by default -- both when it lands outside the project and when it lands in a
    second agent's checkout, which the sibling assertion is here for: `.agentweave/worktrees/` is
    a shared parent, and a decision built on a string prefix rather than on path components would
    let a neighbour's checkout through.

    The run that actually escaped was `manual`, where the operator approved a card that named the
    tool and the full absolute path. This change does not touch `_decide` and does not change any
    posture's decisions; it makes the postures where such a write *is* possible stop being silent.
    """
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(layout.workspace))
    # No run credential: `_report_decision` fails internally and must be swallowed, so this also
    # exercises the decision-reached-anyway path, as `test_permission_approver.py` does.
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)

    assert DEFAULT_CLAUDE_PERMISSION_MODE == WORKSPACE_PERMISSION_MODE

    for destination in (layout.stray_file, layout.neighbour_file):
        decision = _decide("Write", {"file_path": str(destination)})
        assert decision["allow"] is False, f"{destination} was allowed under the default posture"
        assert repr(str(destination)) in decision["reason"]
        assert "outside your workspace" in decision["reason"]

    # The control: the same tool, inside the run's own checkout, is allowed. Without it the two
    # assertions above would also pass against a `_decide` that refused everything.
    assert _decide("Write", {"file_path": str(layout.inside_file)})["allow"] is True

    # And the relative form resolves against the workspace, not against the Hub's cwd -- the
    # distinction task 3.2 turns on. `_decide` gets this right because it *is* the spawned server,
    # whose cwd is the run's workspace; asserted here from a cwd that is not.
    assert os.path.realpath(os.getcwd()) != os.path.realpath(str(layout.workspace))
    assert _decide("Write", {"file_path": "note.txt"})["allow"] is True
