"""The fastmcp APIs the agent tool surface actually stands on, named one by one.

`hub/hub/mcp_server.py` imports stdlib plus `fastmcp` and nothing else, so `fastmcp` is not one
dependency among many — it is the process that starts every agent turn. On 2026-08-31T18:20:31Z
FastMCP 4.0.0 reached PyPI. The pin was `fastmcp>=2.0`, unbounded, in three places; CI resolves
fresh with no lockfile; and so the two CI runs that evening crossed from the 3.x line to a new
major and passed, while the operator's own machine stayed on 3.x. Nobody was told, and nothing
would have told them until an agent failed to start.

This file exists so that the *next* major is caught by a named failing test with a specific
message, instead of by a red board somebody has to bisect. Each test below asserts one thing
`mcp_server.py` does at import or at spawn. `test_the_pin_is_bounded_and_agrees_everywhere`
guards the ceiling itself, because a ceiling that is quietly deleted is worse than none: it
reads as a decision that was made.

Raising the ceiling is a real option, not a forbidden one. The intended sequence is: widen the
pin, run this file, and read what it says. If everything here passes, the surface survived.
"""

from __future__ import annotations

import asyncio
import inspect
import tomllib
from pathlib import Path
from typing import Literal

import pytest
from fastmcp import FastMCP

REPO_ROOT = Path(__file__).resolve().parents[2]
HUB_PYPROJECT = REPO_ROOT / "hub" / "pyproject.toml"
CLI_PYPROJECT = REPO_ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def probe() -> FastMCP:
    """A server built the way `mcp_server.py` builds its own, at :55.

    Constructed once per module rather than per test: `list_tools()` is the expensive call and
    every assertion below reads the same registration.
    """
    server = FastMCP(name="fastmcp-api-probe", instructions="Probe, not a product surface.")

    @server.tool()
    def probe_tool(
        text: str,
        message_type: Literal["message", "delegation", "review"] = "message",
    ) -> str:
        """A plain function with a Literal-constrained parameter, as the real tools are."""
        return f"{message_type}:{text}"

    return server


def test_constructor_takes_name_and_instructions(probe):
    """`mcp_server.py:55` calls `FastMCP(name=..., instructions=...)` by keyword."""
    assert probe.name == "fastmcp-api-probe"


def test_tool_decorator_registers_a_plain_function(probe):
    """`@mcp.tool()` — with the parentheses — on an undecorated function, 27 times over."""
    names = {tool.name for tool in asyncio.run(probe.list_tools())}
    assert "probe_tool" in names, f"@mcp.tool() registered nothing; saw {sorted(names)}"


def test_run_binds_stdio_without_a_banner():
    """`main()` calls `mcp.run(transport="stdio", show_banner=False)` — mcp_server.py:1397.

    A banner on stdout is not cosmetic here: stdout *is* the MCP channel, so a version banner
    printed into it corrupts the first frame the Hub reads.
    """
    signature = inspect.signature(FastMCP.run)
    try:
        signature.bind_partial(transport="stdio", show_banner=False)
    except TypeError as exc:  # pragma: no cover - the failure message is the point
        pytest.fail(f"mcp.run(transport='stdio', show_banner=False) no longer binds: {exc}")


def test_list_tools_yields_name_and_parameters(probe):
    """Seven test files read `.name` and `.parameters` off these objects.

    `test_mcp_tool_schemas.py:38`, `test_tool_surface_matches_server.py:22,41`,
    `test_mcp_server_stdio_surface.py:101`, `test_agent_tool_surface_phase7.py:15`,
    `test_requirement_gate.py:550`, `test_spec_index_writer.py:40`. If this attribute pair
    moves, all seven break at once and none of them says why.
    """
    tool = next(t for t in asyncio.run(probe.list_tools()) if t.name == "probe_tool")
    assert isinstance(tool.parameters, dict)
    assert "properties" in tool.parameters, f"no JSON-Schema properties: {tool.parameters!r}"


def test_a_literal_default_still_renders_as_an_enum(probe):
    """The whole reason `mcp_server.py` declares `Literal` aliases at all.

    A bare `str` advertises nothing, and Codex agents guessed `message_type="text"` and were
    rejected 422 until the enum shipped. If a fastmcp upgrade stops emitting the enum, the
    schema silently reverts to that state and only an agent's failed call would show it.
    """
    tool = next(t for t in asyncio.run(probe.list_tools()) if t.name == "probe_tool")
    prop = tool.parameters["properties"]["message_type"]
    enum = prop.get("enum")
    if enum is None:
        defs = tool.parameters.get("$defs", {})
        for candidate in (prop, *prop.get("anyOf", [])):
            ref = candidate.get("$ref", "")
            if ref.startswith("#/$defs/"):
                enum = defs.get(ref.split("/")[-1], {}).get("enum")
                if enum is not None:
                    break
    assert enum is not None, f"Literal no longer renders an enum: {tool.parameters!r}"
    assert sorted(enum) == ["delegation", "message", "review"]


def _fastmcp_specifiers() -> dict[str, str]:
    """Every place this repository declares its fastmcp requirement, keyed by where."""
    cli = tomllib.loads(CLI_PYPROJECT.read_text(encoding="utf-8"))["project"]
    hub = tomllib.loads(HUB_PYPROJECT.read_text(encoding="utf-8"))["project"]
    found: dict[str, str] = {}
    sources = {
        "pyproject.toml [mcp]": cli["optional-dependencies"]["mcp"],
        "pyproject.toml [all]": cli["optional-dependencies"]["all"],
        "hub/pyproject.toml": hub["dependencies"],
    }
    for where, requirements in sources.items():
        for requirement in requirements:
            if requirement.split(">")[0].split("<")[0].split("=")[0].strip() == "fastmcp":
                found[where] = requirement
    return found


@pytest.mark.skipif(
    not CLI_PYPROJECT.exists(),
    reason="hub/ checked out without the CLI package alongside it",
)
def test_the_pin_is_bounded_and_agrees_everywhere():
    """Three declarations, one requirement, and it has a ceiling.

    Bounded to `<4` on 2026-09-01. The bound is defensive rather than forced — 4.0.0 was
    measured against every API above and survived — but v4 pulls `pydantic>=2.12`,
    `FastAPI>=0.133.0` and `httpx2` behind it, and this suite has never run on that set.
    """
    specifiers = _fastmcp_specifiers()
    assert len(specifiers) == 3, f"expected three declarations, found {specifiers}"
    distinct = set(specifiers.values())
    assert len(distinct) == 1, f"the three fastmcp pins disagree: {specifiers}"
    (pin,) = distinct
    assert "<" in pin, (
        f"fastmcp is declared {pin!r}, with no upper bound. Unbounded is how the tool surface "
        "crossed from 3.x to 4.0.0 in CI on 2026-08-31 with nobody told. If the ceiling was "
        "removed deliberately, delete this assertion and say why in the same commit."
    )
