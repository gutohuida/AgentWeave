"""Drive the applied ui-finesse shell and screens on the app dev server (:5187 -> Terra replica :8130).

Acceptance drive for applying the approved mock: the real app, against real replica data, renders
one 48px top bar (no header stack, no tab strip), the rail stays the project tree everywhere, and
each tab mounts its new screen. Captures every screen dark at 1440 (and light/960 for the shell)
for side-by-side comparison with `mock/shoot.py` of the same routes.

    cd hub/ui && npx vite --config vite.drive.config.mjs     # :5187, proxy to :8130
    py -3.11 scripts/drive/d1020_ui_finesse_apply.py
"""

import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
from uiharness import Judge, replica  # noqa: E402

_hub, KEY, _db = replica()
PROJECT = "proj-cd006955cbe2"
failures = []


def check(cond, what):
    print(("PASS " if cond else "FAIL ") + what)
    if not cond:
        failures.append(what)


TABS = ["overview", "tasks", "spec", "vault", "jobs", "activity"]

with Judge("finesse-apply", hub="http://localhost:5187", key=KEY) as j:
    page = j.page(PROJECT, mode="dark", width=1440)
    page.wait_for_selector('[data-testid="topbar"]', timeout=20000)
    page.wait_for_timeout(1500)

    bar = page.locator('[data-testid="topbar"]').bounding_box()
    check(bar is not None and 46 <= bar["height"] <= 50, f"one top bar, 48px tall ({bar and bar['height']})")
    check(page.get_by_text("Current project").count() == 0, "no 'Current project' eyebrow")
    check(page.locator(".project-tabs").count() == 0, "no separate tab strip")
    check(page.locator('[data-testid="rail-live-dot"]').get_attribute("data-state") == "open", "rail live dot reports an open stream")

    for tab in TABS:
        page.click(f'[data-testid="project-tab-{tab}"]')
        page.wait_for_timeout(1800)
        check(page.locator(f'[data-testid="project-tab-{tab}"]').get_attribute("aria-current") == "page", f"{tab}: tab is current")
        check(page.locator('[data-testid="rail-project-%s"]' % PROJECT).count() == 1, f"{tab}: rail still shows the project tree")
        j.shot(page, f"tab_{tab}_1440_dark")

    # Search button opens the command palette.
    page.click('[data-slot="search-button"]')
    page.wait_for_timeout(400)
    check(page.get_by_role("dialog", name="Command palette").count() == 1, "Search opens the command palette")
    j.shot(page, "palette_1440_dark")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # Project switcher menu.
    page.click('[data-testid="project-switcher"]')
    page.wait_for_timeout(400)
    check(page.get_by_role("menuitem").count() >= 1, "project switcher lists projects")
    j.shot(page, "project_menu_1440_dark")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # Settings: in-page nav, rail unchanged, top bar gear current.
    page.click('[data-testid="topbar-settings"]')
    page.wait_for_timeout(1800)
    check(page.locator('[data-testid="topbar-settings"]').get_attribute("aria-current") == "page", "settings gear is current")
    check(page.locator('[data-testid="rail-project-%s"]' % PROJECT).count() == 1, "settings: rail still shows the project tree")
    check(page.locator('[data-testid^="environment-section-"]').count() == 0, "settings: rail grew no section list")
    j.shot(page, "settings_general_1440_dark")

    # Theme toggle.
    before = page.evaluate("document.documentElement.dataset.mode")
    page.click('button[aria-label="Switch to light mode"]')
    page.wait_for_timeout(500)
    check(page.evaluate("document.documentElement.dataset.mode") == "light" and before == "dark", "theme toggle flips to light")
    j.shot(page, "settings_general_1440_light")
    page.context.close()

    # A conversation: its agent opens itself in the rail and the row is current.
    import json
    import urllib.request

    req = urllib.request.Request(
        f"http://127.0.0.1:8130/api/v1/projects/{PROJECT}/conversations?lifecycle=open",
        headers={"Authorization": "Bearer " + KEY},
    )
    conversations = json.loads(urllib.request.urlopen(req).read())["conversations"]
    conv = conversations[0]
    page = j.page(PROJECT, mode="dark", width=1440, query=f"agent={conv['agent']}&conversation={conv['id']}")
    page.wait_for_selector('[data-testid="conversation-header"]', timeout=20000)
    page.wait_for_timeout(2000)
    row = page.locator(f'[data-testid="rail-conversation-{conv["id"]}"]')
    check(row.count() == 1 and row.get_attribute("aria-current") == "page", "open conversation is visible and current in the rail")
    check(page.locator(".project-tabs").count() == 0 and page.locator('[data-testid="topbar"]').count() == 1, "conversation: one top bar")
    j.shot(page, "conversation_1440_dark")

    # Agent settings: in-page back control, rail unchanged.
    page.goto(f"http://localhost:5187/?project={PROJECT}&agent={conv['agent']}&settings=execution")
    page.wait_for_timeout(2000)
    check(page.get_by_role("button", name=f"Back to {conv['agent']}").count() >= 1, "agent settings: in-page back control")
    check(page.locator('[data-testid="rail-project-%s"]' % PROJECT).count() == 1, "agent settings: rail still shows the project tree")
    j.shot(page, "agent_settings_1440_dark")

    # Collapse the rail.
    page.click('[data-testid="rail-collapse-toggle"]')
    page.wait_for_timeout(500)
    check(page.locator('[data-testid="sidebar"]').get_attribute("data-collapsed") == "true", "rail collapses to icons")
    j.shot(page, "collapsed_1440_dark")
    page.click('[data-testid="rail-collapse-toggle"]')
    page.context.close()

    # Narrow and light shell.
    for width, mode in ((960, "dark"), (1440, "light")):
        page = j.page(PROJECT, mode=mode, width=width)
        page.wait_for_selector('[data-testid="topbar"]', timeout=20000)
        page.wait_for_timeout(1500)
        j.shot(page, f"overview_{width}_{mode}")
        page.context.close()

    print(f"{len(j.errors)} console/page errors")

print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
