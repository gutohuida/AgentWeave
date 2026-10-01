"""The call command's program: the pinned tool server in call mode (`aw-tool`).

`a-run-reaches-the-hub-without-mcp`, design D3, D4, D6 and D7. A run whose harness cannot use MCP
reaches the Hub by running the *same file* the Hub pinned for its MCP server, as
`<python> -I -S <pin> --call <tool> [<args.json>]`. It calls the same functions the MCP tools are,
reads its credential from its environment only, takes its arguments from a JSON file under the
workspace's `.agentweave/calls/`, prints one JSON envelope, and never imports fastmcp.

Every spawned case runs the file as the launcher will -- from a working directory that is not the
package root, against a stub Hub in a thread -- because what matters is the program as spawned,
not the module as imported (`test_mcp_server_stdio_surface.py`'s lesson).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from hub import mcp_server
from hub.tool_server import ToolServerPin

TOKEN = "aw_run_callmode-secret"


# --- the stub Hub ---------------------------------------------------------------------------------


class StubHub:
    """A Hub that records every request and answers from a table, in a thread."""

    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []
        self.routes: Dict[Tuple[str, str], Any] = {}
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def _serve(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                path = self.path.split("?", 1)[0]
                stub.requests.append(
                    {
                        "method": method,
                        "path": path,
                        "auth": self.headers.get("Authorization"),
                        "body": json.loads(raw) if raw else None,
                    }
                )
                answer = stub.routes.get((method, path), (200, {"ok": True}))
                if callable(answer):
                    answer = answer()
                status, body = answer
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._serve("GET")

            def do_POST(self):
                self._serve("POST")

            def do_PATCH(self):
                self._serve("PATCH")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def paths(self) -> List[str]:
        return [f"{r['method']} {r['path']}" for r in self.requests]


@pytest.fixture
def hub():
    stub = StubHub()
    yield stub
    stub.close()


@pytest.fixture
def pin(tmp_path) -> Path:
    """The file as the Hub pins it: a byte-for-byte copy outside the package."""
    return ToolServerPin(Path(mcp_server.__file__), root=tmp_path / "pins").path()


@pytest.fixture
def workspace(tmp_path) -> Path:
    ws = tmp_path / "ws"
    (ws / ".agentweave" / "calls").mkdir(parents=True)
    return ws


def _env(
    hub: Optional[StubHub], workspace: Optional[Path], **extra: Optional[str]
) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AW_", "HUB_", "PYTHON"))}
    if hub is not None:
        env["HUB_URL"] = hub.url
    env["AW_RUN_TOKEN"] = TOKEN
    if workspace is not None:
        env["AW_WORKSPACE_DIR"] = str(workspace)
    for key, value in extra.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def _call(
    pin: Path,
    args: List[str],
    *,
    env: Dict[str, str],
    cwd: Path,
    isolated: bool = True,
    timeout: int = 60,
) -> Tuple[int, Dict[str, Any], str]:
    flags = ["-I", "-S"] if isolated else []
    proc = subprocess.run(
        [sys.executable, *flags, str(pin), "--call", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=timeout,
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    envelope = json.loads(lines[-1]) if lines else {}
    return proc.returncode, envelope, proc.stdout + proc.stderr


def _args_file(workspace: Path, name: str, payload: Any, *, encoding: str = "utf-8") -> str:
    path = workspace / ".agentweave" / "calls" / name
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_bytes(text.encode(encoding))
    return f".agentweave/calls/{name}"


def _served_tools() -> set:
    return {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}


# --- 1.3: the callable set, and no fastmcp in call mode ------------------------------------------


def test_list_names_every_served_tool_but_the_approver(pin, tmp_path):
    code, envelope, raw = _call(pin, ["--list"], env=_env(None, None), cwd=tmp_path)
    assert code == 0, raw
    listed = {tool["name"] for tool in envelope["result"]["tools"]}
    assert listed == _served_tools() - {"approve_tool_call"}
    create = next(t for t in envelope["result"]["tools"] if t["name"] == "create_task")
    assert "title" in create["required"]


def test_the_callable_set_in_process_is_the_listed_set():
    """Review note 12: one plain name set, filled by `_tool()`, read by `--list`, `call_main` and
    the approver's predicate; it equals the fastmcp-registered set minus `approve_tool_call`."""
    assert set(mcp_server._CALLABLE_TOOLS) == _served_tools() - {"approve_tool_call"}
    assert "approve_tool_call" not in mcp_server._CALLABLE_TOOLS


def test_call_mode_does_not_import_fastmcp(pin, tmp_path):
    """Spawned **without** `-I`: isolated mode ignores `PYTHONPATH`, so it would pass whether or
    not call mode imports fastmcp (R3)."""
    poison = tmp_path / "poison"
    (poison / "fastmcp").mkdir(parents=True)
    (poison / "fastmcp" / "__init__.py").write_text("raise ImportError('poisoned fastmcp')\n")
    env = _env(None, None, PYTHONPATH=str(poison))

    code, envelope, raw = _call(pin, ["--list"], env=env, cwd=tmp_path, isolated=False)

    assert code == 0, raw
    assert envelope["ok"] is True


def test_isolated_flags_ignore_a_poisoned_path(pin, tmp_path):
    """`-I -S` (D5): a `json.py` on `PYTHONPATH` cannot change what the auto-approved program runs."""
    poison = tmp_path / "poison"
    poison.mkdir()
    (poison / "json.py").write_text("raise RuntimeError('poisoned json')\n")
    env = _env(None, None, PYTHONPATH=str(poison))

    code, envelope, raw = _call(pin, ["--list"], env=env, cwd=tmp_path)

    assert code == 0, raw
    assert envelope["ok"] is True


# --- 1.4: one call, against a stub Hub ------------------------------------------------------------


def test_a_call_sends_what_the_mcp_tool_sends(pin, hub, workspace, monkeypatch):
    sent: List[Tuple[str, str, Any]] = []
    monkeypatch.setattr(
        mcp_server,
        "_hub_request",
        lambda method, path, body=None, params=None: sent.append((method, path, body)) or {},
    )
    mcp_server.create_task(title="Ship it", description="d")
    ((method, path, expected_body),) = sent

    hub.routes[(method, f"/api/v1/agent-actions{path}")] = (
        201,
        {"id": "task-1", "title": "Ship it"},
    )
    args = _args_file(workspace, "1.json", {"title": "Ship it", "description": "d"})

    code, envelope, raw = _call(pin, ["create_task", args], env=_env(hub, workspace), cwd=workspace)

    assert code == 0, raw
    assert envelope == {"ok": True, "result": {"id": "task-1", "title": "Ship it"}}
    (request,) = hub.requests
    assert (request["method"], request["path"]) == (method, f"/api/v1/agent-actions{path}")
    assert request["auth"] == f"Bearer {TOKEN}"
    assert request["body"] == expected_body
    assert raw.strip().splitlines()[-1] == json.dumps(envelope)  # one object, nothing after it


def test_a_refusal_is_rejected_with_the_readable_detail(pin, hub, workspace):
    hub.routes[("POST", "/api/v1/agent-actions/tasks")] = (
        409,
        {"detail": {"code": "x", "message": "That task already exists."}},
    )
    args = _args_file(workspace, "1.json", {"title": "t"})

    code, envelope, _ = _call(pin, ["create_task", args], env=_env(hub, workspace), cwd=workspace)

    assert code == 1
    assert envelope["ok"] is False
    assert envelope["error"]["kind"] == "rejected"
    assert envelope["error"]["status"] == 409
    assert envelope["error"]["detail"] == "That task already exists."


def test_no_credential_is_unbound_and_sends_nothing(pin, hub, workspace):
    args = _args_file(workspace, "1.json", {"title": "t"})
    env = _env(hub, workspace, AW_RUN_TOKEN=None)

    code, envelope, _ = _call(pin, ["create_task", args], env=env, cwd=workspace)

    assert code == 2
    assert envelope["error"]["kind"] == "unbound"
    assert hub.requests == []


def test_an_unreachable_hub_names_its_address(pin, workspace, tmp_path):
    args = _args_file(workspace, "1.json", {"title": "t"})
    env = _env(None, workspace, HUB_URL="http://127.0.0.1:9")

    code, envelope, _ = _call(pin, ["create_task", args], env=env, cwd=workspace)

    assert code == 2
    assert envelope["error"]["kind"] == "unreachable"
    assert "127.0.0.1:9" in envelope["error"]["detail"]


@pytest.mark.parametrize(
    "argv_tail, payload",
    [
        (["create_task"], {"title": "t", "nosuch": 1}),  # an unknown key
        (["create_task"], {}),  # a missing required key
        (["create_task", "--token", "x"], None),  # no argv spelling of the credential
        (["nosuch_tool"], None),
        (["approve_tool_call"], None),  # a runtime endpoint, not a callable tool
        (["create_task"], ["not", "an", "object"]),
    ],
)
def test_usage_errors_send_nothing(pin, hub, workspace, argv_tail, payload):
    argv = list(argv_tail)
    if payload is not None:
        argv.append(_args_file(workspace, "1.json", payload))

    code, envelope, raw = _call(pin, argv, env=_env(hub, workspace), cwd=workspace)

    assert code == 64, raw
    assert envelope["error"]["kind"] == "usage"
    assert hub.requests == []


def test_an_unknown_key_names_the_accepted_parameters(pin, hub, workspace):
    args = _args_file(workspace, "1.json", {"title": "t", "nosuch": 1})
    _, envelope, _ = _call(pin, ["create_task", args], env=_env(hub, workspace), cwd=workspace)
    assert "title" in envelope["error"]["detail"] and "nosuch" in envelope["error"]["detail"]


def test_call_mode_never_announces(pin, hub, workspace):
    """D4: a shim call that announced would record `connected` for a harness that refused the
    MCP server, and every later run of the agent would be told MCP -- F340's latch, rebuilt."""
    hub.routes[("POST", "/api/v1/agent-actions/tasks")] = (201, {"id": "t"})
    args = _args_file(workspace, "1.json", {"title": "t"})
    env = _env(hub, workspace)
    _call(pin, ["create_task", args], env=env, cwd=workspace)
    _call(pin, ["list_tasks"], env=env, cwd=workspace)
    _call(pin, ["--list"], env=env, cwd=workspace)

    assert hub.requests, "the calls reached the stub"
    assert "POST /api/v1/agent-actions/mcp-adapter-online" not in hub.paths()


def test_a_non_json_success_body_is_internal_without_a_traceback(pin, hub, workspace):
    hub.routes[("POST", "/api/v1/agent-actions/tasks")] = (200, b"<html>proxy</html>")
    args = _args_file(workspace, "1.json", {"title": "t"})

    code, envelope, raw = _call(pin, ["create_task", args], env=_env(hub, workspace), cwd=workspace)

    assert code == 70
    assert envelope["error"]["kind"] == "internal"
    assert "list_tasks" in envelope["error"]["detail"]  # how to check an outcome that is unknown
    assert "Traceback" not in raw


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_a_bom_args_file_is_read(pin, hub, workspace, encoding):
    hub.routes[("POST", "/api/v1/agent-actions/tasks")] = (201, {"id": "t"})
    args = _args_file(workspace, "1.json", {"title": "Ship it — now"}, encoding=encoding)

    code, _, raw = _call(pin, ["create_task", args], env=_env(hub, workspace), cwd=workspace)

    assert code == 0, raw
    assert hub.requests[0]["body"]["title"] == "Ship it — now"


@pytest.mark.skipif(os.name != "nt", reason="the ANSI code page fallback is Windows-only (D3)")
def test_a_bare_set_content_file_decodes_through_the_ansi_code_page(pin, hub, workspace):
    """Review fix 3: a bare PowerShell 5.1 `Set-Content` writes the ANSI code page with no BOM; an
    em dash is the single byte 0x97, which strict UTF-8 refuses."""
    import locale

    if locale.getencoding().lower() not in ("cp1252", "mbcs"):
        pytest.skip(f"this machine's ANSI code page is {locale.getencoding()}")
    hub.routes[("POST", "/api/v1/agent-actions/tasks")] = (201, {"id": "t"})
    path = workspace / ".agentweave" / "calls" / "1.json"
    path.write_bytes(b'{"title": "a \x97 b"}')

    code, _, raw = _call(
        pin, ["create_task", ".agentweave/calls/1.json"], env=_env(hub, workspace), cwd=workspace
    )

    assert code == 0, raw
    assert hub.requests[0]["body"]["title"] == "a — b"


def test_an_undecodable_file_is_usage_naming_the_encoding_flag(workspace, monkeypatch, capsys):
    """In process, so the code page can be patched to one that cannot decode the byte (and the
    POSIX branch, which has no fallback, gives the same answer)."""
    import locale

    path = workspace / ".agentweave" / "calls" / "1.json"
    path.write_bytes(b'{"title": "a \x97 b"}')
    monkeypatch.setattr(locale, "getencoding", lambda: "ascii")
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AW_RUN_TOKEN", TOKEN)
    monkeypatch.chdir(workspace)
    sent: List[Any] = []
    monkeypatch.setattr(mcp_server, "_hub_request", lambda *a, **k: sent.append(a) or {})

    code = mcp_server.call_main(["create_task", ".agentweave/calls/1.json"])

    envelope = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 64
    assert envelope["error"]["kind"] == "usage"
    assert "-Encoding utf8" in envelope["error"]["detail"]
    assert sent == []


# --- 1.4 (review fix 8): the args file is read only from inside the calls directory --------------


def _usage_with_no_request(pin, hub, argv, *, env, cwd):
    code, envelope, raw = _call(pin, argv, env=env, cwd=cwd)
    assert code == 64, raw
    assert envelope["error"]["kind"] == "usage"
    assert ".agentweave" in envelope["error"]["detail"]
    assert hub.requests == []


def test_a_file_outside_the_calls_directory_is_refused(pin, hub, workspace, tmp_path):
    outside = tmp_path / "elsewhere.json"
    outside.write_text(json.dumps({"title": "t"}))
    _usage_with_no_request(
        pin, hub, ["create_task", str(outside)], env=_env(hub, workspace), cwd=workspace
    )


def test_a_dotdot_path_out_of_the_calls_directory_is_refused(pin, hub, workspace):
    (workspace / ".agentweave" / "x.json").write_text(json.dumps({"title": "t"}))
    _usage_with_no_request(
        pin,
        hub,
        ["create_task", ".agentweave/calls/../x.json"],
        env=_env(hub, workspace),
        cwd=workspace,
    )


def test_no_workspace_variable_means_no_calls_directory(pin, hub, workspace):
    args = _args_file(workspace, "1.json", {"title": "t"})
    _usage_with_no_request(
        pin,
        hub,
        ["create_task", args],
        env=_env(hub, workspace, AW_WORKSPACE_DIR=None),
        cwd=workspace,
    )


def test_a_drifted_working_directory_fails_closed(pin, hub, workspace):
    """The shell resolves a relative path against where it now is; a persistent shell keeps a
    `cd`. The same relative path then names a file under the subdirectory, not the calls root."""
    sub = workspace / "sub"
    (sub / ".agentweave" / "calls").mkdir(parents=True)
    (sub / ".agentweave" / "calls" / "1.json").write_text(json.dumps({"title": "t"}))
    _usage_with_no_request(
        pin, hub, ["create_task", ".agentweave/calls/1.json"], env=_env(hub, workspace), cwd=sub
    )


def _link_dir(link: Path, target: Path) -> None:
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=True,
            capture_output=True,
        )
    else:
        link.symlink_to(target, target_is_directory=True)


def test_a_linked_calls_directory_is_not_the_calls_directory(pin, hub, tmp_path):
    """D8 / review fix 1: when `calls` is a junction or symlink, nothing is inside it."""
    ws = tmp_path / "ws-link"
    other = ws / "other"
    other.mkdir(parents=True)
    (other / "1.json").write_text(json.dumps({"title": "t"}))
    (ws / ".agentweave").mkdir()
    _link_dir(ws / ".agentweave" / "calls", other)
    _usage_with_no_request(
        pin, hub, ["create_task", ".agentweave/calls/1.json"], env=_env(hub, ws), cwd=ws
    )


def test_the_same_file_in_a_real_calls_directory_works(pin, hub, workspace):
    hub.routes[("POST", "/api/v1/agent-actions/tasks")] = (201, {"id": "t"})
    args = _args_file(workspace, "1.json", {"title": "t"})
    code, envelope, raw = _call(pin, ["create_task", args], env=_env(hub, workspace), cwd=workspace)
    assert code == 0, raw
    assert envelope["ok"] is True


def test_a_tool_with_no_required_argument_needs_no_file(pin, hub, workspace):
    hub.routes[("GET", "/api/v1/agent-actions/tasks")] = (200, {"tasks": []})
    code, envelope, raw = _call(pin, ["list_tasks"], env=_env(hub, workspace), cwd=workspace)
    assert code == 0, raw
    assert hub.paths() == ["GET /api/v1/agent-actions/tasks"]


# --- 1.5: ask_user waits through the shim too (D7) -------------------------------------------------


def _questions_file(workspace: Path) -> str:
    q = {
        "question": "Which?",
        "header": "Choice",
        "options": [
            {"label": "A", "description": "pick a"},
            {"label": "B", "description": "pick b"},
        ],
    }
    return _args_file(workspace, "q.json", {"questions": [q, dict(q, question="And?")]})


def test_ask_user_returns_the_answers_in_order(pin, hub, workspace):
    hub.routes[("POST", "/api/v1/agent-actions/questions/batch")] = (
        200,
        {"questions": [{"id": "q1"}, {"id": "q2"}]},
    )
    polls = {"q1": 0, "q2": 0}

    def state(qid, answer):
        def answer_on_second_poll():
            polls[qid] += 1
            if polls[qid] < 2:
                return 200, {"answered": False}
            return 200, {"answered": True, "answer": answer, "question": qid}

        return answer_on_second_poll

    hub.routes[("GET", "/api/v1/agent-actions/questions/q1")] = state("q1", "A")
    hub.routes[("GET", "/api/v1/agent-actions/questions/q2")] = state("q2", "B")

    code, envelope, raw = _call(
        pin,
        ["ask_user", _questions_file(workspace)],
        env=_env(hub, workspace, AW_QUESTION_TIMEOUT="10"),
        cwd=workspace,
    )

    assert code == 0, raw
    result = envelope["result"]
    assert result["answered"] is True
    assert [a["answer"] for a in result["answers"]] == ["A", "B"]


def test_ask_user_unanswered_reports_the_wait_ended(pin, hub, workspace):
    hub.routes[("POST", "/api/v1/agent-actions/questions/batch")] = (
        200,
        {"questions": [{"id": "q1"}, {"id": "q2"}]},
    )
    hub.routes[("GET", "/api/v1/agent-actions/questions/q1")] = (200, {"answered": False})
    hub.routes[("GET", "/api/v1/agent-actions/questions/q2")] = (200, {"answered": False})

    code, envelope, raw = _call(
        pin,
        ["ask_user", _questions_file(workspace)],
        env=_env(hub, workspace, AW_QUESTION_TIMEOUT="10"),
        cwd=workspace,
        timeout=60,
    )

    assert code == 0, raw
    assert envelope["result"]["answered"] is False
    assert "POST /api/v1/agent-actions/questions/wait-ended" in hub.paths()
