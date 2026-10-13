"""The law, tested without a database.

Two properties carry the whole design and everything else here is detail. **Resolution can only
narrow** — no pair of inputs produces a capability the project did not grant, which is what makes
"an agent may not widen its own authority" a fact about the type rather than a rule something
checks. And **a refusal is actionable** — it names the capability, rules out retrying, and names the
way to ask, because an unactionable refusal gets worked around.

The third group is the one a future change is most likely to break by accident: a capability that
gates a lookup by identifier must not become distinguishable from not-found.
"""

import itertools

import pytest

from hub import agent_capabilities as caps

# --------------------------------------------------------------------------------------
# Narrowing
# --------------------------------------------------------------------------------------

#: Small enough to enumerate every subset pair exhaustively, which is worth more here than a
#: hand-picked case: the claim is about *all* inputs, so the test should be too.
UNIVERSE = (caps.MESSAGE_SEND, caps.JOB_SCHEDULE, caps.EVIDENCE_ACCEPT)


def _subsets(items):
    for size in range(len(items) + 1):
        yield from (frozenset(combo) for combo in itertools.combinations(items, size))


@pytest.mark.parametrize("floor", list(_subsets(UNIVERSE)))
@pytest.mark.parametrize("agent", list(_subsets(UNIVERSE)) + [None])
def test_resolution_never_exceeds_the_floor(floor, agent):
    """The property the whole model rests on, over every subset pair."""
    assert caps.resolve(floor, agent) <= frozenset(floor)


def test_an_agent_cannot_grant_itself_something_the_project_withheld():
    """The concrete form of the property above -- the attack it forecloses."""
    floor = {caps.MESSAGE_SEND}
    greedy = {caps.MESSAGE_SEND, caps.JOB_SCHEDULE, caps.AGENT_REQUEST}
    assert caps.resolve(floor, greedy) == frozenset({caps.MESSAGE_SEND})


def test_none_inherits_the_floor_whole():
    """`None` means "states nothing", not "holds nothing".

    The same meaning `None` already carries on `Agent.permission_timeout_seconds`: a row storing
    today's default would keep saying it after the default moved.
    """
    floor = {caps.MESSAGE_SEND, caps.TASK_CREATE}
    assert caps.resolve(floor, None) == frozenset(floor)


def test_an_empty_agent_set_is_not_none():
    """An agent that states the empty set holds nothing, and that has to stay expressible."""
    assert caps.resolve({caps.MESSAGE_SEND}, set()) == frozenset()


def test_resolution_is_idempotent():
    """Resolving a resolved set changes nothing, so the seam may be applied more than once."""
    floor, agent = {caps.MESSAGE_SEND, caps.TASK_CREATE}, {caps.MESSAGE_SEND}
    once = caps.resolve(floor, agent)
    assert caps.resolve(floor, once) == once


# --------------------------------------------------------------------------------------
# The vocabulary
# --------------------------------------------------------------------------------------


def test_every_capability_is_described():
    """A capability with no description cannot be briefed or refused actionably."""
    assert set(caps.DESCRIPTION) == set(caps.ALL)


def test_the_default_floor_changes_no_behaviour():
    """Adopting this module must grant nothing that is withheld today and withhold nothing that is
    open today.

    The three legacy flags default closed on the `Agent` row, and `job.schedule` is closed by
    `Project.allow_agent_jobs`. `agent.request` is out because `request_agent` is currently
    unreachable (`2026-08-21-request-agent-cannot-succeed.md`) and a floor should not grant a
    capability nobody can exercise.
    """
    assert caps.DEFAULT_FLOOR <= caps.ALL
    assert not (caps.DEFAULT_FLOOR & set(caps.LEGACY_FLAGS.values()))
    assert caps.JOB_SCHEDULE not in caps.DEFAULT_FLOOR
    assert caps.AGENT_REQUEST not in caps.DEFAULT_FLOOR


def test_legacy_flags_map_onto_real_capabilities():
    """The migration reads this mapping; a typo here would silently drop a grant."""
    assert set(caps.LEGACY_FLAGS.values()) <= caps.ALL
    assert len(set(caps.LEGACY_FLAGS.values())) == len(caps.LEGACY_FLAGS)


# --------------------------------------------------------------------------------------
# The feedback loop
# --------------------------------------------------------------------------------------


def test_a_refusal_names_the_capability_rules_out_retrying_and_names_the_way_out():
    text = caps.remedy(caps.JOB_SCHEDULE)
    assert caps.JOB_SCHEDULE in text
    assert "retrying will not change it" in text
    assert "ask_user" in text


def test_a_refusal_for_an_unknown_capability_is_still_a_sentence():
    """Nothing should be able to produce a refusal that reads as a bug."""
    assert "perform that action" in caps.remedy("something.invented")


def test_the_briefing_names_both_what_is_held_and_what_is_not():
    """The withheld half is the point: an agent that knows it lacks `job.schedule` never plans a
    loop it cannot create."""
    rendered = caps.briefing({caps.MESSAGE_SEND}).render()
    assert "`message.send`" in rendered
    assert "`job.schedule`" in rendered
    assert "ask_user" in rendered


def test_the_briefing_is_stable_across_runs():
    """Turn context that reorders between runs makes two identical turns look different."""
    granted = {caps.TASK_CREATE, caps.MESSAGE_SEND}
    assert caps.briefing(granted).render() == caps.briefing(granted).render()
    assert caps.briefing(granted).held == sorted(granted)


def test_the_briefing_ignores_capabilities_that_do_not_exist():
    """A stale grant left on a row by an older release must not reach an agent's context."""
    assert caps.briefing({caps.MESSAGE_SEND, "removed.capability"}).held == [caps.MESSAGE_SEND]


def test_a_full_grant_briefs_no_withheld_section():
    assert caps.briefing(caps.ALL).withheld == []


# --------------------------------------------------------------------------------------
# Verbs, not objects
# --------------------------------------------------------------------------------------


def test_existence_disclosing_capabilities_are_declared():
    """`checkpoint_access.py:119,145` makes a denied recall indistinguishable from not-found on
    purpose: a distinguishable refusal confirms the observation exists.

    A future capability that gates a lookup by identifier must be added here, and the seam must
    consult it rather than raising the ordinary named refusal. This test is the reminder.
    """
    assert caps.DISCLOSES_EXISTENCE == frozenset(
        {caps.CHECKPOINT_READ, caps.OBSERVATION_RECALL}
    )
    assert caps.DISCLOSES_EXISTENCE <= caps.ALL


def test_a_briefing_may_still_name_an_existence_disclosing_capability():
    """The rule is about objects, not verbs. "You do not hold `observation.recall`" is a fact about
    the agent and is disclosed; "observation obs-4c1 exists but is denied to you" is a fact about
    the world and is not."""
    assert caps.OBSERVATION_RECALL in caps.briefing(set()).withheld
