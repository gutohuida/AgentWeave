"""A Copilot run tests its own MCP server before its first prompt (`a-run-reaches-the-hub-without-mcp`, D9).

Copilot starts the stdio servers it was given inside `session/new`, before the Hub sends any
prompt, so the transport waits (bounded) for this run's announce, decides the surface from the
answer, and only then renders the access notice and the tool section into the first prompt. On a
timeout it sends one `/mcp list` slash prompt -- no model call -- and quotes Copilot's own line
about the server. A run given no server does not wait. Plan mode for a spec turn is decided after
the wait, from the surface the run was actually told.

Driven through slice 2's fake ACP session (`test_copilot_acp_run_turn.py`), whose `request()` pops
one ordered script, so the order of the wire is the thing under test.
"""

from __future__ import annotations

import pytest

import hub.copilot_acp as copilot_acp
from hub.copilot_acp import run_turn

from .test_copilot_acp_run_turn import (
    AGENT_MODE_URI,
    AGENT_NAME,
    PLAN_MODE_URI,
    SESSION_ID,
    WORK,
    _agent_option,
    _allow_all_option,
    _collector,
    _FakeACPSession,
    _mode_option,
    _patch_spawn,
)

pytestmark = pytest.mark.asyncio

PRE_SPAWN_TOOLS = "## Tools (pre-spawn, must not be sent)"
NOTICE = {"mcp": "NOTICE-MCP", "shim": "NOTICE-SHIM"}
SECTION = {"mcp": "## Tools as MCP", "shim": "## Tools as aw-tool"}


def _opening():
    return [
        {
            "response": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
                "agentInfo": {"name": "Copilot", "title": "Copilot", "version": "1.0.88"},
            }
        },
        {
            "response": {
                "sessionId": SESSION_ID,
                "modes": {"currentModeId": AGENT_MODE_URI},
                "configOptions": [_mode_option(), _agent_option(""), _allow_all_option()],
            }
        },
        {
            "response": {
                "configOptions": [_mode_option(), _agent_option(AGENT_NAME), _allow_all_option()]
            }
        },
    ]


def _mcp_list_reply(text):
    return [
        {
            "notification": "session/update",
            "params": {
                "sessionId": SESSION_ID,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text},
                },
            },
        },
        {"response": {"stopReason": "end_turn"}},
    ]


def _servers_loaded(status):
    return {
        "notification": copilot_acp.RAW_EVENT_METHOD,
        "params": {
            "type": "session.mcp_servers_loaded",
            "data": {"servers": [{"name": "agentweave", "status": status}]},
        },
    }


END = {"response": {"stopReason": "end_turn", "usage": {"inputTokens": 1, "outputTokens": 1}}}


class Harness:
    def __init__(self, *, announced, interrupt_during_wait=False):
        self.announced = announced
        self.waited = 0
        self.rendered = []
        self.statuses = []
        self.events = []
        self.interrupt = {"now": False}
        self.interrupt_during_wait = interrupt_during_wait

    async def await_announce(self):
        self.waited += 1
        if self.interrupt_during_wait:
            self.interrupt["now"] = True
        return self.announced

    async def render_surface(self, surface, tested, quote):
        self.rendered.append((surface, tested, quote))
        return [NOTICE[surface], SECTION[surface]]

    async def on_mcp_status(self, status):
        self.statuses.append(status)


async def _run(monkeypatch, script, harness, *, mcp=True, spec=False, **extra):
    fake = _FakeACPSession(script)
    _patch_spawn(monkeypatch, fake)
    outcome = await run_turn(
        cwd=WORK,
        # A run given the MCP form names the home's MCP config (slice 2's precondition).
        env={"COPILOT_HOME": WORK} if mcp else None,
        prompt="Create a task.",
        model=None,
        resume_session_id=None,
        agent=AGENT_NAME,
        per_turn_context="## Workspace",
        tool_surface_context=PRE_SPAWN_TOOLS,
        stable_context=None,
        control_overrides=None,
        told_access_path="shim",
        permission_mode=None,
        workspace=WORK,
        restrict_spec_writes=spec,
        extra_flags=None,
        mcp_command=["py", "mcp_server.py"] if mcp else None,
        on_event=_collector(harness.events),
        should_interrupt=lambda: harness.interrupt["now"],
        await_mcp_announce=harness.await_announce,
        render_surface=harness.render_surface,
        on_mcp_status=harness.on_mcp_status,
        **extra,
    )
    return fake, outcome


def _prompts(fake):
    return [params["prompt"] for method, params in fake.sent_requests if method == "session/prompt"]


def _modes(fake):
    return [
        params["modeId"] for method, params in fake.sent_requests if method == "session/set_mode"
    ]


async def test_no_announce_sends_mcp_list_then_the_shim_surface(monkeypatch):
    h = Harness(announced=False)
    script = [*_opening(), *_mcp_list_reply("- agentweave (disabled)"), {"response": {}}, END]

    fake, outcome = await _run(monkeypatch, script, h)

    assert outcome.status == "completed"
    diagnostic, model = _prompts(fake)
    assert diagnostic == [{"type": "text", "text": "/mcp list"}]  # one block, nothing else (R3)
    assert h.rendered == [("shim", False, "- agentweave (disabled)")]
    context = model[0]["text"]
    assert NOTICE["shim"] in context and SECTION["shim"] in context
    assert PRE_SPAWN_TOOLS not in context  # the pre-spawn section is replaced, never sent
    assert sum(NOTICE[s] in block["text"] for block in model for s in NOTICE) == 1
    assert model[-1]["text"] == "Create a task."
    methods = [m for m, _ in fake.sent_requests]
    assert methods.index("session/set_mode") > methods.index("session/prompt")  # after the wait


async def test_an_announce_during_the_wait_gives_the_mcp_surface_and_no_mcp_list(monkeypatch):
    h = Harness(announced=True)
    script = [*_opening(), {"response": {}}, END]

    fake, _ = await _run(monkeypatch, script, h)

    (model,) = _prompts(fake)
    assert h.rendered == [("mcp", True, None)]
    assert NOTICE["mcp"] in model[0]["text"] and SECTION["mcp"] in model[0]["text"]
    assert PRE_SPAWN_TOOLS not in model[0]["text"]


async def test_a_run_given_no_server_does_not_wait(monkeypatch):
    h = Harness(announced=True)
    script = [*_opening(), {"response": {}}, END]

    fake, _ = await _run(monkeypatch, script, h, mcp=False)

    assert h.waited == 0
    assert h.rendered == [("shim", None, None)]
    assert len(_prompts(fake)) == 1


async def test_an_interrupt_during_the_wait_ends_the_run_untested(monkeypatch):
    h = Harness(announced=False, interrupt_during_wait=True)
    script = [*_opening()]

    fake, outcome = await _run(monkeypatch, script, h)

    assert outcome.status == "interrupted"
    assert h.rendered == []
    assert _prompts(fake) == []


async def test_a_raw_failed_on_a_run_told_mcp_is_recorded_and_reported_once(monkeypatch):
    """R3: the announce came, the run was told MCP, then Copilot's own report says `failed`."""
    h = Harness(announced=True)
    model_reply = [_servers_loaded("failed"), _servers_loaded("failed"), END]
    script = [*_opening(), {"response": {}}, *model_reply]

    await _run(monkeypatch, script, h)

    assert h.statuses == ["failed", "failed"]
    failures = [e for e in h.events if (e.payload or {}).get("code") == "copilot_mcp_server_failed"]
    assert len(failures) == 1


async def test_a_raw_failed_on_a_run_told_shim_is_no_error(monkeypatch):
    h = Harness(announced=False)
    script = [
        *_opening(),
        *_mcp_list_reply("- agentweave (failed)"),
        {"response": {}},
        _servers_loaded("failed"),
        END,
    ]

    await _run(monkeypatch, script, h)

    assert h.statuses == ["failed"]
    codes = [(e.payload or {}).get("code") for e in h.events]
    assert "copilot_mcp_server_failed" not in codes
    unavailable = [
        e for e in h.events if (e.payload or {}).get("code") == "copilot.mcp_server_unavailable"
    ]
    assert all("HTTP" not in e.content and "aw-tool" in e.content for e in unavailable)


async def test_a_raw_connected_is_a_harness_report(monkeypatch):
    h = Harness(announced=True)
    script = [*_opening(), {"response": {}}, _servers_loaded("connected"), END]

    await _run(monkeypatch, script, h)

    assert h.statuses == ["connected"]


@pytest.mark.parametrize("announced, mode", [(True, PLAN_MODE_URI), (False, AGENT_MODE_URI)])
async def test_plan_mode_follows_the_surface_decided_after_the_wait(monkeypatch, announced, mode):
    """D16: Plan mode is sent after the wait, and only for a spec turn told MCP."""
    monkeypatch.setattr(copilot_acp, "SPEC_TURN_USES_PLAN_MODE", True)
    h = Harness(announced=announced)
    middle = [] if announced else _mcp_list_reply("- agentweave (disabled)")
    script = [*_opening(), *middle, {"response": {}}, END]

    fake, _ = await _run(monkeypatch, script, h, spec=True)

    assert _modes(fake) == [mode]


# --- the trigger's `render_surface` (D9, D12): what it records and writes ------------------------


SURFACES = {
    s: {"notice": NOTICE[s], "tool_surface": SECTION[s], "context": f"# context told {s}\n"}
    for s in ("mcp", "shim")
}


async def _run_row(run_id):
    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    async with async_session_factory() as db:
        db.add(Run(id=run_id, project_id="proj-test", agent="cop", status="running", turn_depth=0))
        await db.commit()


async def _row(run_id):
    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    async with async_session_factory() as db:
        return await db.get(Run, run_id)


async def test_a_timed_out_test_records_absent_shim_and_one_event(app, tmp_path):
    from hub.api.v1.agent_trigger import make_render_surface

    await _run_row("run-rs-timeout")
    (tmp_path / ".agentweave" / "context").mkdir(parents=True)
    events = []
    render = make_render_surface(
        run_id="run-rs-timeout",
        agent="cop",
        work_dir=str(tmp_path),
        surfaces=SURFACES,
        on_event=_collector(events),
    )

    texts = await render("shim", False, "- agentweave (disabled)")

    assert texts == [NOTICE["shim"], SECTION["shim"]]
    row = await _row("run-rs-timeout")
    assert (row.plane_surface, row.harness_mcp_status) == ("shim", "absent")
    context = (tmp_path / ".agentweave" / "context" / "cop.md").read_text(encoding="utf-8")
    assert context == "# context told shim\n"
    (event,) = events
    assert event.payload["phase"] == "plane_surface"
    assert event.payload["summary"] == (
        "The AgentWeave MCP server did not start for this run (absent); the run was told to reach "
        "the Hub with `aw-tool`. The runner reported: - agentweave (disabled)"
    )


async def test_an_announced_run_is_told_mcp_and_says_nothing(app, tmp_path):
    from hub.api.v1.agent_trigger import make_render_surface

    await _run_row("run-rs-ok")
    (tmp_path / ".agentweave" / "context").mkdir(parents=True)
    events = []
    render = make_render_surface(
        run_id="run-rs-ok",
        agent="cop",
        work_dir=str(tmp_path),
        surfaces=SURFACES,
        on_event=_collector(events),
    )

    assert await render("mcp", True, None) == [NOTICE["mcp"], SECTION["mcp"]]
    row = await _row("run-rs-ok")
    assert (row.plane_surface, row.harness_mcp_status) == ("mcp", None)
    assert events == []


async def test_render_surface_is_total(app, tmp_path, monkeypatch):
    """A write that fails is logged; the run is still told (D9)."""
    from hub.api.v1 import agent_trigger
    from hub.api.v1.agent_trigger import make_render_surface

    def broken_factory():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(agent_trigger, "async_session_factory", broken_factory)

    async def broken_event(event):
        raise RuntimeError("no stream")

    render = make_render_surface(
        run_id="run-rs-none",
        agent="cop",
        work_dir=str(tmp_path / "missing"),
        surfaces=SURFACES,
        on_event=broken_event,
    )
    assert await render("shim", False, None) == [NOTICE["shim"], SECTION["shim"]]
