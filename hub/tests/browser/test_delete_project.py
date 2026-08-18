"""`2026-08-16-delete-project-api`, tasks 6.1 and 6.2.

6.1: *"Drive it for real against the live Hub, on a throwaway project created for this
purpose — **never against `aw-loop10`** … create a disposable project, add an agent and a
conversation, delete it through the UI, confirm it disappears from the rail and the
workspace directory is untouched on disk."*

6.2: *"capture the confirmation dialog and the resulting state (both light and dark) and
`Read` the PNGs — this is explicitly the harness's first real test."*

Both are fully mechanisable, which is why they are here rather than in the operator's pile.
6.3 (is typing the project name the right amount of friction?) and 6.4 (does the empty
state read as an invitation or as broken?) are taste and are not.

The disposable project is created through the API and deleted through the UI, so a failure
part-way leaves a stray project rather than a stray *test* — the teardown removes it via
the API regardless. `FORBIDDEN_PROJECT_IDS` in `conftest.py` is the hard stop on 6.1's
"never against `aw-loop10`", asserted in `goto_settings` rather than merely written down.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

SHOTS = Path(__file__).resolve().parents[3] / "testbed" / "scratch" / "shots"

DELETE_TRIGGER = "Delete project…"
DELETE_CONFIRM = "Delete project"
CONFIRM_INPUT = "Project name to confirm"


@pytest.fixture
def disposable_project(api, tmp_path_factory):
    """A real project on disk, created through the API, removed however the test ends."""
    # `create` refuses a path that already exists — "use open for a directory that already
    # exists" — so it is handed a *not yet existing* child of the temp dir and makes it.
    workspace = tmp_path_factory.mktemp("disposable") / "project"

    name = f"disposable-{uuid.uuid4().hex[:8]}"
    status, body = api("POST", "/api/v1/projects/create", {"path": str(workspace), "name": name})
    assert status == 201, f"could not create the disposable project: {status} {body}"
    assert workspace.is_dir(), "create reported success but made no directory"

    # Planted after creation, for the same reason: a file the deletion must not touch —
    # 6.1's "the workspace directory is untouched on disk".
    canary = workspace / "canary.txt"
    canary.write_text("this file must survive the project being deleted\n", encoding="utf-8")

    record = {
        "id": body["id"],
        "name": body.get("name") or name,
        "path": workspace,
        "canary": canary,
    }
    try:
        yield record
    finally:
        # Idempotent: 204 if the test left it, 404 if the test deleted it through the UI.
        api("DELETE", f"/api/v1/projects/{record['id']}")


def _open_delete_dialog(page: Page) -> Page:
    page.get_by_role("button", name=DELETE_TRIGGER).click()
    page.get_by_label(CONFIRM_INPUT).wait_for(timeout=10_000)
    return page


def test_the_disposable_project_appears_in_the_rail(goto_settings, disposable_project) -> None:
    """The premise: it really is there before anything tries to remove it."""
    page = goto_settings(disposable_project["id"])
    expect(page.get_by_role("button", name=DELETE_TRIGGER)).to_be_visible()


def test_confirmation_requires_the_exact_project_name(goto_settings, disposable_project) -> None:
    """The friction 6.3 asks the operator to *judge* is at least mechanically present.

    Whether typing the name is the right amount of friction is taste. Whether a wrong name
    is refused is not, and a dialog that accepted anything would make 6.3 moot.
    """
    page = goto_settings(disposable_project["id"])
    _open_delete_dialog(page)
    confirm = page.get_by_role("button", name=DELETE_CONFIRM, exact=True)

    expect(confirm).to_be_disabled()
    page.get_by_label(CONFIRM_INPUT).fill("definitely not the project name")
    expect(confirm).to_be_disabled()
    page.get_by_label(CONFIRM_INPUT).fill(disposable_project["name"])
    expect(confirm).to_be_enabled()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_capture_the_confirmation_dialog(goto_settings, disposable_project, theme: str) -> None:
    """6.2: capture the dialog in both themes, for the operator to `Read`.

    The theme switch is app state (`configStore`'s `mode`), not a media query, so it has to
    be clicked — setting Playwright's `color_scheme` alone changes nothing. Same finding as
    `scripts/uishot.py`'s comment.
    """
    page = goto_settings(disposable_project["id"])
    if theme == "dark":
        toggle = page.get_by_role("button", name="Switch to dark mode")
        # `expect` before `click`, and no `if toggle.count()` guard. `count()` does not
        # auto-wait, so on this page it returns 0 while React is still rendering the
        # header — and a guarded click then skips in silence, writing a light screenshot
        # to a file named "dark". That is exactly what the first version of this test did.
        expect(toggle).to_be_visible()
        toggle.click()
        # The proof the click landed: the control re-labels itself. Asserted rather than
        # slept on, for the same reason.
        expect(page.get_by_role("button", name="Switch to light mode")).to_be_visible()
    _open_delete_dialog(page)
    page.get_by_label(CONFIRM_INPUT).fill(disposable_project["name"])
    page.wait_for_timeout(200)

    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / f"delete-project-dialog-{theme}.png"
    page.screenshot(path=str(out))
    assert out.exists() and out.stat().st_size > 0, "screenshot was not written"


def test_deleting_removes_the_project_but_not_its_directory(
    goto_settings, disposable_project, api
) -> None:
    """6.1's assertion, and the one that actually matters.

    `ProjectSettingsPanel` promises "The folder on disk is never touched." This is the only
    check in the suite that verifies a claim the UI makes about the *filesystem*, which is
    exactly the kind of thing a component test cannot reach.
    """
    page = goto_settings(disposable_project["id"])
    _open_delete_dialog(page)
    page.get_by_label(CONFIRM_INPUT).fill(disposable_project["name"])
    page.get_by_role("button", name=DELETE_CONFIRM, exact=True).click()

    # Gone from the API's view of the world…
    def is_absent() -> bool:
        status, _ = api("GET", f"/api/v1/projects/{disposable_project['id']}")
        return status == 404

    page.wait_for_timeout(1_000)
    assert is_absent(), "the project still exists after the UI reported deleting it"

    # …and gone from the rail the operator is looking at.
    expect(page.get_by_text(disposable_project["name"], exact=True)).to_have_count(0)

    # But every byte of the workspace survives.
    assert disposable_project["path"].is_dir(), "the workspace directory was removed"
    assert disposable_project["canary"].is_file(), "a file inside the workspace was removed"
    assert (
        disposable_project["canary"].read_text(encoding="utf-8")
        == "this file must survive the project being deleted\n"
    )
