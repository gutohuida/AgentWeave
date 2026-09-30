"""Golden-events and one-shot tests for `hub.runner_adapters` (task 1.3).

`stream_events_golden.json` and `one_shot_golden.json` were captured by
`fixtures/runner_adapters/capture_goldens.py` from today's `hub.runner_parsing.parse_claude_line`
/ `parse_codex_line`, `hub.worker.build_worker_command` and
`hub.conversation_titles.build_title_command`, before group 2 built the adapter package. This
file fails on `ModuleNotFoundError: hub.runner_adapters` until group 2 lands; that is correct per
tasks.md's ordering (goldens/tests first, group 2 second).

`claude_stream.jsonl` / `codex_exec.jsonl` are the JSONL lines inlined in
`test_runner_parsing.py`, copied in their file order.
"""

import dataclasses
import json
from pathlib import Path

import pytest

from hub.runner_adapters import get_adapter

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "runner_adapters"
STREAM_EVENTS_GOLDEN_PATH = FIXTURES_DIR / "stream_events_golden.json"
ONE_SHOT_GOLDEN_PATH = FIXTURES_DIR / "one_shot_golden.json"
CLAUDE_STREAM_JSONL = FIXTURES_DIR / "claude_stream.jsonl"
CODEX_EXEC_JSONL = FIXTURES_DIR / "codex_exec.jsonl"

with open(STREAM_EVENTS_GOLDEN_PATH, encoding="utf-8") as f:
    STREAM_EVENTS_GOLDEN = json.load(f)

with open(ONE_SHOT_GOLDEN_PATH, encoding="utf-8") as f:
    ONE_SHOT_GOLDEN = json.load(f)


def _sample_to_dict(sample):
    if sample is None:
        return None
    data = dataclasses.asdict(sample)
    # Wall-clock, not derived from the line -- see capture_goldens.py's own note.
    data.pop("observed_at", None)
    return data


def _parsed_line_to_dict(parsed):
    return {
        "events": [
            {"kind": event.kind, "content": event.content, "payload": event.payload}
            for event in parsed.events
        ],
        "usage": _sample_to_dict(parsed.usage),
        "accounting": _sample_to_dict(parsed.accounting),
        "session_id": parsed.session_id,
    }


def _case_ids(cases):
    return [case["id"] for case in cases]


@pytest.mark.parametrize("case", STREAM_EVENTS_GOLDEN, ids=_case_ids(STREAM_EVENTS_GOLDEN))
def test_map_events_matches_golden(case):
    lines_path = CLAUDE_STREAM_JSONL if case["runner"] == "claude" else CODEX_EXEC_JSONL
    lines = lines_path.read_text(encoding="utf-8").splitlines()
    line = lines[case["line_index"]]

    adapter = get_adapter(case["runner"])
    assert adapter is not None
    transport = adapter.stream_transport()
    assert transport is not None

    model = "gpt-5.5" if case["runner"] == "codex" else None
    parsed = transport.map_events(line, model=model)
    actual = _parsed_line_to_dict(parsed)

    assert actual == {
        "events": case["events"],
        "usage": case["usage"],
        "accounting": case["accounting"],
        "session_id": case["session_id"],
    }


def test_stream_events_golden_file_covers_both_runners():
    runners = {case["runner"] for case in STREAM_EVENTS_GOLDEN}
    assert runners == {"claude", "codex"}


@pytest.mark.parametrize("case", ONE_SHOT_GOLDEN, ids=_case_ids(ONE_SHOT_GOLDEN))
def test_one_shot_matches_golden(case):
    adapter = get_adapter(case["input"]["cli"])
    assert adapter is not None

    kwargs = {"model": case["input"]["model"], "prompt": case["input"]["prompt"]}
    if case["kind"] == "worker":
        kwargs["output_schema_path"] = case["input"]["output_schema_path"]
    argv = adapter.one_shot(case["kind"], **kwargs)

    assert argv == case["argv"]


def test_one_shot_golden_covers_both_kinds_and_runners():
    kinds = {case["kind"] for case in ONE_SHOT_GOLDEN}
    runners = {case["input"]["cli"] for case in ONE_SHOT_GOLDEN}
    assert kinds == {"worker", "title"}
    assert runners == {"claude", "codex"}
