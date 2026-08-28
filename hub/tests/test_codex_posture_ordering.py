"""The four Codex postures, as the ordered table the operator was offered.

Found live on 2026-08-28 by driving one Codex agent through both surfaces that set a posture.
Setting the agent's *default* posture to "Full access" and asking it to write outside its
worktree succeeded; choosing the *same* posture for a single turn through the composer's
Permissions pill, on the same agent and the same command, was refused by Codex's sandbox.

The cause was that `_codex_posture` mapped "Full access" to `None` — which is the *default*
posture — so the thread started `workspace-write`/`on-request` and `decide_approval` fell
through to its `yolo`-or-decline branch. It only appeared to work at all because setting an
agent default also writes the legacy `config["yolo"]` flag, and `yolo` reaches `_thread_policy`
by a route of its own. Nothing writes that flag for a per-run override.

These tests are written as an *ordering* rather than as four independent rows, because the
defect was not that one row was wrong in isolation: it was that the most permissive posture the
operator can choose had become strictly less permissive than the middle one, while still
carrying the label "Full access".
"""

import pytest

from hub.api.v1.agent_trigger import _codex_posture
from hub.codex_appserver import (
    COMMAND_APPROVAL_METHOD,
    FILE_CHANGE_APPROVAL_METHOD,
    PERMISSIONS_APPROVAL_METHOD,
    _thread_policy,
    decide_approval,
)
from hub.model_catalog import FULL_ACCESS_PERMISSION_MODE, WORKSPACE_PERMISSION_MODE
from hub.runner_commands import build_command

OWN_SERVER = "agentweave"
WORKSPACE = r"C:\proj\.agentweave\worktrees\coder"
OUTSIDE = r"C:\proj"

# The two approvals a sandbox raises. Both must answer the same way for a given posture — an
# operator picks one posture, not one per approval kind.
SANDBOX_METHODS = (COMMAND_APPROVAL_METHOD, FILE_CHANGE_APPROVAL_METHOD)


def _decide(method, posture, *, cwd, yolo=False):
    params = (
        {"command": "cmd /c echo x", "cwd": cwd}
        if method == COMMAND_APPROVAL_METHOD
        else {"grantRoot": cwd}
    )
    return decide_approval(
        method,
        params,
        yolo=yolo,
        own_server_name=OWN_SERVER,
        posture=posture,
        workspace=WORKSPACE,
    )


class TestPostureSurvivesTheMapping:
    """Every posture that changes a Codex decision has to reach the code that decides."""

    def test_full_access_is_not_dropped(self):
        # The regression itself: this returned None, and None is the default posture.
        assert _codex_posture(FULL_ACCESS_PERMISSION_MODE) == FULL_ACCESS_PERMISSION_MODE

    @pytest.mark.parametrize(
        "chosen",
        ["manual", WORKSPACE_PERMISSION_MODE, FULL_ACCESS_PERMISSION_MODE],
    )
    def test_every_posture_that_is_not_the_default_is_distinguishable(self, chosen):
        """`acceptEdits` maps to None on purpose — it *is* the default. Nothing else may."""
        assert _codex_posture(chosen) is not None

    def test_accept_edits_maps_to_the_default_deliberately(self):
        assert _codex_posture("acceptEdits") is None


class TestThreadPolicyOrdering:
    """What the thread starts under. This is what the OS sandbox actually enforces."""

    def test_full_access_starts_a_thread_with_no_restraint(self):
        # Reached through the real mapping, not by passing the constant in by hand: the branch
        # for this posture existed all along and was unreachable, so a test that calls
        # `_thread_policy` directly with the string would have passed against the defect.
        posture = _codex_posture(FULL_ACCESS_PERMISSION_MODE)
        assert _thread_policy(yolo=False, posture=posture) == ("danger-full-access", "never")

    def test_full_access_does_not_depend_on_the_legacy_yolo_flag(self):
        """`yolo=False` is what a per-run override carries; the agent-default route sets it."""
        with_flag = _thread_policy(yolo=True, posture=_codex_posture(FULL_ACCESS_PERMISSION_MODE))
        without = _thread_policy(yolo=False, posture=_codex_posture(FULL_ACCESS_PERMISSION_MODE))
        assert with_flag == without == ("danger-full-access", "never")

    def test_full_access_is_not_the_same_thread_as_the_default_posture(self):
        """The exact confusion the defect was: indistinguishable from choosing nothing."""
        assert _thread_policy(
            yolo=False, posture=_codex_posture(FULL_ACCESS_PERMISSION_MODE)
        ) != _thread_policy(yolo=False, posture=_codex_posture("acceptEdits"))

    def test_ask_me_remains_the_strictest_pair(self):
        assert _thread_policy(yolo=False, posture=_codex_posture("manual")) == (
            "read-only",
            "untrusted",
        )


class TestApprovalOrdering:
    """Whatever a narrower posture accepts, a wider one must accept too."""

    @pytest.mark.parametrize("method", SANDBOX_METHODS)
    def test_full_access_accepts_inside_the_workspace(self, method):
        assert _decide(method, _codex_posture(FULL_ACCESS_PERMISSION_MODE), cwd=WORKSPACE) == {
            "decision": "accept"
        }

    @pytest.mark.parametrize("method", SANDBOX_METHODS)
    def test_full_access_accepts_what_workspace_only_refuses(self, method):
        """The inversion, stated directly: outside the workspace, "Workspace only" declines and
        "Full access" — which the operator picked *because* it is wider — must not."""
        narrow = _decide(method, _codex_posture(WORKSPACE_PERMISSION_MODE), cwd=OUTSIDE)
        wide = _decide(method, _codex_posture(FULL_ACCESS_PERMISSION_MODE), cwd=OUTSIDE)
        assert narrow == {"decision": "decline"}
        assert wide == {"decision": "accept"}

    @pytest.mark.parametrize("method", SANDBOX_METHODS)
    def test_full_access_accepts_without_the_legacy_flag(self, method):
        assert _decide(
            method, _codex_posture(FULL_ACCESS_PERMISSION_MODE), cwd=OUTSIDE, yolo=False
        ) == {"decision": "accept"}

    def test_full_access_grants_the_permissions_request(self):
        result = decide_approval(
            PERMISSIONS_APPROVAL_METHOD,
            {},
            yolo=False,
            own_server_name=OWN_SERVER,
            posture=_codex_posture(FULL_ACCESS_PERMISSION_MODE),
        )
        assert result["permissions"], "full access answered a permissions request with nothing"

    @pytest.mark.parametrize("method", SANDBOX_METHODS)
    def test_ask_me_still_reaches_the_operator_rather_than_being_decided_here(self, method):
        """Full access must not have swallowed the posture that has to ask a person."""
        decision = _decide(method, _codex_posture("manual"), cwd=WORKSPACE)
        assert decision["decision"] == "__ask_operator__"

    @pytest.mark.parametrize("method", SANDBOX_METHODS)
    def test_the_default_posture_still_refuses_an_escalation(self, method):
        """Unchanged by the fix, and asserted so a later widening of `_codex_posture` cannot
        quietly take `acceptEdits` with it."""
        assert _decide(method, _codex_posture("acceptEdits"), cwd=OUTSIDE) == {
            "decision": "decline"
        }


class TestExecTransportHasTheSameOrdering:
    """The same posture, on the other Codex transport.

    `codex exec` is the escape hatch a runner selects with `--no-app-server`, and it had the
    identical hole for the identical reason: the catalog's `permission_mode` control renders
    nothing to argv (`ApplySpec(style="none")`, because app-server carries the posture in its
    thread policy instead), so the only thing that could ever reach `exec`'s sandbox flag was
    `yolo` — the flag one surface writes. Found by asking the carry-forward's own question after
    fixing app-server: where else is this rule supposed to hold?
    """

    def _argv(self, **kwargs):
        return build_command(runner="codex", cli="codex", prompt="hi", **kwargs)

    def test_full_access_bypasses_the_sandbox_without_the_legacy_flag(self):
        argv = self._argv(
            yolo=False, control_overrides={"permission_mode": FULL_ACCESS_PERMISSION_MODE}
        )
        assert "--dangerously-bypass-approvals-and-sandbox" in argv
        assert "--sandbox" not in argv

    def test_workspace_only_stays_sandboxed(self):
        argv = self._argv(
            yolo=False, control_overrides={"permission_mode": WORKSPACE_PERMISSION_MODE}
        )
        assert argv[argv.index("--sandbox") + 1] == "workspace-write"
        assert "--dangerously-bypass-approvals-and-sandbox" not in argv

    def test_default_posture_stays_sandboxed(self):
        argv = self._argv(yolo=False, control_overrides={"permission_mode": "acceptEdits"})
        assert argv[argv.index("--sandbox") + 1] == "workspace-write"

    def test_an_open_spec_document_still_outranks_full_access(self):
        """`restrict_spec_writes` is a role boundary, not a posture, and holds unconditionally
        (F4/design D6). Widening the posture must not have given it a way through."""
        argv = self._argv(
            yolo=False,
            control_overrides={"permission_mode": FULL_ACCESS_PERMISSION_MODE},
            restrict_spec_writes=True,
        )
        assert argv[argv.index("--sandbox") + 1] == "read-only"
        assert "--dangerously-bypass-approvals-and-sandbox" not in argv
