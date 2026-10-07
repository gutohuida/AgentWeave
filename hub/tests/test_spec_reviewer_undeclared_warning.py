"""A flow-delivered document whose tasks name no reviewer is warned on submission (F508).

On the trial Hub the planner wrote "Reviewer: aw-reviewer." in the design prose and left every
task's `reviewer` empty; the flow then staffed the review from whoever was free, a leftover stub
agent included (`scheduler.resolve_reviewer`, rung 2). The Hub cannot read the prose promise, so it
says what the fields will do instead. Advisory, like the other task warnings.
"""

import pytest

from .test_spec_undeclared_files_warning import _doc, _submit, planner  # noqa: F401 - fixture

CODE = "reviewer_undeclared"


def _flow(*specs):
    return {**_doc(*specs), "delivery": {"mode": "flow"}}


def _warned(body):
    return [w for w in body["warnings"] if w["code"] == CODE]


@pytest.mark.asyncio
async def test_a_flow_whose_tasks_name_no_reviewer_is_warned(app, planner):  # noqa: F811
    body = await _submit(app, planner, _flow(("a", {"files": ["x.py"]})))
    (warning,) = _warned(body)
    assert warning["where"] == "tasks"
    assert "reviewer" in warning["message"]
    assert "any free agent" in warning["message"]
    # Advisory: it never enters the blocking findings.
    assert CODE not in {f["code"] for f in body["blocking"]}


@pytest.mark.asyncio
async def test_a_flow_with_a_declared_reviewer_is_not_warned(app, planner):  # noqa: F811
    body = await _submit(app, planner, _flow(("a", {"files": ["x.py"], "reviewer": "aw-reviewer"})))
    assert _warned(body) == []


@pytest.mark.asyncio
async def test_a_document_no_flow_delivers_is_not_warned(app, planner):  # noqa: F811
    body = await _submit(app, planner, _doc(("a", {"files": ["x.py"]})))
    assert _warned(body) == []
