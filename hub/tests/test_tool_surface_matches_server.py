"""The tools an agent is told it has are the tools the server serves.

Change `2026-08-13-the-tool-list-matches-the-tools`. `## Your tools` is hand-written prose, and it
has now fallen behind the server twice. The first time, four job tools were never mentioned. The
second time cost a completed interview: a Codex agent was instructed by the phase block to call
`submit_spec_document`, found no such tool in the described surface, concluded *"the required
`submit_spec_document` capability was not exposed in this session"*, and stopped — after three
rounds of `ask_user` had settled the entire scope. The tool was served the whole time.

An enumeration an agent believes is worse than no enumeration when it is wrong, so the agreement is
checked rather than remembered.
"""

import asyncio
import re

from hub.api.v1.agents import UNDESCRIBED_TOOLS, _tool_surface_lines
from hub.mcp_server import mcp


def _served() -> set:
    return {tool.name for tool in asyncio.run(mcp.list_tools())}


def _described() -> set:
    """Tool names as the surface writes them: `name(args)` in backticks."""
    text = "\n".join(_tool_surface_lines())
    return set(re.findall(r"`(\w+)\(", text))


def test_every_served_tool_is_described_or_deliberately_excluded():
    missing = _served() - _described() - set(UNDESCRIBED_TOOLS)
    assert not missing, (
        f"served but neither described nor excluded: {sorted(missing)}. "
        "Describe it in `_tool_surface_lines`, or add it to `UNDESCRIBED_TOOLS` with the reason "
        "the agent does not need it there. An agent that is instructed to use a tool its own "
        "surface omits concludes it does not have the tool, and stops."
    )


def test_no_tool_is_described_that_the_server_does_not_serve():
    """The reverse costs a turn too: an agent told it has a tool discovers otherwise by calling."""
    phantom = _described() - _served()
    assert not phantom, f"described but not served: {sorted(phantom)}"


def test_every_exclusion_states_its_reason():
    """An exclusion without a reason is indistinguishable from the omission this test exists to
    catch — it silences the check without anyone having decided anything."""
    for name, reason in UNDESCRIBED_TOOLS.items():
        assert reason and reason.strip(), f"{name} is excluded with no reason"
        assert len(reason.split()) >= 8, f"{name}'s reason is too short to be one: {reason!r}"


def test_an_excluded_tool_is_actually_served():
    """An exclusion for a tool that no longer exists is dead weight that hides a real omission if
    the name is ever reused."""
    stale = set(UNDESCRIBED_TOOLS) - _served()
    assert not stale, f"excluded but not served: {sorted(stale)}"


def test_the_spec_tool_is_described():
    """Named specifically because the phase block instructs its use, and the two disagreeing is the
    failure that produced this change. A generic coverage test would pass the day someone moved it
    into `UNDESCRIBED_TOOLS` to make the suite green."""
    assert "submit_spec_document" in _described()
    assert "submit_spec_document" not in UNDESCRIBED_TOOLS
