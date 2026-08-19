"""The objective half of the "Human-only" sections, settled in a real browser.

Both open changes end with a section the operator owns — `2026-08-18-one-shell-three-panels`
section 7, and `2026-08-18-a-loop-writes-its-own-queue` sections 13, A6 and B7. Those questions
mix two different claims in one checkbox, exactly as `conftest.py` describes: an objective one a
browser can settle ("does the document stay attached", "are the two badges actually different
colours") and a taste one it cannot ("does it *feel* safe", "is it different enough *at a
glance*").

This file closes the objective halves that need a **real browser** — layout, computed colour,
what survives a click. The objective halves that are really API assertions already live in the
Python suite and are deliberately not duplicated here:

  - 13.3's "the refusal names `send_message`" →
    `test_agent_actions_coordination.py::test_loop_non_creator_non_operator_is_refused_and_told_to_send_message`
  - B7.2's "a refused delete names archiving" → `test_jobs.py::test_delete_job_refuses_and_archive_replaces_it`
  - B7.3's data half ("counts come from `ending_state`, never `stop_reason` text") →
    `test_loop_archival.py`

**Nothing here ticks a human-only box.** A green run is evidence for the operator's judgement,
never a substitute for it — every test below says which half it settled and which it did not.

Fixtures. `proj-b44fac0c` has a real agent, conversation and specification document, so it is the
only project where the spec-attach behaviour can be driven. `proj-5e960453` is the repo's own
registration: it has no conversation but *does* have loops in all three ending states, and the
shell mounts on a bare conversation (a header toggle, not an attached document), which is what
makes the loops index reachable there at all.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest
from playwright.sync_api import Page, expect

# --- the conversation-with-a-document fixture ---------------------------------------------------
SPEC_PROJECT = "proj-b44fac0c"
SPEC_AGENT = "q2verify"
SPEC_CONVERSATION = "conv-b77949d3"
DOCUMENT_PATH = "spec/changes/teal-roc/spec.html"

# --- the project that actually has loops --------------------------------------------------------
LOOP_PROJECT = "proj-5e960453"
LOOP_AGENT = "claude-1"
COMPLETED_LOOP = "loop-f1eab23e"  # ending_state = "completed"
STOPPED_LOOP = "loop-2913d58b"  # ending_state = "stopped"

PANEL_SHELL = '[data-testid="panel-shell"]'


def _open_with_document(page: Page, hub_url: str) -> None:
    query = (
        f"project={SPEC_PROJECT}&agent={SPEC_AGENT}&conversation={SPEC_CONVERSATION}"
        f"&document={quote(DOCUMENT_PATH, safe='')}"
    )
    page.goto(f"{hub_url}/?{query}", wait_until="load")
    page.wait_for_selector(PANEL_SHELL, timeout=20_000)


def _open_loops_index(page: Page, hub_url: str) -> None:
    page.goto(f"{hub_url}/?project={LOOP_PROJECT}&agent={LOOP_AGENT}", wait_until="load")
    page.wait_for_selector('[data-testid="conversation-workspace"]', timeout=20_000)
    toggle = page.get_by_test_id("conversation-toggle-panel")
    expect(toggle).to_be_visible()
    toggle.click()
    launch = page.get_by_test_id("panel-launch-loops")
    expect(launch).to_be_visible()
    launch.click()
    expect(page.get_by_test_id("loops-index-tab")).to_be_visible()


# ================================================================================================
# Panel change, section 7
# ================================================================================================


def test_the_plus_affordance_is_labelled_as_adding_a_tab(page: Page, hub_url: str) -> None:
    """7.1's floor. Whether it *reads* as "add a tab" rather than "settings" is the operator's
    call; that it is **named** so, and carries the add glyph rather than a gear, is not. If this
    fails the taste question is moot, because the control is mislabelled."""
    _open_with_document(page, hub_url)

    add = page.get_by_test_id("panel-tab-add")
    expect(add).to_be_visible()
    label = (add.get_attribute("aria-label") or "") + (add.get_attribute("title") or "")
    assert "add" in label.lower(), f"plus affordance is labelled {label!r}"
    assert "setting" not in label.lower()


def test_closing_a_spec_tab_does_not_detach_the_document(page: Page, hub_url: str) -> None:
    """7.2's objective half, and design D9's whole guarantee: closing a *reader* must not change
    what the agent writes into. Whether that reads as obviously safe is the operator's half.

    The precondition is asserted first — a document really is attached — so this cannot pass on a
    conversation that never had one, which would make the whole assertion vacuous.
    """
    _open_with_document(page, hub_url)

    assert "document=" in page.url, "precondition: a document must be attached to close its tab"
    pill = page.get_by_test_id("composer-spec-control")
    expect(pill).to_be_visible()
    attached_before = pill.inner_text()
    assert attached_before.strip(), "precondition: the composer must name the attached document"

    closers = page.locator('[data-testid^="panel-tab-close-spec:"]')
    expect(closers.first).to_be_visible()
    closers.first.click()

    # The tab is gone...
    expect(page.locator('[data-testid^="panel-tab-spec:"]')).to_have_count(0)
    # ...and the attachment is not.
    expect(pill).to_have_text(attached_before)
    assert "document=" in page.url, "closing the reader must not clear the destination"


@pytest.mark.parametrize("width", [1400, 900, 700, 560])
def test_the_shell_stays_within_its_own_bounds_at_every_width(
    page: Page, hub_url: str, width: int
) -> None:
    """7.4's objective half: at each width the shell is *present and contained* — it never spills
    past the viewport and never overlaps the conversation. Whether it is **usable** rather than
    merely present at the narrowest width is exactly the half a browser cannot answer, and is left
    to the operator.
    """
    page.set_viewport_size({"width": width, "height": 900})
    _open_with_document(page, hub_url)
    page.wait_for_timeout(600)

    shell = page.locator(PANEL_SHELL)
    expect(shell).to_be_visible()
    box = shell.bounding_box()
    assert box is not None, "the shell must have a layout box to be judged at all"
    assert box["width"] > 0 and box["height"] > 0

    # Never wider than the window, and never hanging off either edge.
    assert box["x"] >= -1, f"shell starts off-screen at {width}px (x={box['x']})"
    assert box["x"] + box["width"] <= width + 1, (
        f"shell overflows the viewport at {width}px: " f"x={box['x']} + w={box['width']} > {width}"
    )

    # No horizontal scrollbar on the document — the classic symptom of a pane that does not fit.
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"page scrolls horizontally by {overflow}px at {width}px"


# ================================================================================================
# Loop change, section B7
# ================================================================================================


def test_the_loops_index_states_what_is_running_without_a_drill_down(
    page: Page, hub_url: str
) -> None:
    """B7.1's objective half: the running/complete/stopped split is legible from the index alone,
    with no drill-down open. Whether that counts as "at a glance" is the operator's half."""
    _open_loops_index(page, hub_url)

    summary = page.get_by_test_id("loops-index-summary")
    # `expect().to_contain_text` and not a raw `inner_text()`: the panel renders "no loops" while
    # the loops query is still in flight, and a plain read catches that placeholder rather than the
    # answer. Auto-retry is the right tool *here* — this is waiting for async data to settle, not
    # asserting that something stays true, which is the case where retry hides a race instead of
    # tolerating one (see run 2's C1).
    expect(summary).to_contain_text("running", timeout=15_000)

    rows = page.locator('[data-testid^="loops-index-row-"]')
    expect(rows.first).to_be_visible()
    assert rows.count() >= 2, "precondition: need several loops for this to mean anything"

    # No drill-down was opened to learn any of that.
    expect(page.locator('[data-testid^="panel-tab-loop:"]')).to_have_count(0)


def test_opening_a_drill_down_leaves_the_index_open(page: Page, hub_url: str) -> None:
    """B5.2/B7.1: the index is a governance glance, not a launcher — unlike the files tree, which
    a file replaces. The asymmetry is deliberate and stated in both changes, so it is worth an
    assertion rather than a comment."""
    _open_loops_index(page, hub_url)

    page.get_by_test_id(f"loops-index-row-{COMPLETED_LOOP}").click()

    expect(page.get_by_test_id(f"panel-tab-loop:{COMPLETED_LOOP}")).to_be_visible()
    expect(page.get_by_test_id("panel-tab-loops")).to_be_visible()


def test_complete_and_stopped_early_are_not_the_same_badge(page: Page, hub_url: str) -> None:
    """B7.3's objective half: "complete" and "stopped early" must not render as the same grey
    badge — if they did, `ending_state` bought nothing a sentence did not.

    This asserts only that they **differ** in text and in colour, and prints the property diff.
    It deliberately does not judge whether the difference is *enough* at a glance; that is the
    operator's half, and a test claiming to settle it would be marking its own homework — the same
    posture `board` 5.2a took in the earlier suite.
    """
    _open_loops_index(page, hub_url)

    # Wait for the rows to actually carry their badges before reading any computed style.
    expect(page.get_by_test_id("loops-index-summary")).to_contain_text("running", timeout=15_000)
    expect(page.get_by_test_id(f"loops-index-row-{COMPLETED_LOOP}")).to_be_visible()
    expect(page.get_by_test_id(f"loops-index-row-{STOPPED_LOOP}")).to_be_visible()

    def badge_of(row_id: str) -> tuple[str, str, str]:
        """The row's status badge: its text, colour and background.

        Takes the **innermost** element whose text is the status word. An ancestor's `textContent`
        is identical to its only child's, and `querySelectorAll` returns ancestors first — so the
        naive "first match" is the unstyled wrapper, which reports the inherited near-black text
        colour and a transparent background for *every* status. That made the two badges compare
        equal and failed this test for the wrong reason, which is the good outcome of asserting a
        precondition; a test written to accept it would have reported "identical" forever.
        """
        return tuple(  # type: ignore[return-value]
            page.evaluate(
                """(rowId) => {
                    const row = document.querySelector(`[data-testid="${rowId}"]`)
                    const isStatus = e => /^(Complete|Stopped early|Running)$/.test(e.textContent.trim())
                    const matches = Array.from(row.querySelectorAll('span, div')).filter(isStatus)
                    // innermost = the one with no matching descendant
                    const badge = matches.find(e => !matches.some(o => o !== e && e.contains(o)))
                    if (!badge) return ['', '', '']
                    const s = getComputedStyle(badge)
                    return [badge.textContent.trim(), s.color, s.backgroundColor]
                }""",
                row_id,
            )
        )

    done_text, done_fg, done_bg = badge_of(f"loops-index-row-{COMPLETED_LOOP}")
    stop_text, stop_fg, stop_bg = badge_of(f"loops-index-row-{STOPPED_LOOP}")

    print(
        "\n  B7.3 property diff (operator judges whether this is enough at a glance):"
        f"\n    complete      text={done_text!r} colour={done_fg} background={done_bg}"
        f"\n    stopped early text={stop_text!r} colour={stop_fg} background={stop_bg}"
    )

    # Preconditions: both badges were actually found. Without this the inequality below would
    # pass trivially on two empty strings.
    assert done_text, f"no status badge found on the completed loop row ({COMPLETED_LOOP})"
    assert stop_text, f"no status badge found on the stopped loop row ({STOPPED_LOOP})"

    assert done_text != stop_text, "the two ending states render the same words"
    assert (done_fg, done_bg) != (
        stop_fg,
        stop_bg,
    ), "the two ending states render in identical colours — they would read as the same badge"
