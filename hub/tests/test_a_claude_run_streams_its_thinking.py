"""F578: a Claude run streams its thinking text.

The CLI sends thinking blocks with empty text unless the `showThinkingSummaries` setting is on
(measured 2026-10-17, CLI 2.1.301: Haiku 4.5 sent 0 characters without it and 336 with it). The
Hub passes it as a settings *file*, never inline JSON, because a JSON argument's quotes do not
survive a Windows `.cmd` shim (F549).
"""

import json
from pathlib import Path

from hub.runner_adapters import build_command


def test_every_claude_run_asks_for_thinking_summaries_through_a_settings_file():
    for kwargs in ({}, {"yolo": True}, {"session_id": "s-1"}):
        cmd = build_command(runner="claude", cli="claude", prompt="hi", **kwargs)
        assert cmd.count("--settings") == 1
        path = Path(cmd[cmd.index("--settings") + 1])
        assert path.is_file(), path
        assert json.loads(path.read_text(encoding="utf-8")) == {"showThinkingSummaries": True}
        assert '"' not in cmd[cmd.index("--settings") + 1]


def test_a_thinking_block_with_text_is_recorded():
    from hub.runner_parsing import parse_claude_line

    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "thinking", "thinking": "First, 17*20 = 340.", "signature": "x"}
                ]
            },
        }
    )
    events = parse_claude_line(line).events
    assert any("thinking" in str(e) and "340" in str(e) for e in events), events


def _assistant(*blocks):
    return json.dumps({"type": "assistant", "message": {"content": list(blocks)}})


def test_a_thinking_block_without_text_is_recorded_as_hidden_reasoning():
    """vis-D10: Claude 5.x sends a signed thinking block with no text (Haiku 5.5, CLI 2.1.301);
    the conversation says the agent reasoned rather than showing nothing."""
    from hub.runner_parsing import parse_claude_line

    for block in (
        {"type": "thinking", "thinking": "", "signature": "EqQBCkYI..."},
        {"type": "redacted_thinking", "data": "EmwKAhgBEgy..."},
    ):
        events = parse_claude_line(_assistant(block)).events
        assert [e.kind for e in events] == ["thinking"], (block, events)
        assert events[0].content == ""
        assert events[0].payload["hidden"] is True


def test_a_thinking_block_with_text_is_not_hidden():
    from hub.runner_parsing import parse_claude_line

    events = parse_claude_line(
        _assistant({"type": "thinking", "thinking": "Plan it.", "signature": "x"})
    ).events
    assert "hidden" not in events[0].payload
