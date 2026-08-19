"""`2026-08-18-a-loop-writes-its-own-queue`, tasks B5 and B6.1/B6.5 — the loops index tab and its
drill-down, live against the real Hub.

Section B4 (iteration 21) put `label`, `current_task` correctness, and a project-scoped list
endpoint behind the API; nothing there touches the UI. This is that UI, plus the fix this task's
own brief in `.claude/autonomous/STATE.json` required as a precondition: `ConversationView`
mounted `PanelShell` only when a specification document was attached (`document ? <PanelShell/> :
null`, recorded as a known gap in `decisions_for_user` at iteration 16), which would have made a
document-free tenant like `loops` unreachable from a bare conversation. `ConversationView` now
gates the shell on `documentOpen || shellIsOpen` (the store's own `isOpen` bit, settable via a new
header toggle, `conversation-toggle-panel`) instead of `documentOpen` alone.

**Why `proj-5e960453`, not `proj-b44fac0c`.** `test_panel_shell.py` uses the operator's disposable
project because the default fixture project had no agent with a conversation at the time it was
written. That has since changed: `proj-5e960453`'s own `claude-1` agent now carries real
conversations and real loops (`LB1`-`LB4`'s own live smoke tests, left in place as historical
evidence per their own precedent) — exactly the fixture this suite needs and `proj-b44fac0c` does
not have (it carries zero loops). Read from, never mutated.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

PROJECT_ID = "proj-5e960453"
AGENT = "claude-1"
CONVERSATION_ID = "conv-01af4e70"

# Fixed points in this project's real, accumulated loop history (LB1-LB4's own smoke tests):
# a loop with a real claimed item (D21's own fix, B4.1), and the one loop this run's LB2/LB3
# archived — both exercised live rather than fabricated.
CURRENT_ITEM_LOOP_ID = "loop-8e86eb9f"
ARCHIVED_LOOP_ID = "loop-d57671ec"

PANEL_SHELL = '[data-testid="panel-shell"]'


def _open_bare(page: Page, hub_url: str) -> Page:
    """No `document` param at all — the case that used to leave the shell unreachable."""
    query = f"project={PROJECT_ID}&agent={AGENT}&conversation={CONVERSATION_ID}"
    page.goto(f"{hub_url}/?{query}", wait_until="load")
    page.wait_for_selector('[data-testid="conversation-workspace"]', timeout=20_000)
    return page


def _open_loops_tab(page: Page, hub_url: str) -> Page:
    _open_bare(page, hub_url)
    expect(page.locator(PANEL_SHELL)).not_to_be_attached()

    page.get_by_test_id("conversation-toggle-panel").click()
    expect(page.locator(PANEL_SHELL)).to_be_visible()
    expect(page.get_by_test_id("panel-empty-state")).to_be_visible()

    page.get_by_test_id("panel-tab-add").click()
    page.get_by_role("menuitem", name="Loops").click()
    expect(page.get_by_test_id("panel-tab-loops")).to_have_attribute("aria-selected", "true")
    expect(page.get_by_test_id("loops-index-tab")).to_be_visible()
    return page


def test_the_loops_tab_is_reachable_from_a_bare_conversation(page: Page, hub_url: str) -> None:
    """The precondition this task's own brief required: a document-free tenant must be reachable
    without ever having attached a specification document — the gap flagged at iteration 16 must
    not repeat for `loops`."""
    _open_bare(page, hub_url)

    toggle = page.get_by_test_id("conversation-toggle-panel")
    expect(toggle).to_have_attribute("aria-pressed", "false")
    toggle.click()
    expect(toggle).to_have_attribute("aria-pressed", "true")
    expect(page.locator(PANEL_SHELL)).to_be_visible()

    # Toggling again hides it without discarding anything mounted underneath.
    toggle.click()
    expect(page.locator(PANEL_SHELL)).not_to_be_attached()


def test_loops_index_lists_real_loops_with_counts_by_ending_state(page: Page, hub_url: str) -> None:
    """Task B5.1/B5.3: label, purpose, an ending-state badge per row, and a summary line computed
    from `ending_state` — never `stop_reason` text. `loop-8e86eb9f`'s own `stop_reason` is `None`
    but a sibling fixture loop (`loop-f1eab23e`) has a `stop_reason` set while still `ending_state:
    null` (still running, per D17/D21) — if the summary or badge were reading `stop_reason`
    instead, that loop would misreport as stopped."""
    _open_loops_tab(page, hub_url)

    # `expect(...).to_contain_text` retries until the loops query resolves. A raw `.text_content()`
    # read right after `to_be_visible()` can catch the tab's own pre-fetch "No loops" default —
    # the tab mounts, and the summary renders, before `GET /projects/{id}/loops` has returned.
    summary = page.get_by_test_id("loops-index-summary")
    expect(summary).to_contain_text(
        "running",
        timeout=10_000,
    )

    row = page.get_by_test_id(f"loops-index-row-{CURRENT_ITEM_LOOP_ID}")
    expect(row).to_be_visible()
    expect(row).to_contain_text("Running")
    expect(row).to_contain_text("Queue: 1")


def test_selecting_a_loop_opens_the_drill_down_and_the_index_stays_open(
    page: Page, hub_url: str
) -> None:
    """Task B5.2: unlike the files tree, which `openTab` closes on selection (design D8),
    opening a loop's drill-down leaves the index tab in the strip — a governance glance, not a
    launcher."""
    _open_loops_tab(page, hub_url)

    page.get_by_test_id(f"loops-index-row-{CURRENT_ITEM_LOOP_ID}").click()

    drill_down_tab = page.get_by_test_id(f"panel-tab-loop:{CURRENT_ITEM_LOOP_ID}")
    expect(drill_down_tab).to_have_attribute("aria-selected", "true")
    expect(page.get_by_test_id("loop-tab")).to_be_visible()
    # The index is still open beside it, not replaced.
    expect(page.get_by_test_id("panel-tab-loops")).to_be_visible()


def test_loop_drill_down_shows_the_claimed_item_and_queue(page: Page, hub_url: str) -> None:
    """Task B6.1: the claimed item and queue counts by status, from the same `LoopDetail` the
    index reads (B4.1's fix — an `assigned` task is a real current item, not an invisible one)."""
    _open_loops_tab(page, hub_url)
    page.get_by_test_id(f"loops-index-row-{CURRENT_ITEM_LOOP_ID}").click()

    current_task = page.get_by_test_id("loop-tab-current-task")
    expect(current_task).to_contain_text("assigned")
    expect(page.get_by_test_id("loop-tab")).to_contain_text("assigned: 1")


def test_archived_loops_are_hidden_by_default_and_reachable_behind_the_filter(
    page: Page, hub_url: str
) -> None:
    """Task B5.4: the same `include_archived` shape `list_jobs` already has, exposed as a
    checkbox rather than guessed at."""
    _open_loops_tab(page, hub_url)

    expect(page.get_by_test_id(f"loops-index-row-{ARCHIVED_LOOP_ID}")).not_to_be_attached()

    page.get_by_test_id("loops-index-include-archived").check()

    archived_row = page.get_by_test_id(f"loops-index-row-{ARCHIVED_LOOP_ID}")
    expect(archived_row).to_be_visible()
    expect(archived_row).to_contain_text("Archived")
    expect(archived_row).to_contain_text("Stopped early")
