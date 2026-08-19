"""`2026-08-18-one-shell-three-panels`, tasks 2.2-2.5 and 3.1-3.6 — the re-hosted document panel
and its first real tenant, live.

Section 2 moved `ConversationView`'s one-off panel block into `PanelShell`
(`hub/ui/src/components/spec/PanelShell.tsx`), generalized the column breakpoint, and kept the
overlay below it. Section 3 unfused reading from attaching (design D9) and added the `specs`
index tab. Vitest covers the shell's own mechanics (tab model, keyboard, empty state) and
`ConversationView`'s layout arithmetic in isolation; nothing in that suite mounts the real app
against a real Hub, so nothing there would catch a wiring mistake in `App.tsx` (a missing
`projectId`, a store subscription that never fires), a real browser laying out the drawer
differently than jsdom does, or — the reason section 3 needed a fixture check rather than trusting
vitest's synthetic inventory — the live `/project/specs` response actually carrying the
`document_id` the tab key now depends on. This is that check, per the operator's instruction that
panel-shell testing goes through Playwright.

**Why `proj-b44fac0c`, not this suite's usual `proj-5e960453`.** A conversation destination needs
a real agent, and the default fixture project has none — `test_command_palette.py` already
documents this as a standing gap. `proj-b44fac0c` ("Throwaway (taste pass)") is the operator's own
disposable project and already carries a real agent (`q2verify`) with a real conversation and a
real specification document, so it is read from, never mutated, here.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest
from playwright.sync_api import Page, expect

PROJECT_ID = "proj-b44fac0c"
AGENT = "q2verify"
CONVERSATION_ID = "conv-b77949d3"
DOCUMENT_PATH = "spec/changes/teal-roc/spec.html"

PANEL_SHELL = '[data-testid="panel-shell"]'
TAB_STRIP = '[data-testid="panel-tab-strip"]'
DOCUMENT_PANEL = '[data-testid="spec-document-panel"]'


@pytest.fixture(scope="module")
def spec_tab_id(api) -> str:
    """The live tab key for `DOCUMENT_PATH` — its Hub document id where one exists, else the path
    itself (design D4, task 3.2). Resolved from the API rather than hardcoded: `teal-roc/spec.html`
    already carries a real `spec_documents` row (created through an earlier exploration), so its
    key is `spec:<id>`, not `spec:<path>` — hardcoding the path here would silently test against a
    tab that section 3 no longer opens."""
    status, body = api("GET", f"/api/v1/projects/{PROJECT_ID}/project/specs")
    assert status == 200, body
    entry = next(s for s in body["specs"] if s["path"] == DOCUMENT_PATH)
    key = entry.get("document_id") or DOCUMENT_PATH
    return f"spec:{key}"


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
    page: Page, hub_url: str, spec_tab_id: str
) -> None:
    """Task 2.2: the panel-hosting block is the shell now, not a bespoke `SpecDocumentPanel` mount.

    Both the strip and the document's own breadcrumb/phase bar must be present — re-hosting, not
    rewriting `SpecDocumentPanel`'s internals.
    """
    _open(page, hub_url)

    expect(page.locator(TAB_STRIP)).to_be_visible()
    tab = page.get_by_test_id(f"panel-tab-{spec_tab_id}")
    expect(tab).to_be_visible()
    expect(tab).to_have_attribute("aria-selected", "true")

    expect(page.locator(DOCUMENT_PANEL)).to_be_visible()
    expect(page.get_by_test_id("spec-document-breadcrumb")).to_be_visible()


def test_closing_the_tab_closes_the_reading_pane_but_not_the_document(
    page: Page, hub_url: str, spec_tab_id: str
) -> None:
    """Section 3, task 3.3 (design D9): closing a `spec:` tab used to detach the document — this
    is the behavior the unfuse ends. The tab-strip's own close control now only closes that tab;
    the shell stays mounted (the document is still attached) showing its empty state, and the
    composer's pill still names the document."""
    _open(page, hub_url)

    page.get_by_test_id(f"panel-tab-close-{spec_tab_id}").click()

    expect(page.locator(PANEL_SHELL)).to_be_visible()
    expect(page.locator(DOCUMENT_PANEL)).not_to_be_visible()
    expect(page.get_by_test_id("panel-empty-state")).to_be_visible()
    assert (
        "document=" in page.url
    ), f"document param was dropped by closing a reading tab: {page.url}"
    expect(page.get_by_test_id("composer-spec-control")).to_be_visible()


def test_narrow_window_overlays_the_shell_and_keeps_it_on_dismiss(
    page: Page, hub_url: str, spec_tab_id: str
) -> None:
    """Task 2.3/2.4: below the (now tab-derived) breakpoint the shell moves into the existing
    `Drawer`, and dismissing it must not discard the tab underneath.

    700 is comfortably under `DOCUMENT_COLUMN_BREAKPOINT` (380 + 360 + 1 = 741 today).
    """
    _open(page, hub_url, width=700)

    expect(page.get_by_test_id("workspace-drawer")).to_be_visible()
    expect(page.locator(PANEL_SHELL)).to_be_visible()
    expect(page.get_by_test_id(f"panel-tab-{spec_tab_id}")).to_be_visible()

    dialog = page.get_by_role("dialog")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()

    reopen = page.get_by_test_id("conversation-open-document")
    expect(reopen).to_be_visible()
    reopen.click()

    expect(page.get_by_test_id("workspace-drawer")).to_be_visible()
    # The same tab, not a fresh empty shell — dismissing the overlay must not have dropped it.
    expect(page.get_by_test_id(f"panel-tab-{spec_tab_id}")).to_be_visible()


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
    page: Page, hub_url: str, spec_tab_id: str
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
    expect(page.get_by_test_id(f"panel-tab-{spec_tab_id}")).to_be_visible()
    assert "document=" in page.url


def test_the_specs_index_tab_opens_from_the_plus_affordance(
    page: Page, hub_url: str, spec_tab_id: str
) -> None:
    """Section 3, task 3.1: the specs index — content the Ctrl+K dialog already showed, re-hosted
    as a tab — is reachable from the shell's own plus menu, not just the keyboard shortcut.

    Clicks the plus affordance immediately after `_open`, the same as a real operator would, and
    only THEN waits for the document's own tab to reach its steady-state key (`spec_tab_id`) —
    i.e. for the workspace inventory fetch, in flight or not, to finish resolving — before
    asserting `panel-tab-specs`. This used to pass vacuously: `expect().to_have_attribute`
    auto-retries and can catch the brief instant right after the click but *before* that
    still-in-flight inventory fetch resolves — which, before C1's fix (`replaceTabId` in
    `panelTabsStore.ts`), re-keyed the document tab via `openTab`, forcing it back into focus and
    flipping `panel-tab-specs` to `aria-selected=false` a moment later. The suite reported the
    symptom one test later (the next test would then fail against a vanished specs tree), never
    here, because nothing here looked again after the click.
    """
    _open(page, hub_url)

    page.get_by_test_id("panel-tab-add").click()
    page.get_by_role("menuitem", name="Specs").click()

    # Let the document tab's re-key resolve (whether it was already resolved or still in flight)
    # BEFORE asserting on the specs tab — so the assertion below measures steady state, not a
    # transient window an auto-retrying `expect()` could catch and move on from.
    expect(page.get_by_test_id(f"panel-tab-{spec_tab_id}")).to_be_visible()

    specs_tab = page.get_by_test_id("panel-tab-specs")
    expect(specs_tab).to_have_attribute("aria-selected", "true")
    expect(page.get_by_test_id("spec-document-browser")).to_be_visible()


def test_selecting_a_document_from_the_index_tab_reads_it_without_attaching_it(
    page: Page, hub_url: str, spec_tab_id: str
) -> None:
    """Section 3, task 3.2/3.3 (design D9), live: opening a document from the specs index tab is a
    read, not an attach — the destination (and so the composer's attach pill) must not move.

    Only one document exists in this fixture project, so this exercises the *refocus* path (task
    1.3's store behavior): selecting the already-attached document from the index switches the
    shell back to its existing tab rather than opening a duplicate — itself worth asserting, since
    a naive `onSelect` wired straight to `openTab` could easily double it instead.
    """
    _open(page, hub_url)
    before_url = page.url

    page.get_by_test_id("panel-tab-add").click()
    page.get_by_role("menuitem", name="Specs").click()
    page.get_by_test_id(f"spec-tree-document-{DOCUMENT_PATH}").click()

    tab = page.get_by_test_id(f"panel-tab-{spec_tab_id}")
    expect(tab).to_have_attribute("aria-selected", "true")
    expect(page.locator(DOCUMENT_PANEL)).to_be_visible()
    assert page.url == before_url, "reading from the index tab must not change the destination"
    expect(page.get_by_test_id("composer-spec-control")).to_be_visible()


def test_wide_window_lays_out_as_two_columns(page: Page, hub_url: str) -> None:
    """The companion case to the overlay above — at the width this suite's other tests already
    run at, the shell sits in a column beside the conversation, not behind a drawer."""
    _open(page, hub_url, width=1440)

    expect(page.locator('[data-testid="document-pane"]')).to_be_visible()
    expect(page.locator(PANEL_SHELL)).to_be_visible()
    expect(page.get_by_test_id("workspace-drawer")).not_to_be_attached()
