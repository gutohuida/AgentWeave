"""`a-refusal-names-a-remedy-that-works` groups 1-2 — the remedy, and the column it fits in.

Group 1 (D1): `own_review_remedy(task)` names what a refused actor can do about a task's own
review, by status alone. Group 2 (D2): `JobRun.error_summary` is fitted to its column at the
model, and `_wedged_review_reason` shortens the one sentence measured to overflow it.
"""

from hub.db.models import JobRun, Task, fit_error_summary
from hub.scheduler import _wedged_review_reason, own_review_remedy

# ---------------------------------------------------------------------------
# 1.2 — own_review_remedy names the right action for each status
# ---------------------------------------------------------------------------


def _task(status, title="a task"):
    return Task(id="task-remedy", project_id="proj-test", title=title, status=status)


def test_completed_names_land_it():
    """*Mutation:* swap the two branches. The test must fail."""
    remedy = own_review_remedy(_task("completed"))
    assert remedy == "Land it, on the task, to review it yourself."


def test_under_review_names_the_three_exits_never_land_it():
    """*Mutation:* swap the two branches. The test must fail."""
    remedy = own_review_remedy(_task("under_review"))
    assert remedy == "decide it yourself: approve, reject, or send it back with revision_needed."
    assert "Land it" not in remedy


# ---------------------------------------------------------------------------
# 2.3 — every JobRun.error_summary write is fitted to the column
# ---------------------------------------------------------------------------


def test_a_600_character_error_summary_is_stored_at_500_ending_ellipsis():
    """*Mutation:* remove the `@validates`. The test must fail."""
    run = JobRun(
        id="run-fit-long",
        job_id="job-fit",
        project_id="proj-test",
        status="skipped",
        trigger="scheduled",
        error_summary="x" * 600,
    )
    assert len(run.error_summary) == 500
    assert run.error_summary.endswith("…")
    assert run.error_summary[:499] == "x" * 499


def test_a_500_character_error_summary_is_stored_unchanged():
    text = "y" * 500
    run = JobRun(
        id="run-fit-exact",
        job_id="job-fit",
        project_id="proj-test",
        status="skipped",
        trigger="scheduled",
        error_summary=text,
    )
    assert run.error_summary == text


def test_none_error_summary_stays_none():
    run = JobRun(
        id="run-fit-none",
        job_id="job-fit",
        project_id="proj-test",
        status="fired",
        trigger="scheduled",
    )
    assert run.error_summary is None


def test_fit_error_summary_helper_matches_the_validator():
    assert fit_error_summary(None) is None
    assert fit_error_summary("z" * 500) == "z" * 500
    fitted = fit_error_summary("z" * 600)
    assert len(fitted) == 500
    assert fitted.endswith("…")


# ---------------------------------------------------------------------------
# 2.4 — _wedged_review_reason shortens the quoted title so the remedy survives
# ---------------------------------------------------------------------------


def test_wedged_review_reason_fits_500_at_a_32_char_reviewer_and_256_char_title():
    """*Mutation:* remove 2.2's title-shortening. The test must fail."""
    task = Task(
        id="task-wedged-remedy",
        project_id="proj-test",
        title="t" * 256,
        status="under_review",
    )
    reviewer = "r" * 32
    reason = _wedged_review_reason(task, reviewer)
    assert len(reason) <= 500, f"expected <= 500 chars, got {len(reason)}"
    assert reason.endswith(
        "review it yourself, or send it back with revision_needed."
    ), "the remedy must survive whole even once the title is cut"
