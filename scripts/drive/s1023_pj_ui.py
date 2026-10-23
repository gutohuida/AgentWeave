"""Projects sweep 2026-10-23 -- UI drives in real Chromium against the served bundle (scratch Hub
:8116, profile pj1023). Never presses the native folder dialog (s1023_pj_native.py did, once).

    picker     -- Add project -> "Browse within the Hub instead": a typed path with a space and
                  non-ASCII, a missing path, a file, a UNC path; what each shows
    settings   -- Settings -> General: the group headings, change Hop budget, read it back
    instr      -- Instructions: edit + save; a stale tab's save over a newer write; clear asks first
    delete     -- Delete-project dialog on project B: text, focus, Tab trap, wrong case, Escape,
                  Enter; then what is on disk and where the app lands
    dead <id>  -- the settings and instructions pages for a deleted project id

    py -3.11 scripts/drive/s1023_pj_ui.py delete
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s1023_pj_lib import PA, PB, hub_and_key, req  # noqa: E402
from uiharness import Judge  # noqa: E402

HUB, KEY = hub_and_key()
ACTIVE_JS = (
    "() => { const a = document.activeElement; if (!a) return null; return (a.tagName + "
    "' [' + (a.getAttribute('aria-label') || a.getAttribute('role') || '') + '] ' + "
    "(a.textContent || a.value || '').trim()).slice(0, 80) }"
)


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def active(page):
    return page.evaluate(ACTIVE_JS)


def picker(j):
    page = j.page(PA, mode="dark")
    page.wait_for_timeout(2500)
    page.get_by_text("Add project", exact=True).first.click()
    page.wait_for_timeout(800)
    dlg = page.get_by_role("dialog").first
    path_in = dlg.locator("input").first
    for i, p in enumerate([
        "C:\\Users\\huida\\Documents\\aw-pj1023 sp ção",
        "C:\\nope\\xyz",
        "C:\\Users\\huida\\Documents\\aw-pj1023-a\\README.md",
        "\\\\localhost\\c$\\Users\\huida\\Documents",
        "C:",
    ]):
        path_in.fill(p)
        toggle = page.get_by_text("Hide the in-Hub browser", exact=True)
        if toggle.count():
            toggle.first.dispatch_event("click")
            page.wait_for_timeout(300)
        page.get_by_text("Browse within the Hub instead", exact=True).first.click()
        page.wait_for_timeout(1500)
        pk = page.get_by_role("dialog", name="Browse for a directory")
        head = pk.locator("[aria-label='Up to parent directory']")
        print(f"[{p}] picker={pk.count()} status={txt(pk.get_by_role('status'))!r}")
        print("   options:", [txt(o) for o in pk.get_by_role("option").all()[:6]],
              "| up:", head.count(), "| heading:", txt(pk.locator("p, span").first))
        print("   preview:", txt(page.get_by_test_id("project-path-preview")))
        j.shot(page, f"20_picker_{i}")
    # Choose the odd folder through the picker and read the path field back.
    path_in.fill("C:\\Users\\huida\\Documents")
    toggle = page.get_by_text("Hide the in-Hub browser", exact=True)
    if toggle.count():
        toggle.first.dispatch_event("click")
        page.wait_for_timeout(300)
    page.get_by_text("Browse within the Hub instead", exact=True).first.click()
    page.wait_for_timeout(1500)
    pk = page.get_by_role("dialog", name="Browse for a directory")
    opt = pk.get_by_role("option").filter(has_text="aw-pj1023 sp ção")
    print("odd option present:", opt.count())
    if opt.count():
        opt.first.click()
        page.wait_for_timeout(1000)
        print("after dblclick: status", repr(txt(pk.get_by_role("status"))), "options", [txt(o) for o in pk.get_by_role("option").all()[:4]])
        buttons = [txt(b) for b in pk.locator("button").all()]
        print("picker buttons:", buttons)
        j.shot(page, "21_picker_odd")
        choose = page.get_by_role("button", name="Choose this directory")
        if choose.count():
            choose.first.click()
            page.wait_for_timeout(500)
    print("path field now:", repr(path_in.input_value()))
    page.context.close()


def settings(j):
    page = j.page(PA, mode="light", query="tab=environment&section=settings")
    page.wait_for_timeout(3500)
    heads = [txt(h) for h in page.locator(".aw-settings-scroll h2, .aw-settings-scroll h3").all()]
    print("headings:", heads)
    hop = page.locator("#s-hop_budget, [id*=hop]").first
    print("hop control:", page.locator("[id*=hop]").count())
    if page.locator("[id*=hop]").count():
        hop.fill("4")
        hop.press("Tab")
        page.wait_for_timeout(1500)
    print("stored hop_budget:", req("GET", f"/projects/{PA}/settings")[1]["hop_budget"])
    print("toasts:", [txt(t) for t in page.locator("[data-sonner-toast], [role=status]").all()][:4])
    j.shot(page, "30_settings_general", full_page=True)
    ov = j.page(PA, mode="light")
    ov.wait_for_timeout(3000)
    body = " ".join((ov.locator("main").first.text_content() or "").split())
    print("overview mentions Collaboration:", "Collaboration" in body, "| hop:", "hop" in body.lower())
    ov.context.close()
    page.context.close()


def instr(j):
    req("PUT", f"/projects/{PA}/project/instructions", {"content": "v1: use tabs."})
    page = j.page(PA, mode="light", query="tab=environment&section=instructions")
    page.wait_for_timeout(3000)
    box = page.get_by_label("Project instructions")
    print("editor shows:", repr(box.input_value()))
    # Another tab (the API) writes v2; this tab never re-reads.
    req("PUT", f"/projects/{PA}/project/instructions", {"content": "v2: written elsewhere, keep this."})
    box.fill("v1: use tabs.\nv1b: added here.")
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(1500)
    print("stored after stale save:", repr(req("GET", f"/projects/{PA}/project/instructions")[1]["content"]))
    print("notices:", txt(page.locator("[role=alert]")))
    j.shot(page, "40_instr_stale_save")
    # Clear asks first.
    box.fill("")
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(800)
    dlg = page.get_by_role("alertdialog").or_(page.get_by_role("dialog"))
    print("clear dialog:", dlg.count(), repr(txt(dlg)), "| focus:", active(page))
    j.shot(page, "41_instr_clear_asks")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print("after Escape: editor", repr(box.input_value()), "stored", repr(req("GET", f"/projects/{PA}/project/instructions")[1]["content"]))
    page.context.close()


def delete(j):
    b = req("GET", f"/projects/{PB}")[1]
    b_dir = b["working_directory"]
    print("B:", PB, b_dir)
    page = j.page(PB, mode="dark", query="tab=environment&section=settings")
    misses = []
    page.on("response", lambda r: misses.append(f"{r.status} {r.request.method} {r.url}") if r.status >= 400 else None)
    page.wait_for_timeout(3500)
    print("danger zone:", txt(page.locator("[aria-label='Danger zone']")))
    page.get_by_role("button", name="Delete project…").click()
    page.wait_for_timeout(700)
    dlg = page.get_by_role("dialog").filter(has_text="to confirm")
    print("dialog:", repr(txt(dlg)))
    print("focus on open:", active(page))
    delete_btn = dlg.get_by_role("button", name="Delete project")
    print("delete enabled empty:", delete_btn.is_enabled())
    seen = []
    for _ in range(6):
        page.keyboard.press("Tab")
        seen.append(active(page))
    print("Tab cycle:", seen)
    box = dlg.get_by_label("Project name to confirm")
    box.fill(b["name"].upper())
    print("delete enabled wrong case:", delete_btn.is_enabled())
    box.fill(" " + b["name"] + " ")
    print("delete enabled padded:", delete_btn.is_enabled())
    j.shot(page, "50_delete_dialog")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print("after Escape: dialog", dlg.count(), "focus", active(page))
    page.get_by_role("button", name="Delete project…").click()
    page.wait_for_timeout(700)
    dlg = page.get_by_role("dialog").filter(has_text="to confirm")
    print("reopened box value:", repr(dlg.get_by_label("Project name to confirm").input_value()),
          "checkbox:", dlg.get_by_role("checkbox").is_checked())
    dlg.get_by_label("Project name to confirm").fill(b["name"])
    dlg.get_by_label("Project name to confirm").press("Enter")
    page.wait_for_timeout(3000)
    print("after delete: url", page.url)
    print("  dialogs:", page.get_by_role("dialog").count(), "| alerts:", [txt(a) for a in page.locator("[role=alert]").all()][:3])
    print("  toasts:", [txt(t) for t in page.locator("[data-sonner-toast]").all()][:3])
    print("  rail projects:", [txt(x) for x in page.locator("[data-testid^=rail-project-]").all()][:5])
    j.shot(page, "51_after_delete")
    page.wait_for_timeout(4000)
    print("  failed responses:", json.dumps(misses, indent=1))
    print("projects:", [p["id"] for p in req("GET", "/projects")[1]])
    print("on disk:")
    for root, dirs, files in os.walk(b_dir):
        if ".git" in root.split(os.sep):
            continue
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            print("   ", os.path.join(root, f))
    marker = os.path.join(b_dir, ".agentweave", "project.json")
    if os.path.exists(marker):
        print("  marker:", open(marker, encoding="utf-8").read().strip())
    vault = os.path.expanduser(f"~/.agentweave/hub/vaults/{PB}")
    print("  private vault exists:", os.path.exists(vault))
    print("  git worktrees:", subprocess.run(["git", "worktree", "list"], cwd=b_dir, capture_output=True, text=True).stdout.strip())
    page.context.close()


def dead(j, pid):
    for section in ("settings", "instructions"):
        page = j.page(pid, mode="light", query=f"tab=environment&section={section}")
        page.wait_for_timeout(3500)
        print(section, "url:", page.url)
        print("  alerts:", [txt(a) for a in page.locator("[role=alert]").all()][:3])
        print("  editor:", page.get_by_label("Project instructions").count(), "| selected:",
              page.evaluate("() => localStorage.getItem('agentweave-selected-project')"))
        print("  main text:", txt(page.locator("main"))[:300])
        j.shot(page, f"60_dead_{section}")
        page.context.close()


if __name__ == "__main__":
    with Judge("s1023-pj", hub=HUB, key=KEY) as judge:
        cmd = sys.argv[1]
        if cmd == "dead":
            dead(judge, sys.argv[2])
        else:
            {"picker": picker, "settings": settings, "instr": instr, "delete": delete}[cmd](judge)
        print("errors:", json.dumps(judge.errors[:6]))
