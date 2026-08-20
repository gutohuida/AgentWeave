"""`2026-08-18-one-shell-three-panels`, task 5 — the files tab, live.

Vitest covers `FileTree`/`FilesIndexTab`/`FileTab` in isolation (given `paths`/`data` as props)
and `panelTabsStore`'s D8 asymmetry (opening a `file:` tab closes `files`) against a synthetic
store. Nothing in that suite mounts the real app against a real Hub, so nothing there would
catch the shell not actually offering "Files" from the plus menu, a real click-through from a
real tree row failing to reach `openTab`, or the measured minimum width (task 5.5) being wrong
against real font metrics rather than jsdom's.

Fixture project and reasoning for using it (not the default `project_id`) match
`test_panel_shell.py`: `spec_project_id` (`proj-b44fac0c`, "Throwaway (taste pass)", overridable
with `AW_HUB_SPEC_PROJECT_ID`) is the operator's disposable project, already carrying a real
agent (`q2verify`), conversation, and specification document, read from but never mutated here.
Its own working directory (`testbed/throwaway-taste-project`) is entirely `testbed/.gitignore`d,
so `GET /workspace/paths` legitimately returns empty for it — real enough to prove the "no
files" and read-refusal (404) paths live, but not enough to click through a real tree row. Tests
that need one route `GET /workspace/paths` and `GET /workspace/file` to fixed responses instead
of hand-editing this project's working directory — real component, real store, real network
call, fabricated response, the same tradeoff `page.route` mocking always is.
"""

from __future__ import annotations

import re
from urllib.parse import quote

import pytest
from playwright.sync_api import Page, expect

AGENT = "q2verify"
CONVERSATION_ID = "conv-b77949d3"
DOCUMENT_PATH = "spec/changes/teal-roc/spec.html"
FIXTURE_FILE_PATH = "src/widgets/Button.tsx"
FIXTURE_FILE_CONTENT = "export function Button() {\n  return null\n}\n"

# Measured against the live shell, task 5.5 — see specPreferences.ts's own comment for the
# methodology. Kept here as a plain literal, not imported: this suite verifies the shipped
# number behaves correctly in a real browser, which a re-import of the same constant the
# component reads would not actually exercise.
FILE_TAB_MIN_WIDTH = 260

PANEL_SHELL = '[data-testid="panel-shell"]'
DOCUMENT_PANE = '[data-testid="document-pane"]'


def _open(page: Page, hub_url: str, project_id: str) -> Page:
    query = (
        f"project={project_id}&agent={AGENT}&conversation={CONVERSATION_ID}"
        f"&document={quote(DOCUMENT_PATH, safe='')}"
    )
    page.goto(f"{hub_url}/?{query}", wait_until="load")
    page.wait_for_selector(PANEL_SHELL, timeout=20_000)
    return page


def _route_fixture_paths(page: Page, project_id: str) -> None:
    route = re.compile(rf".*/api/v1/projects/{project_id}/workspace/paths.*")
    page.route(route, lambda r: r.fulfill(json=[FIXTURE_FILE_PATH]))


def _route_fixture_file_content(page: Page, project_id: str) -> None:
    route = re.compile(rf".*/api/v1/projects/{project_id}/workspace/file.*")
    page.route(
        route,
        lambda r: r.fulfill(
            json={
                "path": FIXTURE_FILE_PATH,
                "binary": False,
                "size": len(FIXTURE_FILE_CONTENT),
                "content": FIXTURE_FILE_CONTENT,
            }
        ),
    )


def test_the_files_tab_opens_from_the_plus_affordance(
    page: Page, hub_url: str, spec_project_id: str
) -> None:
    """Task 5.1: the files tree is reachable the same way the specs index tab is — the plus
    menu, not just something wired in isolation."""
    _open(page, hub_url, spec_project_id)

    page.get_by_test_id("panel-tab-add").click()
    page.get_by_role("menuitem", name="Files").click()

    expect(page.get_by_test_id("panel-tab-files")).to_have_attribute("aria-selected", "true")
    expect(page.get_by_test_id("files-index-tab")).to_be_visible()


def test_a_search_with_no_matches_states_it_rather_than_an_empty_box(
    page: Page, hub_url: str, spec_project_id: str
) -> None:
    """An empty *result* says so rather than showing an empty box — the same "a folder view that
    hides drift lies" principle `SpecTree` follows, applied to a result with nothing in it.

    This used to assert the *workspace-is-empty* arm instead, against a fixture project that
    happened to contain no files. That coupled it to mutable fixture state: the moment the project
    gained files (2026-08-19, seeding a workspace to exercise file icons and highlighting) it
    broke, and it could never have coexisted with the four tests below that require a populated
    tree. The workspace arm moved to `filesIndexTab.test.tsx`, where it is a pure function of the
    paths prop; the search arm stays here because it is drivable whatever the fixture holds.
    """
    _open(page, hub_url, spec_project_id)

    page.get_by_test_id("panel-tab-add").click()
    page.get_by_role("menuitem", name="Files").click()
    expect(page.get_by_test_id("files-index-tab")).to_be_visible()

    page.get_by_label("Search files").fill("zzz-no-such-path-zzz")

    expect(page.get_by_text("No matching files.")).to_be_visible()


def test_selecting_a_file_from_the_tree_opens_it_and_closes_the_tree_tab(
    page: Page, hub_url: str, spec_project_id: str
) -> None:
    """Task 5.1 (tree from `GET /workspace/paths`) and 5.2 / design D8 (opening a file closes
    the `files` tab), live: a real click on a real tree row, not a store call made from the
    test."""
    _route_fixture_paths(page, spec_project_id)
    _route_fixture_file_content(page, spec_project_id)
    _open(page, hub_url, spec_project_id)

    page.get_by_test_id("panel-tab-add").click()
    page.get_by_role("menuitem", name="Files").click()
    page.get_by_test_id(f"file-tree-file-{FIXTURE_FILE_PATH}").click()

    file_tab_id = f"panel-tab-file:{FIXTURE_FILE_PATH}"
    expect(page.get_by_test_id(file_tab_id)).to_have_attribute("aria-selected", "true")
    expect(page.get_by_test_id("panel-tab-files")).not_to_be_attached()
    expect(page.get_by_test_id("file-tab-content")).to_have_text(FIXTURE_FILE_CONTENT.strip())


def test_a_missing_file_states_the_refusal_rather_than_hanging_or_blanking(
    page: Page, hub_url: str, spec_project_id: str
) -> None:
    """Task 5.3, against the real `GET /workspace/file` (not routed): this fixture project's
    workspace listing is empty, so every path 404s — itself the case worth covering live, since
    5.3 requires the tab to *state* the outcome."""
    _route_fixture_paths(page, spec_project_id)
    _open(page, hub_url, spec_project_id)

    page.get_by_test_id("panel-tab-add").click()
    page.get_by_role("menuitem", name="Files").click()
    page.get_by_test_id(f"file-tree-file-{FIXTURE_FILE_PATH}").click()

    expect(page.get_by_test_id("file-tab-error")).to_be_visible()
    expect(page.get_by_test_id("file-tab-content")).not_to_be_attached()


def test_insert_into_composer_appends_the_same_mention_the_trigger_would(
    page: Page, hub_url: str, spec_project_id: str
) -> None:
    """Task 5.4, live: pressing the button actually reaches the composer's textarea, not just
    the unit-level guarantee (`composerTrigger.test.ts`) that the two formatters agree."""
    _route_fixture_paths(page, spec_project_id)
    _route_fixture_file_content(page, spec_project_id)
    _open(page, hub_url, spec_project_id)

    page.get_by_test_id("panel-tab-add").click()
    page.get_by_role("menuitem", name="Files").click()
    page.get_by_test_id(f"file-tree-file-{FIXTURE_FILE_PATH}").click()
    page.get_by_test_id("file-tab-insert").click()

    expect(page.get_by_placeholder(re.compile("Message"))).to_have_value(f"@{FIXTURE_FILE_PATH} ")


@pytest.mark.parametrize(
    ("width", "should_overflow"),
    [(FILE_TAB_MIN_WIDTH, False), (FILE_TAB_MIN_WIDTH - 20, True)],
)
def test_file_tab_header_at_the_measured_minimum_width(
    page: Page, hub_url: str, spec_project_id: str, width: int, should_overflow: bool
) -> None:
    """Task 5.5: the measured number actually holds against a real browser's font metrics, and
    a plainly-too-narrow width actually fails the same check — a boundary asserted in only one
    direction would not catch the number being measured against the wrong element."""
    _route_fixture_paths(page, spec_project_id)
    _route_fixture_file_content(page, spec_project_id)
    _open(page, hub_url, spec_project_id)
    page.get_by_test_id("panel-tab-add").click()
    page.get_by_role("menuitem", name="Files").click()
    page.get_by_test_id(f"file-tree-file-{FIXTURE_FILE_PATH}").click()
    page.wait_for_selector('[data-testid="file-tab"]', timeout=20_000)

    pane = page.locator(DOCUMENT_PANE)
    pane.evaluate(
        "(el, w) => { el.style.setProperty('flex', `0 0 ${w}px`, 'important'); "
        "el.style.setProperty('width', `${w}px`, 'important'); "
        "el.style.setProperty('min-width', '0px', 'important'); }",
        width,
    )
    header = page.locator('[data-testid="file-tab"] > div').first
    box = header.evaluate("el => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth })")

    overflowed = box["scrollWidth"] > box["clientWidth"] + 1
    assert (
        overflowed == should_overflow
    ), f"width={width} clientWidth={box['clientWidth']} scrollWidth={box['scrollWidth']}"
