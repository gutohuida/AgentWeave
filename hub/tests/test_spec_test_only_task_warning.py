"""A task that only writes tests, with a later task depending on it, is warned on submission (F512).

Such a task is red by design until its dependent lands, and approval runs the project's checks on
the work it would merge, so it can never pass them: on the trial Hub the F510 slice's first task
("write the failing acceptance test") failed the Hub suite with exactly its own four tests and
landed only by an operator override. The planner is told to put a test and its fix in one task;
this warning catches the document that splits them anyway. Advisory, like the other task warnings.
"""

import pytest

from hub.spec_completeness import is_test_path

from .test_spec_undeclared_files_warning import _doc, _submit, planner  # noqa: F401 - fixture

CODE = "test_only_task"


def _test_only(body):
    return [w for w in body["warnings"] if w["code"] == CODE]


@pytest.mark.parametrize(
    "path",
    [
        "hub/tests/test_a_review_turn.py",
        "tests/test_cli.py",
        "pkg/thing_test.py",
        "hub/ui/src/__tests__/drawer.test.tsx",
        "web/button.spec.ts",
        "test/helpers.js",
    ],
)
def test_test_paths_are_recognised(path):
    assert is_test_path(path)


@pytest.mark.parametrize(
    "path", ["hub/hub/review_turn.py", "src/agentweave/cli.py", "docs/testing.md", "contest.py"]
)
def test_code_paths_are_not(path):
    assert not is_test_path(path)


@pytest.mark.asyncio
async def test_the_f510_shape_is_warned(app, planner):  # noqa: F811
    """The trial document's own tasks: tests first, the fix depending on them."""
    body = await _submit(
        app,
        planner,
        _doc(
            ("red", {"files": ["hub/tests/test_a_review_turn_reviews_the_branch_tip.py"]}),
            ("fix", {"files": ["hub/hub/review_turn.py"], "depends_on": ["red"]}),
        ),
    )
    (warning,) = _test_only(body)
    assert warning["where"] == "tasks"
    assert "'red'" in warning["message"] and "'fix'" in warning["message"]
    assert "one task" in warning["message"]
    assert body["ready_to_propose"] is True


@pytest.mark.asyncio
async def test_a_test_and_its_fix_in_one_task_is_silent(app, planner):  # noqa: F811
    body = await _submit(
        app,
        planner,
        _doc(("one", {"files": ["hub/tests/test_x.py", "hub/hub/x.py"]})),
    )
    assert _test_only(body) == []


@pytest.mark.asyncio
async def test_a_test_task_nothing_depends_on_is_silent(app, planner):  # noqa: F811
    """Adding tests for code that already works is green on its own, and is not this shape."""
    body = await _submit(
        app,
        planner,
        _doc(("cover", {"files": ["tests/test_x.py"]}), ("other", {"files": ["src/y.py"]})),
    )
    assert _test_only(body) == []


def test_the_planner_is_told_to_keep_a_test_with_its_fix():
    from hub.api.v1.agents import SPEC_PHASE_DUTIES

    assert "A test and its fix are one task" in SPEC_PHASE_DUTIES["exploring"]
