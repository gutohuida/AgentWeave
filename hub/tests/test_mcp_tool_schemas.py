"""The MCP tool schema must advertise every constrained parameter's valid values.

A bare `str` parameter tells a client nothing. Codex agents repeatedly guessed
`message_type="text"`, were rejected 422, and only succeeded on a retry; Claude agents happened
to omit the parameter and so never hit it. The fix is the schema, not documentation
(`2026-08-06-agent-permissions-tool-schemas-and-base-knowledge`).
"""

import asyncio
import typing

import pytest

from hub import mcp_server
from hub.schemas.messages import _MESSAGE_TYPES
from hub.schemas.tasks import _PRIORITIES, _TASK_STATUSES


def _schemas():
    """Every tool's generated input schema, keyed by tool name.

    This is the schema an MCP client actually receives, so asserting on it is what proves the
    fix reaches Claude and Codex rather than merely existing in the source.
    """
    tools = asyncio.run(mcp_server.mcp.list_tools())
    return {tool.name: tool.parameters for tool in tools}


def _enum_for(schema, parameter):
    """The declared enum for *parameter*, resolving a `$ref`/`anyOf` wrapper if present."""
    prop = schema["properties"][parameter]
    if "enum" in prop:
        return prop["enum"]
    defs = schema.get("$defs", {})
    for candidate in (prop, *prop.get("anyOf", [])):
        ref = candidate.get("$ref", "")
        if ref.startswith("#/$defs/"):
            target = defs.get(ref.split("/")[-1], {})
            if "enum" in target:
                return target["enum"]
    return None


@pytest.mark.parametrize(
    "tool_name,parameter,expected",
    [
        ("send_message", "message_type", _MESSAGE_TYPES),
        ("create_task", "priority", _PRIORITIES),
        ("update_task", "status", _TASK_STATUSES),
        ("create_job", "session_mode", ["new", "resume"]),
    ],
)
def test_constrained_parameter_declares_its_values(tool_name, parameter, expected):
    schema = _schemas()[tool_name]
    declared = _enum_for(schema, parameter)
    assert declared is not None, f"{tool_name}.{parameter} advertises no enum"
    assert sorted(declared) == sorted(expected)


@pytest.mark.parametrize(
    "alias,runtime",
    [
        (mcp_server.MessageType, _MESSAGE_TYPES),
        (mcp_server.TaskStatus, _TASK_STATUSES),
        (mcp_server.TaskPriority, _PRIORITIES),
    ],
)
def test_alias_agrees_with_the_validator_it_mirrors(alias, runtime):
    """The Literal is restated rather than imported (mcp_server.py stays standalone), so this
    is what stops the two drifting apart."""
    assert sorted(typing.get_args(alias)) == sorted(runtime)


def test_update_task_status_is_required_and_therefore_must_be_discoverable():
    """`status` has no default, so a model must supply one of eight states blind."""
    schema = _schemas()["update_task"]
    assert "status" in schema.get("required", [])
    assert _enum_for(schema, "status") is not None


class TestReadableDetail:
    """A rejection an agent can act on, rather than a stringified list of Pydantic dicts."""

    def test_validation_error_becomes_a_sentence(self):
        detail = mcp_server._readable_detail(
            [
                {
                    "type": "value_error",
                    "loc": ["body", "type"],
                    "msg": "Value error, type must be one of ['message', 'delegation']",
                    "input": "text",
                    "ctx": {"error": {}},
                }
            ]
        )
        assert detail == "type: type must be one of ['message', 'delegation']"
        for noise in ("value_error", "'loc'", "ctx"):
            assert noise not in detail

    def test_several_errors_are_joined(self):
        detail = mcp_server._readable_detail(
            [
                {"loc": ["body", "type"], "msg": "bad type"},
                {"loc": ["body", "recipient"], "msg": "bad recipient"},
            ]
        )
        assert detail == "type: bad type; recipient: bad recipient"

    def test_a_plain_string_detail_is_untouched(self):
        assert mcp_server._readable_detail("Unknown recipient 'nobody'") == (
            "Unknown recipient 'nobody'"
        )
