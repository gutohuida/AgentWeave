"""Reach sweep 2026-10-23, UI (Chromium, served bundle on the scratch Hub :8113):

  1. beta (no tool server) -> agent settings -> Execution -> Permissions: pick "Ask me" through the
     menu, read the row's note and the roster's at-rest posture (F933: what the run really gets);
  2. beta's composer Permissions pill with that default;
  3. alpha's Execution page with a project host grant: the read-only "Own granted reach" chips.

  AW_P=proj-... py -3.11 scripts/drive/s1023_rc_ui.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_rc_lib import B, P, e2e, req  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


def roster(name):
    a = next(x for x in req("GET", f"{B}/agents")[1] if x["name"] == name)
    return {k: a.get(k) for k in ("default_permission_mode", "permission_mode_at_rest", "permission_mode_built_in")}


def perm_group(page):
    return page.locator("section, div").filter(has_text="Default permissions").filter(has_text="Own granted reach").last


req("PUT", f"{B}/settings", {"default_permission_mode": None, "reach_grants": {"hosts": ["example.com"], "roots": []}})
req("PATCH", f"{B}/agents/beta", {"default_permission_mode": None})
try:
    with Judge("s1023-reach", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query="agent=beta&settings=execution")
        page.wait_for_timeout(5000)
        print("URL", page.url)
        print("BEFORE:", norm(perm_group(page).text_content())[:600])
        page.get_by_role("button", name="Default permissions for beta").click()
        page.wait_for_timeout(600)
        items = page.get_by_role("menuitemradio")
        print("MENU:", [norm(items.nth(i).text_content())[:120] for i in range(items.count())])
        items.filter(has_text="Ask me").first.click()
        page.wait_for_timeout(3000)
        print("AFTER:", norm(perm_group(page).text_content())[:800])
        print("ROSTER beta:", roster("beta"))
        j.shot(page, "01_beta_ask_me")

        page.goto(page.url.split("?")[0] + f"?project={P}&agent=beta", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        dock = page.locator("[data-slot=composer], form").last
        text = norm(dock.text_content())
        print("PILL beta:", [w for w in ("Workspace only", "Ask me", "Edit files", "Full access", "Read only") if w in text],
              "|", text[:300])
        j.shot(page, "02_beta_pill")

        page.goto(page.url.split("?")[0] + f"?project={P}&agent=alpha&settings=execution", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        print("ALPHA:", norm(perm_group(page).text_content())[:600])
        j.shot(page, "03_alpha_reach")
        print("console errors:", j.errors[:5])
finally:
    req("PATCH", f"{B}/agents/beta", {"default_permission_mode": None})
    req("PUT", f"{B}/settings", {"reach_grants": None})
