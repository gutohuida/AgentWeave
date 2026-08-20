"""Browser-driven verification of shipped UI changes, via Playwright against a live Hub.

These tests exist to close the *factual half* of the "Human-only verification" sections in
`openspec/changes/*/tasks.md`. Those sections mix two different kinds of claim:

  - objective ones — "a plain job's card shows no loop block", "no Approve button renders
    for a `current` capability document", "an older conversation still renders" — which a
    browser can settle definitively; and
  - taste ones — "does it *read* as tidy", "does the drawer *feel* like Jira" — which it
    cannot, and which no amount of automation should be allowed to tick.

Everything here is the first kind. Where a task contains both, the test asserts the
objective half and says so in its docstring; the operator still owns the rest. A green run
of this suite is evidence for a taste judgement, never a substitute for one.

**Opt-in by design.** CI runs `pytest tests/` from `hub/`, which would collect this
directory. There is no Hub and no browser in CI, so the whole package skips unless
`AW_HUB_URL` is set, and skips again if Playwright is absent. Never make these run by
default — a browser suite that needs a hand-seeded database is not a gate, it is a tool.

Run them:

    cd hub
    AW_HUB_URL=http://127.0.0.1:8010 py -3.11 -m pytest tests/browser -v

`AW_HUB_API_KEY` is only needed for the tests that seed or tear down state through the API;
read one out of `api_keys` in whichever database the Hub is actually serving.

`AW_HUB_PROJECT_ID` overrides the default fixture project (`proj-5e960453`, this repo's own
registration on the machine this suite was written against) — set it to point the suite's
`project_id` fixture at an equivalent project in a different database. `test_files_tab.py`,
`test_panel_shell.py`, and `test_human_only_halves.py` use a *second*, distinct fixture identity
(`proj-b44fac0c`, an operator disposable project with its own agent, conversation and spec
document) via the `spec_project_id` fixture, overridden separately with
`AW_HUB_SPEC_PROJECT_ID` — the two identities are not interchangeable, so they are not reached
by the same variable.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

# Playwright is not a dependency of the Hub and is not installed in CI. Skipping at
# collection time keeps `pytest tests/` green everywhere it currently runs.
pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from playwright.sync_api import Browser, Page, sync_playwright  # noqa: E402

# The operator keeps this project intact for parked judgement tasks; CLAUDE.md and three
# handoffs all say not to touch it. Asserted rather than merely documented, because a
# fixture that seeds into the wrong project would be discovered far too late.
FORBIDDEN_PROJECT_IDS = frozenset({"proj-ff695d96"})

#: The project holding this suite's fixtures — the AgentWeave repo's own registration.
DEFAULT_PROJECT_ID = "proj-5e960453"

#: The disposable project carrying a real agent, conversation and specification document —
#: used wherever a conversation destination is needed, since the default project above has none.
DEFAULT_SPEC_PROJECT_ID = "proj-b44fac0c"

#: `ProjectTabs` renders the active tab with `aria-current="page"`; these are its labels.
TAB_LABELS = {
    "overview": "Overview",
    "tasks": "Tasks",
    "spec": "Spec",
    "jobs": "Jobs",
    "activity": "Activity",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip this package unless a live Hub was named.

    `items` here is the WHOLE session's collected list, not just this package's — a plain
    `for item in items` marks every test in the run skipped the moment this conftest is
    merely importable, which only bites locally (CI has no Playwright, so
    `importorskip` above aborts the import before this hook is ever registered, and the
    bug was invisible there). Scope the skip to items actually under this directory.
    """
    if os.environ.get("AW_HUB_URL"):
        return
    package_dir = Path(__file__).parent
    skip = pytest.mark.skip(reason="set AW_HUB_URL to run browser tests against a live Hub")
    for item in items:
        if package_dir in Path(str(item.fspath)).resolve().parents:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def hub_url() -> str:
    url = os.environ.get("AW_HUB_URL")
    if not url:
        pytest.skip("AW_HUB_URL is not set")
    return url.rstrip("/")


@pytest.fixture(scope="session")
def api_key() -> str:
    key = os.environ.get("AW_HUB_API_KEY")
    if not key:
        pytest.skip("AW_HUB_API_KEY is not set (needed for API-seeded tests)")
    return key


@pytest.fixture(scope="session")
def project_id() -> str:
    pid = os.environ.get("AW_HUB_PROJECT_ID", DEFAULT_PROJECT_ID)
    if pid in FORBIDDEN_PROJECT_IDS:
        pytest.fail(
            f"refusing to run against {pid}: the operator keeps it intact for parked "
            "judgement tasks (CLAUDE.md)"
        )
    return pid


@pytest.fixture(scope="session")
def spec_project_id() -> str:
    pid = os.environ.get("AW_HUB_SPEC_PROJECT_ID", DEFAULT_SPEC_PROJECT_ID)
    if pid in FORBIDDEN_PROJECT_IDS:
        pytest.fail(
            f"refusing to run against {pid}: the operator keeps it intact for parked "
            "judgement tasks (CLAUDE.md)"
        )
    return pid


@pytest.fixture(scope="session")
def api(hub_url: str, api_key: str):
    """Minimal authenticated JSON client — stdlib only, matching HttpTransport's rule."""

    def call(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{hub_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode()
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, raw

    return call


@pytest.fixture(scope="session")
def hub_is_live(hub_url: str) -> None:
    """Fail loudly and early rather than letting every test time out in the browser."""
    try:
        with urllib.request.urlopen(f"{hub_url}/health", timeout=10) as response:
            if response.status != 200:
                pytest.fail(f"{hub_url}/health returned {response.status}")
    except OSError as exc:  # noqa: BLE001 — any connection failure means the same thing
        pytest.fail(f"no Hub reachable at {hub_url}: {exc}")


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture
def page(browser: Browser, hub_is_live: None) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    session = context.new_page()
    try:
        yield session
    finally:
        context.close()


@pytest.fixture
def goto(page: Page, hub_url: str, project_id: str):
    """Deep-link into a project tab.

    `useWorkspaceNavigation` drives the workspace destination straight off
    `window.location`'s search params, so a URL is a complete address for any tab —
    no click-path needed to reach one.
    """

    def navigate(tab: str, **params: str) -> Page:
        query = "&".join(
            [f"project={project_id}", f"tab={tab}", *(f"{k}={v}" for k, v in params.items())]
        )
        page.goto(f"{hub_url}/?{query}", wait_until="load")
        # Not "networkidle": the app holds an SSE connection open, so the network is
        # never idle and that wait would time out on every real page. Same reasoning as
        # scripts/uishot.py.
        #
        # Wait on `active-page-wrapper` plus the tab strip's own `aria-current`, NOT on a
        # `page-<tab>` testid. Those exist only as mocks inside
        # `hub/ui/src/__tests__/App-mount.test.tsx` — the real app never renders them, and
        # grepping `hub/ui/src` without excluding `__tests__` makes it look as though it
        # does. Production markup carries 71 testids; source-plus-mocks shows 104.
        page.wait_for_selector('[data-testid="active-page-wrapper"]', timeout=20_000)
        page.locator(f'[aria-current="page"]:has-text("{TAB_LABELS[tab]}")').first.wait_for(
            timeout=20_000
        )
        return page

    return navigate


@pytest.fixture
def goto_settings(page: Page, hub_url: str):
    """Open a project's settings panel.

    Separate from `goto` because the environment tab is the one destination that renders
    no tab strip at all — `App.tsx` gates `ProjectTabs` on `destination.tab !==
    'environment'` — so the `aria-current` wait `goto` relies on would never resolve here.

    Takes an explicit project id: the only caller deletes a disposable project it just
    created, which is deliberately *not* the session's fixture project.
    """

    def navigate(target_project_id: str) -> Page:
        if target_project_id in FORBIDDEN_PROJECT_IDS:
            pytest.fail(f"refusing to open settings for {target_project_id}")
        page.goto(
            f"{hub_url}/?project={target_project_id}&tab=environment&section=settings",
            wait_until="load",
        )
        page.wait_for_selector(
            '[data-testid="page-settings"], [role="dialog"], main', timeout=20_000
        )
        return page

    return navigate
