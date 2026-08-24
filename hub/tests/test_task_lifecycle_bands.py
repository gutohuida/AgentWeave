"""`loop-notices-and-reacts` group 3 — every status classified once, every set derived.

Five constants around the codebase answered questions of the form *"is this task live?"* and none
knew the others existed. All three loop stall bugs to date lived in the gaps between them:

* 2026-08-20, the spin — `completed` was in neither the claim set nor the terminal set, so a queue
  of completed-but-unapproved tasks was simultaneously unclaimable and "not drained", and the loop
  spawned an agent every tick forever.
* 2026-08-20, `revision_needed` — in neither of those two, while two *other* sets already called it
  live work. A reviewer who correctly sent work back stranded the loop.
* 2026-08-24, the blocked board — the board answered "what is this loop working on" with the
  *claimable* set, so when `blocked` left the claim the board stopped showing blocked tasks and a
  loop parked on an unanswered question read as idle.

**The equality assertions here are the safety property, and they were written before any literal
was deleted** (task 3.3). A refactor that changes a set's membership fails them rather than
shipping. They spell the expected members out in full, deliberately: comparing a derivation against
another derivation would pass while both were wrong together, which is exactly how the
`_loop_queue_order` bug survived review.
"""

import pytest

from hub.task_transitions import (
    BAND_AGENT_ACTIONABLE,
    BAND_AWAITING_HANDOFF,
    BAND_AWAITING_PERSON,
    BAND_TERMINAL,
    BAND_WITH_REVIEWER,
    CLAIMABLE_STATUSES,
    CURRENT_ITEM_STATUSES,
    LIVE_STATUSES,
    REVIEWABLE_STATUSES,
    STATUS_BANDS,
    TERMINAL_STATUSES,
    TRANSITIONS,
    _check_bands,
)

# ---------------------------------------------------------------------------
# 3.1 — every status the machine defines has exactly one band
# ---------------------------------------------------------------------------


def test_every_status_in_the_transition_map_has_a_band():
    """Derived from the map, never from a literal list — so adding a ninth status to `TRANSITIONS`
    without classifying it fails here rather than at 3am in a loop that fires forever."""
    defined = set(TRANSITIONS)
    for to_map in TRANSITIONS.values():
        defined |= set(to_map)
    assert defined == set(STATUS_BANDS), (
        f"unclassified: {sorted(defined - set(STATUS_BANDS))}; "
        f"classified but undefined: {sorted(set(STATUS_BANDS) - defined)}"
    )


def test_a_status_cannot_be_in_more_than_one_band_by_construction():
    """The classification is a mapping *from status to band*, so "in two bands" is unrepresentable
    rather than merely detected.

    This is a stronger guarantee than the startup check the requirement asks for, and it is the
    reason the shape was chosen over a band-to-statuses mapping, which would have made the invalid
    state expressible and then needed a check to catch it.
    """
    assert all(isinstance(band, str) for band in STATUS_BANDS.values())


# ---------------------------------------------------------------------------
# 3.2 — an unclassified status refuses at import, naming it
# ---------------------------------------------------------------------------


def test_an_unclassified_status_is_refused_and_named(monkeypatch):
    monkeypatch.setitem(TRANSITIONS, "invented_status", {})
    with pytest.raises(RuntimeError) as excinfo:
        _check_bands()
    assert "invented_status" in str(excinfo.value)
    assert "STATUS_BANDS" in str(excinfo.value), "the message must say where to fix it"


def test_a_status_in_an_unknown_band_is_refused_and_named(monkeypatch):
    """The other direction: a band name that is not one of the five. A typo in a band constant
    would otherwise silently drop a status out of every derived set."""
    monkeypatch.setitem(STATUS_BANDS, "pending", "agent_actionabel")
    with pytest.raises(RuntimeError) as excinfo:
        _check_bands()
    message = str(excinfo.value)
    assert "pending" in message
    assert "agent_actionabel" in message


def test_a_band_for_a_status_the_machine_does_not_define_is_refused(monkeypatch):
    monkeypatch.setitem(STATUS_BANDS, "ghost_status", BAND_TERMINAL)
    with pytest.raises(RuntimeError) as excinfo:
        _check_bands()
    assert "ghost_status" in str(excinfo.value)


def test_the_real_classification_passes_its_own_check():
    _check_bands()


# ---------------------------------------------------------------------------
# 3.3 — each derived set equals the literal it replaced
# ---------------------------------------------------------------------------


def test_claimable_matches_the_literal_it_replaced():
    """`scheduler.CLAIMABLE_LOOP_TASK_STATUSES`, measured 2026-08-24.

    `blocked` is absent, and that is the correction this task's own text needed: the change
    specified these members with `blocked` included, which stopped being true on 2026-08-21 when it
    left the claim to stop the spin. Asserting the spec's version would have re-added it.
    """
    assert (
        frozenset({"in_progress", "assigned", "pending", "revision_needed"}) == CLAIMABLE_STATUSES
    )


def test_current_item_matches_the_literal_it_replaced():
    """`scheduler.CURRENT_ITEM_TASK_STATUSES` — the claimable four, plus `blocked`, plus
    `completed`.

    `completed` joined in `loop-becomes-a-flow` group 3 and is the second status to enter this set
    without entering the claim, for the same reason as the first arriving from the other direction.
    `blocked` is here because a firing may *not* take it and the operator must see it; `completed`
    because a firing now *may* take it — for review, by an agent that did not finish it — and if
    the board's query could not return the row it would show no current item for a loop that was
    actively reviewing. That is the 2026-08-21 defect again, mirrored.
    """
    assert (
        frozenset({"in_progress", "assigned", "pending", "revision_needed", "blocked", "completed"})
        == CURRENT_ITEM_STATUSES
    )


def test_terminal_matches_the_literal_it_replaced():
    """`run_task_binding.TERMINAL_FOR_BINDING`. `completed` and `under_review` are deliberately
    absent — a run may still bind to a task awaiting review."""
    assert frozenset({"approved", "rejected"}) == TERMINAL_STATUSES


def test_live_matches_both_literals_it_replaced():
    """`agents._ACTIVE_TASK_STATUSES` and `checkpoints._LIVE_TASK_STATUSES` were identical in
    content and separate in code. One set now."""
    expected = frozenset({"pending", "assigned", "in_progress", "under_review", "revision_needed"})
    assert expected == LIVE_STATUSES


def test_the_consumers_agree_with_the_derived_sets():
    """Value equality at every consumer. Necessary but not sufficient — a hand-written literal that
    happens to be correct passes this — which is why the source scan below exists too."""
    from hub.api.v1.agents import _ACTIVE_TASK_STATUSES
    from hub.checkpoints import _LIVE_TASK_STATUSES
    from hub.run_task_binding import TERMINAL_FOR_BINDING
    from hub.scheduler import CLAIMABLE_LOOP_TASK_STATUSES, CURRENT_ITEM_TASK_STATUSES

    assert frozenset(CLAIMABLE_LOOP_TASK_STATUSES) == CLAIMABLE_STATUSES
    assert frozenset(CURRENT_ITEM_TASK_STATUSES) == CURRENT_ITEM_STATUSES
    assert frozenset(TERMINAL_FOR_BINDING) == TERMINAL_STATUSES
    assert frozenset(_ACTIVE_TASK_STATUSES) == LIVE_STATUSES
    assert frozenset(_LIVE_TASK_STATUSES) == LIVE_STATUSES


# ---------------------------------------------------------------------------
# The distinctions the bands exist to keep
# ---------------------------------------------------------------------------


def test_current_item_holds_everything_claimable_and_more():
    """The 2026-08-24 defect, as a property of the classification rather than of two literals.

    `blocked` is *no* to "may a firing claim this?" and *yes* to "is this the loop's current
    work?". A classification that collapsed those into one "live" band would reproduce the bug it
    was written to prevent.

    **Renamed and loosened by `loop-becomes-a-flow` group 3**, which added a second such status.
    The direction is what is load-bearing and is asserted exactly: nothing claimable may be missing
    from current-item, or the board would fail to name work the firing is about to take. What may
    be present without being claimable is open-ended by design, and the two members it has today
    are pinned by name below so a *third* arriving unnoticed still fails something.
    """
    assert frozenset() == CLAIMABLE_STATUSES - CURRENT_ITEM_STATUSES
    assert {"blocked", "completed"} == CURRENT_ITEM_STATUSES - CLAIMABLE_STATUSES


def test_the_two_statuses_that_are_current_without_being_claimable_differ_in_kind():
    """They are in the same difference for opposite reasons, and conflating them would lose the
    distinction group 3 depends on.

    `blocked` is unclaimable by *everyone*: the answer that unblocks it comes from a person, so
    firing any agent at it cannot help. `completed` is unclaimable by exactly *one* agent, the one
    that finished it, and claimable by everyone else — which is why it is the reviewable set and
    `blocked` is not. A future refactor that merged the two bands would either make finished work
    unreviewable or make blocked work claimable, and both have already shipped once.
    """
    assert {"completed"} == REVIEWABLE_STATUSES
    assert "blocked" not in REVIEWABLE_STATUSES
    assert REVIEWABLE_STATUSES <= CURRENT_ITEM_STATUSES
    assert frozenset() == REVIEWABLE_STATUSES & CLAIMABLE_STATUSES


def test_live_and_current_item_are_not_the_same_question_either():
    """`blocked` is the loop's current work but not live work anyone is doing; `under_review` is
    live work but not this loop's current item. Neither set contains the other."""
    assert "blocked" in CURRENT_ITEM_STATUSES and "blocked" not in LIVE_STATUSES
    assert "under_review" in LIVE_STATUSES and "under_review" not in CURRENT_ITEM_STATUSES


def test_the_awaiting_someone_else_gap_is_exactly_three_statuses():
    """Neither claimable nor terminal — the gap both 2026-08-20 stall bugs lived in. Derived from
    the bands here rather than listed, which is what makes a newly added status unable to fall into
    it unnoticed."""
    gap = set(STATUS_BANDS) - CLAIMABLE_STATUSES - TERMINAL_STATUSES
    assert gap == {"completed", "under_review", "blocked"}
    assert {STATUS_BANDS[s] for s in gap} == {
        BAND_AWAITING_HANDOFF,
        BAND_WITH_REVIEWER,
        BAND_AWAITING_PERSON,
    }


def test_agent_actionable_is_the_band_that_decided_two_arguments():
    """The band's test is "does firing an agent make progress possible". It is what put
    `revision_needed` in the claim on 2026-08-20 and what kept `blocked` out on 2026-08-21."""
    assert STATUS_BANDS["revision_needed"] == BAND_AGENT_ACTIONABLE
    assert STATUS_BANDS["blocked"] == BAND_AWAITING_PERSON


# ---------------------------------------------------------------------------
# The literals are gone, not merely correct
# ---------------------------------------------------------------------------


def test_no_module_spells_a_status_set_out_by_hand():
    """A source scan, in the manner of `test_task_transitions.py`'s origin scan (task 7.5).

    Value equality alone cannot tell a derivation from a literal that is currently right, and a
    literal that is currently right is precisely what all three loop stall bugs started as. This
    fails if any module writes one of the derived sets out longhand.

    **Inspects each bracketed literal rather than whole files, and ignores complete enumerations.**
    Two legitimate declarations list every status the machine has — `mcp_server.TaskStatus`, which
    may import only stdlib and fastmcp so it has to restate, and `schemas.tasks._TASK_STATUSES`,
    already pinned to `TRANSITIONS` by `test_task_transitions.py`. Both are supersets of the sets
    below, so a file-level scan flags them and would be switched off within a week. A complete
    enumeration always contains both `approved` and `rejected`, and no derived set here contains
    either, so that is what separates them.
    """
    import re
    from pathlib import Path

    hub_package = Path(__file__).resolve().parents[1] / "hub"
    permitted = {"task_transitions.py"}
    signatures = {
        "the claimable set": {'"in_progress"', '"assigned"', '"pending"', '"revision_needed"'},
        "the live set": {'"pending"', '"assigned"', '"in_progress"', '"under_review"'},
    }
    enumeration_marker = {'"approved"', '"rejected"'}

    offenders = []
    for path in sorted(hub_package.rglob("*.py")):
        if path.name in permitted:
            continue
        source = path.read_text(encoding="utf-8")
        code = chr(10).join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        # Innermost bracketed groups only — a tuple, list or set literal of bare strings.
        for match in re.finditer(r"[(\[{]([^()\[\]{}]*?)[)\]}]", code, re.S):
            quoted = set(re.findall(r'"[a-z_]+"', match.group(1)))
            if not quoted or enumeration_marker <= quoted:
                continue
            for label, members in signatures.items():
                if members <= quoted:
                    offenders.append(f"{path.name} re-lists {label}")

    assert sorted(set(offenders)) == [], (
        "status sets are derived from STATUS_BANDS, never listed at their point of use "
        f"(loop-notices-and-reacts D9); found: {sorted(set(offenders))}"
    )
