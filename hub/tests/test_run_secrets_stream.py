"""F488: a registered value is removed from a run's recorded text even when two or more `text` /
`thinking` events split it (`a-secret-split-across-two-events-is-still-scrubbed`, design D1, D7).

Unit cases on `run_secrets.scrub_stream`, one per row of design D1's prototype table. The order
each case feeds is an order a runner emits; the cases driven through the real Copilot mapper and
the real executors are in `test_copilot_byok_env.py` and `test_agent_trigger.py`.
"""

from __future__ import annotations

import pytest

from hub import run_secrets
from hub.runner_events import (
    error_event,
    text_event,
    thinking_event,
    tool_result_event,
    tool_use_event,
)

KEY = "plainproxykey123"
RUN = "run-f488-unit"


@pytest.fixture(autouse=True)
def _registered():
    run_secrets.register(RUN, [KEY])
    yield
    run_secrets.forget(RUN)


def _tool_use():
    return tool_use_event(
        tool="Shell", category="execute", input_data={"command": "ls"}, call_id="c1"
    )


def _tool_result():
    return tool_result_event(tool="Shell", output="a.txt", call_id="c1")


def _scrubbed(events, run_id=RUN):
    out = [run_secrets.scrub_stream(run_id, event) for event in events]
    for event in out:
        if event.kind in ("text", "thinking"):
            assert event.payload["text"] == event.content
    return out


def _texts(events):
    return [(e.kind, e.content) for e in events if e.kind in ("text", "thinking")]


ROWS = {
    "thought-message": (
        [thinking_event("I will use plainproxy"), text_event("key123 now.")],
        [("thinking", "I will use <redacted>"), ("text", "<redacted> now.")],
    ),
    "message-tool-message": (
        [text_event("Key: plainproxy"), _tool_use(), _tool_result(), text_event("key123 done")],
        [("text", "Key: <redacted>"), ("text", "<redacted> done")],
    ),
    "message-thought-at-5": (
        [text_event("plain"), thinking_event("proxykey123 hmm")],
        [("text", "plain"), ("thinking", "<redacted> hmm")],
    ),
    "message-finish-dangling": (
        [text_event("the key starts plainproxyk")],
        [("text", "the key starts <redacted>")],
    ),
    "three-way": (
        [thinking_event("x plain"), text_event("proxy"), thinking_event("key123 y")],
        [("thinking", "x plain"), ("text", "<redacted>"), ("thinking", "<redacted> y")],
    ),
    "false-positive": (
        [thinking_event("Let me explai"), text_event("n this.")],
        [("thinking", "Let me explai"), ("text", "n this.")],
    ),
    "thought-ending-in-whitespace": (
        [thinking_event("I will use plainproxy\n\n"), text_event("key123 now.")],
        [("thinking", "I will use <redacted>\n\n"), ("text", "<redacted> now.")],
    ),
    "thought-starting-with-whitespace": (
        [text_event("Key: plainpr"), thinking_event("\n oxykey123 hmm")],
        [("text", "Key: plainpr"), ("thinking", "\n <redacted> hmm")],
    ),
}


@pytest.mark.parametrize("case", list(ROWS))
def test_a_value_split_across_events_is_redacted_as_design_d1_tabulates(case):
    events, expected = ROWS[case]
    assert _texts(_scrubbed(events)) == expected


def test_other_kinds_are_returned_unchanged_and_do_not_move_the_tail():
    use, result = _tool_use(), _tool_result()
    error = error_event(code="copilot.unknown", message="zzzzzzzzzzzzzzzzzzzzzzzz")
    out = _scrubbed([text_event("a plainpr"), use, result, error, text_event("oxykey123 b")])
    assert out[1] is use and out[2] is result and out[3] is error
    assert _texts(out) == [("text", "a plainpr"), ("text", "<redacted> b")]


def test_a_value_contained_in_a_longer_one_is_replaced_whole_once():
    run_secrets.register("run-f488-nested", [KEY, "proxykey"])
    try:
        out = _scrubbed([text_event("k=plainproxykey123!")], run_id="run-f488-nested")
        assert out[0].content == "k=<redacted>!"
        out = _scrubbed(
            [thinking_event("k=plainprox"), text_event("ykey123 and proxykey")],
            run_id="run-f488-nested",
        )
        assert _texts(out) == [("thinking", "k=<redacted>"), ("text", "<redacted> and <redacted>")]
    finally:
        run_secrets.forget("run-f488-nested")


def test_forget_drops_the_tail_so_a_new_registration_does_not_join_across_it():
    _scrubbed([text_event("a plainpr")])
    run_secrets.forget(RUN)
    assert RUN not in run_secrets._tail_by_run
    run_secrets.register(RUN, [KEY])
    assert _texts(_scrubbed([text_event("oxykey123 b")])) == [("text", "oxykey123 b")]


def test_a_late_call_after_forget_creates_no_state():
    run_secrets.forget(RUN)
    event = text_event("a plainproxy")
    assert run_secrets.scrub_stream(RUN, event) is event
    assert RUN not in run_secrets._tail_by_run


def test_a_run_with_nothing_registered_is_recorded_exactly_as_emitted():
    """Control (1.6): no state, the very same event objects."""
    events = [thinking_event("I will use plainproxy\n\n"), text_event("key123 now.")]
    out = [run_secrets.scrub_stream("run-f488-none", event) for event in events]
    assert all(a is b for a, b in zip(out, events, strict=True))
    assert "run-f488-none" not in run_secrets._tail_by_run


def test_reversing_the_emitted_order_changes_the_rows():
    """1.3's second half: the expected rows depend on the order the mapper emits, so a fixture in
    an order no runner produces would not stand in for it."""
    forward = _texts(
        _scrubbed([thinking_event("I will use plainpr"), text_event("oxykey123 now.")])
    )
    run_secrets.forget(RUN)
    run_secrets.register(RUN, [KEY])
    backward = _texts(
        _scrubbed([text_event("oxykey123 now."), thinking_event("I will use plainpr")])
    )
    assert forward == [("thinking", "I will use plainpr"), ("text", "<redacted> now.")]
    assert sorted(backward) != sorted(forward)


# Design D7: registration strips each value (review 2026-10-04).


def test_a_value_registered_with_surrounding_whitespace_is_matched_without_it():
    run_secrets.register("run-f488-strip", [KEY + "\n"])
    try:
        assert run_secrets.scrub("run-f488-strip", "use plainproxykey123 now") == (
            "use <redacted> now"
        )
        out = _scrubbed([text_event("use plainproxykey123 now")], run_id="run-f488-strip")
        assert out[0].content == "use <redacted> now"
        # The raw value is still replaced where it occurs as written.
        assert run_secrets.scrub("run-f488-strip", "raw plainproxykey123\n end") == (
            "raw <redacted> end"
        )
    finally:
        run_secrets.forget("run-f488-strip")


def test_a_whitespace_only_value_registers_nothing():
    run_secrets.register("run-f488-blank", ["  \n", "\t"])
    assert run_secrets.registered("run-f488-blank") == ()
