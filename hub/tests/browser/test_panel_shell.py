"""`2026-08-18-one-shell-three-panels`, task 2.2-2.5 — the re-hosted document panel, live.

Section 2 moved `ConversationView`'s one-off panel block into `PanelShell`
(`hub/ui/src/components/spec/PanelShell.tsx`), generalized the column breakpoint, and kept the
overlay below it. Vitest covers the shell's own mechanics (tab model, keyboard, empty state) and
`ConversationView`'s layout arithmetic in isolation; nothing in that suite mounts the real app
against a real Hub, so nothing there would catch a wiring mistake in `App.tsx` (a missing
`projectId`, a store subscription that never fires) or a real browser laying out the drawer
differently than jsdom does. This is that check, per the operator's instruction that panel-shell
testing goes through Playwright.

**Why `proj-b44fac0c`, not this suite's usual `proj-5e960453`.** A conversation destination needs
a real agent, and the default fixture project has none — `test_command_palette.py` already
documents this as a standing gap. `proj-b44fac0c` ("Throwaway (taste pass)") is the operator's own
disposable project and already carries a real agent (`q2verify`) with a real conversation and a
real specification document, so it is read from, never mutated, here.
"""

from __future__ import annotations

from urllib.parse import quote

from playwright.sync_api import Page, expect

PROJECT_ID = "proj-b44fac0c"
AGENT = "q2verify"
CONVERSATION_ID = "conv-b77949d3"
DOCUMENT_PATH = "spec/changes/teal-roc/spec.html"
SPEC_TAB_ID = f"spec:{DOCUMENT_PATH}"

PANEL_SHELL = '[data-testid="panel-shell"]'
TAB_STRIP = '[data-testid="panel-tab-strip"]'
DOCUMENT_PANEL = '[data-testid="spec-document-panel"]'


def _open(page: Page, hub_url: str, *, width: int | None = None) -> Page:
    if width is not None:
        page.set_viewport_size({"width": width, "height": 900})
    query = (
        f"project={PROJECT_ID}&agent={AGENT}&conversation={CONVERSATION_ID}"
        f"&document={quote(DOCUMENT_PATH, safe='')}"
    )
    page.goto(f"{hub_url}/?{query}", wait_until="load")
    page.wait_for_selector(PANEL_SHELL, timeout=20_000)
    return page


def test_the_document_opens_inside_the_shell_not_as_a_one_off_block(
    page: Page, hub_url: str
) -> None:
    """Task 2.2: the panel-hosting block is the shell now, not a bespoke `SpecDocumentPanel` mount.

    Both the strip and the document's own breadcrumb/phase bar must be present — re-hosting, not
    rewriting `SpecDocumentPanel`'s internals.
    """
    _open(page, hub_url)

    expect(page.locator(TAB_STRIP)).to_be_visible()
    tab = page.get_by_test_id(f"panel-tab-{SPEC_TAB_ID}")
    expect(tab).to_be_visible()
    expect(tab).to_have_attribute("aria-selected", "true")

    expect(page.locator(DOCUMENT_PANEL)).to_be_visible()
    expect(page.get_by_test_id("spec-document-breadcrumb")).to_be_visible()


def test_closing_the_tab_closes_the_document(page: Page, hub_url: str) -> None:
    """The tab-strip's own close control, not just the breadcrumb's, drops the document —
    section 3 will add real multi-tab semantics; today there is exactly one tab and closing it is
    the only close path this task promises."""
    _open(page, hub_url)

    page.get_by_test_id(f"panel-tab-close-{SPEC_TAB_ID}").click()

    expect(page.locator(PANEL_SHELL)).not_to_be_visible()
    expect(page.locator(DOCUMENT_PANEL)).not_to_be_visible()
    assert "document=" not in page.url, f"document param survived close: {page.url}"


def test_narrow_window_overlays_the_shell_and_keeps_it_on_dismiss(page: Page, hub_url: str) -> None:
    """Task 2.3/2.4: below the (now tab-derived) breakpoint the shell moves into the existing
    `Drawer`, and dismissing it must not discard the tab underneath.

    700 is comfortably under `DOCUMENT_COLUMN_BREAKPOINT` (380 + 360 + 1 = 741 today).
    """
    _open(page, hub_url, width=700)

    expect(page.get_by_test_id("workspace-drawer")).to_be_visible()
    expect(page.locator(PANEL_SHELL)).to_be_visible()
    expect(page.get_by_test_id(f"panel-tab-{SPEC_TAB_ID}")).to_be_visible()

    dialog = page.get_by_role("dialog")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()

    reopen = page.get_by_test_id("conversation-open-document")
    expect(reopen).to_be_visible()
    reopen.click()

    expect(page.get_by_test_id("workspace-drawer")).to_be_visible()
    # The same tab, not a fresh empty shell — dismissing the overlay must not have dropped it.
    expect(page.get_by_test_id(f"panel-tab-{SPEC_TAB_ID}")).to_be_visible()


def test_the_composers_own_close_control_also_closes_the_shell(page: Page, hub_url: str) -> None:
    """A third close entry point besides the tab strip and the breadcrumb: the composer's
    attach pill (`ComposerSpecControl`) has its own "Close the document" button, unaffected by
    this task, but only correct if it still tears the shell down through the same
    destination -> store sync the other two paths use."""
    _open(page, hub_url)

    page.get_by_test_id("composer-stop-exploring").click()

    expect(page.locator(PANEL_SHELL)).not_to_be_visible()
    expect(page.locator(DOCUMENT_PANEL)).not_to_be_visible()
    assert "document=" not in page.url


def test_opening_a_document_from_a_bare_conversation_mounts_the_shell(
    page: Page, hub_url: str
) -> None:
    """Starting with no document at all, then attaching one through the composer's picker
    (Ctrl+K) — the path most conversations actually take, as opposed to `_open`'s deep link."""
    query = f"project={PROJECT_ID}&agent={AGENT}&conversation={CONVERSATION_ID}"
    page.goto(f"{hub_url}/?{query}", wait_until="load")
    page.wait_for_selector('[data-testid="conversation-workspace"]', timeout=20_000)
    expect(page.locator(PANEL_SHELL)).not_to_be_attached()

    page.keyboard.press("Control+k")
    page.get_by_placeholder("Search by title, path, or change name — or browse below").wait_for(
        timeout=10_000
    )
    page.get_by_test_id(f"spec-tree-document-{DOCUMENT_PATH}").click()

    expect(page.locator(PANEL_SHELL)).to_be_visible()
    expect(page.get_by_test_id(f"panel-tab-{SPEC_TAB_ID}")).to_be_visible()
    assert "document=" in page.url


def test_wide_window_lays_out_as_two_columns(page: Page, hub_url: str) -> None:
    """The companion case to the overlay above — at the width this suite's other tests already
    run at, the shell sits in a column beside the conversation, not behind a drawer."""
    _open(page, hub_url, width=1440)

    expect(page.locator('[data-testid="document-pane"]')).to_be_visible()
    expect(page.locator(PANEL_SHELL)).to_be_visible()
    expect(page.get_by_test_id("workspace-drawer")).not_to_be_attached()
