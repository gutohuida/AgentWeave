"""Phase 4 of `a-write-outside-the-workspace-is-recorded`: the record, and the two sinks.

Phase 1 reproduced F115 -- a `Write` to an absolute path outside the run's workspace lands, and
nothing anywhere says where it went. Phase 3 built the classifier. This is the wiring: one
recorder, called from both event sinks, writing `Run.outside_workspace_writes` and one
`agent_wrote_outside_workspace` activity event on the *first* sighting of each destination.

Two halves, deliberately:

* **The recorder on its own** -- shape, bounds, the once-per-destination rule, and the
  never-kill-a-turn wrap. These construct `OutsideWriteRecorder` directly, because the
  interesting inputs (a write into another agent's checkout, twenty-five distinct destinations,
  a classifier that raises) are awkward to provoke through a spawned turn and trivial here.

* **Both sinks, driven through a real turn** -- `_fake_pty` for Claude and `_fake_run_turn` for
  the Codex app-server transport, the same fakes `test_a_turn_says_how_it_ended.py` uses to drive
  both spawn paths. These are what make the wiring claim true rather than plausible: a recorder
  that works and is called from nowhere passes every test in the first half. Deleting either
  `note` call from `agent_trigger.py` turns exactly one of them red, and deleting the `watch`
  call turns a third red -- measured, not assumed.
"""

import json
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import patch

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Conversation, EventLog, Run
from hub.outside_write_record import EVENT_TYPE, MAX_DESTINATIONS, OutsideWriteRecorder
from hub.runner_events import tool_use_event
from hub.workspace_writes import WriteLocation
from hub.worktrees import worktree_path

# The same fakes phase 2 of `a-turn-says-how-it-ended` drives both spawn paths with. Imported
# rather than re-declared, which is the convention this suite already follows.
from tests.test_agent_trigger import (
    _await_background_run,
    _bind_codex_app_server_runner,
    _fake_pty,
    _fake_run_turn,
)

PROJECT = "proj-test"
BASE = f"/api/v1/projects/{PROJECT}"
SESSION = "sess-p4"


def _write_event(path: Path, *, tool: str = "Write", call_id: str = "call-1"):
    """One `tool_use` `RunEvent` declaring a write at *path* -- `write_paths` populated for real.

    Built through `tool_use_event` rather than by hand: `write_paths` is derived inside it from
    the structured input, and a hand-built `RunEvent` would prove the recorder against a field
    the product does not necessarily populate the same way.

    The two providers name their path in different places -- Claude at `file_path`, Codex under
    `changes[].path` -- and the input is shaped per tool here for the same reason: a Codex event
    carrying `file_path` would extract nothing, so a test written that way would assert against
    an event no runner produces.
    """
    if tool == "apply_patch":
        input_data: Any = {"changes": [{"path": str(path), "diff": "@@\n+x\n"}]}
    else:
        input_data = {"file_path": str(path), "content": "x\n"}
    return tool_use_event(
        tool=tool,
        category="write",
        input_data=input_data,
        call_id=call_id,
    )


def write_call_line(path: Path, *, call_id: str = "call_w1") -> str:
    """One `assistant` line of Claude's `stream-json` carrying a `Write` at *path*.

    Phase 1's helper, restated here rather than imported so the two files can diverge: phase 1's
    is bound to that file's own session id and agents, and 4.7 will rewrite its assertions.
    """
    return (
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_01p4",
                    "model": "claude-haiku-4-5-20251001",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": call_id,
                            "name": "Write",
                            "input": {"file_path": str(path), "content": "stray\n"},
                        }
                    ],
                },
                "session_id": SESSION,
            }
        )
        + "\n"
    )


async def seed_run(run_id: str, agent: str) -> None:
    async with async_session_factory() as db:
        db.add(Conversation(id=f"conv-{run_id}", project_id=PROJECT, agent=agent, lifecycle="open"))
        db.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent=agent,
                conversation_id=f"conv-{run_id}",
                status="running",
            )
        )
        await db.commit()


async def column_of(run_id: str) -> Any:
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        return run.outside_workspace_writes


async def notices(run_id: str) -> List[EventLog]:
    """Every `agent_wrote_outside_workspace` row naming *run_id*, oldest first."""
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(
            select(EventLog)
            .where(EventLog.event_type == EVENT_TYPE)
            .order_by(EventLog.timestamp, EventLog.id)
        )
        return [row for row in result.scalars() if (row.data or {}).get("run_id") == run_id]


def recorder(
    run_id: str,
    agent: str,
    *,
    workspace_dir: Optional[str],
    project_root: Optional[str],
) -> OutsideWriteRecorder:
    return OutsideWriteRecorder(
        project_id=PROJECT,
        agent=agent,
        run_id=run_id,
        workspace_dir=workspace_dir,
        project_root=project_root,
    )


@pytest.fixture()
def layout(tmp_path):
    """A project root, this run's own checkout under it, a neighbour's, and one stray directory.

    `worktree_path` is `worktrees.py`'s real layout rather than an invented one, so `agent` is a
    kind the classifier reaches the same way it will in production.
    """
    root = tmp_path / "project"
    workspace = worktree_path(root, "p4-writer")
    neighbour = worktree_path(root, "p4-neighbour")
    stray = tmp_path / "elsewhere"
    for directory in (workspace, neighbour, stray):
        directory.mkdir(parents=True)
    return {"root": root, "workspace": workspace, "neighbour": neighbour, "stray": stray}


# ---------------------------------------------------------------------------
# The recorder on its own
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_watched_run_that_writes_nothing_outside_ends_as_an_empty_list(app, layout):
    """Task 4.1's `[]`, reached. *Observed, and nothing left the workspace.*

    The distinction between `NULL` and `[]` is the whole value of the column, and it is only
    true if something writes `[]`. Recording on first sight alone would leave every clean run
    `NULL` -- indistinguishable from a run that predates the detector.
    """
    await seed_run("run-clean", "p4-writer")
    rec = recorder(
        "run-clean",
        "p4-writer",
        workspace_dir=str(layout["workspace"]),
        project_root=str(layout["root"]),
    )

    await rec.watch()
    await rec.note(_write_event(layout["workspace"] / "note.txt"))
    await rec.flush()

    assert await column_of("run-clean") == [], "a watched run with no escape reads as []"
    assert await notices("run-clean") == [], "nothing escaped, so the operator is told nothing"


@pytest.mark.asyncio
async def test_a_run_whose_workspace_cannot_be_resolved_is_left_null(app, layout):
    """`NULL` means *nobody was looking*, and an unresolvable workspace is exactly that.

    The honest answer for a run with no recorded workspace is not `[]` -- that would claim it
    was watched and found clean -- and it is not an `outside` entry either, which would accuse
    it of something nobody could establish.
    """
    await seed_run("run-blind", "p4-writer")
    rec = recorder("run-blind", "p4-writer", workspace_dir=None, project_root=str(layout["root"]))
    assert rec.watching is False

    await rec.watch()
    await rec.note(_write_event(layout["stray"] / "note.txt"))
    await rec.flush()

    assert await column_of("run-blind") is None, "an unwatched run stays NULL, never []"
    assert await notices("run-blind") == []


@pytest.mark.asyncio
async def test_one_outside_write_lands_one_entry_and_one_warn_event(app, layout):
    """Tasks 4.4 and 4.5 together: the durable record and the operator's notice, one each.

    They name the same tool and the same path deliberately -- the column is the fact later reads
    consult and the event is what the operator sees, and the two describing different writes
    would be a disagreement about one instant that nothing downstream could resolve.
    """
    await seed_run("run-stray", "p4-writer")
    stray_file = layout["stray"] / "drive-note.txt"
    rec = recorder(
        "run-stray",
        "p4-writer",
        workspace_dir=str(layout["workspace"]),
        project_root=str(layout["root"]),
    )

    await rec.watch()
    await rec.note(_write_event(stray_file))

    assert await column_of("run-stray") == [
        {
            "kind": "outside",
            "name": None,
            "tool": "Write",
            "path": str(stray_file),
            "calls": 1,
        }
    ]

    (notice,) = await notices("run-stray")
    assert notice.severity == "warn"
    assert notice.agent == "p4-writer"
    assert notice.data["tool"] == "Write"
    assert notice.data["path"] == str(stray_file)
    assert notice.data["destination_kind"] == "outside"
    assert notice.data["destination_name"] is None
    assert notice.data["workspace_dir"] == str(layout["workspace"])


@pytest.mark.asyncio
async def test_a_write_into_another_agents_checkout_names_that_agent(app, layout):
    """The case whose whole meaning is *which* workspace -- F115's cross-worktree write.

    `outside` would be true and useless here: the destination is another agent's checkout under
    this same project, and the record has to say whose.
    """
    await seed_run("run-neighbour", "p4-writer")
    neighbour_file = layout["neighbour"] / "note.txt"
    rec = recorder(
        "run-neighbour",
        "p4-writer",
        workspace_dir=str(layout["workspace"]),
        project_root=str(layout["root"]),
    )

    await rec.watch()
    await rec.note(_write_event(neighbour_file))

    (entry,) = await column_of("run-neighbour")
    assert (entry["kind"], entry["name"]) == ("agent", "p4-neighbour")
    (notice,) = await notices("run-neighbour")
    assert notice.data["destination_name"] == "p4-neighbour"


@pytest.mark.asyncio
async def test_a_second_write_to_a_recorded_destination_adds_no_row_and_no_event(app, layout):
    """Task 4.5's *once per distinct destination per run*, and 4.4b's counter.

    An agent that writes forty files into the operator's checkout is one fact told forty times;
    forty `warn` rows would be the noise `note_turn_that_produced_nothing` explicitly refuses to
    create. The count still moves, and `flush` is what makes it exact.
    """
    await seed_run("run-repeat", "p4-writer")
    rec = recorder(
        "run-repeat",
        "p4-writer",
        workspace_dir=str(layout["workspace"]),
        project_root=str(layout["root"]),
    )

    await rec.watch()
    first = layout["stray"] / "one.txt"
    await rec.note(_write_event(first))
    await rec.note(_write_event(layout["stray"] / "two.txt", call_id="call-2"))
    await rec.note(_write_event(layout["stray"] / "three.txt", call_id="call-3"))

    assert len(await notices("run-repeat")) == 1, "one destination, one notice"
    (mid,) = await column_of("run-repeat")
    assert mid["path"] == str(first), "the record keeps the *first* path into the destination"

    await rec.flush()
    (entry,) = await column_of("run-repeat")
    assert entry["calls"] == 3, "the per-destination count is exact once the run ends"
    assert entry["path"] == str(first)
    assert len(await notices("run-repeat")) == 1


@pytest.mark.asyncio
async def test_every_destination_survives_a_run_that_never_reaches_its_end(app, layout):
    """Design D5's reason for writing on first sight rather than at the run boundary.

    No `flush` at all here -- the shape of a killed run, or of a Hub that restarted mid-turn.
    Both destinations and both first paths are already on the row; only the exact counts are
    lost, which is the one field the design says is safe to lose.
    """
    await seed_run("run-killed", "p4-writer")
    rec = recorder(
        "run-killed",
        "p4-writer",
        workspace_dir=str(layout["workspace"]),
        project_root=str(layout["root"]),
    )

    await rec.watch()
    await rec.note(_write_event(layout["stray"] / "a.txt"))
    await rec.note(_write_event(layout["neighbour"] / "b.txt", call_id="call-2"))
    await rec.note(_write_event(layout["stray"] / "c.txt", call_id="call-3"))

    recorded = await column_of("run-killed")
    assert [(e["kind"], e["name"]) for e in recorded] == [
        ("outside", None),
        ("agent", "p4-neighbour"),
    ]
    assert len(await notices("run-killed")) == 2, "one notice per distinct destination"


@pytest.mark.asyncio
async def test_beyond_the_bound_the_list_ends_with_one_overflow_record(app, layout):
    """Task 4.4's bound, and the shape decision it forced.

    "20 entries plus a total count" and `[] == observed and nothing escaped` pull in opposite
    directions -- a count beside the list makes the empty case an object, and `[]` stops being
    literally true. The resolution is a final element of a different shape, carrying `kind` like
    every other element so one loop reads the whole list.
    """
    await seed_run("run-many", "p4-writer")
    rec = recorder(
        "run-many",
        "p4-writer",
        workspace_dir=str(layout["workspace"]),
        project_root=str(layout["root"]),
    )

    await rec.watch()
    for index in range(MAX_DESTINATIONS + 5):
        target = worktree_path(layout["root"], f"p4-n{index:02d}") / "note.txt"
        await rec.note(_write_event(target, call_id=f"call-{index}"))

    recorded = await column_of("run-many")
    assert len(recorded) == MAX_DESTINATIONS + 1
    assert recorded[-1] == {"kind": "overflow", "destinations": 5}
    assert all(entry["kind"] == "agent" for entry in recorded[:-1])
    assert (
        len(await notices("run-many")) == MAX_DESTINATIONS
    ), "the twenty-first destination is counted, not described -- and not announced either"


@pytest.mark.asyncio
async def test_a_classification_nobody_could_make_is_not_recorded_as_an_escape(app, layout):
    """`unknown` is not `outside`, and this is the assertion that keeps it that way.

    `classify` returns `unknown` when it cannot establish where a path went. Entering that in a
    column whose entries mean "this left the workspace", under an event named
    `agent_wrote_outside_workspace`, would turn *nobody could tell* into an accusation.
    """
    await seed_run("run-unknown", "p4-writer")
    rec = recorder(
        "run-unknown",
        "p4-writer",
        workspace_dir=str(layout["workspace"]),
        project_root=str(layout["root"]),
    )

    await rec.watch()
    with patch("hub.outside_write_record.classify", return_value=WriteLocation("unknown")):
        await rec.note(_write_event(layout["stray"] / "note.txt"))

    assert await column_of("run-unknown") == [], "watched, and nothing it could call an escape"
    assert await notices("run-unknown") == []


@pytest.mark.asyncio
async def test_recording_that_fails_never_reaches_the_turn(app, layout):
    """Task 4.6. A run that dies because a path could not be classified is the worse outcome.

    Wrapped on the same terms `mcp_server._report_decision` states of itself: observational, and
    never able to change or delay what it observes. The wrap is *tested* rather than merely
    written -- an `except Exception` around the wrong span looks identical in review.
    """
    await seed_run("run-broken", "p4-writer")
    rec = recorder(
        "run-broken",
        "p4-writer",
        workspace_dir=str(layout["workspace"]),
        project_root=str(layout["root"]),
    )
    await rec.watch()

    with patch(
        "hub.outside_write_record.classify", side_effect=RuntimeError("classifier exploded")
    ):
        await rec.note(_write_event(layout["stray"] / "note.txt"))

    assert await column_of("run-broken") == [], "the failure changed nothing and raised nothing"

    with patch(
        "hub.outside_write_record.async_session_factory", side_effect=RuntimeError("db gone")
    ):
        await rec.watch()
        await rec.note(_write_event(layout["stray"] / "note.txt"))
        await rec.flush()


# ---------------------------------------------------------------------------
# Both sinks, driven through a real turn
# ---------------------------------------------------------------------------


async def _sync(app, auth_headers, agent: str, runner: str = "claude") -> None:
    response = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {agent: {"runner": runner}}}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_a_claude_turn_that_writes_outside_its_workspace_records_it(
    app, auth_headers, bind_runner, tmp_path
):
    """Task 4.3a, driven: `_flush_line` is wired to the recorder.

    The turn is real -- `POST /agent/trigger`, the background task, `_execute_run`, the parser --
    and only the process is a fake. `tmp_path` is what the suite resolves as both this project's
    root and this run's working directory, so a sibling of it is genuinely outside both.
    """
    agent = "p4-claude"
    stray = tmp_path.parent / "p4-outside" / "left-behind.txt"
    again = tmp_path.parent / "p4-outside" / "and-again.txt"
    await _sync(app, auth_headers, agent)
    await bind_runner(agent, cli="claude")

    lines = [
        write_call_line(stray),
        write_call_line(again, call_id="call_w2"),
    ]
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", _fake_pty(lines)):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            trigger = await app.post(
                f"{BASE}/agent/trigger",
                json={"agent": agent, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert trigger.status_code == 200, trigger.text
            run_id = trigger.json()["run_id"]
            await _await_background_run()

    (entry,) = await column_of(run_id)
    assert entry["kind"] == "outside"
    assert entry["tool"] == "Write"
    assert entry["path"] == str(stray), "the first path into the destination, not the last"
    # Two writes, one destination, one notice -- and a count that only reaches 2 because the
    # run's end flushed it. Asserted here rather than only in the recorder's own tests: `flush`
    # is wired into a `finally` block, and a `finally` is exactly where a call gets dropped.
    assert entry["calls"] == 2
    (notice,) = await notices(run_id)
    assert notice.severity == "warn"
    assert notice.data["agent"] == agent


@pytest.mark.asyncio
async def test_a_claude_turn_that_stays_inside_ends_watched_and_clean(
    app, auth_headers, bind_runner, tmp_path
):
    """The other half of the same wiring: `watch` fires, and an inside write is not an escape.

    Without the `watch` call in `_execute_run` this run would end `NULL` and be
    indistinguishable from one that ran before the detector existed.
    """
    agent = "p4-claude-clean"
    inside = tmp_path / "note.txt"
    await _sync(app, auth_headers, agent)
    await bind_runner(agent, cli="claude")

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", _fake_pty([write_call_line(inside)])):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            trigger = await app.post(
                f"{BASE}/agent/trigger",
                json={"agent": agent, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            run_id = trigger.json()["run_id"]
            await _await_background_run()

    assert await column_of(run_id) == [], "watched, and nothing left the workspace"
    assert await notices(run_id) == []


@pytest.mark.asyncio
async def test_a_turn_writing_into_a_neighbours_checkout_names_it_because_the_root_arrived(
    app, auth_headers, bind_runner, tmp_path, monkeypatch
):
    """Task 4.3, driven: the project root reaches the recorder, and it is what makes this case.

    Every other driven test here would pass with `repo_root=None`. A path outside the workspace
    and outside the project classifies `outside` either way, so none of them can tell whether
    the parameter added in 4.3 arrives at all.

    This one can. The run executes in its own checkout under the project root and writes into
    another agent's checkout beside it -- inside the project, outside the workspace. With the
    root, that is `agent`/`p4-neighbour-live`; without it, the classifier stops at "not inside
    this workspace" and says `outside`, which is true and useless.
    """
    import hub.worktrees as worktrees

    agent = "p4-rooted"
    workspace = worktree_path(tmp_path, agent)
    neighbour = worktree_path(tmp_path, "p4-neighbour-live")
    for directory in (workspace, neighbour):
        directory.mkdir(parents=True)
    monkeypatch.setattr(
        worktrees, "resolve_agent_workspace", lambda repo_root, name, config: workspace
    )

    await _sync(app, auth_headers, agent)
    await bind_runner(agent, cli="claude")

    line = write_call_line(neighbour / "note.txt")
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", _fake_pty([line])):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            trigger = await app.post(
                f"{BASE}/agent/trigger",
                json={"agent": agent, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert trigger.status_code == 200, trigger.text
            run_id = trigger.json()["run_id"]
            await _await_background_run()

    (entry,) = await column_of(run_id)
    assert (entry["kind"], entry["name"]) == ("agent", "p4-neighbour-live"), (
        "the record names whose checkout it was; `outside` here means the project root never "
        "reached `_execute_run`"
    )
    (notice,) = await notices(run_id)
    assert notice.data["destination_name"] == "p4-neighbour-live"


@pytest.mark.asyncio
async def test_a_codex_app_server_turn_records_it_the_same_way(app, auth_headers, tmp_path):
    """Task 4.3b, driven: the transport that never reaches `_flush_line`.

    `map_item_to_events` hands `_on_event` its events directly, so a recorder wired only into
    `_flush_line` would cover two transports of three and this run would end `[]` -- watched,
    and wrongly clean. That is the exact failure this test exists to catch.
    """
    agent = "p4-codex"
    stray = tmp_path.parent / "p4-outside-codex" / "left-behind.txt"
    await _sync(app, auth_headers, agent, runner="codex")
    await _bind_codex_app_server_runner(app, auth_headers)(agent)

    fake = _fake_run_turn(events=[_write_event(stray, tool="apply_patch")])
    with patch("hub.api.v1.agent_trigger.codex_run_turn", fake):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
            trigger = await app.post(
                f"{BASE}/agent/trigger",
                json={"agent": agent, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert trigger.status_code == 200, trigger.text
            run_id = trigger.json()["run_id"]
            await _await_background_run()

    (entry,) = await column_of(run_id)
    assert entry["kind"] == "outside"
    assert entry["path"] == str(stray)
    (notice,) = await notices(run_id)
    assert notice.data["run_id"] == run_id
