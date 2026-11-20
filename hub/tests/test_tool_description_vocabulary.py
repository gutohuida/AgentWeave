"""The tools agents are given speak of profiles, threads and runs, and keep their names.

Spec `profiles-threads-and-builds-everywhere`, FR-11 (D7). A tool's description is what teaches an
agent the model, so where it means a configured identity it says *profile*, where it means a
conversation it says *thread*, and where it means a turn it says *run*. Names are another matter:
renaming a tool or a parameter would break every agent's context and every saved prompt, so
`to_agent`, `conversation_id`, `allow_agent_jobs` and the like stay, and
`fixtures/tool_surface_names.json` records the served names and parameter names as they were
before the wording changed (tool-names-unchanged).

What is read is the served surface (`mcp.list_tools()`): each tool's description and each of its
parameters' descriptions, as an agent receives them.
"""

import asyncio
import json
import re
from pathlib import Path

from hub.mcp_server import mcp

FIXTURE = Path(__file__).parent / "fixtures" / "tool_surface_names.json"

WORDS = re.compile(r"(?<![\w.-])(agents?|conversations?|turns?)(?![\w-])", re.IGNORECASE)

#: A tool, parameter, field or value name is written in backticks (`agent`, `turns`) or quoted as
#: a value (`"agent"`); either is a name, not a word, and is left out before the words are matched.
_NAMES = re.compile(r"`[^`\n]*`|\"\w+\"")

#: Fixed phrases a description may keep, each a use of the word that is not a configured identity,
#: a conversation or a turn. Matched case-insensitively within one line of a description.
ALLOWED_PHRASES: tuple[str, ...] = ()


def _served() -> list:
    return asyncio.run(mcp.list_tools())


def _descriptions(tool) -> list[tuple[str, str]]:
    """(where, text) for the tool's description and each parameter's."""
    texts = [(tool.name, tool.description or "")]
    for name, schema in (tool.parameters or {}).get("properties", {}).items():
        texts.append((f"{tool.name}.{name}", schema.get("description", "") or ""))
    return texts


def vocabulary_uses(where: str, text: str, parameters: tuple[str, ...] = ()) -> list[str]:
    """Each line of *text* that says agent, conversation or turn outside a name or a phrase.

    A line of the `Args:` block opens with the parameter it describes (`agent: Exact name of...`);
    that opening is the parameter's name, given in *parameters*.
    """
    found = []
    for line in text.splitlines():
        prose = _NAMES.sub(" ", line)
        opening = re.match(r"\s*(\w+):", prose)
        if opening and opening.group(1) in parameters:
            prose = prose[opening.end() :]
        for phrase in ALLOWED_PHRASES:
            prose = re.sub(re.escape(phrase), " ", prose, flags=re.IGNORECASE)
        if WORDS.search(prose):
            found.append(f"{where}: {line.strip()}")
    return found


def _surface() -> dict[str, list[str]]:
    return {
        tool.name: sorted((tool.parameters or {}).get("properties", {}).keys())
        for tool in _served()
    }


def test_no_served_description_says_agent_conversation_or_turn():
    found = [
        use
        for tool in _served()
        for where, text in _descriptions(tool)
        for use in vocabulary_uses(
            where, text, tuple((tool.parameters or {}).get("properties", {}))
        )
    ]
    assert not found, (
        "say profile, thread or run in a tool description (FR-11); write a name in backticks:\n"
        + "\n".join(found)
    )


def test_the_check_finds_the_words_the_descriptions_used_to_say():
    # Lines as the descriptions read before FR-11, so the check is known to fail on them.
    assert vocabulary_uses(
        "hand_out_task", "hand one of its tasks to an agent, and start that agent's turn on it."
    )
    assert vocabulary_uses(
        "read_shells", "Read the operator's shells in this conversation's Terminal tab"
    )
    assert vocabulary_uses("create_task.builder", "The open agent who builds it.")


def test_names_in_backticks_or_quoted_are_not_words():
    assert not vocabulary_uses("x", "with `agent`, `conversation_id` and `turns`")
    assert not vocabulary_uses("x", 'who checks it, e.g. "agent" or "operator"')
    assert not vocabulary_uses(
        "x", "to_agent, allow_agent_jobs, priced_turns, subagent, AgentWeave"
    )
    assert not vocabulary_uses("x", "    agent: Exact name of a registered profile.", ("agent",))
    assert vocabulary_uses("x", "    agent: Exact name of a registered agent.", ("agent",))


def test_every_tool_name_and_parameter_set_is_unchanged():
    recorded = json.loads(FIXTURE.read_text(encoding="utf-8"))
    served = _surface()
    assert sorted(served) == sorted(recorded), "the served tool names changed (FR-11)"
    changed = {
        name: (recorded[name], served[name]) for name in recorded if served[name] != recorded[name]
    }
    assert not changed, f"parameter names changed (FR-11), recorded vs served: {changed}"
