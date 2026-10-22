"""Reach sweep 2026-10-22, UI (Chromium, served bundle on the scratch Hub :8118):

  1. Project settings -> General -> Reach: Default permissions (pick Ask me, read back, Reset);
  2. Granted reach chips (ReachGrantsChips): the temp folder, the project folder, a typed folder,
     the access toggle, a relative folder (refused?), a host typed then Escape (kept or dropped?),
     the draft on reopening, Escape's layer, Remove -- each read back from GET /settings;
  3. the composer's Permissions pill against the roster's at-rest posture, for alpha (MCP) and
     beta (no tool server), with and without the project default.

  py -3.11 scripts/drive/s1022_rc_ui.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_rc_lib import P, e2e, req  # noqa: E402
from uiharness import Judge  # noqa: E402

OUTSIDE = str(pathlib.Path(__file__).resolve().parents[2] / "testbed" / "reach1022-outside")


def norm(s):
    return " ".join((s or "").split())


def stored():
    s = req("GET", f"projects/{P}/settings")[1]
    return json.dumps({"default": s.get("default_permission_mode"), "grants": s.get("reach_grants")})


def reach_group(page):
    return page.locator("section, div").filter(has_text="Granted reach").filter(has_text="Default permissions").last


def notices(page):
    loc = page.locator("[role=alert], [role=status], [data-sonner-toast], .aw-settings-notice")
    return [norm(loc.nth(i).text_content())[:240] for i in range(loc.count())]


def add(page, kind):
    page.get_by_role("button", name="Add", exact=True).first.click()
    page.get_by_role("menuitem", name=kind).click()
    page.wait_for_timeout(400)


def type_into(page, label, value, key="Enter"):
    box = page.get_by_role("textbox", name=label, exact=True)
    print(f"  field '{label}' opened with:", repr(box.input_value()))
    box.fill(value)
    box.press(key)
    page.wait_for_timeout(2500)


def pill(page, agent):
    page.get_by_text(agent, exact=True).first.click()
    page.wait_for_timeout(3000)
    dock = page.locator("[data-slot=composer], form").last
    text = norm(dock.text_content())
    hits = [w for w in ("Workspace only", "Ask me", "Edit files", "Full access", "Read only") if w in text]
    print(f"PILL {agent}: {hits} | roster:",
          {a["name"]: a.get("permission_mode_at_rest") for a in req("GET", f"projects/{P}/agents")[1]}[agent])
    return hits


with Judge("s1022-reach", hub=e2e.hub(), key=e2e.key()) as j:
    req("PUT", f"projects/{P}/settings", {"default_permission_mode": None, "reach_grants": None})
    page = j.page(P, mode="light", query="tab=environment&section=settings")
    page.wait_for_timeout(5000)
    print("URL", page.url)
    print("heading:", norm(page.locator("h1, h2").first.text_content()))
    page.get_by_text("Granted reach", exact=True).first.scroll_into_view_if_needed()
    j.shot(page, "01_reach_group")

    # 1. Default permissions.
    trig = page.get_by_role("button", name="Default permissions")
    print("default trigger:", norm(trig.text_content()))
    trig.click()
    page.wait_for_timeout(500)
    items = page.get_by_role("menuitemradio")
    print("options:", [norm(items.nth(i).text_content()) for i in range(items.count())])
    j.shot(page, "02_default_menu")
    page.get_by_role("menuitemradio").filter(has_text="Ask me").first.click()
    page.wait_for_timeout(2500)
    print("after Ask me:", stored(), "| notices:", notices(page), "| trigger:", norm(trig.text_content()))

    # 3a. The pill with the project default set.
    conv = j.page(P, mode="light")
    conv.wait_for_timeout(3000)
    pill(conv, "alpha")
    pill(conv, "beta")
    j.shot(conv, "03_beta_pill_project_ask")

    # 2. Chips.
    add(page, "The temp folder")
    page.wait_for_timeout(2500)
    print("temp:", stored())
    add(page, "The project folder")
    page.wait_for_timeout(2500)
    print("project:", stored())
    add(page, "A folder…")
    type_into(page, "Folder path", OUTSIDE)
    print("typed folder:", stored())
    page.locator("[data-slot=reach-access]").nth(2).click()
    page.wait_for_timeout(2500)
    print("toggled 3rd chip:", stored())
    add(page, "A folder…")
    type_into(page, "Folder path", "relative\\folder")
    print("relative folder:", stored(), "| notices:", notices(page))
    j.shot(page, "04_relative_folder")
    add(page, "A host…")
    type_into(page, "Host", "escape-me.example", key="Escape")
    print("host + Escape:", stored(), "| url:", page.url)
    add(page, "A host…")
    type_into(page, "Host", "localhost:*")
    print("host + Enter:", stored())
    add(page, "A host…")
    type_into(page, "Host", "http://bad host")
    print("bad host:", stored(), "| notices:", notices(page))
    j.shot(page, "05_bad_host")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    rm = page.get_by_role("button", name="Remove Temp folder")
    print("remove buttons:", rm.count())
    if rm.count():
        rm.first.click()
        page.wait_for_timeout(2500)
    print("removed temp:", stored())
    chips = page.locator(".aw-reach-chip")
    print("chips on screen:", [norm(chips.nth(i).text_content()) for i in range(chips.count())])
    j.shot(page, "06_chips")

    # 1b. Reset the default from its row.
    reset = page.get_by_role("button", name="Reset").first
    print("reset buttons:", page.get_by_role("button", name="Reset").count())
    try:
        reset.click(timeout=3000)
        page.wait_for_timeout(2500)
    except Exception as exc:  # noqa: BLE001
        print("reset not clickable:", str(exc)[:160])
    print("after reset:", stored(), "| trigger:", norm(trig.text_content()))

    # 3b. The pill without the project default.
    conv2 = j.page(P, mode="light")
    conv2.wait_for_timeout(3000)
    pill(conv2, "alpha")
    pill(conv2, "beta")
    j.shot(conv2, "07_beta_pill_at_rest")
    print("console errors:", j.errors[:8])
