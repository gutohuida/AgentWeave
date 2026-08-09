"""When a checkpoint is taken, and who decides.

Tasks 8.4-8.8 of 2026-08-07-conversation-handoff-rework.

Both threshold units exist because context windows differ by an order of magnitude. A percentage
is natural when you think "most of the way full"; an absolute count is natural when you know from
experience that a model degrades past 150k regardless of what fraction of its window that is.
"""

import pytest

from hub.checkpoint_policy import (
    DEFAULT_NOTES_VALUE,
    DEFAULT_THRESHOLD_MODE,
    DEFAULT_THRESHOLD_VALUE,
    FINAL_WARNING_PERCENT,
    CheckpointPolicy,
    crosses,
    describe_threshold,
    needs_final_warning,
    resolve_policy,
    should_checkpoint,
    should_request_notes,
    threshold_error,
)
from hub.db.models import Agent, Project


def _project(**overrides):
    fields = {"id": "proj-test", "name": "Testbed", "checkpoint_mode": "off"}
    fields.update(overrides)
    return Project(**fields)


def _agent(**overrides):
    fields = {"id": "agent-1", "project_id": "proj-test", "name": "claude-1"}
    fields.update(overrides)
    return Agent(**fields)


# --------------------------------------------------------------------------- resolution


def test_nothing_configured_falls_back_to_the_built_in_default():
    policy = resolve_policy(_agent(), _project())
    assert policy.mode == "off"
    assert (policy.threshold_mode, policy.threshold_value) == (
        DEFAULT_THRESHOLD_MODE,
        DEFAULT_THRESHOLD_VALUE,
    )
    assert policy.threshold_source == "default"


def test_the_default_leaves_room_before_the_cli_compacts_on_its_own():
    """Claude Code auto-compacts near 95%. If it fires first the provider session survives but
    its context is the CLI's own summary — ours never happened, on a compaction nobody authored
    and nothing can inspect."""
    assert DEFAULT_THRESHOLD_VALUE < 95
    # And notes are asked for earlier still, or they are written from the context the cutover
    # exists to escape.
    assert DEFAULT_NOTES_VALUE < DEFAULT_THRESHOLD_VALUE


def test_a_project_threshold_is_inherited_by_an_agent_that_states_none():
    policy = resolve_policy(
        _agent(),
        _project(checkpoint_threshold_mode="tokens", checkpoint_threshold_value=150_000),
    )
    assert (policy.threshold_mode, policy.threshold_value) == ("tokens", 150_000)
    assert policy.threshold_source == "project"


def test_an_agent_threshold_replaces_the_projects_whole_threshold():
    """Task 8.6. Mode and value together, never field by field."""
    policy = resolve_policy(
        _agent(checkpoint_threshold_mode="percent", checkpoint_threshold_value=60),
        _project(checkpoint_threshold_mode="tokens", checkpoint_threshold_value=150_000),
    )
    assert (policy.threshold_mode, policy.threshold_value) == ("percent", 60)
    assert policy.threshold_source == "agent"


def test_a_value_without_a_mode_is_not_half_a_threshold():
    """The failure this prevents is concrete: an agent supplying only `150`, inheriting `percent`
    from the project, and producing a threshold of 150% that never fires."""
    policy = resolve_policy(
        _agent(checkpoint_threshold_value=150),
        _project(checkpoint_threshold_mode="percent", checkpoint_threshold_value=80),
    )
    assert (policy.threshold_mode, policy.threshold_value) == ("percent", 80)
    assert policy.threshold_source == "project"


def test_mode_and_threshold_resolve_independently():
    """An agent may sensibly turn checkpointing off for itself while accepting the project's
    threshold, or tighten its threshold while leaving the project to decide automation."""
    policy = resolve_policy(
        _agent(checkpoint_mode="off"),
        _project(
            checkpoint_mode="automatic",
            checkpoint_threshold_mode="tokens",
            checkpoint_threshold_value=120_000,
        ),
    )
    assert policy.mode == "off"
    assert (policy.threshold_mode, policy.threshold_value) == ("tokens", 120_000)


def test_a_project_is_off_until_somebody_turns_it_on():
    """A project must not start spending tokens on generation, or cutting conversations over,
    because it was upgraded."""
    assert resolve_policy(_agent(), _project()).mode == "off"
    assert not resolve_policy(_agent(), _project()).enabled


# --------------------------------------------------------------------------- validation


def test_a_token_threshold_at_or_above_the_window_is_refused():
    """Task 8.7. It would never fire, so accepting it is accepting a setting that does nothing."""
    assert threshold_error("tokens", 200_000, context_window=200_000) is not None
    assert threshold_error("tokens", 250_000, context_window=200_000) is not None
    assert threshold_error("tokens", 150_000, context_window=200_000) is None


def test_a_token_threshold_is_accepted_when_the_window_is_unknown():
    """Task 8.8, and the reconciliation with 8.7: the refusal is conditional on knowing the
    window. An unknown window is not evidence that a number is wrong."""
    assert threshold_error("tokens", 250_000, context_window=None) is None


def test_a_percentage_at_or_above_a_hundred_is_refused():
    assert threshold_error("percent", 100) is not None
    assert threshold_error("percent", 99) is None


@pytest.mark.parametrize("bad", [0, -5, "80", True, None])
def test_a_threshold_must_be_a_positive_whole_number(bad):
    assert threshold_error("percent", bad) is not None


def test_an_unknown_mode_is_refused():
    assert threshold_error("proportion", 50) is not None


# --------------------------------------------------------------------------- both readings


def test_a_threshold_is_describable_in_both_units_when_both_are_knowable():
    """An operator setting one unit is reasoning about the other; making them work it out is how
    a threshold ends up somewhere it will never fire."""
    assert describe_threshold("tokens", 150_000, context_window=200_000) == "150k — 75% of 200k"
    assert describe_threshold("percent", 75, context_window=200_000) == "75% — 150k of 200k"


def test_a_threshold_still_describes_itself_without_a_window():
    assert describe_threshold("tokens", 150_000) == "150k"
    assert describe_threshold("percent", 80) == "80%"


# --------------------------------------------------------------------------- firing


def test_token_mode_needs_only_a_token_count():
    """Task 8.8. This is the case the mode exists for: providers that never report a limit."""
    assert crosses("tokens", 150_000, context_tokens=150_000, percent=None)
    assert not crosses("tokens", 150_000, context_tokens=149_999, percent=None)


def test_percent_mode_declines_rather_than_inventing_a_denominator():
    """Acting on a guessed window is worse than not acting: it is the number the operator would
    then act on themselves."""
    assert not crosses("percent", 80, context_tokens=500_000, percent=None)
    assert crosses("percent", 80, context_tokens=None, percent=80.0)


def test_offered_still_generates_a_checkpoint_and_withholds_only_the_cutover():
    """Task 8.10. The offer is "I made one, here it is, cut over?" — not "shall I ask the agent
    to write one?". Generation no longer depends on the agent, so there is nothing to seek
    permission for beforehand, and offering to generate *later* would mean generating from a
    context that has degraded in the meantime."""

    def policy(mode):
        return CheckpointPolicy(
            mode=mode,
            threshold_mode="percent",
            threshold_value=80,
            notes_value=70,
            runner_id=None,
            model=None,
        )

    assert should_checkpoint(policy("offered"), context_tokens=None, percent=95.0)
    assert should_checkpoint(policy("automatic"), context_tokens=None, percent=95.0)
    assert not should_checkpoint(policy("off"), context_tokens=None, percent=95.0)
    # The distinction lives on the policy, and is what the cutover reads.
    assert policy("offered").automatic is False
    assert policy("automatic").automatic is True


# --------------------------------------------------------------------------- the notes window


def _policy(**overrides):
    fields = {
        "mode": "automatic",
        "threshold_mode": "percent",
        "threshold_value": 80,
        "notes_value": 70,
        "runner_id": None,
        "model": None,
    }
    fields.update(overrides)
    return CheckpointPolicy(**fields)


def test_notes_are_asked_for_between_the_two_thresholds():
    policy = _policy()
    assert not should_request_notes(policy, context_tokens=None, percent=65.0)
    assert should_request_notes(policy, context_tokens=None, percent=72.0)


def test_notes_are_not_asked_for_once_cutover_is_due():
    """Past the cutover the conversation is about to be succeeded, and notes written there come
    from exactly the context the cutover exists to escape."""
    assert not should_request_notes(_policy(), context_tokens=None, percent=85.0)


def test_a_notes_point_that_is_not_earlier_is_ignored_rather_than_honoured():
    """Honouring it would ask for notes at the worst possible moment, which is worse than not
    asking at all."""
    assert not should_request_notes(
        _policy(notes_value=80), context_tokens=None, percent=85.0
    )
    assert not should_request_notes(
        _policy(notes_value=90), context_tokens=None, percent=95.0
    )


def test_notes_are_asked_for_under_offered_not_only_automatic():
    """The operator still has to be offered something worth reading."""
    assert should_request_notes(_policy(mode="offered"), context_tokens=None, percent=72.0)
    assert not should_request_notes(_policy(mode="off"), context_tokens=None, percent=72.0)


# ------------------------------------------------------- the point a dismissal runs out of room


def test_the_final_warning_sits_between_the_default_threshold_and_the_cli_compaction():
    """It has to be past any ordinary threshold, or it would fire at a conversation the operator
    has not yet had a chance to dismiss; and short of the ~95% the CLI compacts at, or there would
    be no conversation left to checkpoint by the time anyone acted."""
    assert DEFAULT_THRESHOLD_VALUE < FINAL_WARNING_PERCENT < 95


def test_a_dismissal_runs_out_of_room_at_the_final_mark():
    assert not needs_final_warning(_policy(mode="offered"), percent=FINAL_WARNING_PERCENT - 1)
    assert needs_final_warning(_policy(mode="offered"), percent=FINAL_WARNING_PERCENT)
    assert needs_final_warning(_policy(mode="offered"), percent=99.0)


def test_no_percentage_means_no_final_warning():
    """"Near the window" is a claim about a proportion. A token count with no window to divide by
    does not make a smaller version of that claim — it makes none at all, and inventing a
    denominator to have one is what every other decision here refuses to do."""
    assert not needs_final_warning(_policy(mode="offered"), percent=None)


def test_the_final_warning_belongs_only_to_the_mode_that_asks():
    """`automatic` generates and hands over at its own threshold, so it never reaches a dismissal
    to run out of room on; `off` was never warning in the first place."""
    assert not needs_final_warning(_policy(mode="automatic"), percent=99.0)
    assert not needs_final_warning(_policy(mode="off"), percent=99.0)
