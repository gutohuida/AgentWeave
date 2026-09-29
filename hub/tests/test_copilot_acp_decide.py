"""`decide_permission` (design D8): the pure judge Copilot's `session/request_permission`
answers go through, `decide_permission(params, *, posture, workspace, hub_url, calls,
spec_turn=False) -> {"outcome": "ALLOW"|"REJECT"|"ASK_OPERATOR", "reason": str}`.

The module does not exist yet, so every test below fails at collection today
(`ModuleNotFoundError: No module named 'hub.copilot_acp'`) — task 3.x adds it against this file.

Scope of this slice (task 1.6, part 1 of N — the task's own note says to split across firings
rather than leave the checkbox covering an incomplete list): the base D8 table
(design.md:634-645) for each `toolCall.kind`, across the four postures
(`workspace`, `acceptEdits`, `manual`, `bypassPermissions`/full access), plus the task's five
explicitly named baseline bullets ("a PowerShell command writing `..\\..\\x` refused under
`workspace`", "`agentweave` MCP allowed under `manual`", "a foreign MCP server judged",
"`memory` refused"). `spec_turn=True` is never exercised here.

Part 2 of N adds the `spec_turn=True` rows (tasks.md bullets 1-2; D9 item 1a, design.md:896-908;
operator decision 2026-09-28, open question 13, option (c), design.md:666-669, 796-812):
`TestSpecTurn` below.

Deliberately NOT covered here (left for a follow-up sub-task of 1.6):
  - R2/R3's MCP-server-identification edge cases (raw `tool.execution_start` vs. a foreign
    `tool_call` title, `agentweave-x`, the Hub-own load-time condition / `session.mcp_servers_loaded`
    source+transport check — reviews findings 5 and 6);
  - review finding 2's `fetch`-vs-shell-classified-`url` rows in full (only the plain
    `web_fetch`/bypass rows are covered here);
  - review finding 1/slice 3's `write_powershell`/`local_shell` execute-shape rows;
  - "the answer never being `allow_always`" — that is a property of the RPC-answering step
    (D8 § Answering), a different function than `decide_permission`, and belongs with whatever
    task tests it.
  - "(R2) an unset `permission_mode` judged exactly as `workspace`" — that's `posture_for`,
    not `decide_permission` (D8's own posture-mapping table, design.md:654-660), tested
    alongside that function instead.

One open question this slice surfaced rather than guessed an answer to: design.md's `fetch` +
`requestSandboxBypass: true` row (finding 2) only gives `workspace`/`acceptEdits` cells
(both REJECT); nothing in the doc says what `manual` or full access do with it, so this file
does not assert either. Recorded in the night log rather than invented here.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from hub.copilot_acp import CallFacts, decide_permission
from hub.model_catalog import FULL_ACCESS_PERMISSION_MODE, WORKSPACE_PERMISSION_MODE

ACCEPT_EDITS = "acceptEdits"
MANUAL = "manual"
HUB_URL = "http://127.0.0.1:8010"

ALL_POSTURES = (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS, MANUAL, FULL_ACCESS_PERMISSION_MODE)


def _params(
    *,
    tool_call_id: str = "call_1",
    kind: str,
    raw_input: Optional[Dict[str, Any]] = None,
    locations: Optional[list] = None,
    title: str = "probe",
) -> Dict[str, Any]:
    tool_call: Dict[str, Any] = {
        "toolCallId": tool_call_id,
        "title": title,
        "kind": kind,
        "status": "pending",
        "rawInput": raw_input or {},
    }
    if locations is not None:
        tool_call["locations"] = locations
    return {
        "sessionId": "sess-1",
        "toolCall": tool_call,
        "options": [
            {"optionId": "allow_once", "kind": "allow_once", "name": "Allow once"},
            {"optionId": "allow_always", "kind": "allow_always", "name": "Always allow"},
            {"optionId": "reject_once", "kind": "reject_once", "name": "Deny"},
        ],
    }


def _decide(params, posture, workspace, calls=None, spec_turn=False):
    return decide_permission(
        params,
        posture=posture,
        workspace=str(workspace),
        hub_url=HUB_URL,
        calls=calls or {},
        spec_turn=spec_turn,
    )


class TestExecute:
    """design.md:636 — `kind:"execute"`, `rawInput.command`."""

    def test_command_naming_a_path_outside_the_workspace_is_refused_under_workspace(
        self, tmp_path
    ):
        params = _params(kind="execute", raw_input={"command": "Remove-Item ..\\..\\x"})
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "REJECT"

    def test_harmless_command_is_allowed_under_workspace(self, tmp_path):
        params = _params(kind="execute", raw_input={"command": "Get-ChildItem"})
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "ALLOW"

    @pytest.mark.parametrize("command", ["Get-ChildItem", "Remove-Item ..\\..\\x"])
    def test_every_execute_request_is_rejected_under_accept_edits(self, tmp_path, command):
        params = _params(kind="execute", raw_input={"command": command})
        result = _decide(params, ACCEPT_EDITS, tmp_path)
        assert result["outcome"] == "REJECT"

    def test_execute_asks_the_operator_under_manual(self, tmp_path):
        params = _params(kind="execute", raw_input={"command": "Get-ChildItem"})
        result = _decide(params, MANUAL, tmp_path)
        assert result["outcome"] == "ASK_OPERATOR"

    def test_execute_is_allowed_under_full_access(self, tmp_path):
        params = _params(kind="execute", raw_input={"command": "Remove-Item ..\\..\\x"})
        result = _decide(params, FULL_ACCESS_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "ALLOW"

    def test_command_that_is_not_a_non_empty_string_is_rejected(self, tmp_path):
        """`write_powershell`-shaped input (`{shellId, input}`) has no `command` key."""
        params = _params(kind="execute", raw_input={"shellId": "s1", "input": "hi"})
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "REJECT"


class TestEdit:
    """design.md:637 — `kind:"edit"`, `locations[].path` / `rawInput.fileName`."""

    def test_edit_inside_the_workspace_is_allowed_under_workspace_and_accept_edits(self, tmp_path):
        target = str(tmp_path / "probe.txt")
        params = _params(kind="edit", locations=[{"path": target}])
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS):
            result = _decide(params, posture, tmp_path)
            assert result["outcome"] == "ALLOW", posture

    def test_edit_outside_the_workspace_is_refused_under_workspace_and_accept_edits(self, tmp_path):
        params = _params(kind="edit", locations=[{"path": "C:\\Windows\\System32\\evil.txt"}])
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS):
            result = _decide(params, posture, tmp_path)
            assert result["outcome"] == "REJECT", posture

    def test_edit_with_no_path_at_all_is_refused(self, tmp_path):
        """(R2) an `edit` request with no `locations` and no `fileName` — never allowed by an
        empty per-path loop."""
        params = _params(kind="edit", raw_input={})
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS):
            result = _decide(params, posture, tmp_path)
            assert result["outcome"] == "REJECT", posture

    def test_edit_asks_the_operator_under_manual(self, tmp_path):
        params = _params(kind="edit", locations=[{"path": str(tmp_path / "probe.txt")}])
        result = _decide(params, MANUAL, tmp_path)
        assert result["outcome"] == "ASK_OPERATOR"

    def test_edit_is_allowed_under_full_access(self, tmp_path):
        params = _params(kind="edit", locations=[{"path": "C:\\Windows\\System32\\evil.txt"}])
        result = _decide(params, FULL_ACCESS_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "ALLOW"


class TestRead:
    """design.md:638 — `kind:"read"`, `rawInput.path` (or `locations[0].path`)."""

    def test_read_inside_the_workspace_is_allowed_under_workspace_and_accept_edits(self, tmp_path):
        target = str(tmp_path / "probe.txt")
        params = _params(kind="read", raw_input={"path": target})
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS):
            result = _decide(params, posture, tmp_path)
            assert result["outcome"] == "ALLOW", posture

    def test_read_outside_the_workspace_is_refused_under_workspace_and_accept_edits(self, tmp_path):
        params = _params(kind="read", raw_input={"path": "C:\\Windows\\System32\\secret.txt"})
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS):
            result = _decide(params, posture, tmp_path)
            assert result["outcome"] == "REJECT", posture

    def test_read_with_no_path_at_all_is_refused(self, tmp_path):
        """(R3) a `read` request with no `rawInput.path` and no `locations` → REJECT."""
        params = _params(kind="read", raw_input={})
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS):
            result = _decide(params, posture, tmp_path)
            assert result["outcome"] == "REJECT", posture

    def test_read_asks_the_operator_under_manual(self, tmp_path):
        params = _params(kind="read", raw_input={"path": str(tmp_path / "probe.txt")})
        result = _decide(params, MANUAL, tmp_path)
        assert result["outcome"] == "ASK_OPERATOR"

    def test_read_is_allowed_under_full_access(self, tmp_path):
        params = _params(kind="read", raw_input={"path": "C:\\Windows\\System32\\secret.txt"})
        result = _decide(params, FULL_ACCESS_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "ALLOW"


class TestFetch:
    """design.md:639-641 — `kind:"fetch"`."""

    def test_web_fetch_is_allowed_under_workspace_and_full_access(self, tmp_path):
        params = _params(tool_call_id="call_f1", kind="fetch", raw_input={"url": "http://x/"})
        calls = {"call_f1": CallFacts(tool_name="web_fetch", mcp_server=None, mcp_tool=None)}
        for posture in (WORKSPACE_PERMISSION_MODE, FULL_ACCESS_PERMISSION_MODE):
            result = _decide(params, posture, tmp_path, calls)
            assert result["outcome"] == "ALLOW", posture

    def test_web_fetch_is_rejected_under_accept_edits(self, tmp_path):
        params = _params(tool_call_id="call_f1", kind="fetch", raw_input={"url": "http://x/"})
        calls = {"call_f1": CallFacts(tool_name="web_fetch", mcp_server=None, mcp_tool=None)}
        result = _decide(params, ACCEPT_EDITS, tmp_path, calls)
        assert result["outcome"] == "REJECT"

    def test_web_fetch_asks_the_operator_under_manual(self, tmp_path):
        params = _params(tool_call_id="call_f1", kind="fetch", raw_input={"url": "http://x/"})
        calls = {"call_f1": CallFacts(tool_name="web_fetch", mcp_server=None, mcp_tool=None)}
        result = _decide(params, MANUAL, tmp_path, calls)
        assert result["outcome"] == "ASK_OPERATOR"

    def test_fetch_with_sandbox_bypass_is_refused_under_workspace_and_accept_edits(self, tmp_path):
        """(review, finding 2) 'a request to bypass Copilot's sandbox is not something this
        Hub grants' — out of scope regardless of the URL."""
        params = _params(
            tool_call_id="call_f1",
            kind="fetch",
            raw_input={"url": "https://example.com", "requestSandboxBypass": True},
        )
        calls = {"call_f1": CallFacts(tool_name="web_fetch", mcp_server=None, mcp_tool=None)}
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS):
            result = _decide(params, posture, tmp_path, calls)
            assert result["outcome"] == "REJECT", posture


class TestMcp:
    """design.md:642-645 — `kind:"other"`."""

    def test_hub_own_tool_is_allowed_under_workspace_accept_edits_and_full_access(self, tmp_path):
        params = _params(tool_call_id="call_m1", kind="other", raw_input={})
        calls = {
            "call_m1": CallFacts(tool_name=None, mcp_server="agentweave", mcp_tool="list_tasks")
        }
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS, FULL_ACCESS_PERMISSION_MODE):
            result = _decide(params, posture, tmp_path, calls)
            assert result["outcome"] == "ALLOW", posture

    def test_agentweave_mcp_allowed_under_manual(self, tmp_path):
        """Task 1.6's own bullet: '`agentweave` MCP allowed under `manual`'
        (design.md:763, "as `approve_tool_call` does")."""
        params = _params(tool_call_id="call_m1", kind="other", raw_input={})
        calls = {
            "call_m1": CallFacts(tool_name=None, mcp_server="agentweave", mcp_tool="send_message")
        }
        result = _decide(params, MANUAL, tmp_path, calls)
        assert result["outcome"] == "ALLOW"

    def test_a_foreign_mcp_server_is_judged(self, tmp_path):
        """Task 1.6's own bullet: 'a foreign MCP server judged' — args naming a path outside
        the workspace are refused exactly as a shell/edit request would be."""
        params = _params(
            tool_call_id="call_m2",
            kind="other",
            raw_input={"path": "C:\\Windows\\System32\\secret.txt"},
        )
        calls = {
            "call_m2": CallFacts(
                tool_name=None, mcp_server="some-other-server", mcp_tool="read_file"
            )
        }
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path, calls)
        assert result["outcome"] == "REJECT"

    def test_a_foreign_mcp_server_is_rejected_outright_under_accept_edits(self, tmp_path):
        params = _params(tool_call_id="call_m2", kind="other", raw_input={})
        calls = {
            "call_m2": CallFacts(
                tool_name=None, mcp_server="some-other-server", mcp_tool="read_file"
            )
        }
        result = _decide(params, ACCEPT_EDITS, tmp_path, calls)
        assert result["outcome"] == "REJECT"

    def test_a_foreign_mcp_call_naming_no_path_and_no_command_is_allowed_under_workspace(
        self, tmp_path
    ):
        """R3, for slice 5: Claude parity — `_decide` allows a call whose arguments name no
        path and no command."""
        params = _params(tool_call_id="call_m3", kind="other", raw_input={"note": "hi"})
        calls = {
            "call_m3": CallFacts(
                tool_name=None, mcp_server="some-other-server", mcp_tool="ping"
            )
        }
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path, calls)
        assert result["outcome"] == "ALLOW"

    def test_mcp_request_with_no_identified_server_is_rejected_under_every_posture(self, tmp_path):
        """design.md:583-585, 704-709 — answered at step 1, before any server-specific rule
        (slice 5's included): REJECT under `workspace`, `acceptEdits` and the full-access
        fallback; a card under `manual`. Never treated as a foreign server of unknown name."""
        params = _params(tool_call_id="call_m4", kind="other", raw_input={})
        calls: Dict[str, CallFacts] = {}
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS, FULL_ACCESS_PERMISSION_MODE):
            result = _decide(params, posture, tmp_path, calls)
            assert result["outcome"] == "REJECT", posture
        result = _decide(params, MANUAL, tmp_path, calls)
        assert result["outcome"] == "ASK_OPERATOR"


class TestMemoryAndUnrecognised:
    """design.md:645 — `memory`, `custom-tool`, `extension-*`, `factory`, anything unrecognised."""

    @pytest.mark.parametrize("kind", ["memory", "custom-tool", "extension-foo", "factory"])
    def test_refused_under_workspace_and_accept_edits(self, tmp_path, kind):
        """Task 1.6's own bullet: '`memory` refused', generalised to the row's other named
        kinds."""
        params = _params(kind=kind, raw_input={})
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS):
            result = _decide(params, posture, tmp_path)
            assert result["outcome"] == "REJECT", (kind, posture)

    def test_memory_asks_the_operator_under_manual(self, tmp_path):
        params = _params(kind="memory", raw_input={})
        result = _decide(params, MANUAL, tmp_path)
        assert result["outcome"] == "ASK_OPERATOR"

    def test_memory_is_allowed_under_full_access(self, tmp_path):
        """Full access answers ALLOW to any request that still reaches the client
        (design.md:806-807) — `memory` is not the unidentified-MCP special case, so it is
        not the full-access REJECT fallback either."""
        params = _params(kind="memory", raw_input={})
        result = _decide(params, FULL_ACCESS_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "ALLOW"


class TestSpecTurn:
    """design.md:896-908 (D9 item 1a) and design.md:666-669, 796-812 (operator decision
    2026-09-28, open question 13, option (c)) — `spec_turn=True`."""

    def test_edit_inside_workspace_is_rejected_under_every_posture_on_a_spec_turn(self, tmp_path):
        """(bullet 1) Until slice 3 lands there is no step-3 allow, so every `edit` request is
        REJECTed on a spec turn, in every posture — including full access, which never sets
        `allow_all` on for a spec turn, and including `manual`, which never puts up a card for
        it ('no card under `manual`')."""
        target = str(tmp_path / "probe.txt")
        params = _params(kind="edit", locations=[{"path": target}])
        for posture in ALL_POSTURES:
            result = _decide(params, posture, tmp_path, spec_turn=True)
            assert result["outcome"] == "REJECT", posture

    def test_edit_inside_workspace_keeps_its_postures_answer_when_not_a_spec_turn(self, tmp_path):
        """The same request with `spec_turn=False` (the default) keeps each posture's ordinary
        answer per the base table (design.md:637): ALLOW under `workspace`/`acceptEdits` and
        full access, a card under `manual`."""
        target = str(tmp_path / "probe.txt")
        params = _params(kind="edit", locations=[{"path": target}])
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS, FULL_ACCESS_PERMISSION_MODE):
            result = _decide(params, posture, tmp_path)
            assert result["outcome"] == "ALLOW", posture
        result = _decide(params, MANUAL, tmp_path)
        assert result["outcome"] == "ASK_OPERATOR"

    @pytest.mark.parametrize(
        "command,expected",
        [
            ("Remove-Item ..\\..\\x", "REJECT"),
            ("Set-Content .\\x", "ALLOW"),
        ],
    )
    def test_spec_turn_under_full_access_judges_powershell_as_workspace(
        self, tmp_path, command, expected
    ):
        """(bullet 2) Under full access, a spec turn's non-`edit` requests are judged as
        `workspace`, never ALLOW on full access's own account."""
        params = _params(kind="execute", raw_input={"command": command})
        result = _decide(params, FULL_ACCESS_PERMISSION_MODE, tmp_path, spec_turn=True)
        assert result["outcome"] == expected

    def test_spec_turn_under_full_access_judges_a_foreign_mcp_server_as_workspace(self, tmp_path):
        params = _params(
            tool_call_id="call_m2",
            kind="other",
            raw_input={"path": "C:\\Windows\\System32\\secret.txt"},
        )
        calls = {
            "call_m2": CallFacts(
                tool_name=None, mcp_server="some-other-server", mcp_tool="read_file"
            )
        }
        result = _decide(
            params, FULL_ACCESS_PERMISSION_MODE, tmp_path, calls, spec_turn=True
        )
        assert result["outcome"] == "REJECT"

    def test_spec_turn_under_full_access_rejects_an_unidentified_mcp_request(self, tmp_path):
        params = _params(tool_call_id="call_m4", kind="other", raw_input={})
        result = _decide(params, FULL_ACCESS_PERMISSION_MODE, tmp_path, spec_turn=True)
        assert result["outcome"] == "REJECT"

    def test_spec_turn_under_full_access_rejects_memory(self, tmp_path):
        params = _params(kind="memory", raw_input={})
        result = _decide(params, FULL_ACCESS_PERMISSION_MODE, tmp_path, spec_turn=True)
        assert result["outcome"] == "REJECT"

    @pytest.mark.parametrize(
        "kind,raw_input",
        [
            ("execute", {"command": "Remove-Item ..\\..\\x"}),
            ("memory", {}),
        ],
    )
    def test_same_requests_are_allowed_under_full_access_when_not_a_spec_turn(
        self, tmp_path, kind, raw_input
    ):
        params = _params(kind=kind, raw_input=raw_input)
        result = _decide(params, FULL_ACCESS_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "ALLOW"

    def test_foreign_mcp_is_allowed_but_unidentified_mcp_stays_rejected_under_full_access_off_a_spec_turn(
        self, tmp_path
    ):
        """The unidentified-MCP request is `decide_permission`'s standing full-access REJECT
        fallback (design.md:583-585) whether or not it is a spec turn; the foreign server is
        not that fallback, so off a spec turn it gets full access's ordinary defensive ALLOW."""
        foreign_params = _params(
            tool_call_id="call_m2",
            kind="other",
            raw_input={"path": "C:\\Windows\\System32\\secret.txt"},
        )
        calls = {
            "call_m2": CallFacts(
                tool_name=None, mcp_server="some-other-server", mcp_tool="read_file"
            )
        }
        result = _decide(foreign_params, FULL_ACCESS_PERMISSION_MODE, tmp_path, calls)
        assert result["outcome"] == "ALLOW"

        unidentified_params = _params(tool_call_id="call_m4", kind="other", raw_input={})
        result = _decide(unidentified_params, FULL_ACCESS_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "REJECT"


class TestReason:
    def test_every_decision_carries_a_non_empty_reason(self, tmp_path):
        params = _params(kind="execute", raw_input={"command": "Get-ChildItem"})
        for posture in ALL_POSTURES:
            result = _decide(params, posture, tmp_path)
            assert isinstance(result["reason"], str) and result["reason"]
