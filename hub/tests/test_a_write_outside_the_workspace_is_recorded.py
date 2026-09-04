"""F115: a file tool writes outside the run's workspace and nothing anywhere says so.

A run executes in a directory the Hub chose for it -- an agent's own checkout under
`.agentweave/worktrees/<agent>`, a task's checkout, a review checkout, or the project root. A
`Write` naming an absolute path somewhere else is a write the product has no record of: the path
survives only inside the tool call's stringified `input` blob, alongside every other argument of
every other call, and nothing distinguishes "wrote into its own workspace" from "wrote into a
second agent's workspace" from "wrote into a directory outside the project".

**This file is the reproduction, and it is now the gate on the fix.** Every test here passed
against unmodified code first -- that is what makes the change's behaviour claim a measurement
rather than an inference from reading the source. Tests 1.1, 1.2 and 1.3 were written to flip in
phase 4, and all three have: the parsed event carries the paths structurally (1.1, flipped by
phase 2b), the run carries the record (1.2), and the cross-worktree case names the *other*
agent's workspace by kind and name (1.3).

What did **not** flip is everything each test says about the *transcript*. The `tool_use` payload
is byte-for-byte what it was, and the two turns 1.3 compares are still indistinguishable in it.
That is deliberate and is asserted rather than dropped: the fix is a record beside the transcript,
not a change to it, so a future change that starts putting classified paths into the payload
should have to come here and say so.

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
from unittest.mock import patch

import pytest
from sqlalchemy import select

import hub.worktrees as worktrees
from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput, EventLog, Run
from hub.mcp_server import _decide
from hub.model_catalog import WORKSPACE_PERMISSION_MODE, permission_mode_values
from hub.runner_commands import DEFAULT_CLAUDE_PERMISSION_MODE
from hub.runner_events import RunEvent
from hub.runner_parsing import parse_claude_line
from hub.worktrees import worktree_path

# The fake spawn `test_agent_trigger.py` drives the Claude path with, imported rather than
# re-declared -- the convention this suite already follows. Tasks 1.2 and 1.3 are driven through
# a real turn rather than through a local mirror of `_flush_line`; see `drive` below.
from tests.test_agent_trigger import _await_background_run, _fake_pty

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
    """The three destinations, laid out under the root the suite resolves for this project.

    `root` is `tmp_path` itself and not a directory beneath it, because `conftest`'s
    `_default_project_workspace` resolves every project id to this test's own `tmp_path` -- so
    that, and nothing else, is what a driven turn's classifier will compare against. Tasks 1.2
    and 1.3 are driven turns (see `drive`), and a layout rooted anywhere else would put every
    path outside the project and quietly collapse the `agent` case into the `outside` one.

    `stray` is therefore a sibling of the root rather than a child of it. Shared between tests in
    a session, hence `exist_ok`; nothing is ever written into it.
    """
    root = tmp_path
    workspace = worktree_path(root, WRITER)
    neighbour = worktree_path(root, NEIGHBOUR)
    stray = tmp_path.parent / "f115-elsewhere"
    for directory in (workspace, neighbour, stray):
        directory.mkdir(parents=True, exist_ok=True)
    return Layout(root=root, workspace=workspace, neighbour=neighbour, stray=stray)


def write_call_line(path: Path, *, call_id: str = "call_w1", session_id: str = SESSION) -> str:
    """One `assistant` line of Claude's `stream-json`, carrying a `Write` at *path*.

    The shape `test_runner_parsing.py`'s `CLAUDE_TOOL_USE_LINE` uses, with a `Write` in place of
    its `Bash` and an absolute `file_path` -- which is what F115 reproduced live, on
    `run-72de0f5c6898`.

    *session_id* is a parameter because two driven turns for one agent are two conversations, and
    a provider session id is unique per project and agent: 1.3 drives two and would otherwise
    fail on that constraint rather than on anything it is about.
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
            "session_id": session_id,
        }
    )


async def prepare(app, auth_headers, bind_runner, agent: str) -> None:
    """Register *agent* and bind it a Claude runner. Once per agent, not once per turn."""
    sync = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {agent: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(agent, cli="claude")


async def drive(app, auth_headers, agent: str, destination: Path, *, session_id=SESSION) -> str:
    """Run one real turn for *agent* whose only tool call is a `Write` at *destination*.

    **This replaced a local mirror of `_flush_line` when phase 4 landed, and the replacement is
    the point.** Tasks 1.2 and 1.3 assert what the *product* records about a turn, and until
    phase 4 nothing recorded anything, so a hand-rolled loop that called `record_agent_output`
    the way `_flush_line` does was an adequate stand-in for a turn: the claim was that the
    database ends up empty, and an empty database is easy to reproduce. Once there is a record,
    the mirror stops being adequate -- it does not call `OutsideWriteRecorder` and could not, so
    a flipped assertion written against it would have measured a copy of the product rather than
    the product, and would have passed just as happily with the wiring deleted from
    `agent_trigger.py`.

    So this goes through `POST /agent/trigger`, the background task, `_execute_run`, the real
    parser and both of `_flush_line`'s writes, with only the spawned process faked.
    """
    line = write_call_line(destination, session_id=session_id)
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", _fake_pty([line])):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            trigger = await app.post(
                f"/api/v1/projects/{PROJECT}/agent/trigger",
                json={"agent": agent, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert trigger.status_code == 200, trigger.text
            run_id = trigger.json()["run_id"]
            await _await_background_run()
    return run_id


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
async def test_the_run_records_the_outside_write(
    app, auth_headers, bind_runner, layout, monkeypatch
):
    """1.2 -- **flipped by phase 4 (task 4.7).** The same call, and now the run says where it went.

    The run's `workspace_dir` is its own agent checkout and the write lands outside the project
    entirely, so every value needed to notice is on the row. As reproduced, the turn produced one
    `AgentOutput` and no event at all, and the path existed exactly once in the database, inside
    the blob 1.1 measured. It now produces the same `AgentOutput`, *plus* a record on the run and
    one `agent_wrote_outside_workspace` event.

    **Driven through a real turn, which is the flip's whole cost.** As a reproduction this test
    used a local mirror of `_flush_line`, and that was adequate while the assertion was that the
    database stays empty. It is not adequate for asserting a record exists: the mirror does not
    call `OutsideWriteRecorder`, so an assertion written against it would pass with the wiring in
    `agent_trigger.py` deleted -- the exact failure mode this repository keeps producing. The
    alternative, teaching the mirror to call the recorder, would have been cheaper and would have
    tested the mirror. See `drive`.

    The three things that did *not* change are asserted too, because the fix is a record beside
    the transcript rather than a change to it: the payload still holds the path only as text
    inside the argument dump, the destination still appears exactly once among the output rows,
    and `write_paths` still reaches no persisted column.
    """
    monkeypatch.setattr(
        worktrees, "resolve_agent_workspace", lambda repo_root, name, config: layout.workspace
    )
    await prepare(app, auth_headers, bind_runner, WRITER)
    run_id = await drive(app, auth_headers, WRITER, layout.stray_file)

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        # Was `not hasattr(...)`, then `is None` between migration `0101` and the wiring landing.
        # Now the record itself. `name` is `None` because a path belonging to no workspace has no
        # *which one* to answer -- `outside` is the whole answer, and the field is present rather
        # than absent so one loop reads every entry the same way.
        assert run.workspace_dir == str(layout.workspace)
        assert run.outside_workspace_writes == [
            {
                "kind": "outside",
                "name": None,
                "tool": "Write",
                "path": str(layout.stray_file),
                "calls": 1,
            }
        ]

    events = await all_events()
    (notice,) = [event for event in events if event.event_type == "agent_wrote_outside_workspace"]
    assert notice.severity == "warn"
    assert notice.agent == WRITER
    assert notice.data["destination_kind"] == "outside"
    assert notice.data["path"] == str(layout.stray_file)
    assert notice.data["workspace_dir"] == str(layout.workspace)

    # And the transcript is unchanged. One `tool_use` row, the destination in it exactly once,
    # and still only inside the stringified argument dump.
    rows = await outputs_for(run_id)
    tool_rows = [row for row in rows if row.kind == "tool_use"]
    assert [row.payload["tool"] for row in tool_rows] == ["Write"]
    assert set(tool_rows[0].payload) == TOOL_USE_PAYLOAD_KEYS
    appearances = [row.id for row in rows if mentions(row.payload, layout.stray_file)]
    assert appearances == [tool_rows[0].id]


# --- 1.3 The cross-worktree shape --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_write_into_another_agents_workspace_is_named_as_theirs(
    app, auth_headers, bind_runner, layout, monkeypatch
):
    """1.3 -- **flipped by phase 4 (task 4.7).** The case whose whole meaning is the destination.

    A stray file in a temp directory is untidy. A write into
    `.agentweave/worktrees/<other-agent>` is work appearing on another agent's branch, under
    another agent's identity, attributed to them by every snapshot commit that follows --
    proposal.md's "launders work through the wrong identity". As reproduced, the product's record
    of the two was the same record.

    **Both halves are asserted, and they now say opposite things.** The transcript still cannot
    tell them apart: normalise the two turns' output rows by replacing the destination path with
    a placeholder, and what is left is byte-identical. That has not been fixed and is not being
    fixed -- the payload is unchanged by design. What changed is beside it: one run records
    `outside` with no name, the other records `agent`/`f115-neighbour`, and only the second names
    a workspace that belongs to somebody.

    The normalisation is the assertion that would break first if a later change started putting
    classified paths into the payload -- at which point this test should be revisited rather than
    relaxed.
    """
    monkeypatch.setattr(
        worktrees, "resolve_agent_workspace", lambda repo_root, name, config: layout.workspace
    )
    await prepare(app, auth_headers, bind_runner, WRITER)
    stray_run = await drive(
        app, auth_headers, WRITER, layout.stray_file, session_id=f"{SESSION}-stray"
    )
    neighbour_run = await drive(
        app, auth_headers, WRITER, layout.neighbour_file, session_id=f"{SESSION}-neighbour"
    )

    def normalised(rows: List[AgentOutput], destination: Path) -> str:
        dumped = json.dumps(
            [{"kind": row.kind, "content": row.content, "payload": row.payload} for row in rows],
            sort_keys=True,
            ensure_ascii=False,
        )
        return flatten_slashes(dumped).replace(flatten_slashes(str(destination)), "<DESTINATION>")

    stray_rows = [row for row in await outputs_for(stray_run) if row.kind == "tool_use"]
    neighbour_rows = [row for row in await outputs_for(neighbour_run) if row.kind == "tool_use"]
    assert mentions(stray_rows[0].payload, layout.stray_file)
    assert mentions(neighbour_rows[0].payload, layout.neighbour_file)
    assert normalised(stray_rows, layout.stray_file) == normalised(
        neighbour_rows, layout.neighbour_file
    ), "the transcript still cannot distinguish the two, and that is not what phase 4 changed"
    assert NEIGHBOUR not in normalised(neighbour_rows, layout.neighbour_file)

    # Beside it, the record -- and it distinguishes them by kind and by name.
    async with async_session_factory() as db:
        (stray_entry,) = (await db.get(Run, stray_run)).outside_workspace_writes
        (neighbour_entry,) = (await db.get(Run, neighbour_run)).outside_workspace_writes
    assert (stray_entry["kind"], stray_entry["name"]) == ("outside", None)
    assert (neighbour_entry["kind"], neighbour_entry["name"]) == ("agent", NEIGHBOUR)
    assert neighbour_entry["path"] == str(layout.neighbour_file)

    notices = [
        event for event in await all_events() if event.event_type == "agent_wrote_outside_workspace"
    ]
    assert [event.data["destination_name"] for event in notices] == [None, NEIGHBOUR]


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


# --------------------------------------------------------------------------------------
# Phase 7 -- the postures are documented, per posture, by what they check.
# --------------------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
POSTURES_DOC = REPO_ROOT / "docs" / "reference" / "permission-postures.md"

#: Every posture the model catalog offers an operator, and the phrase the documentation has to
#: reach a verdict with for each. Built from the catalog rather than restated, so a fifth posture
#: shipping with no documented verdict fails here rather than being documented by omission.
_EXPECTED_VERDICTS = {
    "workspace": "Checked by the Hub",
    "manual": "Put to you",
    "acceptEdits": "Not checked",
    "bypassPermissions": "Not checked",
}


def _postures_doc() -> str:
    if not (REPO_ROOT / "mkdocs.yml").exists():  # pragma: no cover - not a source checkout
        pytest.skip("documentation is not present in this environment")
    assert POSTURES_DOC.exists(), f"{POSTURES_DOC} is missing"
    return POSTURES_DOC.read_text(encoding="utf-8")


def test_every_posture_is_documented_by_what_it_checks():
    """7.1 -- each posture states whether a file write is checked against the run's workspace.

    Read off `permission_mode_values()` rather than from a list written here: the requirement is
    about *the postures the product offers*, so a posture added to the catalog and not to the page
    is exactly the failure this asserts, and a list restated in the test would not notice it.
    """
    text = _postures_doc()
    offered = {value.id for value in permission_mode_values()}
    assert offered == set(_EXPECTED_VERDICTS), (
        "the catalog's postures and the documented ones have diverged: "
        f"{sorted(offered)} vs {sorted(_EXPECTED_VERDICTS)}"
    )
    for posture, verdict in _EXPECTED_VERDICTS.items():
        row = next((line for line in text.splitlines() if f"`{posture}`" in line), None)
        assert row is not None, f"{posture} is not documented"
        assert verdict in row, f"{posture} is documented without saying whether writes are checked"

    # The default is part of the answer, not a footnote: an operator who never touches the pill is
    # running `workspace`, and the page would be misread without it.
    assert DEFAULT_CLAUDE_PERMISSION_MODE == WORKSPACE_PERMISSION_MODE
    assert "**Workspace only**" in text


def test_the_documentation_says_the_workspace_is_not_a_wall():
    """7.2 -- the three sentences the requirement names, each present."""
    text = _postures_doc()
    for sentence in (
        "working directory, not a wall",
        "you are the boundary",
        "recorded rather than prevented",
    ):
        assert sentence in text.lower() or sentence in text, f"missing: {sentence}"


def test_containment_is_not_claimed_or_denied_for_a_mode():
    """7.3 -- the prohibition, both halves.

    Round 1's correction is the reason this is a test and not a note. "Native mode does not
    confine" is the sentence a reader reaches for, and it is false for the default posture; its
    mirror image ("native mode confines") is false for the two postures that check nothing. The
    scan is for the *claims*, not for the word "native" -- the page is allowed to discuss the
    subject, and does.
    """
    lowered = _postures_doc().lower()
    for claim in (
        "native mode does not confine",
        "native execution does not confine",
        "native does not confine",
        "native mode confines",
        "native execution confines",
    ):
        assert claim not in lowered, f"the page makes the prohibited claim: {claim!r}"


def test_the_postures_page_is_published():
    """A page absent from the nav is not documentation; it is a file in the repository."""
    if not (REPO_ROOT / "mkdocs.yml").exists():  # pragma: no cover - not a source checkout
        pytest.skip("documentation is not present in this environment")
    nav = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "reference/permission-postures.md" in nav
