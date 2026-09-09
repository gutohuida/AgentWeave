"""The tools an agent is told it has are the tools the server serves.

Change `2026-08-13-the-tool-list-matches-the-tools`. `## Your tools` is hand-written prose, and it
has now fallen behind the server twice. The first time, four job tools were never mentioned. The
second time cost a completed interview: a Codex agent was instructed by the phase block to call
`submit_spec_document`, found no such tool in the described surface, concluded *"the required
`submit_spec_document` capability was not exposed in this session"*, and stopped — after three
rounds of `ask_user` had settled the entire scope. The tool was served the whole time.

An enumeration an agent believes is worse than no enumeration when it is wrong, so the agreement is
checked rather than remembered.

**Two renderings, both checked** (task 2.3 of
`2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`). `_tool_surface_lines` now writes the
same operations either as injected MCP calls or as HTTP requests, and this file is the reason that
was the right home for the second rendering: a rendering not covered here drifts the first time a
tool is added, silently, which is the failure the paragraph above describes. The MCP rendering is
checked against `mcp.list_tools()`; the HTTP rendering is checked against the app's own OpenAPI
schema, which is the equivalent ground truth on that path — the routes actually mounted, with the
fields they actually accept and require.
"""

import asyncio
import re

from hub.api.v1.agents import _AGENT_ACTIONS_PREFIX, UNDESCRIBED_TOOLS, _tool_surface_lines
from hub.mcp_server import mcp

# Anything that is not `"mcp"` selects the HTTP rendering. `"cli"` is the value
# `resolve_access_path` actually returns for a run without an injected server.
HTTP_PATH = "cli"


def _served() -> set:
    return {tool.name for tool in asyncio.run(mcp.list_tools())}


def _described() -> set:
    """Tool names as the MCP rendering writes them: `name(args)` in backticks."""
    text = "\n".join(_tool_surface_lines())
    return set(re.findall(r"`(\w+)\(", text))


def _described_over_http() -> set:
    """Operation names as the HTTP rendering writes them: `(`name`)` after the route."""
    return {operation["tool"] for operation in _http_operations()}


def _described_signatures() -> dict:
    """Each described tool mapped to the argument names the surface gives it."""
    text = "\n".join(_tool_surface_lines())
    return {
        name: [arg.split("=")[0].strip() for arg in args.split(",") if arg.strip()]
        for name, args in re.findall(r"`(\w+)\(([^)]*)\)`", text)
    }


_HEAD_RE = re.compile(r"^- `([A-Z]+) ([^`]+)` \(`(\w+)`\)(.*)$")
_FIELDS_RE = re.compile(r"^ — (body|query) ((?:`[^`]+`\*?)(?:, `[^`]+`\*?)*) — ")


def _http_operations() -> list:
    """Parse the HTTP rendering back into the request each line tells an agent to make.

    Parsed rather than read off the source structure on purpose: what is checked has to be the
    text the agent receives, because that text is the only thing the agent has.
    """
    operations = []
    for line in _tool_surface_lines(access_path=HTTP_PATH):
        head = _HEAD_RE.match(line)
        if head is None:
            continue
        method, path, tool, rest = head.groups()
        fields, required, where = [], set(), ""
        clause = _FIELDS_RE.match(rest)
        if clause is not None:
            where = clause.group(1)
            for token in clause.group(2).split(", "):
                name = token.strip("`*")
                fields.append(name)
                if token.endswith("*"):
                    required.add(name)
        operations.append(
            {
                "tool": tool,
                "method": method,
                "path": path,
                "where": where,
                "fields": fields,
                "required": required,
            }
        )
    return operations


def _schemas() -> dict:
    return {tool.name: (tool.parameters or {}) for tool in asyncio.run(mcp.list_tools())}


def _openapi() -> dict:
    """The routes the app actually mounts, keyed by the `METHOD path` the surface prints."""
    from hub.main import app

    spec = app.openapi()
    routes = {}
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            body_properties, body_required = {}, set()
            request_body = operation.get("requestBody")
            if request_body:
                schema = request_body["content"]["application/json"]["schema"]
                reference = schema.get("$ref")
                if reference:
                    component = spec["components"]["schemas"][reference.split("/")[-1]]
                    body_properties = component.get("properties", {})
                    body_required = set(component.get("required", []))
            query = {
                parameter["name"]: parameter.get("required", False)
                for parameter in operation.get("parameters", [])
                if parameter["in"] == "query"
            }
            routes[(method.upper(), path)] = {
                "body_properties": set(body_properties),
                "body_required": body_required,
                "query": query,
            }
    return routes


def test_every_served_tool_is_described_or_deliberately_excluded():
    missing = _served() - _described() - set(UNDESCRIBED_TOOLS)
    assert not missing, (
        f"served but neither described nor excluded: {sorted(missing)}. "
        "Describe it in `_tool_surface_lines`, or add it to `UNDESCRIBED_TOOLS` with the reason "
        "the agent does not need it there. An agent that is instructed to use a tool its own "
        "surface omits concludes it does not have the tool, and stops."
    )


def test_every_served_tool_is_described_over_http_too():
    """The same check on the other rendering. An agent without MCP that is told about fewer
    capabilities than an agent with it has been handed the very inequality this change removed —
    only quieter, because nothing on the HTTP path was ever checked before."""
    missing = _served() - _described_over_http() - set(UNDESCRIBED_TOOLS)
    assert not missing, f"served but absent from the HTTP rendering: {sorted(missing)}"


def test_no_tool_is_described_that_the_server_does_not_serve():
    """The reverse costs a turn too: an agent told it has a tool discovers otherwise by calling."""
    phantom = _described() - _served()
    assert not phantom, f"described but not served: {sorted(phantom)}"


def test_the_two_renderings_describe_the_same_operations():
    """One source, two renderings (`design.md` D3). Set equality is what makes that structural
    rather than aspirational: adding an operation to one rendering alone fails here, whichever
    one was forgotten."""
    assert _described() == _described_over_http()


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


def test_no_described_argument_is_one_the_tool_does_not_take():
    """Matching names is not enough: the arguments have to be the real ones.

    `submit_spec_document` was described as taking `(path, document)` for two days after this
    file was written to stop exactly this. The real tool takes `(path, title, kind, ...)` and has
    no `document` parameter at all, so an agent following its own tool list would have been
    rejected for an unexpected keyword argument on top of two missing required ones. The
    name-only check above passed the whole time, because the name was never the part that drifted.
    """
    schemas = _schemas()
    wrong = {}
    for name, args in _described_signatures().items():
        properties = schemas.get(name, {}).get("properties", {})
        phantom = [arg for arg in args if arg not in properties]
        if phantom:
            wrong[name] = phantom
    assert not wrong, (
        f"described arguments that the tool does not accept: {wrong}. "
        "Correct the entry in `_tool_surface_lines` to the real signature."
    )


def test_every_required_argument_is_described():
    """An omitted optional argument costs an agent a capability it did not know it had. An omitted
    *required* one costs it the call, which is what makes this the stricter half."""
    schemas = _schemas()
    missing = {}
    for name, args in _described_signatures().items():
        required = set(schemas.get(name, {}).get("required", []))
        absent = sorted(required - set(args))
        if absent:
            missing[name] = absent
    assert not missing, (
        f"required arguments the surface never mentions: {missing}. "
        "An agent cannot supply an argument it was not told about."
    )


def test_the_spec_tool_is_described():
    """Named specifically because the phase block instructs its use, and the two disagreeing is the
    failure that produced this change. A generic coverage test would pass the day someone moved it
    into `UNDESCRIBED_TOOLS` to make the suite green."""
    assert "submit_spec_document" in _described()
    assert "submit_spec_document" not in UNDESCRIBED_TOOLS


# --- The HTTP rendering against the routes the app actually mounts ------------------------------


def test_the_prefix_the_surface_prints_is_a_prefix_the_app_mounts():
    """The constant is repeated in `access_path_notice`'s prose. An agent given the wrong prefix
    cannot perform a single operation, and every failure it sees is a 404 that looks like the Hub
    being down rather than like the instructions being wrong."""
    mounted = {path for _, path in _openapi()}
    assert any(path.startswith(_AGENT_ACTIONS_PREFIX) for path in mounted)


def test_every_described_route_exists():
    """The MCP rendering can be wrong about a name; this rendering can be wrong about an address,
    and an address that does not exist is the same dead end with a different status code."""
    routes = _openapi()
    unknown = [
        f"{operation['method']} {operation['path']}"
        for operation in _http_operations()
        if (operation["method"], operation["path"]) not in routes
    ]
    assert not unknown, f"described routes the app does not mount: {sorted(unknown)}"


def test_no_described_field_is_one_the_route_does_not_accept():
    """The HTTP counterpart of the argument check above, and it catches a mistake MCP cannot make:
    the wire names are not always the tool's argument names. `send_message(to_agent=...)` is
    `{"recipient": ...}` on the route, and a surface that printed `to_agent` would be describing a
    field the route silently ignores."""
    routes = _openapi()
    wrong = {}
    for operation in _http_operations():
        route = routes.get((operation["method"], operation["path"]))
        if route is None:
            continue  # the previous test owns this failure
        known = route["query"] if operation["where"] == "query" else route["body_properties"]
        phantom = [field for field in operation["fields"] if field not in known]
        if phantom:
            wrong[f"{operation['method']} {operation['path']}"] = phantom
    assert not wrong, f"described fields the route does not accept: {wrong}"


def test_every_field_the_route_requires_is_described_and_marked():
    """Required-ness is rendered as a `*`, so it has to mean what the route means by it. A field
    the route requires and the surface leaves unmarked costs the agent the call on its first try —
    and a `*` the route does not require sends it hunting for a value it never needed."""
    routes = _openapi()
    disagreements = {}
    for operation in _http_operations():
        route = routes.get((operation["method"], operation["path"]))
        if route is None:
            continue
        if operation["where"] == "query":
            required = {name for name, is_required in route["query"].items() if is_required}
        else:
            required = route["body_required"]
        # Only over the fields this operation actually uses: a route may require a field for a
        # different caller's purpose, and this rendering describes one operation, not the route.
        expected = required & set(operation["fields"])
        if expected != operation["required"]:
            disagreements[f"{operation['method']} {operation['path']}"] = {
                "route requires": sorted(expected),
                "surface marks": sorted(operation["required"]),
            }
    assert not disagreements, f"required-ness disagrees with the route: {disagreements}"


def test_a_route_required_field_is_never_left_out_of_the_description():
    """The stricter half of the one above: a required field the surface does not name at all
    cannot be marked, so an equality check on the marks alone would pass while the agent has no
    way to learn the field exists."""
    routes = _openapi()
    missing = {}
    for operation in _http_operations():
        route = routes.get((operation["method"], operation["path"]))
        if route is None:
            continue
        required = (
            {name for name, is_required in route["query"].items() if is_required}
            if operation["where"] == "query"
            else route["body_required"]
        )
        absent = sorted(required - set(operation["fields"]))
        if absent:
            missing[f"{operation['method']} {operation['path']}"] = absent
    assert not missing, f"fields the route requires and the surface never names: {missing}"


def test_the_http_rendering_names_the_credential_variable_and_never_a_value(monkeypatch):
    """The same boundary as `access_path_notice`'s (`design.md` D4), on the other half of the text
    an agent without MCP reads. This surface is written into the durable turn prompt, so a value
    interpolated here is a credential in stored turn text.

    The variables are set to sentinels *before* rendering, deliberately: rendering with them unset
    would pass against an implementation that interpolates, which is the assertion that cannot
    fail this repository keeps re-learning (`F190`, `F296`).
    """
    monkeypatch.setenv("AW_RUN_TOKEN", "aw-run-SURFACELEAKCHECK")
    monkeypatch.setenv("HUB_URL", "http://127.0.0.1:65432")

    text = "\n".join(_tool_surface_lines(access_path=HTTP_PATH))

    assert "AW_RUN_TOKEN" in text
    assert "HUB_URL" in text
    assert "Authorization: Bearer" in text
    assert "aw-run-SURFACELEAKCHECK" not in text
    assert "65432" not in text


def test_the_mcp_rendering_is_what_a_caller_that_says_nothing_gets():
    """Every caller outside a run keeps the injected-tool wording, and that default is what makes
    `access_path` safe to add: `GET /agents/agent-context` and `POST /agents/register` are answered
    without a run, so they have no path to describe and must not invent one."""
    assert _tool_surface_lines() == _tool_surface_lines(access_path="mcp")
    assert _tool_surface_lines() != _tool_surface_lines(access_path=HTTP_PATH)


def _http_line_for(tool: str) -> str:
    """Every line the HTTP rendering writes about one operation, joined.

    An operation's description spans its head line plus the notes under it, and the protocol these
    two tests are about lives in the notes.
    """
    lines = _tool_surface_lines(access_path=HTTP_PATH)
    start = next(index for index, line in enumerate(lines) if f"(`{tool}`)" in line)
    end = start + 1
    while end < len(lines) and lines[end].startswith("  "):
        end += 1
    return "\n".join(lines[start:end])


def test_the_http_rendering_states_the_wait_protocol_ask_user_performs():
    """§3.5/§3.7 of `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`.

    `ask_user` is a call that waits, and the waiting was the adapter's alone: the contract offered
    no way to wait and never disclosed the deadline it stamps. The deadline is now on the response
    (`QuestionResponse.wait_expires_at`), and this is the other half — a caller with no injected
    tool is told, here, how to participate: poll, stop at the deadline, then report.

    The expired-only clause is the one worth a test of its own. A decline is a decision the operator
    made and handed back; reporting one as a wait that ran out records the opposite of what
    happened, and `mcp_server.ask_user` is careful about it in a comment that only governs itself.
    """
    described = _http_line_for("ask_user")

    assert "wait_expires_at" in described
    assert f"GET {_AGENT_ACTIONS_PREFIX}/questions/" in described
    assert f"{_AGENT_ACTIONS_PREFIX}/questions/wait-ended" in described
    assert "declined" in described
    assert "only the ones that ran out of time" in described


def test_the_http_rendering_states_how_an_archive_is_directed():
    """§3.1/§3.5: the always-ask rule is the route's now, so an HTTP caller meets a `409` it has to
    act on. A description that stated the rule without stating the protocol would leave that caller
    reading its own refusal as a defect."""
    described = _http_line_for("archive_job")

    assert "operator_direction_required" in described
    assert "permission_request_id" in described
    assert f"{_AGENT_ACTIONS_PREFIX}/permission-requests/" in described
    # The rule itself is in the shared description, so both renderings carry it.
    assert "whatever this run's permission posture is" in "\n".join(_tool_surface_lines())
