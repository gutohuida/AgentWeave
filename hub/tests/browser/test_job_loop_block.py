"""`2026-08-16-many-named-loops`, task 8.1 — the factual half.

8.1 asks two things at once: "does a plain job's card look unchanged?" (taste — the
operator's) and "confirm a job created without loop fields shows no loop block" (fact —
this file's).

`hub/ui/src/__tests__/jobCard.test.tsx` already asserts the same absence at component
level against a hand-built prop. What it cannot show is that the whole path — API
serialisation, the `loop` field being null for a plain job, and the card's own gate —
agrees on real rows. That is what these drive.

**Why the assertions are page-wide rather than per-card.** `JobCard`'s root carries no
testid, and the loop block renders *outside* the header div, so the nearest ancestor
holding the expand button does not contain it. Scoping by DOM traversal would be brittle
in exactly the way that produces a test which passes for the wrong reason. With a mix of
loop and non-loop jobs in the fixture project, "expand all, expect one loop block per job
that has a loop" proves the same claim and cannot pass vacuously — which the earlier
per-card version did, reporting a green "plain job has no loop block" on a page that
rendered no loop blocks at all.

**Job count is derived from the API, not hardcoded.** The fixture project started with
three taste-pass jobs (one plain, two with a loop) but has since grown smoke-test loops
left deliberately as evidence (`LB2`, `LB4`, `A4`, `LA3`, ...; see
`.claude/autonomous/STATE.json`'s C2b entry) — a literal `3` here would rot every time a
future run adds another. `job_counts` fetches the live job list and counts how many have a
`loop` object at all, so this stays a real regression check on "loop blocks render only for
jobs that have a loop" instead of a number someone has to remember to bump.

Task 8.2 — "does the loop block read as an extension, not a second concept?" — is pure
taste and is deliberately absent from this file.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

PLAIN_JOB = "taste-pass plain job (no loop)"
LOOP_JOB = "taste-pass demo loop"
NEVER_FILLED_JOB = "taste-pass never-filled loop"

LOOP_BLOCK = '[data-testid="job-loop-block"]'


@pytest.fixture
def job_counts(api, project_id: str) -> dict[str, int]:
    """How many jobs the project has, and how many of those carry a `loop` object — read live
    rather than assumed, so the fixture project can grow smoke-test jobs without rotting these
    tests (see the module docstring)."""
    status, jobs = api("GET", f"/api/v1/projects/{project_id}/jobs")
    assert status == 200, jobs
    return {
        "total": len(jobs),
        "with_loop": sum(1 for job in jobs if job.get("loop") is not None),
    }


def _expand_every_card(page: Page, expected_total: int) -> int:
    """Expand every collapsed job card; return how many were expanded.

    Waits for a fixture job's name before touching anything. The tab strip's
    `aria-current` flips as soon as the destination changes, which is *before* the jobs
    query resolves and well before React has attached the toggles' handlers — clicking
    into that gap finds the buttons, reports three of them, and silently does nothing.
    That produced a green "no loop blocks" run against a page whose cards had simply
    never opened.

    The post-condition is asserted rather than slept on: every button must have re-labelled
    itself to "Collapse job details".
    """
    page.get_by_text(PLAIN_JOB, exact=True).wait_for(timeout=20_000)
    toggles = page.get_by_label("Expand job details")
    expect(toggles).to_have_count(expected_total)
    count = toggles.count()
    # Iterate backwards: clicking re-labels the button to "Collapse job details", which
    # shrinks the matched set and would shift the indices of anything after it.
    for index in reversed(range(count)):
        toggles.nth(index).click()
    expect(page.get_by_label("Collapse job details")).to_have_count(count)
    return count


def test_jobs_page_shows_the_three_taste_pass_fixture_jobs(goto) -> None:
    """The premise of 8.1: a *mix* of loop and non-loop jobs is on screen. Other jobs (smoke-test
    loops left as evidence by earlier runs) may also be present — this only asserts these three."""
    page = goto("jobs")
    for name in (PLAIN_JOB, LOOP_JOB, NEVER_FILLED_JOB):
        expect(page.get_by_text(name, exact=True)).to_be_visible()


def test_loop_blocks_render_only_for_jobs_that_have_a_loop(
    goto, job_counts: dict[str, int]
) -> None:
    """8.1's assertion, stated so it cannot pass vacuously.

    Expanding every job card must produce exactly one loop block per job that carries a `loop`
    object. A count equal to the total job count means 4.2's "at least one field" gate is
    creating `Loop` rows unconditionally; a count of 0 means the block stopped rendering
    entirely, which the previous formulation would have scored as a pass.
    """
    page = goto("jobs")
    expanded = _expand_every_card(page, job_counts["total"])
    assert (
        expanded == job_counts["total"]
    ), f"expected {job_counts['total']} collapsed job cards to expand, found {expanded}"
    expect(page.locator(LOOP_BLOCK)).to_have_count(job_counts["with_loop"])


def test_each_loop_block_names_its_own_purpose(goto, job_counts: dict[str, int]) -> None:
    """Both taste-pass loops' purposes reach the page; the plain job contributes none."""
    page = goto("jobs")
    _expand_every_card(page, job_counts["total"])
    blocks = page.locator(LOOP_BLOCK)
    expect(blocks).to_have_count(job_counts["with_loop"])
    rendered = " ".join(blocks.nth(i).inner_text() for i in range(job_counts["with_loop"]))
    assert "drain the taste-pass demo queue" in rendered
    assert "never had a task queued" in rendered
    assert PLAIN_JOB not in rendered


def test_collapsed_cards_show_no_loop_block(goto) -> None:
    """The block is expansion-gated, so a freshly loaded page shows none at all.

    Guards the helper above as much as the app: if cards defaulted to expanded, the
    "expand every card" count would silently become 0 and the other tests would stop
    testing what they claim to.
    """
    page = goto("jobs")
    expect(page.locator(LOOP_BLOCK)).to_have_count(0)
