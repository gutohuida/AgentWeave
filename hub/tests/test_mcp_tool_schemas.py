"""The MCP tool schema must advertise every constrained parameter's valid values.

A bare `str` parameter tells a client nothing. Codex agents repeatedly guessed
`message_type="text"`, were rejected 422, and only succeeded on a retry; Claude agents happened
to omit the parameter and so never hit it. The fix is the schema, not documentation
(`2026-08-06-agent-permissions-tool-schemas-and-base-knowledge`).
"""

import asyncio
import json
import typing

import pytest

from hub import mcp_server
from hub.db.models import EVIDENCE_DECISIONS
from hub.schemas.messages import _MESSAGE_TYPES
from hub.schemas.tasks import _PRIORITIES, _TASK_STATUSES
from hub.task_transitions import STATUS_BLOCKED

#: What an agent may ask `update_task` for: every status the validator accepts except the waiting
#: one. `blocked` is withheld from the agent surface on purpose (design D3 of
#: `2026-08-10-blocked-and-conversation-binding`) — the runtime observes that a run is waiting on a
#: person, by seeing it end with an unanswered blocking question. An agent that could assert the
#: status could claim to be waiting on someone it never asked.
#:
#: Derived from `_TASK_STATUSES` rather than written out, so a ninth status added later still has
#: to be declared in one place and is still checked here.
_AGENT_REQUESTABLE_STATUSES = [s for s in _TASK_STATUSES if s != STATUS_BLOCKED]


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
        ("update_task", "status", _AGENT_REQUESTABLE_STATUSES),
        ("create_job", "session_mode", ["new", "resume"]),
        # `kind` is deliberately absent: `EVIDENCE_KINDS` is open at the edges, so a Literal
        # here would make the tool narrower than the route it posts to.
        ("decide_evidence", "decision", list(EVIDENCE_DECISIONS)),
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
        (mcp_server.TaskStatus, _AGENT_REQUESTABLE_STATUSES),
        (mcp_server.TaskPriority, _PRIORITIES),
        (mcp_server.EvidenceDecision, list(EVIDENCE_DECISIONS)),
    ],
)
def test_alias_agrees_with_the_validator_it_mirrors(alias, runtime):
    """The Literal is restated rather than imported (mcp_server.py stays standalone), so this
    is what stops the two drifting apart."""
    assert sorted(typing.get_args(alias)) == sorted(runtime)


def test_update_task_status_is_required_and_therefore_must_be_discoverable():
    """`status` has no default, so a model must supply one of the states blind."""
    schema = _schemas()["update_task"]
    assert "status" in schema.get("required", [])
    assert _enum_for(schema, "status") is not None


def test_the_agent_is_never_offered_the_waiting_status():
    """Stated as its own assertion, not left implicit in a derived list.

    The two tests above would keep passing if `blocked` were quietly added back to both the
    validator and the agent surface together. This one says the thing that must stay true: an agent
    cannot ask for the status that means "a person owes me an answer", because being able to assert
    it is being able to assert it falsely.
    """
    declared = _enum_for(_schemas()["update_task"], "status")
    assert STATUS_BLOCKED not in declared
    assert STATUS_BLOCKED not in typing.get_args(mcp_server.TaskStatus)
    assert STATUS_BLOCKED in _TASK_STATUSES, "but it is still a real status the operator can set"


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


# ---------------------------------------------------------------------------
# submit_spec_document
# ---------------------------------------------------------------------------


def test_spec_kind_agrees_with_the_payload_validator():
    """`mcp_server` restates these because it is spawned standalone and may import
    only stdlib and fastmcp. Restating is the rule; drifting is the risk this closes."""
    from hub.spec_payload import KINDS

    assert set(typing.get_args(mcp_server.SpecKind)) == set(KINDS)


def test_the_declared_schema_version_agrees_with_the_hub():
    from hub.spec_payload import SCHEMA_VERSION

    assert mcp_server.SPEC_SCHEMA_VERSION == SCHEMA_VERSION


def test_submit_spec_document_advertises_the_document_kinds():
    schema = _schemas()["submit_spec_document"]
    assert schema["properties"]["kind"]["enum"]


def test_submit_spec_document_offers_no_way_to_set_a_phase_or_approve():
    """The gate is only real if the surface has no lever on it. Keyed to the
    parameter names rather than to a list of forbidden values, so a later
    `phase` argument added for any reason fails here."""
    schema = _schemas()["submit_spec_document"]
    offered = set(schema["properties"])

    assert not offered & {"phase", "status", "approve", "approved", "approved_by", "state"}


def test_submit_spec_document_does_not_take_an_agent_identity():
    """Identity comes from the run credential. A caller that could name itself
    could name somebody else."""
    schema = _schemas()["submit_spec_document"]
    offered = set(schema["properties"])

    assert not offered & {"agent", "actor", "author", "run_id", "project_id"}


def test_structured_parameters_do_not_use_a_closed_object_type():
    """Deliberate, and the reason is not laziness: pydantic validates a TypedDict
    by *dropping* keys it does not declare. Typing `requirements` as a list of
    TypedDict would silently discard the fields a later schema version adds, so
    the forward compatibility the payload guarantees would be lost at the tool
    boundary rather than at the Hub. The shape lives in the description instead."""
    schema = _schemas()["submit_spec_document"]
    items = schema["properties"]["requirements"]

    text = json.dumps(items)
    assert "additionalProperties" not in text or '"additionalProperties": false' not in text


# ---------------------------------------------------------------------------
# rename_spec_document
# ---------------------------------------------------------------------------


def test_rename_spec_document_takes_a_subject_and_not_a_destination():
    """Path validation is the only control keeping a document from being written
    to an arbitrary location beneath `spec/`. A rename that accepted a
    destination would put the least trusted caller in the system behind that one
    guard; a subject makes the shape unexpressible instead of merely rejected."""
    schema = _schemas()["rename_spec_document"]
    offered = set(schema["properties"])

    assert offered == {"path", "subject"}
    assert not offered & {"to", "new_path", "destination", "target", "slug", "name"}


def test_rename_spec_document_does_not_take_an_agent_identity():
    schema = _schemas()["rename_spec_document"]
    offered = set(schema["properties"])

    assert not offered & {"agent", "actor", "author", "run_id", "project_id"}


def test_rename_spec_document_offers_no_lever_on_the_phase():
    schema = _schemas()["rename_spec_document"]
    offered = set(schema["properties"])

    assert not offered & {"phase", "status", "approve", "approved", "state"}
