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

Part 3 of N (tasks.md bullets 6-9, 12, 16-17) adds `TestMcpServerIdentification` and
`TestReadPathSplitting` below. Two things learned doing it, not guessed:

  - `decide_permission` never sees *how* a `calls` entry was populated — it only ever sees the
    resolved `CallFacts` map (design.md:575-577), and R3 makes it never read `toolCall.title`
    either (design.md:676-687). So bullets 6, 7 and (review, note 12), which each describe a
    different *upstream* source feeding `calls` (a raw `tool.execution_start`; a title-only call
    with no raw event; a call id reused after `tool.execution_complete` deleted its entry),
    collapse at this function's boundary into exactly two shapes: a call id **present** in
    `calls` (bullet 6 — already covered by `TestMcp.test_agentweave_mcp_allowed_under_manual`,
    part 1/N) and a call id **absent** from it (bullet 7 and note 12 — both must answer exactly
    as `TestMcp.test_mcp_request_with_no_identified_server_is_rejected_under_every_posture`,
    part 1/N, already does, including REJECT under the full-access fallback: design.md:582-585 is
    the settled, authoritative text, and it carves out no exception for full access, so this file
    follows it rather than tasks.md line 107's older "but full access" gloss);
  - (review, note 17) a genuinely differentiating fixture — where judging split pieces alone
    would disagree with judging the whole unsplit string — could not be derived from real Windows
    path semantics: a real absolute path's drive-and-directory prefix, which decides inside vs.
    outside, always lands entirely in the first `", "`-delimited piece (a Windows filename cannot
    itself contain the `:` a second absolute path would need), so piece-only judging already
    answers correctly by itself for every construction tried. `TestReadPathSplitting` tests both
    directions a comma-bearing single filename can go instead, and says so rather than inventing
    an adversarial case.

Part 4 of N (review finding 2) adds `TestFetchAsShellText` below: a `fetch` request whose call is
not `web_fetch` (a `powershell` call, or an unknown/default id) is judged as shell text, so only
the run's own Hub URL passes; everything else refuses. Only `workspace` is exercised, per the
task's own wording for this slice.

Part 5 of N (review finding 5) adds `TestMcpForeignNameCollision` below: the naming bug itself,
distinct from finding 6. R3 wrote the foreign-MCP name as `mcp__<server>__<tool>`, but `_decide`'s
own first statement (`mcp_server.py:1557-1558`) allows *any* name starting `mcp__agentweave__`
unconditionally — so a server reporting exactly `agentweave` with a tool the Hub's own server does
not serve, or a server registered under the config key `agentweave__x` (whose buggy name,
`mcp__agentweave__x__<tool>`, also starts with that prefix — a plain hyphen, `agentweave-x`, does
not, which is why bullet 8's `TestMcpServerIdentification` case above does not already cover this),
would have been allowed **whatever its arguments** on that naming. `decide_permission` must instead
pass `_decide` the `copilot-mcp:{server}/{tool}` name (design.md:643), which carries no such prefix,
so each case is written with a command that breaks out of the workspace and must REJECT — a test
that fails on R3's `mcp__`-prefixed naming, not just one that passes on the fixed `copilot-mcp:`
naming.

Part 6 of N (review finding 1/slice 3) adds `TestExecuteDialectSelection` below: an `execute`
request whose `calls` entry names `write_powershell` or `local_shell` is keyed `"Shell"` (both
dialects read), never `"PowerShell"` alone — proven with a command verified directly against
`_read_command`/`_decide` (`mcp_server.py`) to be refused only when read as Bash, never as
PowerShell, so a `"PowerShell"`-only reading would wrongly ALLOW it. The no-`command`-key half of
finding 1/slice 3 (`write_powershell`'s real `{shellId, input}` shape) was already covered by part
1/N's `test_command_that_is_not_a_non_empty_string_is_rejected`; not repeated here.

Still deliberately NOT covered (left for a follow-up sub-task of 1.6):
  - review finding 6's true load-time-condition row (the `agentweave` server's
    `session.mcp_servers_loaded` source+transport check) — genuinely blocked, not merely
    unattempted: design.md:572 states `decide_permission`'s full keyword signature
    (`posture, workspace, hub_url, calls, spec_turn=False`) with no parameter carrying this map,
    `CallFacts` is stated as exactly `(tool_name, mcp_server, mcp_tool)` (design.md:576) with no
    room for a verification flag, and no CODE citation anywhere in design.md shows a `servers=`
    keyword or a `ServerFacts`-shaped value reaching this function — searched for all three.
    design.md:725-726 describes the `servers` map only as something "fed" from spawn onward "like
    `calls`", which is the client's own bookkeeping, not a stated argument to this pure function.
    Writing a fixture here means guessing an unstated parameter shape, which is exactly what the
    round discipline exists to catch before code, not paper over in a test. Recorded here and in
    the night log as an open question for a review round, not guessed — still open after part 6/N;
  - (review, note 16) the operator card's label text ("an MCP tool Copilot did not identify",
    never the title) — that is `RpcTransport.permission_card_label`'s output (D3, design.md:
    778-781), a different function than `decide_permission`, which only returns `{"outcome",
    "reason"}`; `decide_permission`'s own contribution (never reading `title`) is exercised by
    `TestMcpServerIdentification` above;
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

    def test_command_naming_a_path_outside_the_workspace_is_refused_under_workspace(self, tmp_path):
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


class TestFetchAsShellText:
    """design.md:640 -- (review, finding 2) a `fetch` request whose call is not `web_fetch` (a
    shell, or unknown/unrecognised) is judged exactly as the shell text `_decide` would read:
    only the run's own Hub passes; any other address is refused, the same way a network word in
    a PowerShell command is. Only `workspace` is exercised here -- part 1/N's `TestFetch` already
    covers the plain `web_fetch` and sandbox-bypass rows across postures.
    """

    def test_url_on_a_powershell_call_is_rejected_under_workspace(self, tmp_path):
        params = _params(
            tool_call_id="call_u1", kind="fetch", raw_input={"url": "https://example.com"}
        )
        calls = {"call_u1": CallFacts(tool_name="powershell", mcp_server=None, mcp_tool=None)}
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path, calls)
        assert result["outcome"] == "REJECT"

    @pytest.mark.parametrize("tool_call_id", ["url-permission", "some-unrecognised-id"])
    def test_url_with_unknown_or_default_id_is_judged_as_shell_text(self, tmp_path, tool_call_id):
        """Neither id has a `calls` entry, so both are read as an unidentified call, never as
        `web_fetch` -- the network address is refused for the same reason the identified
        `powershell` call above is."""
        params = _params(
            tool_call_id=tool_call_id, kind="fetch", raw_input={"url": "https://example.com"}
        )
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path, calls={})
        assert result["outcome"] == "REJECT"

    def test_url_naming_the_runs_own_hub_is_allowed_even_read_as_shell_text(self, tmp_path):
        """`_is_own_hub` (mcp_server.py:1210) matches the URL's scheme, host and port against
        `hub_url`; the judge then reads the text as the relative path it spells (`_judge_url` ->
        `_judge_path`), which lands inside the workspace root because it is not an absolute
        filesystem path -- so it is allowed even though nothing here ever reads it as
        `web_fetch`."""
        params = _params(tool_call_id="url-permission", kind="fetch", raw_input={"url": HUB_URL})
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path, calls={})
        assert result["outcome"] == "ALLOW"


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
            "call_m3": CallFacts(tool_name=None, mcp_server="some-other-server", mcp_tool="ping")
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
        result = _decide(params, FULL_ACCESS_PERMISSION_MODE, tmp_path, calls, spec_turn=True)
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


class TestMcpServerIdentification:
    """(R2/R3's MCP-server-identification edge cases, tasks.md task 1.6 bullets 6-9, 12, part
    3/N.) `decide_permission` receives only the already-resolved `calls: Dict[str, CallFacts]`
    map, and never reads `toolCall.title` for MCP identification — the whole point of R3's fix
    over R2 (design.md:676-687). So bullets describing *which upstream source* fed `calls`
    collapse here into two shapes: a call id present in it, and one absent from it. Bullet 9 ("a
    `read` request with no `rawInput.path` and no `locations` → REJECT") is already covered by
    `TestRead.test_read_with_no_path_at_all_is_refused` (part 1/N); no new test for it here.
    """

    def test_server_identified_from_calls_is_allowed_under_manual(self, tmp_path):
        """(bullet 6) The design's route to this `CallFacts` entry is a raw
        `tool.execution_start` read before the request (design.md:692-697); decide_permission
        only ever sees the resolved entry. Same shape as
        `TestMcp.test_agentweave_mcp_allowed_under_manual` (part 1/N) — restated under the
        bullet's own name for task-tracking, not because the outcome differs."""
        params = _params(tool_call_id="call_m1", kind="other", raw_input={})
        calls = {
            "call_m1": CallFacts(tool_name=None, mcp_server="agentweave", mcp_tool="send_message")
        }
        result = _decide(params, MANUAL, tmp_path, calls)
        assert result["outcome"] == "ALLOW"

    def test_a_title_only_call_with_no_calls_entry_is_treated_as_unidentified(self, tmp_path):
        """(bullet 7) 'No raw event read, but a preceding `tool_call` titled
        `agentweave-send_message`' means `calls` carries no entry for this id — decide_permission
        never reads `title` (R3), so this is indistinguishable from any other unidentified call.
        A title naming the Hub's own tool is exactly the prompt-injection shape design.md:680-683
        warns about ('a foreign MCP tool ... called with description: "agentweave-send_message"
        ... would read as the Hub's own'); asserting REJECT/ASK_OPERATOR here (never ALLOW) is
        what 'it must fail on R2's code' means, since R2 read the title and would have allowed
        it as the Hub's own tool."""
        params = _params(
            tool_call_id="call_m5", kind="other", raw_input={}, title="agentweave-send_message"
        )
        calls: Dict[str, CallFacts] = {}
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS, FULL_ACCESS_PERMISSION_MODE):
            result = _decide(params, posture, tmp_path, calls)
            assert result["outcome"] == "REJECT", posture
        result = _decide(params, MANUAL, tmp_path, calls)
        assert result["outcome"] == "ASK_OPERATOR"

    def test_a_call_id_reused_after_execution_complete_is_treated_as_unidentified(self, tmp_path):
        """(review, note 12) `calls` holds open calls only; `tool.execution_complete` deletes the
        entry. A later request reusing the same id (`call_0`, the shape some OpenAI-compatible
        servers under slice 5's BYOK send every time) with no new `tool.execution_start` finds no
        entry — the same unidentified shape as bullet 7 above, never a stale `agentweave` one
        inherited from the completed call."""
        params = _params(tool_call_id="call_0", kind="other", raw_input={})
        calls: Dict[str, CallFacts] = {}
        for posture in (WORKSPACE_PERMISSION_MODE, ACCEPT_EDITS, FULL_ACCESS_PERMISSION_MODE):
            result = _decide(params, posture, tmp_path, calls)
            assert result["outcome"] == "REJECT", posture
        result = _decide(params, MANUAL, tmp_path, calls)
        assert result["outcome"] == "ASK_OPERATOR"

    @pytest.mark.parametrize(
        "mcp_server,mcp_tool",
        [
            ("agentweave-x", "send_message"),
            ("agentweave", "not_a_real_tool"),
        ],
    )
    def test_a_lookalike_server_or_tool_is_judged_as_foreign(self, tmp_path, mcp_server, mcp_tool):
        """(bullet 8; design.md:716-724, "a server name is a config key, not an identity") A
        server registered under a different config key (`agentweave-x`) and `agentweave`
        reporting a tool the Hub's own server does not serve both fail D8's Hub-own test — the
        first because the reported server isn't exactly `agentweave`, the second because the
        reported tool isn't one the Hub's server serves — so both fall to the foreign-server row
        (design.md:643), never the Hub-own ALLOW (design.md:642). Judged under `acceptEdits`,
        where the foreign row's REJECT is unconditional (design.md:643's `acceptEdits` column),
        unlike `workspace`, where a foreign call naming no path or command is allowed by Claude
        parity (`TestMcp.test_a_foreign_mcp_call_naming_no_path_and_no_command_is_allowed_under_workspace`,
        part 1/N) and so would not by itself distinguish 'foreign' from 'Hub's own'."""
        params = _params(tool_call_id="call_m6", kind="other", raw_input={})
        calls = {"call_m6": CallFacts(tool_name=None, mcp_server=mcp_server, mcp_tool=mcp_tool)}
        result = _decide(params, ACCEPT_EDITS, tmp_path, calls)
        assert result["outcome"] == "REJECT"


class TestReadPathSplitting:
    """(review, note 17; design.md:638; tasks.md task 1.6 bullet 17, part 3/N.) `rawInput.path`
    (or `locations[0].path`) is split on `", "` because Copilot's own reporting sometimes joins
    several read paths that way (`eNo`, CODE) — but a single real file whose own name contains the
    literal substring `", "` must not be swallowed by that split: design.md:638 requires judging
    the unsplit whole *as well as* the split pieces, REJECTing if either finds a path outside the
    workspace.

    This tests both directions a comma-bearing single filename can go (ALLOW when the real, whole
    path is inside the workspace; REJECT when it is outside), rather than a fixture where
    piece-only judging would disagree with whole-string judging: for a real absolute path, the
    drive-and-directory prefix that decides inside vs. outside always lands entirely in the first
    split piece (a Windows filename cannot itself contain the `:` a second absolute path would
    need), so piece-only judging already answers these two cases correctly by itself. Whether some
    path shape truly needs the whole-string check to disagree with pieces-only judging is not
    established here — surfaced, not guessed a fixture for it.
    """

    def test_a_single_path_inside_the_workspace_whose_name_contains_a_comma_is_allowed(
        self, tmp_path
    ):
        target = str(tmp_path / "log, final.txt")
        params = _params(kind="read", raw_input={"path": target})
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "ALLOW"

    def test_a_single_path_outside_the_workspace_whose_name_contains_a_comma_is_refused(
        self, tmp_path
    ):
        outside = str(tmp_path.parent / "elsewhere, place" / "log, final.txt")
        params = _params(kind="read", raw_input={"path": outside})
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "REJECT"

    def test_two_real_paths_joined_by_comma_are_each_judged(self, tmp_path):
        """The ordinary, intended use of the join: two genuinely separate real paths in one
        string (Copilot reporting more than one file read in a single request). Splitting must
        see both — one outside the workspace refuses the whole request even though the other,
        alone, would be allowed."""
        inside = str(tmp_path / "a.txt")
        outside = "C:\\Windows\\System32\\evil.txt"
        params = _params(kind="read", raw_input={"path": f"{inside}, {outside}"})
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path)
        assert result["outcome"] == "REJECT"


class TestMcpForeignNameCollision:
    """(review, finding 5; design.md:643; tasks.md task 1.6, part 5/N.) `_decide`'s own first
    statement (`mcp_server.py:1557-1558`) allows *any* tool name starting `mcp__agentweave__`
    unconditionally, whatever its arguments. R3 wrote the foreign-MCP name it passes to `_decide`
    as `mcp__<server>__<tool>` — which collides with that prefix for two server reports that are
    not actually the Hub's own: `agentweave` reporting a tool the Hub's server does not serve, and
    a server registered under the config key `agentweave__x` (whose buggy name,
    `mcp__agentweave__x__<tool>`, also starts with `mcp__agentweave__`, unlike the plain hyphen
    `agentweave-x` `TestMcpServerIdentification.test_a_lookalike_server_or_tool_is_judged_as_foreign`
    already covers). `decide_permission` must instead pass `_decide` the `copilot-mcp:{server}/{tool}`
    name (design.md:643), which carries no such prefix. Each test below supplies a command that
    breaks out of the workspace, so it REJECTs on the correct `copilot-mcp:` naming and would
    wrongly ALLOW on R3's `mcp__`-prefixed naming — written to fail on that code, not merely to
    pass on the fixed one.
    """

    def test_agentweave_reporting_an_unserved_tool_is_still_judged_by_its_arguments(self, tmp_path):
        params = _params(
            tool_call_id="call_m7",
            kind="other",
            raw_input={"command": "Remove-Item ..\\..\\x"},
        )
        calls = {
            "call_m7": CallFacts(
                tool_name=None, mcp_server="agentweave", mcp_tool="not_a_real_tool"
            )
        }
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path, calls)
        assert result["outcome"] == "REJECT"

    def test_agentweave_double_underscore_lookalike_server_is_still_judged_by_its_arguments(
        self, tmp_path
    ):
        params = _params(
            tool_call_id="call_m8",
            kind="other",
            raw_input={"command": "Remove-Item ..\\..\\x"},
        )
        calls = {
            "call_m8": CallFacts(
                tool_name=None, mcp_server="agentweave__x", mcp_tool="send_message"
            )
        }
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path, calls)
        assert result["outcome"] == "REJECT"


class TestExecuteDialectSelection:
    """(review, finding 1/slice 3; design.md:636; tasks.md task 1.6, part 6/N.) The dialect key
    `_decide` receives for an `execute` request comes from the call's real tool name in `calls`
    (design.md:636): `powershell` -> `"PowerShell"`, `bash` -> `"Bash"`, and *any other name*
    (`local_shell`, `write_powershell`, ...) or no name known -> `"Shell"`, a key `_TOOL_DIALECTS`
    lacks, so `_decide` falls back to reading the command in **both** dialects and refuses if
    either refuses (`mcp_server.py:1611`). R2's platform rule -- deciding `local_shell` by the
    OS the Hub happens to run on -- is gone; nothing guarantees that matches the shell Copilot
    actually spawned (design.md:636, "Review 2026-09-28").

    `_BASH_ONLY_REFUSAL_COMMAND` is refused only when read as Bash, never as PowerShell --
    verified directly against the real `_read_command`/`_decide` (`mcp_server.py:1430-1619`)
    before writing these assertions, not assumed:

      - Bash treats a backtick pair as command substitution (`mcp_server.py:1467-1472`, gated
        `if bash and char == "`"`). It excises the enclosed `..` from the outer word (leaving
        the harmless placeholder `x$(...)y`, which judges clean by itself) and separately,
        recursively judges the substitution's own text, `..`, as its own command
        (`_read_command`'s `nested` loop, `mcp_server.py:1563-1566`) -- an exact `".."` word,
        refused by rule 4 (`mcp_server.py:1289-1290`) as the workspace's own parent.
      - PowerShell has no substitution syntax; a backtick is only its escape character
        (`mcp_server.py:1441`, `escape = "`" if not bash`), so each backtick-and-following-char
        pair collapses to just that one character, and `` `..` `` becomes the literal two
        characters `..`, glued between the surrounding `x` and `y` into a single word,
        `"x..y"` -- not `".."`, and carrying no separator, so rule 4 lets it stand.

    Confirmed directly: `_decide("PowerShell", {"command": ...})` on this text returns
    `allow=True`; `_decide("write_powershell", ...)` and `_decide("local_shell", ...)` (both
    outside `_TOOL_DIALECTS`, so both dialects) return `allow=False`. So a `"PowerShell"`-only
    reading (R2's platform guess) would wrongly ALLOW this exact command; reading both, as the
    `"Shell"` fallback requires, REJECTs it.
    """

    _BASH_ONLY_REFUSAL_COMMAND = "echo x`..`y"

    def test_write_powershell_with_a_command_is_keyed_shell_not_powershell(self, tmp_path):
        """(review, finding 1/slice 3) An `execute` whose tool name is `write_powershell`,
        carrying a `command`, is judged with the `"Shell"` fallback -- never treated as
        `"PowerShell"`, which alone would allow this command."""
        params = _params(
            tool_call_id="call_s1",
            kind="execute",
            raw_input={"command": self._BASH_ONLY_REFUSAL_COMMAND},
        )
        calls = {"call_s1": CallFacts(tool_name="write_powershell", mcp_server=None, mcp_tool=None)}
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path, calls)
        assert result["outcome"] == "REJECT"

    def test_local_shell_is_read_in_both_dialects_not_just_powershell(self, tmp_path):
        """(R3) `local_shell`'s command is REJECTed because the Bash reading refuses it, proving
        both dialects are actually read -- not merely PowerShell, which alone would allow this
        exact command (see class docstring)."""
        params = _params(
            tool_call_id="call_s2",
            kind="execute",
            raw_input={"command": self._BASH_ONLY_REFUSAL_COMMAND},
        )
        calls = {"call_s2": CallFacts(tool_name="local_shell", mcp_server=None, mcp_tool=None)}
        result = _decide(params, WORKSPACE_PERMISSION_MODE, tmp_path, calls)
        assert result["outcome"] == "REJECT"
