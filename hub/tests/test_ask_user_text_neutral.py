"""`ask_user`'s static text no longer points an exploring turn at the tool (F545).

Change `an-exploring-turn-asks-its-questions-in-its-reply`, requirement `tool-text-neutral`. The
description named "writing a specification step by step" as the one reason to ask one question per
call, which sent the exploring turn to the tool the turn context says not to use. Static text
reaches every turn, so the clause goes, in both renderings, and the bundled spec charter says where
an exploring turn's questions go.
"""

import asyncio
from pathlib import Path

from hub.api.v1.agents import _tool_surface_lines
from hub.mcp_server import mcp

CHARTER = Path(__file__).parent.parent / "hub" / "data" / "charters" / "spec.md"


def _mcp_description() -> str:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    return tools["ask_user"].description


def test_the_mcp_description_does_not_name_writing_a_specification():
    text = _mcp_description().lower()
    assert "specification" not in text
    assert "one question per call" not in text


def test_the_surface_rendering_does_not_name_writing_a_specification():
    text = "\n".join(_tool_surface_lines()).lower()
    assert "specification step by step" not in text
    assert "one question per call" not in text


def test_the_charter_says_exploring_questions_are_asked_in_the_reply():
    charter = " ".join(CHARTER.read_text(encoding="utf-8").split()).lower()
    assert "while a document is being explored" in charter
    assert "ask your questions in your reply" in charter
