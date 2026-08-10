"""The transition map, tested as a declaration rather than through the API.

The map is the one place the lifecycle is stated, so these tests are the lifecycle's specification
in executable form: change an edge and exactly the test describing it should fail.
"""

from pathlib import Path

import pytest

from hub.task_transitions import (
    ACTOR_OPERATOR,
    ACTOR_RUN,
    ENTRY_STATUSES,
    STATUSES,
    TRANSITIONS,
    Actor,
    allowed_map_for,
    allowed_targets,
    is_allowed,
    is_entry_status,
    operator,
    refusal_detail,
    run_actor,
)

# --------------------------------------------------------------------------------------
# The map agrees with the two independent status declarations
# --------------------------------------------------------------------------------------


def test_map_covers_exactly_the_cli_status_list():
    """A ninth status added to the CLI without declaring its edges must fail here, not silently
    produce a status nothing can reach."""
    from agentweave.constants import TASK_STATUSES

    assert set(TASK_STATUSES) == STATUSES


def test_map_covers_exactly_the_hub_schema_status_list():
    from hub.schemas.tasks import _TASK_STATUSES

    assert set(_TASK_STATUSES) == STATUSES


def test_every_declared_target_is_itself_a_known_status():
    """An edge pointing at a status the map does not declare would be unreachable-by-construction:
    a task could enter it and then have nowhere to go."""
    for from_status, edges in TRANSITIONS.items():
        for to_status in edges:
            assert to_status in STATUSES, f"{from_status} -> {to_status} names an unknown status"


def test_no_edge_declares_an_unknown_actor_kind():
    for from_status, edges in TRANSITIONS.items():
        for to_status, actors in edges.items():
            assert actors, f"{from_status} -> {to_status} permits no actor at all"
            assert actors <= {ACTOR_RUN, ACTOR_OPERATOR}


def test_no_status_declares_a_transition_to_itself():
    """Restating the current status is a no-op handled by the service (D7), not an edge. An edge
    would make it a recordable transition and corrupt "who completed this"."""
    for from_status, edges in TRANSITIONS.items():
        assert from_status not in edges


# --------------------------------------------------------------------------------------
# Entry statuses
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", sorted(ENTRY_STATUSES))
def test_entry_statuses_are_accepted_at_creation(status):
    assert is_entry_status(status)


@pytest.mark.parametrize(
    "status",
    ["in_progress", "completed", "under_review", "revision_needed", "approved", "rejected"],
)
def test_non_entry_statuses_are_refused_at_creation(status):
    """The hole the 2026-08-10 scan found: without this, a caller creates a task already `approved`
    and never transitions at all, walking around the whole machine."""
    assert not is_entry_status(status)


def test_entry_statuses_are_a_subset_of_known_statuses():
    assert ENTRY_STATUSES <= STATUSES


# --------------------------------------------------------------------------------------
# The lifecycle an agent may drive
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        ("pending", "assigned"),
        ("pending", "in_progress"),
        ("assigned", "in_progress"),
        ("assigned", "pending"),
        ("in_progress", "completed"),
        ("in_progress", "assigned"),
        ("completed", "under_review"),
        ("under_review", "approved"),
        ("under_review", "revision_needed"),
        ("under_review", "rejected"),
        ("revision_needed", "in_progress"),
    ],
)
def test_agent_may_walk_the_ordinary_lifecycle(from_status, to_status):
    assert is_allowed(from_status, to_status, ACTOR_RUN)


def test_agent_cannot_skip_review_to_approve():
    """The hole this change exists to close: reachable today from MCP `update_task` in one call."""
    assert not is_allowed("in_progress", "approved", ACTOR_RUN)
    assert not is_allowed("completed", "approved", ACTOR_RUN)


def test_agent_cannot_reach_approved_from_anywhere_but_review():
    for from_status in STATUSES - {"under_review"}:
        assert not is_allowed(from_status, "approved", ACTOR_RUN)


# --------------------------------------------------------------------------------------
# The operator's extra edges (D9)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "from_status", ["pending", "assigned", "in_progress", "completed", "revision_needed"]
)
def test_only_the_operator_may_reject_before_review(from_status):
    assert is_allowed(from_status, "rejected", ACTOR_OPERATOR)
    assert not is_allowed(from_status, "rejected", ACTOR_RUN)


def test_an_agent_may_reject_at_review_because_that_is_a_review_outcome():
    assert is_allowed("under_review", "rejected", ACTOR_RUN)


@pytest.mark.parametrize(
    "from_status,to_status", [("approved", "revision_needed"), ("rejected", "pending")]
)
def test_only_the_operator_may_reopen_a_decided_task(from_status, to_status):
    assert is_allowed(from_status, to_status, ACTOR_OPERATOR)
    assert not is_allowed(from_status, to_status, ACTOR_RUN)


def test_an_agent_has_no_exit_from_a_decided_task():
    for from_status in ("approved", "rejected"):
        assert allowed_targets(from_status, ACTOR_RUN) == frozenset()


def test_the_operator_is_still_bound_by_the_map():
    """Operator authority is extra edges, not a bypass (D9) — which is what lets every recorded
    history describe a legal sequence."""
    assert not is_allowed("pending", "approved", ACTOR_OPERATOR)
    assert not is_allowed("in_progress", "under_review", ACTOR_OPERATOR)
    assert not is_allowed("approved", "in_progress", ACTOR_OPERATOR)


def test_the_operator_can_reach_every_status_the_agent_can():
    """The operator's set is a superset everywhere; there is no edge an agent has and they do not."""
    for from_status in STATUSES:
        agent_targets = allowed_targets(from_status, ACTOR_RUN)
        operator_targets = allowed_targets(from_status, ACTOR_OPERATOR)
        assert agent_targets <= operator_targets, from_status


# --------------------------------------------------------------------------------------
# Unknown statuses
# --------------------------------------------------------------------------------------


def test_an_unknown_status_yields_no_targets_rather_than_raising():
    """Callers arrive here with a status read from a row. An unknown one is the case to refuse, not
    the case to crash on."""
    assert allowed_targets("banana", ACTOR_OPERATOR) == frozenset()
    assert not is_allowed("banana", "approved", ACTOR_OPERATOR)


# --------------------------------------------------------------------------------------
# The actor type (D2)
# --------------------------------------------------------------------------------------


def test_a_run_actor_must_carry_a_run_id():
    with pytest.raises(ValueError):
        Actor(kind=ACTOR_RUN, agent="claude")


def test_a_run_actor_must_carry_its_agent():
    """Author/reviewer separation compares the agent, so an actor that cannot name one would slip
    past the rule the same way the run-based version did."""
    with pytest.raises(ValueError):
        Actor(kind=ACTOR_RUN, run_id="run-1")


def test_an_operator_actor_must_not_carry_an_agent():
    with pytest.raises(ValueError):
        Actor(kind=ACTOR_OPERATOR, agent="claude")


def test_an_operator_actor_must_not_carry_a_run_id():
    """Otherwise a run could present itself as the operator while still being attributable, which is
    the privilege escalation D2 exists to make unstateable."""
    with pytest.raises(ValueError):
        Actor(kind=ACTOR_OPERATOR, run_id="run-1")


def test_an_unknown_actor_kind_is_refused():
    with pytest.raises(ValueError):
        Actor(kind="admin")


def test_the_constructors_build_what_they_say():
    assert operator().is_operator
    assert operator().run_id is None
    assert not run_actor("run-1", "claude").is_operator
    assert run_actor("run-1", "claude").run_id == "run-1"
    assert run_actor("run-1", "claude").agent == "claude"


# --------------------------------------------------------------------------------------
# The actor-scoped map the UI reads (D13)
# --------------------------------------------------------------------------------------


def test_allowed_map_covers_every_status_for_both_actors():
    for actor_kind in (ACTOR_RUN, ACTOR_OPERATOR):
        assert set(allowed_map_for(actor_kind)) == STATUSES


def test_allowed_map_agrees_with_the_edge_queries():
    """The endpoint must serve the same declaration the service enforces, or the control offers
    moves that are then refused."""
    for actor_kind in (ACTOR_RUN, ACTOR_OPERATOR):
        for from_status, targets in allowed_map_for(actor_kind).items():
            assert set(targets) == allowed_targets(from_status, actor_kind)


def test_allowed_map_targets_are_sorted_for_a_stable_response():
    for actor_kind in (ACTOR_RUN, ACTOR_OPERATOR):
        for targets in allowed_map_for(actor_kind).values():
            assert list(targets) == sorted(targets)


def test_the_operator_map_shows_the_reopen_edges():
    operator_map = allowed_map_for(ACTOR_OPERATOR)
    assert operator_map["approved"] == ("revision_needed",)
    assert operator_map["rejected"] == ("pending",)


def test_the_agent_map_shows_no_exit_from_a_decided_task():
    agent_map = allowed_map_for(ACTOR_RUN)
    assert agent_map["approved"] == ()
    assert agent_map["rejected"] == ()


# --------------------------------------------------------------------------------------
# Refusal text — an agent's only feedback
# --------------------------------------------------------------------------------------


def test_refusal_names_the_current_status_and_what_is_reachable():
    detail = refusal_detail("in_progress", "approved", ACTOR_RUN)
    assert "in_progress" in detail
    assert "approved" in detail
    assert "completed" in detail


def test_refusal_from_a_dead_end_says_so_rather_than_listing_nothing():
    detail = refusal_detail("approved", "in_progress", ACTOR_RUN)
    assert "approved" in detail
    assert "no transitions available" in detail


def test_refusal_for_an_unknown_status_says_it_is_unknown():
    detail = refusal_detail("banana", "approved", ACTOR_OPERATOR)
    assert "unknown status" in detail


# --------------------------------------------------------------------------------------
# Append-only is a property of the source, not of the database (D4)
# --------------------------------------------------------------------------------------


def test_no_application_path_updates_or_deletes_a_transition():
    """Append-only is enforced by the absence of a write path, not by a database trigger (D4).

    Scans the Hub package for a mutation aimed at TaskTransition. A future `delete(TaskTransition)`
    or an assignment to a persisted row's field fails here rather than quietly eroding the one
    record whose value is that nothing in it changes.
    """
    from pathlib import Path

    hub_package = Path(__file__).resolve().parents[1] / "hub"
    offenders = []
    forbidden = ("delete(TaskTransition", "TaskTransition).where", "update(TaskTransition")
    for path in hub_package.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            if pattern in source:
                # `select(TaskTransition).where(...)` is a read and reaches this via the second
                # pattern, so only flag it when it is not preceded by `select(`.
                if pattern == "TaskTransition).where" and "select(TaskTransition).where" in source:
                    continue
                offenders.append(f"{path.name}: {pattern}")
    assert offenders == [], f"transition history must be append-only, found: {offenders}"


# ---------------------------------------------------------------------------
# The MCP adapter surfaces a refusal as a failure, not a success (section 6)
# ---------------------------------------------------------------------------


def test_mcp_reports_a_refusal_as_a_failure_carrying_the_reachable_set():
    """A refused agent's only feedback is this string. `_hub_request` already raises on non-2xx, so
    what needs proving is that the detail survives `_readable_detail` intact and is never converted
    into an empty or successful result."""
    import json
    import urllib.error
    from unittest.mock import patch

    from hub.mcp_server import HubAPIError, _hub_request
    from hub.task_transitions import ACTOR_RUN, refusal_detail

    detail = refusal_detail("in_progress", "approved", ACTOR_RUN)
    body = json.dumps({"detail": detail}).encode()

    error = urllib.error.HTTPError(
        url="http://hub/api/v1/agent-actions/tasks/task-1",
        code=409,
        msg="Conflict",
        hdrs=None,
        fp=None,
    )
    error.read = lambda: body  # type: ignore[method-assign]

    with patch("hub.mcp_server._bound_token", return_value="aw_run_x"), patch(
        "urllib.request.urlopen", side_effect=error
    ):
        with pytest.raises(HubAPIError) as excinfo:
            _hub_request("PATCH", "/tasks/task-1", {"status": "approved"})

    assert excinfo.value.status_code == 409
    # The agent must be able to correct itself: current status and what it can actually reach.
    assert "in_progress" in excinfo.value.detail
    assert "completed" in excinfo.value.detail


def test_mcp_states_the_statuses_but_holds_no_adjacency():
    """`mcp_server.py` is spawned standalone and may import only stdlib + fastmcp, so anything it
    restates needs an agreement test (CLAUDE.md).

    It legitimately restates the *status list*, as the `TaskStatus` literal its tool signature
    needs — so that list is pinned here. It must not restate the *map*: which status follows which
    is knowledge the service enforces, and a copy here would be a second answer that drifts. The
    map reaches the agent as a refusal message instead.
    """
    import typing

    from hub import mcp_server
    from hub.task_transitions import STATUSES

    assert set(typing.get_args(mcp_server.TaskStatus)) == STATUSES

    source = (Path(__file__).resolve().parents[1] / "hub" / "mcp_server.py").read_text(
        encoding="utf-8"
    )
    for adjacency_marker in ("TRANSITIONS", "allowed_targets", "ENTRY_STATUSES", "is_allowed"):
        assert adjacency_marker not in source, (
            f"{adjacency_marker} appears in mcp_server.py — the transition map must not be copied "
            f"into the adapter"
        )


# --------------------------------------------------------------------------------------
# The transition origin, and the two things that keep it honest (run-task-binding, D5)
# --------------------------------------------------------------------------------------


def test_the_actor_kinds_are_unchanged_by_the_runtime_origin():
    """The runtime is a *cause*, not an actor.

    A third actor kind would require every edge in the map to declare whether the runtime may take
    it, and would admit moves no one is accountable for. Recording the cause separately leaves the
    map — and author/reviewer separation, which reads agent identity — untouched.
    """
    from hub.task_transitions import ACTOR_KINDS

    assert set(ACTOR_KINDS) == {"run", "operator"}


def test_only_the_binding_module_may_record_a_runtime_transition():
    """A source scan, in the manner of the append-only scan above.

    `origin='runtime'` exempts a transition from the divergence check — it says "the Hub did this,
    not the agent". A second caller acquiring it would silently make its own transitions invisible
    to the run-boundary check, which is the failure this whole capability exists to prevent. The
    default is `actor` for the same reason: a forgotten argument must not exempt anything.
    """
    from pathlib import Path

    from hub.task_transition_service import ORIGIN_RUNTIME

    hub_package = Path(__file__).resolve().parents[1] / "hub"
    permitted = {"run_task_binding.py", "task_transition_service.py"}
    offenders = []
    for path in hub_package.rglob("*.py"):
        if path.name in permitted:
            continue
        source = path.read_text(encoding="utf-8")
        if f'origin="{ORIGIN_RUNTIME}"' in source or f"origin='{ORIGIN_RUNTIME}'" in source:
            offenders.append(path.name)
    assert offenders == [], (
        "only the run→task binding may record a runtime-caused transition, " f"found: {offenders}"
    )
