"""F578: a Claude run streams its thinking text.

The CLI sends thinking blocks with empty text unless asked for summaries. The
`showThinkingSummaries` setting does it for Haiku 4.5 only (2026-10-17, CLI 2.1.301: 0 characters
without it, 336 with it); on 5.5 models it sends nothing. `--thinking-display summarized` does it
for both (research 2026-10-10 on 2.1.291; re-measured 2026-10-18 on 2.1.301: Haiku 5.5 0 -> 199
characters with the setting on, Haiku 4.5 858 with the flag alone).
"""

import json

from hub.runner_adapters import build_command


def test_every_claude_run_asks_for_summarized_thinking():
    for kwargs in ({}, {"yolo": True}, {"session_id": "s-1"}):
        cmd = build_command(runner="claude", cli="claude", prompt="hi", **kwargs)
        assert cmd.count("--thinking-display") == 1
        assert cmd[cmd.index("--thinking-display") + 1] == "summarized"
        # The settings-file route it replaces asked 5.5 models for nothing they sent.
        assert "--settings" not in cmd


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
