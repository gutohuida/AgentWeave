"""Text the Hub puts in front of a model must describe the system that exists.

Charters are inlined into an agent's context verbatim, and the turn preamble is prepended to
every prompt, so both are live instruction rather than documentation. Telling an agent to read
`roles.json` or run `agentweave status` sends it after things that were removed
(`2026-08-03-single-runtime`, `runner/agent/charter` phase 4), which is how the operator's test
produced an agent that read files it could not find
(`2026-08-06-agent-permissions-tool-schemas-and-base-knowledge`).
"""

from pathlib import Path

import pytest

from hub.agent_status import STALLED_STATUS_MESSAGE
from hub.launchability import access_path_notice

CHARTER_DIR = Path(__file__).resolve().parents[1] / "hub" / "data" / "charters"

# Each entry is (needle, why it must not appear).
REMOVED_SUBSYSTEMS = [
    ("roles.json", "the role subsystem and its files were removed"),
    ("protocol.md", "the Hub never writes a protocol file"),
    ("shared/context.md", "the shared-context convention was removed with the CLI runtime"),
    ("agentweave.yml", "Hub-owned projects have no agentweave.yml"),
    ("agentweave status", "the CLI was reduced to app-lifecycle commands"),
    ("agentweave msg", "the CLI was reduced to app-lifecycle commands"),
    ("agentweave task", "the CLI was reduced to app-lifecycle commands"),
    ("agentweave inbox", "the CLI was reduced to app-lifecycle commands"),
    ("watchdog", "the watchdog was deleted"),
]


def _charters():
    return sorted(CHARTER_DIR.glob("*.md"))


def test_there_are_charters_to_check():
    """A glob that silently matched nothing would make every assertion below vacuous."""
    assert _charters(), f"no charter seeds found under {CHARTER_DIR}"


@pytest.mark.parametrize("charter", _charters(), ids=lambda p: p.name)
def test_seeded_charter_cites_no_removed_subsystem(charter):
    content = charter.read_text(encoding="utf-8")
    lowered = content.lower()
    for needle, why in REMOVED_SUBSYSTEMS:
        assert needle.lower() not in lowered, f"{charter.name} references {needle!r}: {why}"


@pytest.mark.parametrize("charter", _charters(), ids=lambda p: p.name)
def test_seeded_charter_does_not_defer_to_a_principal(charter):
    """A Hub-owned project has a roster, not a principal — an agent addressing one gets a 404."""
    lowered = charter.read_text(encoding="utf-8").lower()
    assert "principal" not in lowered, f"{charter.name} still refers to a principal"


class TestTurnPreamble:
    def test_mcp_branch_names_the_tools(self):
        notice = access_path_notice("mcp")
        assert "send_message" in notice

    def test_fallback_branch_offers_no_removed_commands(self):
        """It used to instruct `agentweave msg send`, `task create`, `question ask` and
        `agent request`, none of which survived the reduction to five commands."""
        notice = access_path_notice("cli")
        for removed in ("agentweave msg", "agentweave task", "agentweave question", "agent request"):
            assert removed not in notice


def test_stalled_status_does_not_name_the_watchdog():
    assert "watchdog" not in STALLED_STATUS_MESSAGE.lower()


def test_the_context_describes_ask_user_as_it_actually_behaves():
    """The generated tool list is a second description of the same tool, and the two disagreeing
    is worse than either being absent: it told agents `blocking=False` after the default became
    True, and never mentioned `options` at all, so no agent would offer a choice."""
    from hub.api.v1.agents import _tool_surface_lines

    text = "\n".join(_tool_surface_lines())
    assert "blocking=False)" not in text
    assert "options" in text
    assert "wait" in text.lower()


def test_the_context_and_the_tool_signature_agree_on_ask_user():
    """Guards the actual failure mode: someone changes the signature and leaves the prose."""
    import inspect

    from hub.api.v1.agents import _tool_surface_lines
    from hub.mcp_server import ask_user

    text = "\n".join(_tool_surface_lines())
    for name in inspect.signature(ask_user).parameters:
        if name == "blocking":
            continue  # deliberately not advertised; the default is what agents should use
        assert name in text, f"context does not mention ask_user's {name!r} parameter"
