"""Text the Hub puts in front of a model must describe the system that exists.

Charters are inlined into an agent's context verbatim, and the turn preamble is prepended to
every prompt, so both are live instruction rather than documentation. Telling an agent to read
`roles.json` or run `agentweave status` sends it after things that were removed
(`2026-08-03-single-runtime`, `runner/agent/charter` phase 4), which is how the operator's test
produced an agent that read files it could not find
(`2026-08-06-agent-permissions-tool-schemas-and-base-knowledge`).
"""

import json
import re
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
    ("shared/design-", "nothing writes a shared design note"),
    ("shared/plan-", "nothing writes a shared session plan"),
    ("agentweave.yml", "Hub-owned projects have no agentweave.yml"),
    ("agentweave status", "the CLI was reduced to app-lifecycle commands"),
    ("agentweave msg", "the CLI was reduced to app-lifecycle commands"),
    ("agentweave task", "the CLI was reduced to app-lifecycle commands"),
    ("agentweave inbox", "the CLI was reduced to app-lifecycle commands"),
    ("watchdog", "the watchdog was deleted"),
]

# The defect this catches is an instruction to *address* somebody: a directive verb
# followed by a roster title. It is deliberately keyed to that shape rather than to a list
# of titles, because a title list would pass on the very bug it was written for — 16 of the
# 21 pre-change charters escalated to a "Tech Lead" that a project need never contain, and
# a list derived from the manifest contains exactly the titles that are legitimately there.
#
# Verified against the pre-change charter set: 21 of 21 files flagged. Against the set that
# replaced them: 0 of 9.
_DIRECTIVE = r"""(?:
      escalat(?:e|es|ed|ing)\s+(?:it\s+|this\s+)?to
    | notif(?:y|ies|ied)
    | report(?:s|ed)?\s+(?:it\s+|this\s+)?to
    | hand[\s-]*off?\s+(?:it\s+|this\s+)?to
    | defer(?:s|red)?\s+to
    | consults?
    | flags?\s+(?:it\s+|this\s+)?to
    | raise(?:s|d)?\s+(?:it\s+|this\s+)?with
    | coordinates?\s+with
    | checks?\s+with
    | asks?
    | messages?
    | belongs?\s+to
    | surfaces?\s+(?:it\s+|this\s+|the\s+\w+\s+)?to
)"""

# A roster title as prose writes one: Title Case, or a shouted abbreviation.
_TITLE = r"(?:[A-Z][a-z]+(?:\s+(?:/\s+)?[A-Z][a-z]+)*|PM|QA|DevOps|ML)"

ADDRESSES_A_TITLE = re.compile(
    rf"\b{_DIRECTIVE}\s+\(?(?:the\s+|or\s+)*(?P<title>{_TITLE})\b",
    re.VERBOSE,
)

# Not parties. Kept deliberately short: the design accepts that this heuristic can misfire,
# because a false positive is fixed by rewording one sentence, whereas a permissive
# allowlist silently restores the defect.
NOT_A_PARTY = {"Yourself", "Yourselves", "Anyone", "Someone", "Somebody", "Whoever"}


def _charters():
    return sorted(CHARTER_DIR.glob("*.md"))


def _manifest():
    return json.loads((CHARTER_DIR / "charters.json").read_text(encoding="utf-8"))["charters"]


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


@pytest.mark.parametrize("charter", _charters(), ids=lambda p: p.name)
def test_seeded_charter_addresses_no_roster_title(charter):
    """The clause that had no test, and that 16 of the 21 pre-change charters broke.

    A roster is whatever agents the operator created. A charter telling its holder to
    escalate to a "Tech Lead" assumes a participant the project need never contain, and the
    agent that follows it addresses nobody. Escalation resolves to the operator instead,
    who always exists.
    """
    offenders = [
        match.group(0).strip()
        for match in ADDRESSES_A_TITLE.finditer(charter.read_text(encoding="utf-8"))
        if match.group("title") not in NOT_A_PARTY
    ]
    assert not offenders, (
        f"{charter.name} directs the agent at a roster title: {offenders}. "
        "Escalation belongs to the operator via `ask_user`, which always exists."
    )


@pytest.mark.parametrize("charter", _charters(), ids=lambda p: p.name)
def test_seeded_charter_names_no_aw_skill(charter):
    """Nothing installs the `aw-*` skills, so naming one sends the agent after a command
    that is not there. This is the specific needle the charter re-shape started from."""
    found = re.findall(r"\baw-[a-z-]+", charter.read_text(encoding="utf-8"))
    assert not found, f"{charter.name} names uninstalled skills: {sorted(set(found))}"


def test_the_starter_set_demonstrates_a_non_software_separation_of_duties():
    """Keyed to the manifest so that deleting the pair fails here, rather than silently
    narrowing what the product claims to be for.

    One capable model can perform every activity in a software workflow, which makes
    charters look like topic labels. A separation of duties is what shows a charter
    carrying a guarantee, so the starter set has to contain one.
    """
    manifest = _manifest()
    pair = ("underwriter", "underwriting_approver")

    for key in pair:
        assert key in manifest, f"the starter set lost its non-software pair: {key} is missing"

    for key in pair:
        content = (CHARTER_DIR / f"{key}.md").read_text(encoding="utf-8").lower()
        assert "you do not" in content or "may not" in content, (
            f"{key}.md no longer states the step it may not perform, so the pair "
            "documents a topic split rather than a control"
        )


class TestTurnPreamble:
    def test_mcp_branch_names_the_tools(self):
        notice = access_path_notice("mcp")
        assert "send_message" in notice

    def test_fallback_branch_offers_no_removed_commands(self):
        """It used to instruct `agentweave msg send`, `task create`, `question ask` and
        `agent request`, none of which survived the reduction to five commands."""
        notice = access_path_notice("cli")
        for removed in (
            "agentweave msg",
            "agentweave task",
            "agentweave question",
            "agent request",
        ):
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
