"""Import-boundary tests for `hub.runner_adapters` (task 2.1).

`runner_adapters` must stay import-safe for a worker-style spawn: it must not reach the database,
the worker's bookkeeping, the launchability probe, or any API route (design D1). Each boundary
check runs in a fresh `py -3.11` subprocess, not in this pytest process, because a sibling test
file collected earlier in the same run may already have imported `hub.worker` or `hub.api`, which
would make an in-process `sys.modules` check pass by accident whether or not this package pulls
them in itself.
"""

from __future__ import annotations

import subprocess
import sys

FORBIDDEN_ON_RUNNER_ADAPTERS_IMPORT = (
    "hub.db.engine",
    "hub.worker",
    "hub.launchability",
    "hub.api",
)


def _run_fresh_interpreter(code: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_importing_runner_adapters_avoids_db_worker_launchability_and_api():
    forbidden = repr(FORBIDDEN_ON_RUNNER_ADAPTERS_IMPORT)
    _run_fresh_interpreter(
        "import sys\n"
        "import hub.runner_adapters\n"
        f"forbidden = {forbidden}\n"
        "hit = [m for m in forbidden if m in sys.modules]\n"
        "assert not hit, hit\n"
    )


def test_importing_runner_commands_alone_avoids_codex_appserver():
    # D1/D12's one load-bearing edge: codex_appserver imports runner_commands for
    # OPERATOR_POSTURE, so the reverse import would close a cycle.
    _run_fresh_interpreter(
        "import sys\n"
        "import hub.runner_commands\n"
        "assert 'hub.codex_appserver' not in sys.modules\n"
    )


def test_rpc_turn_request_repr_hides_env():
    # Consistency pass, 2026-09-28: env carries the run's tokens (and, under slice 5, a BYOK key);
    # a dataclass repr in a log line would otherwise print them.
    from hub.runner_adapters.base import RpcTurnRequest

    req = RpcTurnRequest(
        cli="codex",
        cwd=".",
        env={"GH_TOKEN": "aw-sentinel"},
        prompt="hello",
        model=None,
        resume_session_id=None,
        yolo=False,
        mcp_command=None,
        config_overrides=None,
        permission_mode=None,
        workspace=".",
        extra_flags=None,
        restrict_spec_writes=False,
    )
    assert "aw-sentinel" not in repr(req)


def test_runner_adapter_and_transports_are_abstract():
    from hub.runner_adapters.base import RpcTransport, RunnerAdapter, StreamTransport

    for abstract_cls in (RunnerAdapter, StreamTransport, RpcTransport):
        try:
            abstract_cls()  # type: ignore[abstract]
        except TypeError:
            continue
        raise AssertionError(f"{abstract_cls} instantiated with abstract members unimplemented")
