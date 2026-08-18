"""Computed-style evidence for two taste tasks that a browser can measure but not settle.

`2026-08-16-spec-surface-legibility` **7.2** — *"F2 — does the background actually match,
to the eye, not just by variable name? 1.4's computed-style check (if run) is strong
evidence but the operator's original complaint was a felt mismatch, not a value."*

`2026-08-16-the-board-scoped-by-document` **5.2** — *"Does the document-tasks link read as
the same kind of control as the coverage bar's per-requirement links? … confirm they do not
visually compete or look like two different features."*

Neither task is closed by anything here. 7.2 explicitly discounts the measurement in
advance, and 5.2 asks how two controls *read* side by side. What these produce is the hard
number underneath each: the frame's actual background against `HUB_NEUTRALS`, and a
property-by-property diff of the two links. The operator then judges with the values in
hand rather than from memory.

**The stale-render trap, from task 1.4's own notes.** Spec documents are rendered to HTML
*once, at write time*, and stored — so a document written before this change still carries
the old colours, and pointing a browser at it shows a mismatch that is not a bug. All three
fixture documents here were written 2026-08-17 or later, after the 2026-08-16 change, so
they are rendered with the current palette. Re-point this at an older document and it will
fail for that reason and no other.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest
from playwright.sync_api import Page, expect

CAPABILITY_DOC = "spec/capabilities/quiet-hours/spec.html"
ARCHIVED_DOC = "spec/changes/quiet-hours-for-agent-notifications/spec.html"

# hub/ui/src/components/spec/hubTheme.ts — the values the frame's background must match.
HUB_NEUTRALS_BG = {"light": "rgb(250, 250, 250)", "dark": "rgb(10, 10, 11)"}

SPEC_FRAME = '[data-testid="spec-frame"]'
DOC_TASKS_LINK = '[data-testid="spec-document-tasks-link"]'

# The properties that decide whether two text buttons read as the same kind of control.
LINK_PROPERTIES = (
    "color",
    "background-color",
    "border-bottom-style",
    "font-size",
    "font-weight",
    "text-decoration-line",
    "cursor",
)


def _open(goto, path: str) -> Page:
    page = goto("spec", document=quote(path, safe=""))
    page.wait_for_selector('[data-testid="spec-document-panel"]', timeout=20_000)
    return page


def _switch_to_dark(page: Page) -> None:
    toggle = page.get_by_role("button", name="Switch to dark mode")
    expect(toggle).to_be_visible()
    toggle.click()
    expect(page.get_by_role("button", name="Switch to light mode")).to_be_visible()


def _computed(page: Page, selector: str, prop: str) -> str:
    return page.eval_on_selector(
        selector,
        "(el, prop) => getComputedStyle(el).getPropertyValue(prop).trim()",
        prop,
    )


# --------------------------------------------------------------------------------------
# 7.2 — F2, the background
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_document_frame_background_matches_hub_neutrals(goto, theme: str) -> None:
    """1.4's assertion, re-run against a document written after the change.

    The document renders inside an iframe (`SpecFrame`), so the background that matters is
    the one *inside* the frame — reading the host element's style would measure the shell
    and always agree with itself.
    """
    page = _open(goto, CAPABILITY_DOC)
    if theme == "dark":
        _switch_to_dark(page)
    page.wait_for_timeout(400)

    frame = page.frame_locator(SPEC_FRAME)
    body_bg = frame.locator("body").evaluate("el => getComputedStyle(el).backgroundColor")
    assert body_bg == HUB_NEUTRALS_BG[theme], (
        f"{theme}: frame background is {body_bg}, HUB_NEUTRALS says "
        f"{HUB_NEUTRALS_BG[theme]}. If this document predates 2026-08-16 the render is "
        "stale rather than wrong — check its written date before treating it as a defect."
    )


def test_the_frame_background_actually_changes_with_the_theme(goto) -> None:
    """The control that stops the test above passing on a frame that ignores the theme.

    If both themes produced the same value, one of the two parametrised cases would fail —
    unless the expected values were themselves wrong. This asserts the difference directly.
    """
    page = _open(goto, CAPABILITY_DOC)
    frame = page.frame_locator(SPEC_FRAME)
    light = frame.locator("body").evaluate("el => getComputedStyle(el).backgroundColor")
    _switch_to_dark(page)
    page.wait_for_timeout(400)
    dark = frame.locator("body").evaluate("el => getComputedStyle(el).backgroundColor")
    assert light != dark, f"the frame background did not change with the theme ({light})"


# --------------------------------------------------------------------------------------
# 5.2 — the two links, side by side
# --------------------------------------------------------------------------------------


def test_both_task_links_are_present_to_compare(goto) -> None:
    """The premise. The archived document is the one that has both controls at once."""
    page = _open(goto, ARCHIVED_DOC)
    expect(page.locator(DOC_TASKS_LINK)).to_be_visible()


def test_report_how_the_two_task_links_differ(goto) -> None:
    """5.2's evidence: a property-by-property diff, printed for the operator.

    This does not assert the two are identical, because they are not — `SpecCoverageBar`
    gives its per-requirement link `textDecoration: 'underline'` and
    `SpecDocumentTasksLink` does not. Whether that reads as "two different features" is
    exactly the judgement 5.2 reserves. What is asserted is the part that is not a matter
    of taste: they must at least agree on colour, or they are not the same kind of control
    by anyone's reading.
    """
    page = _open(goto, ARCHIVED_DOC)

    doc_link = f"{DOC_TASKS_LINK} button"
    coverage_link = '[data-testid^="coverage-tasks-link-"]'

    # The per-requirement rows live behind the coverage bar's own disclosure
    # (`aria-expanded` on its summary button), so the links do not exist in the DOM until
    # it is opened. Without this the comparison skipped itself and reported nothing.
    summary = page.locator('[data-testid="spec-coverage"] [aria-expanded]').first
    expect(summary).to_be_visible()
    if summary.get_attribute("aria-expanded") == "false":
        summary.click()
    page.wait_for_timeout(300)

    if page.locator(coverage_link).count() == 0:
        pytest.skip(
            "no requirement in this document has linked tasks, so the coverage bar renders "
            "no per-requirement link to compare against"
        )

    differences = {}
    for prop in LINK_PROPERTIES:
        a = _computed(page, doc_link, prop)
        b = _computed(page, coverage_link, prop)
        if a != b:
            differences[prop] = (a, b)

    print("\n5.2 — document-tasks link vs coverage per-requirement link:")
    for prop in LINK_PROPERTIES:
        a = _computed(page, doc_link, prop)
        b = _computed(page, coverage_link, prop)
        mark = "  " if a == b else "->"
        print(f"  {mark} {prop:24} doc={a!r:28} coverage={b!r}")

    assert (
        "color" not in differences
    ), f"the two links do not even share a colour: {differences['color']}"
