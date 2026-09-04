"""`RunEvent.write_paths` — one population site, reached by all three transports.

Phase 2b of `a-write-outside-the-workspace-is-recorded`. Phase 2a built `workspace_writes`
with no call site; this is the call site, and it is deliberately a single one.

**Why the field is on `RunEvent` and not on `ParsedLine`.** Round 1 of the proposal put it on
`ParsedLine`, and round 2 caught that: the Codex app-server transport never builds a
`ParsedLine` at all — `map_item_to_events` returns `List[RunEvent]` straight to its caller and
never reaches `_flush_line` (design D2). A field on `ParsedLine` would have shipped covering two
transports out of three, with two green tests to say so.

**Why there is a test per transport when only one function changed.** That single population
site *is* the claim. "None of the three transports needed a change of its own" is not provable
by reading `tool_use_event`; it is provable only by driving each transport's own entry point and
finding the field populated at the far end. The three entry points, all confirmed against the
tree on 2026-09-04:

* Claude — `parse_claude_line`'s `tool_use` block branch (`runner_parsing.py:264-272`).
* Codex `exec` — `parse_codex_line`'s **snake_case** `file_change` branch
  (`runner_parsing.py:486-499`). Round 1 named this transport nowhere.
* Codex app-server — `map_item_to_events`' **camelCase** `fileChange` branch
  (`codex_appserver.py:448-459`).

Both Codex branches hand `tool_use_event` the identical `{"changes": [...]}`, which is why one
`workspace_writes` entry covers both — asserted below rather than assumed.
"""

import ast
import json
from dataclasses import fields
from pathlib import Path

import pytest

from hub.codex_appserver import map_item_to_events
from hub.runner_events import (
    RunEvent,
    text_event,
    thinking_event,
    tool_result_event,
    tool_use_event,
)
from hub.runner_parsing import parse_claude_line, parse_codex_line

HUB_PACKAGE = Path(__file__).resolve().parents[1] / "hub"

#: An absolute path with `-` in it, so `redact_secrets` leaves it alone and a test that finds it
#: missing from `write_paths` is measuring this change rather than F278. The blob half of these
#: tests reads the payload only where that is the point.
OUTSIDE = "/tmp/not-the-workspace/stray-notes.txt"


def claude_write_line(path: str) -> str:
    """One `assistant` line carrying a `Write` block, in the shape the Claude CLI emits."""
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "Write",
                        "input": {"file_path": path, "content": "hello\n"},
                    }
                ]
            },
        }
    )


def codex_exec_file_change_line(*paths: str) -> str:
    """One `item.started` line carrying a `file_change`, in `codex exec --json`'s snake_case."""
    return json.dumps(
        {
            "type": "item.started",
            "item": {
                "type": "file_change",
                "id": "call_1",
                "changes": [{"path": path, "diff": "+x\n"} for path in paths],
            },
        }
    )


def codex_appserver_file_change_item(*paths: str) -> dict:
    """One app-server `item`, in its camelCase taxonomy. Shape copied from the live-measured
    fixtures in `test_codex_appserver.py`, `kind` included so this is the real item and not a
    reduction of it."""
    return {
        "type": "fileChange",
        "id": "call_1",
        "changes": [{"path": path, "diff": "+x\n", "kind": {"type": "add"}} for path in paths],
    }


# --- 2.4 The field itself ----------------------------------------------------------------------


def test_the_field_defaults_to_empty_on_every_other_builder():
    """2.4 — arriving on `RunEvent` must change nothing for the events that are not tool calls.

    `write_paths` defaults to `()` precisely so that `text_event`, `thinking_event`,
    `tool_result_event` and the status/diagnostic/error builders keep their existing signatures
    and their existing call sites. This asserts the default is actually reached rather than
    merely declared — a builder that started passing `write_paths=None` would satisfy the
    declaration and break every consumer expecting a tuple.
    """
    for event in (
        text_event("hi"),
        thinking_event("hmm"),
        tool_result_event(tool="Write", output="ok", call_id="toolu_01"),
    ):
        assert event.write_paths == ()

    # And a `tool_use` that is not a write: the field exists, and it is empty.
    read = tool_use_event(
        tool="Read", category="tool", input_data={"file_path": OUTSIDE}, call_id="toolu_02"
    )
    assert read.kind == "tool_use"
    assert read.write_paths == ()


def test_the_field_is_read_before_the_payload_is_redacted_and_truncated():
    """2.4 — the ordering inside `tool_use_event`, stated as behaviour rather than as source.

    Both halves were measured on 2026-09-04 and both destroy the path outright, which is why
    reading first is the design and not a nicety:

    * `redact_secrets` matches `/` inside its high-entropy class, so an ordinary POSIX path with
      a 32-character run free of `.`, `_` and `-` is replaced wholesale (filed as **F278**).
    * `json.dumps(sort_keys=True)` orders `content` before `file_path`, and the result is cut at
      `MAX_TOOL_RESULT_BYTES`. A `Write` with a body over 8 KiB therefore keeps the content and
      loses the name of the file it is writing.

    So `payload["input"]` is not a lesser copy of this field. For both of these shapes it holds
    nothing at all, and this test fails if the read is ever moved below either transformation.
    """
    redacted_away = "/workspace/project/src/services/handler.py"
    event = tool_use_event(
        tool="Write",
        category="tool",
        input_data={"file_path": redacted_away, "content": "x"},
        call_id="toolu_03",
    )
    assert event.write_paths == (redacted_away,)
    assert redacted_away not in event.payload["input"]
    assert "<redacted>" in event.payload["input"]

    big_body = "some ordinary source line - not a secret\n" * 400
    truncated = tool_use_event(
        tool="Write",
        category="tool",
        input_data={"file_path": OUTSIDE, "content": big_body},
        call_id="toolu_04",
    )
    assert truncated.write_paths == (OUTSIDE,)
    assert truncated.payload["truncated"] is True
    assert OUTSIDE not in truncated.payload["input"]


def test_the_payload_did_not_grow_a_key():
    """2.4 — the field is on the event, and *not* in the payload, because it is never persisted.

    `record_agent_output` stores `kind` and `payload` only. Adding a key here would put the
    paths in the database as a side effect of a phase whose design says they are not stored
    yet, and phase 4 would then have two records disagreeing about the same write.
    """
    event = tool_use_event(
        tool="Write", category="tool", input_data={"file_path": OUTSIDE}, call_id="toolu_05"
    )
    assert set(event.payload) == {
        "version",
        "call_id",
        "tool",
        "category",
        "input",
        "summary",
        "truncated",
    }
    assert event.write_paths == (OUTSIDE,)


# --- 2.5 One test per transport ----------------------------------------------------------------


def test_claude_transport_carries_the_path_without_a_change_of_its_own():
    """2.5 — `parse_claude_line`, driven from a real `assistant` line.

    The `tool_use` branch passes `block["input"]` straight through, so the structured input
    reaches `tool_use_event` intact and the field is populated with no edit to this branch.
    """
    parsed = parse_claude_line(claude_write_line(OUTSIDE))

    assert len(parsed.events) == 1
    event = parsed.events[0]
    assert event.kind == "tool_use"
    assert event.payload["tool"] == "Write"
    assert event.write_paths == (OUTSIDE,)


def test_codex_exec_transport_carries_every_path_in_the_patch():
    """2.5 — `parse_codex_line`'s snake_case `file_change` branch, the transport round 1 missed.

    Two changes in one patch, because the tuple return exists for exactly this: Codex names
    several destinations in a single call, and a scalar field would have silently kept the
    first and dropped the rest.
    """
    second = "/tmp/not-the-workspace/second-stray.txt"
    parsed = parse_codex_line(codex_exec_file_change_line(OUTSIDE, second))

    assert len(parsed.events) == 1
    event = parsed.events[0]
    assert event.kind == "tool_use"
    assert event.payload["tool"] == "apply_patch"
    assert event.write_paths == (OUTSIDE, second)


def test_codex_appserver_transport_carries_the_path_though_it_has_no_parsed_line():
    """2.5 — `map_item_to_events`' camelCase `fileChange` branch.

    This is design D2's whole reason: this function returns `List[RunEvent]` and never
    constructs a `ParsedLine`, so it is the transport a field on `ParsedLine` would have
    missed. Asserted here, so the reason survives as a test rather than as prose.
    """
    events = map_item_to_events(codex_appserver_file_change_item(OUTSIDE), is_start=True)

    assert len(events) == 1
    assert events[0].kind == "tool_use"
    assert events[0].payload["tool"] == "apply_patch"
    assert events[0].write_paths == (OUTSIDE,)

    # And the claim that made one `workspace_writes` entry enough for both Codex transports:
    # the two branches build the same input, so they cannot diverge in what gets extracted.
    exec_event = parse_codex_line(codex_exec_file_change_line(OUTSIDE)).events[0]
    assert events[0].write_paths == exec_event.write_paths


def test_a_completed_file_change_is_a_tool_result_and_carries_nothing():
    """2.5 — the other half of both Codex branches, which must stay empty.

    `item.completed` builds a `tool_result_event`, and a result is not a declaration of intent:
    recording the same write twice, once on the call and once on its outcome, would double
    every Codex destination in phase 4's record.
    """
    completed = parse_codex_line(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "file_change",
                    "id": "call_1",
                    "changes": [{"path": OUTSIDE, "diff": "+x\n"}],
                },
            }
        )
    )
    assert completed.events[0].kind == "tool_result"
    assert completed.events[0].write_paths == ()

    app = map_item_to_events(codex_appserver_file_change_item(OUTSIDE), is_start=False)
    assert app[0].kind == "tool_result"
    assert app[0].write_paths == ()


@pytest.mark.parametrize(
    "changes",
    [None, {}, {"changes": "not-a-list"}, {"changes": [{"path": 1}, {}, None]}],
    ids=["none", "empty", "not-a-list", "junk-elements"],
)
def test_a_malformed_codex_item_extracts_nothing_and_raises_nothing(changes):
    """2.5b's cases, driven through the transport rather than through the pure module.

    Phase 2a asserted these against `written_paths` directly. Here they go through
    `tool_use_event`, because that is where a raise would cost the whole turn's output rather
    than one path — the parser is on the live stream of a running agent.
    """
    event = tool_use_event(
        tool="apply_patch", category="file_change", input_data=changes, call_id="call_1"
    )
    assert event.write_paths == ()
    assert event.kind == "tool_use"


# --- 2.5c Exactly one construction site --------------------------------------------------------


def _tool_use_construction_sites() -> list:
    """Every `RunEvent(kind="tool_use", ...)` literal in `hub/hub`, by file and enclosing function.

    Parsed with `ast` rather than grepped, so a call spread over several lines (which is what
    the one real site became when this change added an argument to it) is still found, and a
    mention inside a docstring or a `Literal[...]` is not.

    Reported by **function name, not line number**, on purpose. The first draft of this asserted
    `("runner_events.py", 154)` and was red on its first run — against a tree where the site had
    not moved anywhere, only *down*, because the same commit's edit added lines above it. A line
    number pins where the code sits; the question here is whether a *second* site exists, and a
    name answers that without failing every time something above it grows. This repo has already
    spent four corrections this week on drifted line anchors.
    """
    sites = []
    for path in sorted(HUB_PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for parent in ast.walk(tree):
            enclosing = getattr(parent, "name", None)
            if not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(parent):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name != "RunEvent":
                    continue
                for keyword in node.keywords:
                    if (
                        keyword.arg == "kind"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value == "tool_use"
                    ):
                        sites.append((path.relative_to(HUB_PACKAGE).as_posix(), enclosing))
    return sorted(set(sites))


def test_tool_use_events_are_constructed_in_exactly_one_place():
    """2.5c — the population site is single, and this is what keeps it single.

    `write_paths` is populated inside `tool_use_event` and nowhere else. That is what lets one
    edit serve three transports, and it is also the change's only detection point: a second
    constructor elsewhere in `hub/hub` would emit `tool_use` events that no longer carry the
    field, and every test above would stay green while the coverage quietly halved. This test
    is the thing that would not.

    **The one boundary, stated rather than guarded.** `POST /api/v1/agents/{name}/output`
    accepts `kind="tool_use"` through `AgentOutputCreate` (`schemas/agents.py`'s
    `StreamEventKind`), from an agent the Hub did not spawn. That path has no `RunEvent`, no
    parser and no workspace to check a path against, so it is outside this change by
    construction rather than by omission — there is nothing there to classify a write relative
    to. It is named here so a later reader does not mistake this test for a claim that every
    stored `tool_use` row came through `tool_use_event`.
    """
    assert _tool_use_construction_sites() == [("runner_events.py", "tool_use_event")]


def test_the_only_other_run_event_fields_are_the_four_that_predate_this_change():
    """2.5c's companion — what `RunEvent` is, in one assertion, so an addition is deliberate.

    The reproduction in `test_a_write_outside_the_workspace_is_recorded.py` asserted the
    four-field set as the *before* picture and was rewritten when this field landed (that flip
    is phase 2b's, not task 4.7's, which flips 1.2 and 1.3 only). This is the *after* picture,
    and it is here rather than there because a reproduction should describe the defect, not
    track the fix.
    """
    assert {f.name for f in fields(RunEvent)} == {
        "kind",
        "content",
        "payload",
        "call_id",
        "write_paths",
    }
