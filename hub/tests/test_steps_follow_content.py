"""A save moves an exploring change document's step to where its content stands (RMSTA-3).

Change: spec/changes/ready-means-the-same-thing-to-the-author-and-the-operator, FR-8 and FR-13.
"""

import pytest

from hub import spec_journey

from .test_approval_warnings_routes import _check, _checked
from .test_project_spec_steps import THREAT, _steps, _write
from .test_spec_documents_api import (  # noqa: F401  (run_headers is a fixture)
    _create,
    _submit,
    run_headers,
)
from .test_spec_journey_briefing import _place, _row


def _skipped(items):
    return [i for i in items if i["code"] == "steps_skipped"]


@pytest.mark.asyncio
async def test_a_complete_document_saved_at_intake_ends_at_build_with_nothing_skipped(
    app, auth_headers, run_headers  # noqa: F811
):
    """ac-steps-complete: fails on master, which leaves the step at intake and warns."""
    await _create(app, auth_headers)
    await _place(step="intake", size="large")

    saved = (await _submit(app, run_headers, _checked(design="Decision one."))).json()

    assert (await _row()).step == "build"
    assert _skipped(saved["warnings"]) == []
    checked = (await _check(app, auth_headers)).json()
    assert _skipped(checked["warnings"]) == []


@pytest.mark.asyncio
async def test_a_document_without_tasks_stops_before_tasks_and_names_what_is_missing(
    app, auth_headers, run_headers  # noqa: F811
):
    """ac-steps-missing: design present, tasks absent: the step is approach."""
    await _create(app, auth_headers)
    await _place(step="intake", size="large")

    saved = (await _submit(app, run_headers, _checked(design="Decision one.", tasks=[]))).json()

    assert (await _row()).step == "approach"
    message = _skipped(saved["warnings"])[0]["message"]
    assert "tasks" in message and "build" in message


@pytest.mark.asyncio
async def test_a_custom_step_after_requirements_stops_the_move_and_is_named(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    """ac-steps-custom."""
    await _create(app, auth_headers)
    _write(tmp_path, _steps(THREAT))
    await _place(step="intake", size="large")

    saved = (await _submit(app, run_headers, _checked(design="Decision one."))).json()

    assert (await _row()).step == "requirements"
    assert "threat-model" in _skipped(saved["warnings"])[0]["message"]


@pytest.mark.asyncio
async def test_a_save_never_moves_the_step_back(app, auth_headers, run_headers):  # noqa: F811
    await _create(app, auth_headers)
    await _place(step="build", size="large")

    await _submit(app, run_headers, _checked(tasks=[]))

    assert (await _row()).step == "build"


def test_no_step_text_declares_the_document_ready_and_the_last_tells_the_author_to_wait():
    for step, text in spec_journey.STEP_DUTIES.items():
        assert "is then ready" not in text and "ready for the operator" not in text, step
        if step != spec_journey.BUILD:
            assert "ready" not in text.lower().replace("already", ""), step
    last = spec_journey.STEP_DUTIES[spec_journey.BUILD]
    assert "ready_to_approve" in last and "only when" in last
