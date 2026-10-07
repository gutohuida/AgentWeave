"""F462 -- a specification turn on Codex app-server keeps no write tools.

F4's rule: a turn triggered with a specification document open loses file-write tools, regardless
of phase, rigor or permission posture. It is applied by `restrict_spec_writes=bool(spec_document)`
on the runner request. `codex exec` honours it (`--sandbox read-only`, `runner_commands.py`), but
app-server -- Codex's default transport -- reads no argv, and `CodexAppServerTransport.run_turn`
dropped the flag, so the thread started under the posture's own sandbox and could write.

Codex cannot be driven on this machine (plan cancelled 2026-08-29), so this is the acceptance
check, held at two seams: the real `POST /agent/trigger` handing the flag to `run_turn` (patched
there, as F99's test does), and the real `run_turn` over a scripted app-server session. Every
restriction has a control -- the same request on a turn with no document open -- so a test that
cannot tell the two apart fails.

What a spec turn keeps is the Hub's own call (`mcp_server._hub_own_call`, D16 of
`a-run-reaches-the-hub-without-mcp`): a run told the call command has to write its arguments file
under `.agentweave/calls/` and run `aw-tool`, or it cannot submit the document it was opened on.
"""

from unittest.mock import patch

import pytest

from hub import codex_appserver
from hub.codex_appserver import run_turn
from hub.model_catalog import FULL_ACCESS_PERMISSION_MODE, WORKSPACE_PERMISSION_MODE
from tests.test_agent_trigger import _await_background_run, _fake_run_turn
from tests.test_codex_appserver_run_turn import (
    THREAD_START_RESULT,
    TURN_START_RESULT,
    _FakeSession,
    _noop,
    _patch_spawn,
)

OPERATOR = "operator"
POSTURES = [None, OPERATOR, WORKSPACE_PERMISSION_MODE, FULL_ACCESS_PERMISSION_MODE]
COMMAND = codex_appserver.COMMAND_APPROVAL_METHOD
FILE_CHANGE = codex_appserver.FILE_CHANGE_APPROVAL_METHOD


# --- the dispatch hands the restriction to the app-server transport ---------------------------


@pytest.mark.parametrize("spec_document", ["spec/changes/some-change/spec.html", None])
async def test_the_dispatch_hands_the_restriction_to_run_turn(
    app, auth_headers, bind_runner, spec_document
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"spec-codex": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner("spec-codex", cli="codex")
    body = {"agent": "spec-codex", "message": "look at it", "session_mode": "new"}
    if spec_document:
        body["spec_document"] = spec_document

    fake = _fake_run_turn()
    with patch("hub.codex_appserver.run_turn", fake):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/codex"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger", json=body, headers=auth_headers
            )
            assert response.status_code == 200, response.text
            await _await_background_run()

    assert fake.call_args.kwargs.get("restrict_spec_writes") is bool(spec_document)


# --- run_turn: the thread a spec turn starts -------------------------------------------------


def _session(*notifications):
    return _FakeSession(
        responses={
            "initialize": {},
            "thread/start": THREAD_START_RESULT,
            "turn/start": TURN_START_RESULT,
        },
        notifications=[
            *notifications,
            {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
        ],
    )


async def _run(monkeypatch, fake, *, posture, workspace, restrict, request_approval=None):
    _patch_spawn(monkeypatch, fake)
    await run_turn(
        cli="codex",
        cwd=workspace,
        env=None,
        prompt="hi",
        model=None,
        resume_thread_id=None,
        yolo=False,
        mcp_command=None,
        on_event=_noop,
        posture=posture,
        workspace=workspace,
        request_approval=request_approval,
        restrict_spec_writes=restrict,
    )
    return fake


def _thread_start(fake):
    return next(params for method, params in fake.sent_requests if method == "thread/start")


@pytest.mark.parametrize("posture", POSTURES)
async def test_a_spec_turn_starts_a_read_only_thread_that_can_ask(monkeypatch, tmp_path, posture):
    """Read-only in every posture, and never `never`: under `never` Codex refuses the Hub's own
    arguments-file write silently instead of asking, and the turn could not reach the Hub."""
    fake = await _run(
        monkeypatch, _session(), posture=posture, workspace=str(tmp_path), restrict=True
    )

    started = _thread_start(fake)
    assert started["sandbox"] == "read-only"
    assert started["approvalPolicy"] == ("untrusted" if posture == OPERATOR else "on-request")


async def test_without_a_document_full_access_is_unchanged(monkeypatch, tmp_path):
    """The control: the restriction is the document's, not a narrowing of Full access."""
    fake = await _run(
        monkeypatch,
        _session(),
        posture=FULL_ACCESS_PERMISSION_MODE,
        workspace=str(tmp_path),
        restrict=False,
    )

    started = _thread_start(fake)
    assert (started["sandbox"], started["approvalPolicy"]) == ("danger-full-access", "never")


# --- run_turn: what a spec turn's approvals are answered -------------------------------------


def _command(command, cwd, request_id=7):
    return {"id": request_id, "method": COMMAND, "params": {"command": command, "cwd": cwd}}


def _file_change(*paths):
    item = {
        "method": "item/started",
        "params": {
            "item": {
                "id": "fc-1",
                "type": "fileChange",
                "changes": [{"path": p, "kind": "add"} for p in paths],
            }
        },
    }
    request = {"id": 7, "method": FILE_CHANGE, "params": {"itemId": "fc-1", "grantRoot": None}}
    return item, request


@pytest.mark.parametrize("restrict, expected", [(True, "decline"), (False, "accept")])
async def test_a_write_the_posture_allows_is_declined_on_a_spec_turn(
    monkeypatch, tmp_path, restrict, expected
):
    """Workspace only accepts a command inside the workspace (the control); a spec turn does not."""
    fake = await _run(
        monkeypatch,
        _session(_command("touch NOTES.md", str(tmp_path))),
        posture=WORKSPACE_PERMISSION_MODE,
        workspace=str(tmp_path),
        restrict=restrict,
    )

    assert fake.sent_responses == [(7, {"decision": expected})]


@pytest.mark.parametrize("posture", [None, WORKSPACE_PERMISSION_MODE, FULL_ACCESS_PERMISSION_MODE])
async def test_a_file_change_is_declined_on_a_spec_turn(monkeypatch, tmp_path, posture):
    fake = await _run(
        monkeypatch,
        _session(*_file_change(str(tmp_path / "NOTES.md"))),
        posture=posture,
        workspace=str(tmp_path),
        restrict=True,
    )

    assert fake.sent_responses == [(7, {"decision": "decline"})]


async def test_under_ask_me_a_file_change_is_declined_without_a_card(monkeypatch, tmp_path):
    asked = []

    async def _ask(method, subject):
        asked.append(method)
        return True

    fake = await _run(
        monkeypatch,
        _session(*_file_change(str(tmp_path / "NOTES.md"))),
        posture=OPERATOR,
        workspace=str(tmp_path),
        restrict=True,
        request_approval=_ask,
    )

    assert asked == []
    assert fake.sent_responses == [(7, {"decision": "decline"})]


async def test_under_ask_me_another_command_still_goes_to_the_operator(monkeypatch, tmp_path):
    asked = []

    async def _ask(method, subject):
        asked.append(method)
        return False

    fake = await _run(
        monkeypatch,
        _session(_command("git status", str(tmp_path))),
        posture=OPERATOR,
        workspace=str(tmp_path),
        restrict=True,
        request_approval=_ask,
    )

    assert asked == [COMMAND]
    assert fake.sent_responses == [(7, {"decision": "decline"})]


@pytest.mark.parametrize("posture", POSTURES)
async def test_the_hubs_own_call_is_accepted_on_a_spec_turn(monkeypatch, tmp_path, posture):
    """The arguments file and the `aw-tool` command are the one write a spec turn keeps (D16)."""
    (tmp_path / ".agentweave" / "calls").mkdir(parents=True)
    item, write = _file_change(str(tmp_path / ".agentweave" / "calls" / "1.json"))
    call = _command(
        "aw-tool submit_spec_document .agentweave/calls/1.json", str(tmp_path), request_id=8
    )

    fake = await _run(
        monkeypatch,
        _session(item, write, call),
        posture=posture,
        workspace=str(tmp_path),
        restrict=True,
    )

    assert fake.sent_responses == [(7, {"decision": "accept"}), (8, {"decision": "accept"})]


async def test_a_file_change_reaching_outside_the_calls_root_is_declined(monkeypatch, tmp_path):
    """Every path must be the Hub's own; one calls file beside a real edit does not carry it."""
    (tmp_path / ".agentweave" / "calls").mkdir(parents=True)
    fake = await _run(
        monkeypatch,
        _session(
            *_file_change(
                str(tmp_path / ".agentweave" / "calls" / "1.json"), str(tmp_path / "NOTES.md")
            )
        ),
        posture=FULL_ACCESS_PERMISSION_MODE,
        workspace=str(tmp_path),
        restrict=True,
    )

    assert fake.sent_responses == [(7, {"decision": "decline"})]


def test_the_hubs_own_mcp_tools_are_unchanged_on_a_spec_turn():
    """A spec turn's work is `submit_spec_document`; told the MCP form, that is an elicitation."""
    params = {"serverName": "agentweave", "_meta": {"codex_approval_kind": "mcp_tool_call"}}

    verdict = codex_appserver.decide_approval(
        codex_appserver.ELICITATION_METHOD,
        params,
        yolo=False,
        own_server_name="agentweave",
        posture=WORKSPACE_PERMISSION_MODE,
        workspace="/workspace",
        restrict_spec_writes=True,
    )

    assert verdict == {"action": "accept"}


@pytest.mark.parametrize("restrict, granted", [(True, False), (False, True)])
def test_full_access_grants_no_permissions_on_a_spec_turn(restrict, granted):
    """`item/permissions/requestApproval` is the third way out: under Full access it grants write on
    the root (the control). On a spec turn it grants nothing."""
    verdict = codex_appserver.decide_approval(
        codex_appserver.PERMISSIONS_APPROVAL_METHOD,
        {},
        yolo=False,
        own_server_name="agentweave",
        posture=FULL_ACCESS_PERMISSION_MODE,
        workspace="/workspace",
        restrict_spec_writes=restrict,
    )

    assert bool(verdict["permissions"]) is granted
