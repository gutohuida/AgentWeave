"""Group D, task 1.13 of `a-copilot-agent-uses-hooks-and-its-own-agents` (design D9): an agent's
`config.copilot_github_mcp` toggle lets a Copilot run keep its built-in MCP servers (GitHub's
among them) instead of disabling them.

**Fail-before evidence (task 1.13's own bullet).** Before this slice, `mcp_server._decide`
already allows a GitHub tool's input unconditionally -- it refuses only through a path key or a
readable `command`, and a GitHub call's `owner`/`repo`/`title` is neither:

    >>> from hub.mcp_server import _decide
    >>> _decide("mcp__github-mcp-server__create_issue", {"owner": "x", "repo": "y", "title": "z"},
    ...         workspace="/work", hub_url="http://127.0.0.1:8010")
    {'allow': True, 'reason': 'inside your workspace'}

So without D9's rule, a Copilot agent run with the toggle on under Workspace only would open
GitHub issues as the operator with no card. `TestDecidePermissionGithubRule` below is what makes
that call `ASK_OPERATOR` instead; `test_fail_before_evidence_the_old_decide_allows_it` records the
`_decide` call above directly, so this file does not merely assert the new behaviour but also
proves the gap it closes.

Scope: the pure functions (`build_acp_argv`, `decide_permission`, `permission_label`,
`workspace_verdict`, `CopilotEventMapper`) are each exercised directly, in the same style
`test_copilot_acp_decide.py` and `test_copilot_acp_mapper.py` already use; the full wiring
(`run_turn` reading `RpcTurnRequest.agent_config`, threading `github_mcp` to all four, and the
spawned argv) is exercised through `test_copilot_acp_run_turn.py`'s own `_drive`/`_new_with`
harness, imported here rather than re-built. `GET /agents` exposing `copilot_github_mcp` in the
roster (the task's last bullet) is a route-level test, reusing `add_agent`/`bind_runner` the way
`test_review_turn_copilot_agents.py` does for `copilot_review_agents`.
"""

from __future__ import annotations

import pytest

from hub.copilot_acp import (
    GITHUB_MCP_SERVER_NAME,
    CallFacts,
    CopilotEventMapper,
    build_acp_argv,
    decide_permission,
    permission_label,
    permission_subject,
    workspace_verdict,
)
from hub.copilot_home import HUB_MCP_SERVER_NAME as AGENTWEAVE_SERVER_NAME
from hub.model_catalog import FULL_ACCESS_PERMISSION_MODE, WORKSPACE_PERMISSION_MODE

from .test_copilot_acp_run_turn import (
    _END_TURN,
    _OPTIONS,
    SESSION_ID,
    _drive,
    _new_with,
    _raw_event,
)

ACCEPT_EDITS = "acceptEdits"
MANUAL = "manual"
HUB_URL = "http://127.0.0.1:8010"


def test_fail_before_evidence_the_old_decide_allows_it(tmp_path):
    """Task 1.13's own fail-before bullet, run for real against `mcp_server._decide` (not a
    canned string): a GitHub tool's input has no path key and no `command`, so today's judge
    allows it with no ground to refuse -- the reason D9's rule is needed at all."""
    from hub.mcp_server import _decide

    result = _decide(
        "mcp__github-mcp-server__create_issue",
        {"owner": "octocat", "repo": "hello-world", "title": "filed by the model"},
        workspace=str(tmp_path),
        hub_url=HUB_URL,
    )
    assert result == {"allow": True, "reason": "inside your workspace"}


# --- `build_acp_argv` ------------------------------------------------------------------------


class TestBuildAcpArgv:
    def test_disable_builtin_mcps_present_by_default(self):
        argv = build_acp_argv("copilot.exe")
        assert "--disable-builtin-mcps" in argv

    def test_disable_builtin_mcps_present_when_toggle_is_false(self):
        argv = build_acp_argv("copilot.exe", github_mcp=False)
        assert "--disable-builtin-mcps" in argv

    def test_disable_builtin_mcps_omitted_when_toggle_is_true(self):
        argv = build_acp_argv("copilot.exe", github_mcp=True)
        assert "--disable-builtin-mcps" not in argv


# --- `decide_permission` ----------------------------------------------------------------------


def _params(*, tool_call_id="call_1", kind="other", raw_input=None, title="probe"):
    return {
        "sessionId": "sess-1",
        "toolCall": {
            "toolCallId": tool_call_id,
            "title": title,
            "kind": kind,
            "status": "pending",
            "rawInput": raw_input or {},
        },
        "options": _OPTIONS,
    }


AGENTWEAVE_SERVERS = {
    "agentweave": [{"name": "agentweave", "status": "connected"}],
}


def _decide(
    params,
    posture,
    workspace,
    calls=None,
    *,
    github_mcp=False,
    servers=AGENTWEAVE_SERVERS,
):
    return decide_permission(
        params,
        posture=posture,
        workspace=str(workspace),
        hub_url=HUB_URL,
        calls=calls or {},
        servers=servers,
        github_mcp=github_mcp,
    )


class TestDecidePermissionGithubRule:
    """D9 (design.md:998-1123): with the toggle on, a reported MCP server that is not
    `agentweave` is the operator's call under `workspace` -- before `_decide`/`_judge` is
    reached. `manual`, full access and `acceptEdits` already answer the way the rule asks for
    without any change (ASK_OPERATOR, ALLOW, REJECT respectively), so those are regression
    checks, not new behaviour."""

    def _calls(self, server="github-mcp-server", tool="create_issue"):
        return {
            "call_gh": CallFacts(tool_name=None, mcp_server=server, mcp_tool=tool),
        }

    def test_workspace_asks_the_operator_with_the_toggle_on(self, tmp_path):
        params = _params(tool_call_id="call_gh", raw_input={"owner": "o", "repo": "r"})
        result = _decide(
            params, WORKSPACE_PERMISSION_MODE, tmp_path, self._calls(), github_mcp=True
        )
        assert result["outcome"] == "ASK_OPERATOR"

    def test_workspace_still_allows_with_the_toggle_off(self, tmp_path):
        """Unaffected: `github_mcp=False` leaves slice 2's rows (foreign MCP falls to `_judge`,
        which allows input naming no path and no command) exactly as before."""
        params = _params(tool_call_id="call_gh", raw_input={"owner": "o", "repo": "r"})
        result = _decide(
            params, WORKSPACE_PERMISSION_MODE, tmp_path, self._calls(), github_mcp=False
        )
        assert result["outcome"] == "ALLOW"

    def test_accept_edits_stays_refused_with_the_toggle_on(self, tmp_path):
        params = _params(tool_call_id="call_gh", raw_input={})
        result = _decide(params, ACCEPT_EDITS, tmp_path, self._calls(), github_mcp=True)
        assert result["outcome"] == "REJECT"

    def test_full_access_is_allowed_with_the_toggle_on(self, tmp_path):
        params = _params(tool_call_id="call_gh", raw_input={})
        result = _decide(
            params, FULL_ACCESS_PERMISSION_MODE, tmp_path, self._calls(), github_mcp=True
        )
        assert result["outcome"] == "ALLOW"

    def test_manual_asks_the_operator_with_the_toggle_on(self, tmp_path):
        params = _params(tool_call_id="call_gh", raw_input={})
        result = _decide(params, MANUAL, tmp_path, self._calls(), github_mcp=True)
        assert result["outcome"] == "ASK_OPERATOR"

    def test_a_different_reported_server_is_also_asked_under_workspace(self, tmp_path):
        """Review 2026-09-28, finding 4: the rule matches everything that is not `agentweave`,
        not only the literal name `github-mcp-server` -- Copilot's built-in list is plural and
        not fully visible, so a non-GitHub built-in server must ask too."""
        params = _params(tool_call_id="call_gh", raw_input={})
        calls = self._calls(server="some-other-builtin-server", tool="do_a_thing")
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path, calls, github_mcp=True)
        assert result["outcome"] == "ASK_OPERATOR"

    def test_an_unidentified_server_is_rejected_outright_whatever_the_toggle(self, tmp_path):
        """DECIDED 2026-09-28, finding 5: slice 2's identify step REJECTs a request whose server
        Copilot did not report before this rule ever runs, in every posture and whatever the
        toggle -- it is never treated as a foreign/GitHub server."""
        params = _params(tool_call_id="call_unknown", raw_input={})
        for github_mcp in (True, False):
            for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS):
                result = _decide(params, posture, tmp_path, calls={}, github_mcp=github_mcp)
                assert result["outcome"] == "REJECT", (github_mcp, posture)
            result = _decide(params, MANUAL, tmp_path, calls={}, github_mcp=github_mcp)
            assert result["outcome"] == "ASK_OPERATOR", github_mcp

    def test_the_agentweave_server_is_decided_exactly_as_before(self, tmp_path):
        """The rule exempts `agentweave`: with the toggle on, the Hub's own server's calls are
        still the Hub's own tools, allowed under every posture that reaches it."""
        params = _params(tool_call_id="call_hub", raw_input={})
        calls = {
            "call_hub": CallFacts(tool_name=None, mcp_server="agentweave", mcp_tool="list_tasks")
        }
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS, FULL_ACCESS_PERMISSION_MODE):
            result = _decide(params, posture, tmp_path, calls, github_mcp=True)
            assert result["outcome"] == "ALLOW", posture


# --- `permission_label` / `permission_subject` ------------------------------------------------


class TestPermissionLabel:
    def test_github_server_gets_the_github_sentence_with_the_toggle_on(self):
        calls = {
            "c": CallFacts(tool_name=None, mcp_server="github-mcp-server", mcp_tool="create_issue")
        }
        params = _params(tool_call_id="c")
        label = permission_label(params, calls, github_mcp=True)
        assert label == "github-mcp-server/create_issue — acts on GitHub as you"

    def test_a_different_reported_server_names_itself_not_github(self):
        """Review 2026-09-28, finding 4: a card must never claim GitHub for a server that is
        not GitHub."""
        calls = {"c": CallFacts(tool_name=None, mcp_server="some-other-server", mcp_tool="ping")}
        params = _params(tool_call_id="c")
        label = permission_label(params, calls, github_mcp=True)
        assert (
            label
            == "some-other-server/ping — a tool of MCP server some-other-server, not the Hub's"
        )
        assert "github" not in label.lower()

    def test_agentweave_label_is_unaffected_by_the_toggle(self):
        calls = {"c": CallFacts(tool_name=None, mcp_server="agentweave", mcp_tool="list_tasks")}
        params = _params(tool_call_id="c")
        assert permission_label(params, calls, github_mcp=True) == "agentweave/list_tasks"
        assert permission_label(params, calls, github_mcp=False) == "agentweave/list_tasks"

    def test_github_server_label_is_plain_with_the_toggle_off(self):
        calls = {
            "c": CallFacts(tool_name=None, mcp_server="github-mcp-server", mcp_tool="create_issue")
        }
        params = _params(tool_call_id="c")
        assert permission_label(params, calls, github_mcp=False) == "github-mcp-server/create_issue"

    def test_permission_subject_threads_the_toggle_into_tool_name(self):
        calls = {"c": CallFacts(tool_name=None, mcp_server="github-mcp-server", mcp_tool="x")}
        params = _params(tool_call_id="c")
        subject = permission_subject(params, calls, github_mcp=True)
        assert subject["tool_name"] == "github-mcp-server/x — acts on GitHub as you"


# --- `workspace_verdict` ----------------------------------------------------------------------


class TestWorkspaceVerdictNone:
    """D9, R3 (design.md:1075-1094): a two-valued `allow` cannot say "Workspace only would ask
    you too" -- so for a request D9's own rule sends to the operator, the Copilot
    `workspace_verdict` is `None`, not a computed `{allow: False, ...}`."""

    def test_none_for_a_github_request_with_the_toggle_on(self, tmp_path):
        calls = {"c": CallFacts(tool_name=None, mcp_server="github-mcp-server", mcp_tool="x")}
        params = _params(tool_call_id="c")
        verdict = workspace_verdict(
            params, str(tmp_path), hub_url=HUB_URL, calls=calls, github_mcp=True
        )
        assert verdict is None

    def test_none_for_any_other_reported_server_with_the_toggle_on(self, tmp_path):
        calls = {"c": CallFacts(tool_name=None, mcp_server="some-other-server", mcp_tool="x")}
        params = _params(tool_call_id="c")
        verdict = workspace_verdict(
            params, str(tmp_path), hub_url=HUB_URL, calls=calls, github_mcp=True
        )
        assert verdict is None

    def test_still_computed_for_an_ordinary_request(self, tmp_path):
        """Regression: a request the D9 rule does not touch (an ordinary command) still gets a
        real `{allow, reason}` verdict, toggle or no toggle."""
        params = _params(kind="execute", raw_input={"command": "Get-ChildItem"})
        for github_mcp in (True, False):
            verdict = workspace_verdict(
                params, str(tmp_path), hub_url=HUB_URL, calls={}, github_mcp=github_mcp
            )
            assert verdict is not None
            assert verdict["allow"] is True

    def test_still_computed_for_the_agentweave_server_with_the_toggle_on(self, tmp_path):
        calls = {"c": CallFacts(tool_name=None, mcp_server="agentweave", mcp_tool="list_tasks")}
        params = _params(tool_call_id="c")
        verdict = workspace_verdict(
            params, str(tmp_path), hub_url=HUB_URL, calls=calls, github_mcp=True
        )
        assert verdict is not None
        assert verdict["allow"] is True


# --- `CopilotEventMapper`'s unavailable-server diagnostic -------------------------------------


def _mcp_servers_loaded(name, status):
    data = {"servers": [{"name": name, "status": status}]}
    params = {
        "sessionId": "synthetic-session",
        "type": "session.mcp_servers_loaded",
        "timestamp": "2026-10-03T00:00:00.000Z",
        "data": data,
    }
    return "session.mcp_servers_loaded", data, params


class TestGithubMcpUnavailableDiagnostic:
    """Design.md:1103-1123 (R3): a raw status naming `github-mcp-server` in a state other than
    `pending`/`connected` gives one `copilot.github_mcp_unavailable` diagnostic per turn, only
    while the toggle is on."""

    @pytest.mark.parametrize(
        "status", ["failed", "needs-auth", "disabled", "stopped", "not_configured"]
    )
    def test_each_unavailable_status_gives_one_diagnostic_with_the_toggle_on(self, status):
        mapper = CopilotEventMapper(github_mcp=True)
        type_, data, params = _mcp_servers_loaded(GITHUB_MCP_SERVER_NAME, status)
        events = mapper.on_raw_event(type_, data, params)
        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert len(diagnostics) == 1, status
        assert diagnostics[0].payload["code"] == "copilot.github_mcp_unavailable"

    @pytest.mark.parametrize("status", ["pending", "connected"])
    def test_pending_and_connected_report_nothing(self, status):
        mapper = CopilotEventMapper(github_mcp=True)
        type_, data, params = _mcp_servers_loaded(GITHUB_MCP_SERVER_NAME, status)
        events = mapper.on_raw_event(type_, data, params)
        assert not any(e.kind == "diagnostic" for e in events)

    def test_nothing_reported_with_the_toggle_off(self):
        """The toggle off disables the server on purpose; the task's own words: 'with the
        toggle off, nothing is reported.'"""
        mapper = CopilotEventMapper(github_mcp=False)
        type_, data, params = _mcp_servers_loaded(GITHUB_MCP_SERVER_NAME, "failed")
        events = mapper.on_raw_event(type_, data, params)
        assert events == []

    def test_once_per_turn(self):
        mapper = CopilotEventMapper(github_mcp=True)
        type_, data, params = _mcp_servers_loaded(GITHUB_MCP_SERVER_NAME, "failed")
        first = mapper.on_raw_event(type_, data, params)
        second = mapper.on_raw_event(type_, data, params)
        assert len([e for e in first if e.kind == "diagnostic"]) == 1
        assert len([e for e in second if e.kind == "diagnostic"]) == 0

    def test_the_agentweave_diagnostic_is_unaffected(self):
        """The two servers' failure-reporting are independent: a failed `agentweave` with the
        GitHub toggle on still gives the pre-existing `copilot.mcp_server_unavailable`, and a
        failed GitHub server does not suppress or duplicate it."""
        mapper = CopilotEventMapper(github_mcp=True, told_access_path="cli")
        type_, data, params = _mcp_servers_loaded(AGENTWEAVE_SERVER_NAME, "failed")
        events = mapper.on_raw_event(type_, data, params)
        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert len(diagnostics) == 1
        assert diagnostics[0].payload["code"] == "copilot.mcp_server_unavailable"


# --- Full wiring, through `run_turn` -----------------------------------------------------------


class TestRunTurnThreadsAgentConfig:
    """`run_turn` reads `agent_config.get("copilot_github_mcp") is True` (finding 14: a stored
    `"false"` string is not the operator's choice) and passes it to the argv builder, the judge
    and the mapper alike -- exercised here through the real `run_turn`, not re-derived."""

    async def test_toggle_true_omits_disable_builtin_mcps_on_the_real_spawn(self, monkeypatch):
        captured: list = []
        await _drive(
            monkeypatch,
            _new_with() + [_END_TURN],
            captured_cmds=captured,
            agent_config={"copilot_github_mcp": True},
        )
        assert "--disable-builtin-mcps" not in captured[0]

    async def test_toggle_absent_keeps_disable_builtin_mcps(self, monkeypatch):
        captured: list = []
        await _drive(
            monkeypatch,
            _new_with() + [_END_TURN],
            captured_cmds=captured,
            agent_config=None,
        )
        assert "--disable-builtin-mcps" in captured[0]

    async def test_a_stored_string_false_is_not_treated_as_true(self, monkeypatch):
        """Finding 14: `POST`/`PATCH` stores a raw `config`, and `"false"` as a string is
        truthy in Python -- `run_turn` must read it as `is True`, not `bool(...)`."""
        captured: list = []
        await _drive(
            monkeypatch,
            _new_with() + [_END_TURN],
            captured_cmds=captured,
            agent_config={"copilot_github_mcp": "false"},
        )
        assert "--disable-builtin-mcps" in captured[0]

    async def test_a_github_mcp_request_is_asked_with_the_github_label_and_no_verdict(
        self, monkeypatch
    ):
        """End to end: a raw `tool.execution_start` naming `github-mcp-server`, then its
        `session/request_permission`, under `workspace` with the toggle on -- the operator is
        asked, the card names GitHub, and the Workspace-only verdict is `None` (design.md:
        1075-1094)."""
        asked = []

        async def request_approval(method, subject):
            asked.append((method, subject))
            return False

        call_id = "call_gh_live"
        start = _raw_event(
            "tool.execution_start",
            {
                "toolCallId": call_id,
                "toolName": "github-mcp-server-create_issue",
                "arguments": {"owner": "o", "repo": "r"},
                "mcpServerName": "github-mcp-server",
                "mcpToolName": "create_issue",
            },
        )
        permission_request = {
            "server_request": {
                "id": 9,
                "method": "session/request_permission",
                "params": {
                    "sessionId": SESSION_ID,
                    "toolCall": {
                        "toolCallId": call_id,
                        "title": "create_issue",
                        "kind": "other",
                        "status": "pending",
                        "rawInput": {"owner": "o", "repo": "r"},
                    },
                    "options": _OPTIONS,
                },
            }
        }
        script = _new_with() + [start, permission_request, _END_TURN]
        await _drive(
            monkeypatch,
            script,
            permission_mode=None,  # unset -> `workspace` (no `yolo`)
            agent_config={"copilot_github_mcp": True},
            request_approval=request_approval,
        )

        assert len(asked) == 1
        _, subject = asked[0]
        assert subject["tool_name"] == "github-mcp-server/create_issue — acts on GitHub as you"
        assert subject["workspace_verdict"] is None

    async def test_a_github_mcp_diagnostic_reaches_the_timeline_with_the_toggle_on(
        self, monkeypatch
    ):
        events: list = []

        async def on_event(event):
            events.append(event)

        loaded = _raw_event(
            "session.mcp_servers_loaded",
            {"servers": [{"name": "github-mcp-server", "status": "failed"}]},
        )
        script = _new_with(loaded) + [_END_TURN]
        await _drive(
            monkeypatch,
            script,
            agent_config={"copilot_github_mcp": True},
            on_event=on_event,
        )

        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert any(d.payload["code"] == "copilot.github_mcp_unavailable" for d in diagnostics)

    async def test_no_github_mcp_diagnostic_with_the_toggle_off(self, monkeypatch):
        events: list = []

        async def on_event(event):
            events.append(event)

        loaded = _raw_event(
            "session.mcp_servers_loaded",
            {"servers": [{"name": "github-mcp-server", "status": "failed"}]},
        )
        script = _new_with(loaded) + [_END_TURN]
        await _drive(
            monkeypatch,
            script,
            agent_config=None,
            on_event=on_event,
        )

        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert not any(d.payload["code"] == "copilot.github_mcp_unavailable" for d in diagnostics)


# --- `GET /agents` roster exposure --------------------------------------------------------------

PROJECT = "proj-test"
P = f"/api/v1/projects/{PROJECT}"


class TestRosterExposure:
    """Task 1.13's last bullet: `GET /agents` returns `copilot_github_mcp` in the agent's
    `config` -- it must be in `ROSTER_CONFIG_KEYS` (`api/v1/agents.py`), the same allow-list
    `copilot_review_agents` already goes through."""

    async def test_copilot_github_mcp_round_trips_through_the_roster(
        self, app, auth_headers, add_agent, bind_runner
    ):
        await add_agent("cp1")
        await bind_runner("cp1", cli="copilot")
        patched = await app.patch(
            f"{P}/agents/cp1",
            json={"config": {"copilot_github_mcp": True}},
            headers=auth_headers,
        )
        assert patched.status_code == 200, patched.text

        roster = await app.get(f"{P}/agents", headers=auth_headers)
        [cp1] = [row for row in roster.json() if row["name"] == "cp1"]
        assert cp1["config"]["copilot_github_mcp"] is True

    async def test_absent_by_default(self, app, auth_headers, add_agent, bind_runner):
        await add_agent("cp2")
        await bind_runner("cp2", cli="copilot")
        roster = await app.get(f"{P}/agents", headers=auth_headers)
        [cp2] = [row for row in roster.json() if row["name"] == "cp2"]
        assert "copilot_github_mcp" not in cp2["config"]


# --- D9a (amendment 2026-10-04, F485): GitHub write tools only under Full access -------------


class TestGithubWriteToolFlagsAreWidening:
    """F485: with the toggle on, Copilot loads only its read-only GitHub tools and runs them
    without asking (`mcp-read-only`), so no card can come from them. What adds write tools is a
    runner flag: `--enable-all-github-mcp-tools`, `--add-github-mcp-toolset <t>`,
    `--add-github-mcp-tool <t>` (clap help: one value each, repeatable, like `--add-dir`), or
    `--additional-mcp-config`, which adds any server (pre-approval review, finding 2). Each is a
    widening flag: removed outside Full access. Fails today: none is in the table."""

    FLAGS = [
        "--enable-all-github-mcp-tools",
        "--add-github-mcp-toolset",
        "issues",
        "--add-github-mcp-tool",
        "create_issue",
        "--additional-mcp-config",
        "@C:/elsewhere/servers.json",
        "--model",
        "x",
    ]

    def test_outside_full_access_only_the_ordinary_flags_are_kept(self):
        from hub.copilot_acp import strip_widening_flags

        kept, removed = strip_widening_flags(self.FLAGS, full_access=False)
        assert kept == ["--model", "x"]
        assert removed == [
            "--enable-all-github-mcp-tools",
            "--add-github-mcp-toolset",
            "--add-github-mcp-tool",
            "--additional-mcp-config",
        ]

    def test_under_full_access_all_are_kept(self):
        from hub.copilot_acp import strip_widening_flags

        kept, removed = strip_widening_flags(self.FLAGS, full_access=True)
        assert kept == self.FLAGS and removed == []

    def test_the_equals_forms_are_removed_too(self):
        from hub.copilot_acp import strip_widening_flags

        kept, removed = strip_widening_flags(
            [
                "--add-github-mcp-toolset=all",
                "--add-github-mcp-tool=*",
                "--additional-mcp-config=@x",
            ],
            full_access=False,
        )
        assert kept == [] and len(removed) == 3

    def test_each_add_flag_takes_exactly_one_value(self):
        from hub.copilot_acp import strip_widening_flags

        kept, _removed = strip_widening_flags(
            ["--add-github-mcp-tool", "a", "b", "--add-github-mcp-toolset", "c", "d"],
            full_access=False,
        )
        assert kept == ["b", "d"]


class TestRunTurnRemovesGithubWriteToolFlags:
    async def test_the_flag_is_absent_from_the_spawn_under_workspace_and_said_plainly(
        self, monkeypatch
    ):
        captured: list = []
        _fake, events, _outcome = await _drive(
            monkeypatch,
            _new_with() + [_END_TURN],
            captured_cmds=captured,
            permission_mode=WORKSPACE_PERMISSION_MODE,
            extra_flags=["--enable-all-github-mcp-tools"],
            agent_config={"copilot_github_mcp": True},
        )
        assert "--enable-all-github-mcp-tools" not in captured[0]
        removed = [
            e
            for e in events
            if e.kind == "diagnostic" and e.payload.get("code") == "copilot.runner_flag_removed"
        ]
        assert [e.payload["facts"]["flag"] for e in removed] == ["--enable-all-github-mcp-tools"]
        assert "adds GitHub tools that write" in removed[0].content
        assert "its own account" not in removed[0].content

    async def test_the_flag_stays_under_full_access(self, monkeypatch):
        captured: list = []
        await _drive(
            monkeypatch,
            _new_with() + [_END_TURN],
            captured_cmds=captured,
            permission_mode=FULL_ACCESS_PERMISSION_MODE,
            extra_flags=["--enable-all-github-mcp-tools"],
            agent_config={"copilot_github_mcp": True},
        )
        assert "--enable-all-github-mcp-tools" in captured[0]

    @pytest.mark.parametrize("posture", [WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS, MANUAL])
    async def test_a_runners_additional_mcp_config_goes_and_the_hubs_own_stays(
        self, monkeypatch, tmp_path, posture
    ):
        captured: list = []
        _fake, events, _outcome = await _drive(
            monkeypatch,
            _new_with() + [_END_TURN],
            captured_cmds=captured,
            permission_mode=posture,
            env={"COPILOT_HOME": str(tmp_path)},
            mcp_command=["python", "mcp_server.py"],
            extra_flags=["--additional-mcp-config", "@C:/elsewhere/servers.json"],
        )
        argv = captured[0]
        assert "@C:/elsewhere/servers.json" not in argv
        hubs = [argv[i + 1] for i, word in enumerate(argv) if word == "--additional-mcp-config"]
        assert len(hubs) == 1 and hubs[0].startswith("@") and str(tmp_path) in hubs[0]
        removed = [
            e
            for e in events
            if e.kind == "diagnostic" and e.payload.get("code") == "copilot.runner_flag_removed"
        ]
        assert "adds MCP servers" in removed[0].content
