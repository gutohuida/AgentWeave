# ruff: noqa: F811  (a fixture imported by name is redefined as an argument)
"""Every task comes with a recommended builder and checker (ETCRB-3): the prompt half and the
warnings half. The Build dialog half is a UI test (`BuildDialog.test.tsx`)."""

import pytest

from hub import spec_journey
from hub.spec_completeness import recommended_people_warnings
from hub.spec_payload import SpecPayload

from .test_spec_undeclared_files_warning import _doc, _submit, planner  # noqa: F401 - fixture

CODE = "recommended_people"
ROSTER = [("DeveloperOpus", "claude-opus-5-5"), ("Developer", "claude-sonnet-5-5")]


def _tasks_prompt(size, roster=ROSTER):
    return spec_journey.duty(spec_journey.TASKS, size=size, roster=roster)


def _named(body):
    return [w for w in body["warnings"] if w["code"] == CODE]


# ac-asked
def test_the_tasks_step_asks_for_a_builder_a_checker_and_a_reason_for_each():
    text = _tasks_prompt("large")
    for word in ("builder", "checker", "builder_reason", "checker_reason"):
        assert word in text
    assert "reviewer" not in text and "tester" not in text


def test_the_build_step_no_longer_asks_for_reasons_keyed_reviewer_or_tester():
    text = spec_journey.duty(spec_journey.BUILD)
    assert "`reviewer`, `tester`" not in text
    assert "`stop` and `cron`" in text


# ac-models
def test_the_prompt_names_every_open_agents_model_and_asks_for_cost_and_complexity():
    text = _tasks_prompt("large")
    assert "claude-opus-5-5" in text and "claude-sonnet-5-5" in text
    assert "cost and performance" in text and "complexity" in text
    assert "hazardous" in text and "routine" in text


# ac-sources
def test_a_large_document_asks_for_the_three_sources_and_a_fix_does_not():
    large = _tasks_prompt("large")
    assert "state your current view" in large
    for source in spec_journey.SOURCES:
        assert source in large
    assert "evidence" in large and "unavailable" in large
    fix = _tasks_prompt("fix")
    assert "which sources" not in fix and "web search" not in fix


# ac-not-self
def test_a_one_agent_project_is_told_to_leave_the_checker_empty_with_a_reason():
    text = _tasks_prompt("fix", [("Solo", "claude-sonnet-5-5")])
    assert "one open agent" in text and "leave every `checker` empty" in text


@pytest.mark.asyncio
async def test_a_task_checked_by_its_builder_is_warned_by_name(app, planner):  # noqa: F811
    body = await _submit(
        app,
        planner,
        _doc(
            (
                "a",
                {
                    "builder": "Dev",
                    "checker": "Dev",
                    "builder_reason": "cheap model, simple copy",
                    "checker_reason": "same",
                },
            )
        ),
    )
    (warning,) = _named(body)
    assert "'a'" in warning["message"] and "both builder and checker" in warning["message"]


@pytest.mark.asyncio
async def test_an_empty_checker_with_a_reason_is_not_warned(app, planner):  # noqa: F811
    body = await _submit(
        app,
        planner,
        _doc(
            (
                "a",
                {
                    "builder": "Solo",
                    "builder_reason": "only agent, cheap model for a simple task",
                    "checker_reason": "one open agent, so nobody else can check",
                },
            )
        ),
    )
    assert _named(body) == []


# ac-warns
@pytest.mark.asyncio
async def test_missing_checker_and_missing_reason_are_named_and_never_block(
    app, planner
):  # noqa: F811
    body = await _submit(
        app,
        planner,
        _doc(
            ("nochecker", {"builder": "A", "builder_reason": "r"}),
            (
                "noreason",
                {"builder": "A", "checker": "B", "checker_reason": "r"},
            ),
        ),
    )
    text = " ".join(w["message"] for w in _named(body))
    assert "'nochecker'" in text and "'noreason'" in text
    assert CODE not in {f["code"] for f in body["blocking"]}


def test_a_document_written_before_picks_existed_draws_no_warning():
    payload = SpecPayload.model_validate(_doc(("a", {}), ("b", {})))
    assert recommended_people_warnings(payload) == []
