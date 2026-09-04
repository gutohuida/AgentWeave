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

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import MagicMock, patch

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
# The destinations the tasks named one at a time (tasks 10.2, 10.3, 10.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_record_is_not_a_refusal_and_does_not_read_as_one(app, layout):
    """Task 10.2, against the payload rather than against the prose that describes it.

    The requirement says the record *SHALL NOT be a refusal and SHALL NOT be presented as one*:
    the action it describes was allowed, by an operator who answered for it or by a posture that
    checked nothing, and a record reading as a refusal would tell the operator the write did not
    land when it did. Two things follow, and both are asserted here.

    First, this is not the product's refusal record. That record has a name --
    `permission_denied`, which `agent_actions`, `agent_trigger` and `permissions` all write when
    a decision comes back `allowed=False` (grepped 2026-09-04; it is a literal at all three
    sites, not a shared constant) -- and this is a different event type, so nothing reading
    refusals by type picks this up.

    Second, the payload's own vocabulary. Task 8.3 requires the label to read *wrote outside the
    workspace* and never *escaped* -- because two write vectors are out of scope by construction
    (a shell redirect, a symlink inside the workspace pointing out), so a name promising
    containment would read as coverage this does not have. That check needs something to fail
    against, which is what the scan below is: every name the product chose, against the words
    that would make this a refusal or a claim of prevention.
    """
    await seed_run("run-allowed-write", "p4-writer")
    rec = recorder(
        "run-allowed-write",
        "p4-writer",
        workspace_dir=str(layout["workspace"]),
        project_root=str(layout["root"]),
    )
    await rec.watch()
    await rec.note(_write_event(layout["stray"] / "left-behind.txt"))
    await rec.flush()

    (notice,) = await notices("run-allowed-write")
    assert notice.event_type != "permission_denied", "a refusal reader must not pick this up"
    assert notice.event_type == EVENT_TYPE == "agent_wrote_outside_workspace"

    # Scanned over every name the *product* chose -- the event type, the severity, every payload
    # key, and the one payload value the recorder decides rather than copies -- because "does not
    # read as a refusal" is not provable by checking the key one happens to think of.
    #
    # The values the run supplied are deliberately excluded, and the first draft of this test is
    # why: it scanned the whole row and failed on `refus` inside pytest's own temp directory,
    # named after this test. A path, an agent name or a run id is the run's own data, and a
    # project in a directory called `denied/` is not the product presenting a refusal.
    vocabulary = " ".join(
        [
            notice.event_type,
            notice.severity,
            *notice.data.keys(),
            str(notice.data["destination_kind"]),
        ]
    ).lower()
    for word in ("refus", "denied", "blocked", "prevent", "escap", "violat", "unauthor"):
        assert word not in vocabulary, "the record reads as a refusal: " + word

    # And the write it describes really did land -- the record is of an allowed action. The
    # recorder has no opinion about permission and consults no approver: nothing here asked a
    # posture anything, and the entry exists anyway.
    (entry,) = await column_of("run-allowed-write")
    assert entry["kind"] == "outside"
    assert entry["path"] == str(layout["stray"] / "left-behind.txt")


@pytest.mark.asyncio
async def test_a_reviewer_writing_into_its_own_checkout_is_outside_its_workspace(app, tmp_path):
    """Task 10.3: the review turn, whose workspace is not the reviewer's own directory.

    A review run executes in the detached review checkout -- `.agentweave/reviews/<reviewer>`,
    which `agent_trigger` prepares through `review_turn.prepare_review_turn` -- and *not* in
    `.agentweave/worktrees/<reviewer>`. So a reviewer writing into its own agent worktree is
    writing outside the workspace it was given, and is recorded as having done so, naming itself.

    That reads odd and it is correct. A review turn's work does not belong on the reviewer's own
    branch; a file left there arrives on that branch under that agent's identity and is
    attributed by the next snapshot commit to work the reviewer was not doing. It is written down
    here so the first person to meet it finds a test that expected it rather than a surprise.

    The task checkout under review is the same story with a different kind: a reviewer writing
    into the tree it is reviewing is writing outside its own workspace, and `task` is what
    distinguishes that from the agent case.
    """
    from hub.worktrees import review_path, task_worktree_path

    reviewer = "p4-reviewer"
    root = tmp_path / "project"
    workspace = review_path(root, reviewer)
    own_worktree = worktree_path(root, reviewer)
    task_checkout = task_worktree_path(root, "task-ab12cd34ef56")
    for directory in (workspace, own_worktree, task_checkout):
        directory.mkdir(parents=True)

    await seed_run("run-review", reviewer)
    rec = recorder("run-review", reviewer, workspace_dir=str(workspace), project_root=str(root))
    await rec.watch()
    await rec.note(_write_event(workspace / "review-notes.md"))
    await rec.note(_write_event(own_worktree / "leftover.py", call_id="call-2"))
    await rec.note(_write_event(task_checkout / "patch.py", call_id="call-3"))
    await rec.flush()

    entries = await column_of("run-review")
    assert [(entry["kind"], entry["name"]) for entry in entries] == [
        ("agent", reviewer),
        ("task", "task-ab12cd34ef56"),
    ], "the review checkout itself is inside; the reviewer's own worktree is not"
    assert [entry["path"] for entry in entries] == [
        str(own_worktree / "leftover.py"),
        str(task_checkout / "patch.py"),
    ]
    assert len(await notices("run-review")) == 2


@pytest.mark.asyncio
async def test_a_run_whose_workspace_is_the_project_root_records_nothing_inside_it(app, tmp_path):
    """Task 10.5, design D12: the least confined run the product has, recorded as `[]`.

    A read-only agent, a project that is not a git repository, or a machine with no git all
    produce a run whose workspace *is* the project directory. Every path inside the project is
    then inside that run's workspace -- the tracked tree, the Hub's own subtree, and another
    agent's checkout alike -- so nothing it writes there is outside anything, and the run ends
    `[]`.

    **`[]` here means "nothing left this run's boundary", never "this run was confined."** The
    two readings are only compatible while the recorded directory is read as *where the run
    started*, which is what `workspace-isolation`'s companion requirement establishes and what
    this change's own requirement says in the paragraph beginning *A run whose workspace is the
    project's own directory is outside this requirement's reach*. This test is that paragraph's
    behaviour. Nothing in the product turns the empty list into a confinement claim, and the
    column's own comment in `models.py` says so where a reader would look.

    The control matters as much as the claim: a path outside the project *is* recorded for the
    same run. Without it this would also pass against a recorder that had stopped working.
    """
    agent = "p4-rootbound"
    root = tmp_path / "project"
    neighbour = worktree_path(root, "p4-someone-else")
    hub_dir = root / ".agentweave" / "evidence"
    tracked = root / "src"
    for directory in (neighbour, hub_dir, tracked):
        directory.mkdir(parents=True)

    await seed_run("run-rootbound", agent)
    rec = recorder("run-rootbound", agent, workspace_dir=str(root), project_root=str(root))
    await rec.watch()
    await rec.note(_write_event(tracked / "module.py"))
    await rec.note(_write_event(neighbour / "note.txt", call_id="call-2"))
    await rec.note(_write_event(hub_dir / "e-1.json", call_id="call-3"))
    await rec.flush()

    assert await column_of("run-rootbound") == [], (
        "everything inside the project is inside this run's workspace, including another "
        "agent's checkout"
    )
    assert await notices("run-rootbound") == []

    # The control. `tmp_path` is the project's parent, so a sibling of the root is genuinely
    # outside it, and this run notices -- so the empty list above is an answer, not a silence.
    stray = tmp_path / "elsewhere" / "drive-note.txt"
    stray.parent.mkdir(parents=True)
    await rec.note(_write_event(stray, call_id="call-4"))
    (entry,) = await column_of("run-rootbound")
    assert entry["kind"] == "outside"


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


# ---------------------------------------------------------------------------
# A run that is killed, and a reader that can see the result (tasks 4.4c, 4.7)
# ---------------------------------------------------------------------------


def _pty_that_stalls_after(lines, stalled: threading.Event, gate: threading.Event, pid: int = 4343):
    """A fake `PtySession` that streams *lines*, then stops talking while still alive.

    `_fake_pty` returns EOF after its lines, so a run driven with it can only be observed after
    `_execute_run`'s `finally` -- and a test built on that could not tell a record written on
    first sight from one swept at the run boundary. This one blocks instead, in the worker thread
    `pty.read` already runs in, until the test opens *gate*.

    *stalled* is set at the moment the block begins, which is a stronger signal than it looks:
    `read` is only called again once the previous chunk has been through `_flush_line`, so by the
    time the block starts, every scripted line has been fully processed and the run is making no
    further database writes of its own. The test therefore reads the row from a quiescent
    mid-turn state rather than polling into the middle of the run's own transactions -- which the
    first draft did, and which intermittently broke the run itself with a `Could not refresh
    instance` out of `record_agent_output` under concurrent SQLite sessions.

    The `wait` carries a timeout so a failing test cannot wedge the executor's worker forever;
    the test opens the gate in a `finally` regardless.
    """

    def _spawn(*args, **kwargs):
        session = MagicMock()
        session.pid = pid
        remaining = iter(lines)

        def _read(*args, **kwargs):
            try:
                return next(remaining)
            except StopIteration:
                stalled.set()
                gate.wait(timeout=10.0)
                return ""

        session.read.side_effect = _read
        session.wait.return_value = 0
        return session

    return MagicMock(side_effect=_spawn)


async def _wait_for(flag: threading.Event, what: str, timeout: float = 5.0) -> None:
    """Wait on a thread event from the loop without touching the database while the run works."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if flag.is_set():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.mark.asyncio
async def test_a_run_killed_mid_turn_keeps_the_destination_it_already_reached(
    app, auth_headers, bind_runner, tmp_path
):
    """Task 4.4c: the record survives a run that never reaches its own end.

    This is why the design refuses to follow `turn_produced_nothing`'s *timing*. That event is
    emitted from `evaluate_run_end`, and a record written there is lost entirely for a run that
    is killed or whose Hub restarts -- exactly the population whose stray writes matter most. A
    recorder-level test of the same claim already exists
    (`test_every_destination_survives_a_run_that_never_reaches_its_end`); what this adds is the
    claim through a real spawned turn.

    **The mid-turn read is the half that cannot be faked.** The fake process has stopped talking
    and has not exited, so `_execute_run` is still inside its read loop and its `finally` has not
    begun. A record swept at the boundary is simply not on the row at that moment. `calls` is 1
    there while the run has made two writes into that destination, which is the design stated as
    a measurement: the destination is durable from first sight, and the count is refreshed once
    at the end.

    **Then the run is killed** -- its background task is cancelled, which is what an event loop
    going down does to a run in flight -- and the destination and its first path are still there.
    `calls` is deliberately not asserted afterwards: it is the one field the boundary owns and
    the only one it is safe to lose.

    Deliberately **not** driven through the stop endpoint. F279 records both of this suite's
    stop-then-await tests failing intermittently on an unmodified tree (7 failures in 12,
    measured 2026-09-04), and a new test on that pattern would inherit a coin-flip red no gate
    could attribute.
    """
    import hub.api.v1.agent_trigger as agent_trigger

    agent = "p4-killed"
    stray = tmp_path.parent / "p4-outside-killed" / "left-behind.txt"
    again = tmp_path.parent / "p4-outside-killed" / "and-again.txt"
    await _sync(app, auth_headers, agent)
    await bind_runner(agent, cli="claude")

    stalled, gate = threading.Event(), threading.Event()
    lines = [write_call_line(stray), write_call_line(again, call_id="call_w2")]
    try:
        with patch(
            "hub.api.v1.agent_trigger.PtySession.spawn",
            _pty_that_stalls_after(lines, stalled, gate),
        ):
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                trigger = await app.post(
                    f"{BASE}/agent/trigger",
                    json={"agent": agent, "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert trigger.status_code == 200, trigger.text
                run_id = trigger.json()["run_id"]
                await _wait_for(stalled, "the run to finish its scripted output")

                # Mid-turn: both writes are through the sink, nothing has ended.
                (entry,) = await column_of(run_id)
                assert (entry["kind"], entry["tool"], entry["path"]) == (
                    "outside",
                    "Write",
                    str(stray),
                ), "the destination is on the row before the run ends, or not at all"
                assert entry["calls"] == 1, (
                    "written once, on first sight: the second write into the same destination "
                    "touched the run's own accumulator and nothing else"
                )
                async with async_session_factory() as db:
                    assert (await db.get(Run, run_id)).status == "running"

                # The kill.
                running = list(agent_trigger._background_runs)
                assert running, "the run's background task should still be in flight"
                for task in running:
                    task.cancel()
                gate.set()
                await asyncio.gather(*running, return_exceptions=True)
    finally:
        gate.set()

    (survivor,) = await column_of(run_id)
    assert (survivor["kind"], survivor["tool"], survivor["path"]) == (
        "outside",
        "Write",
        str(stray),
    ), "a killed run keeps the destination and the first path into it"
    (notice,) = await notices(run_id)
    assert notice.data["path"] == str(stray)


@pytest.mark.asyncio
async def test_the_timeline_reports_what_a_run_wrote_outside_its_workspace(
    app, auth_headers, bind_runner, tmp_path
):
    """Task 4.7: the column reaches a reader, through the route that already serves run facts.

    Written on the row by `OutsideWriteRecorder` and read by nobody, this record would be a
    column the product maintains and never shows. `GET /agents/{name}/timeline` is where a run's
    own facts are already served -- `RunFacts`, keyed by the run ids the returned events name --
    and the `agent_wrote_outside_workspace` event carries `run_id`, so a run whose write escaped
    is in that map by construction.

    Both readings are asserted, because only one of them is reachable through a written entry. A
    run that escaped reports its destinations; a watched, clean run reports `[]`. `None` and `[]`
    are different answers and `RunFacts` must not collapse them: a `Field(default_factory=list)`
    here would tell an operator that every run predating the detector was watched and found
    clean.
    """
    escaping, clean = "p4-timeline", "p4-timeline-clean"
    stray = tmp_path.parent / "p4-outside-timeline" / "left-behind.txt"
    runs = {}
    for agent, target in ((escaping, stray), (clean, tmp_path / "note.txt")):
        await _sync(app, auth_headers, agent)
        await bind_runner(agent, cli="claude")
        with patch(
            "hub.api.v1.agent_trigger.PtySession.spawn", _fake_pty([write_call_line(target)])
        ):
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                trigger = await app.post(
                    f"{BASE}/agent/trigger",
                    json={"agent": agent, "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert trigger.status_code == 200, trigger.text
                runs[agent] = trigger.json()["run_id"]
                await _await_background_run()

    escaped = await app.get(f"{BASE}/agents/{escaping}/timeline", headers=auth_headers)
    assert escaped.status_code == 200, escaped.text
    (reported,) = escaped.json()["runs"][runs[escaping]]["outside_workspace_writes"]
    assert (reported["kind"], reported["tool"], reported["path"]) == (
        "outside",
        "Write",
        str(stray),
    )

    quiet = await app.get(f"{BASE}/agents/{clean}/timeline", headers=auth_headers)
    assert quiet.status_code == 200, quiet.text
    assert (
        quiet.json()["runs"][runs[clean]]["outside_workspace_writes"] == []
    ), "watched and clean is `[]`, and the schema must not turn it into `None` or the reverse"
