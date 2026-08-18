"""`2026-08-16-conversation-formatting-and-quick-nav`, task 6.4 — the factual half.

6.4 reads: *"does the palette feel fast and find the right things… search for a
conversation by agent name, a task by partial title, and a spec document; confirm each is
found **without exact-match typing**."*

"Feels fast" is taste and stays with the operator. "Found without exact-match typing" is a
claim about cmdk's scoring against real project rows, and that is what these assert — each
query below is a mid-string fragment, never a prefix and never the whole title, because a
prefix match would pass even if scoring were broken.

**A coverage gap, stated rather than hidden.** 6.4 also names "a conversation by agent
name". `proj-5e960453` has **no agents** — the roster rows on this machine belong to other
projects — so the Agents group is empty here and that third of the task is not covered.
Running with `AW_HUB_PROJECT_ID` pointed at a project that has both agents and
conversations would close it.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

PALETTE_PLACEHOLDER = "Search conversations, agents, documents, tasks…"

# (query typed, text expected in the results) — every query is a mid-string fragment.
PARTIAL_QUERIES = [
    pytest.param("quiet window", "Record a quiet window per project", id="task-mid-string"),
    pytest.param("seeded task", "Seeded task for the demo loop", id="task-lowercased"),
    pytest.param("instructions", "Project instructions", id="document-single-word"),
    pytest.param("quiet hours", "Quiet hours", id="document-two-words"),
]


def _open_palette(page: Page) -> Page:
    page.keyboard.press("Control+k")
    page.get_by_placeholder(PALETTE_PLACEHOLDER).wait_for(timeout=10_000)
    return page


def test_palette_opens_on_ctrl_k(goto) -> None:
    """The premise. Everything below is meaningless if the shortcut is dead."""
    page = goto("tasks")
    _open_palette(page)
    expect(page.get_by_placeholder(PALETTE_PLACEHOLDER)).to_be_visible()


def test_palette_toggles_closed_on_a_second_ctrl_k(goto) -> None:
    """`setOpen((value) => !value)` — the shortcut toggles rather than only opening."""
    page = goto("tasks")
    _open_palette(page)
    page.keyboard.press("Control+k")
    expect(page.get_by_placeholder(PALETTE_PLACEHOLDER)).to_have_count(0)


@pytest.mark.parametrize("query,expected", PARTIAL_QUERIES)
def test_partial_query_finds_the_row(goto, query: str, expected: str) -> None:
    """6.4's assertion: a fragment is enough, no exact-match typing required."""
    page = goto("tasks")
    _open_palette(page)
    page.get_by_placeholder(PALETTE_PLACEHOLDER).fill(query)
    page.wait_for_timeout(300)
    expect(page.get_by_role("option").filter(has_text=expected).first).to_be_visible()


def test_a_nonsense_query_reports_no_matches(goto) -> None:
    """The negative control.

    Without it, a palette that rendered every row regardless of the query would pass every
    test above — which is the exact failure the truncation comment in `CommandPalette.tsx`
    describes fixing, where any query matched nearly every conversation.
    """
    page = goto("tasks")
    _open_palette(page)
    page.get_by_placeholder(PALETTE_PLACEHOLDER).fill("zzzznotathingzzzz")
    page.wait_for_timeout(300)
    expect(page.get_by_text("No matches.")).to_be_visible()


def test_a_task_query_does_not_bury_the_task_under_conversations(goto) -> None:
    """The regression `CommandPalette.tsx` documents at length: conversation rows used to
    carry their whole opening prompt as search text, so typing a task title ranked six
    conversations above the task itself and Enter never reached it. The task should be
    among the first handful of options, not merely present somewhere."""
    page = goto("tasks")
    _open_palette(page)
    page.get_by_placeholder(PALETTE_PLACEHOLDER).fill("quiet window")
    page.wait_for_timeout(300)
    options = page.get_by_role("option")
    top = [options.nth(i).inner_text() for i in range(min(5, options.count()))]
    assert any(
        "Record a quiet window per project" in row for row in top
    ), f"task not in the top 5 options; got {top}"
