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
in exactly the way that produces a test which passes for the wrong reason. With three
jobs in the fixture project and exactly one of them plain, "expand all, expect two loop
blocks" proves the same claim and cannot pass vacuously — which the earlier per-card
version did, reporting a green "plain job has no loop block" on a page that rendered no
loop blocks at all.

Task 8.2 — "does the loop block read as an extension, not a second concept?" — is pure
taste and is deliberately absent from this file.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

PLAIN_JOB = "taste-pass plain job (no loop)"
LOOP_JOB = "taste-pass demo loop"
NEVER_FILLED_JOB = "taste-pass never-filled loop"

LOOP_BLOCK = '[data-testid="job-loop-block"]'


def _expand_every_card(page: Page) -> int:
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
    expect(toggles).to_have_count(3)
    count = toggles.count()
    # Iterate backwards: clicking re-labels the button to "Collapse job details", which
    # shrinks the matched set and would shift the indices of anything after it.
    for index in reversed(range(count)):
        toggles.nth(index).click()
    expect(page.get_by_label("Collapse job details")).to_have_count(count)
    return count


def test_jobs_page_shows_all_three_fixture_jobs(goto) -> None:
    """The premise of 8.1: a *mix* of loop and non-loop jobs is on screen."""
    page = goto("jobs")
    for name in (PLAIN_JOB, LOOP_JOB, NEVER_FILLED_JOB):
        expect(page.get_by_text(name, exact=True)).to_be_visible()


def test_loop_blocks_render_only_for_jobs_that_have_a_loop(goto) -> None:
    """8.1's assertion, stated so it cannot pass vacuously.

    Three jobs, two with a `loop` object and one with `loop: null`. Expanding all three
    must produce exactly two loop blocks. A count of 3 means 4.2's "at least one field"
    gate is creating `Loop` rows unconditionally; a count of 0 means the block stopped
    rendering entirely, which the previous formulation would have scored as a pass.
    """
    page = goto("jobs")
    expanded = _expand_every_card(page)
    assert expanded == 3, f"expected 3 collapsed job cards to expand, found {expanded}"
    expect(page.locator(LOOP_BLOCK)).to_have_count(2)


def test_each_loop_block_names_its_own_purpose(goto) -> None:
    """Both loops' purposes reach the page; the plain job contributes none."""
    page = goto("jobs")
    _expand_every_card(page)
    blocks = page.locator(LOOP_BLOCK)
    expect(blocks).to_have_count(2)
    rendered = " ".join(blocks.nth(i).inner_text() for i in range(2))
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
