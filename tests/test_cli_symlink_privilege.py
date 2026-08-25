"""F22: a machine that cannot create symlinks provisions every worktree without shared deps.

`worktrees._symlink_shared_dependencies` catches the `OSError` and carries on, which is right —
failing a whole turn over a missing `node_modules` would be worse than provisioning without one.
What was missing is anything *saying so*. The agent finds out by running the suite and failing; the
operator sees a checkout that looks complete; `doctor` did not look.

Measured on this machine 2026-08-24:

    Path.symlink_to(...) -> OSError [WinError 1314]
    A required privilege is not held by the client
"""

from pathlib import Path
from unittest.mock import patch

from agentweave import diagnostics


def _result():
    return diagnostics.check_symlink_privilege()


def test_a_machine_that_can_symlink_passes():
    with patch.object(Path, "symlink_to", lambda *args, **kwargs: None):
        result = _result()

    assert result.status == "pass"
    assert result.id == "symlink_privilege_ready"
    assert result.category == "environment"


def test_a_machine_that_cannot_symlink_warns_and_names_the_remedy():
    """A warning, not a failure: the Hub runs correctly without it, and on a project whose tooling
    is all on PATH nothing is lost. What it must not do is stay silent."""

    def refuse(*args, **kwargs):
        raise OSError(1314, "A required privilege is not held by the client")

    with patch.object(Path, "symlink_to", refuse):
        result = _result()

    assert result.status == "warn"
    assert result.id == "symlink_privilege_missing"
    # The consequence, in the words the operator will meet it in — an agent reporting that it could
    # not run the tests. Without this the warning is a fact with no meaning attached.
    assert "could not run the project's tests" in result.message
    # And the remedy, which is one machine-wide setting rather than something per worktree.
    assert "Developer Mode" in (result.hint or "")
    assert "every worktree" in (result.hint or "")


def test_the_failure_is_carried_for_diagnosis():
    def refuse(*args, **kwargs):
        raise OSError(1314, "A required privilege is not held by the client")

    with patch.object(Path, "symlink_to", refuse):
        result = _result()

    assert "1314" in str(result.data)


def test_the_probe_leaves_nothing_behind():
    """It writes into the Hub's own state directory, so it must not accumulate anything there."""
    NATIVE_HUB_DIR = diagnostics.NATIVE_HUB_DIR

    before = set(Path(NATIVE_HUB_DIR).iterdir()) if Path(NATIVE_HUB_DIR).exists() else set()
    _result()
    after = set(Path(NATIVE_HUB_DIR).iterdir()) if Path(NATIVE_HUB_DIR).exists() else set()

    assert before == after


def test_doctor_runs_it():
    """A check nothing calls is a check that does not exist — which is the shape of defect this
    same session found in `note_turn_that_produced_nothing` (F41)."""
    results = diagnostics.collect_diagnostics(port=8010, profile="beta")

    assert any(result.id.startswith("symlink_privilege_") for result in results)


def test_the_restated_directory_list_agrees_with_the_hubs():
    """The message names the directories that will be missing, so it has to name the right ones.

    Restated rather than imported because the CLI's own code imports nothing outside the stdlib —
    the same convention `mcp_server.py` uses for everything it cannot import, and the same reason
    it needs a test.
    """
    from hub.worktrees import SHARED_DEPENDENCY_DIRS

    assert diagnostics._SHARED_DEPENDENCY_DIRS == SHARED_DEPENDENCY_DIRS
