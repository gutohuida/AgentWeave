"""Sweep D UI tour: open each of group D's screens in Chromium, screenshot it, dump its text, and
record every console error. Usage: s1018_D_ui.py <phase>  (tour | vault | keyboard | delete)."""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import SCRATCH, mine, sc  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = SCRATCH / "ui"
OUT.mkdir(exist_ok=True)
m = mine()
HUB = f"http://127.0.0.1:{sc.CFG['port']}"
errors = []
log = []


def note(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    log.append(line)


def seed(project):
    return (
        "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s); } catch (e) {}"
        % (json.dumps(sc.CFG["key"]), json.dumps(HUB), json.dumps(project))
    )


def open_page(browser, project, width=1440, height=940):
    ctx = browser.new_context(viewport={"width": width, "height": height})
    ctx.add_init_script(seed(project))
    page = ctx.new_page()
    page.on("console", lambda msg: msg.type == "error" and errors.append(f"console: {msg.text}"))
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.goto(HUB + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    return page


def shot(page, name, full=False):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=full)
    text = page.locator("main").first.text_content() if page.locator("main").count() else ""
    (OUT / f"{name}.txt").write_text(page.locator("body").text_content() or "", encoding="utf-8")
    note("shot", path)
    return text


def click(page, testid, wait=1500):
    loc = page.get_by_test_id(testid)
    if loc.count() == 0:
        note("  MISSING testid", testid)
        return False
    loc.first.click()
    page.wait_for_timeout(wait)
    return True


def tour(browser):
    page = open_page(browser, m["pid"])
    shot(page, "00-landing")
    for tab in ("overview", "vault", "activity"):
        click(page, f"project-tab-{tab}")
        shot(page, f"10-tab-{tab}", full=True)
    for label in ("Ledger", "Logs"):
        btn = page.locator("[aria-label='Activity view'] button", has_text=label)
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(2000)
            shot(page, f"11-activity-{label}", full=True)
        else:
            note("  no Activity view button", label)
    gear = page.get_by_role("button", name="Configure aw-sweepD-1018", exact=True)
    note("  gear buttons:", gear.count())
    if gear.count() == 0:
        gear = page.locator("button[aria-label*='nvironment']")
        note("  env buttons:", gear.count())
    if gear.count():
        gear.last.click()
        page.wait_for_timeout(1500)
    for section in ("manager", "budgets", "diagnostics", "settings"):
        if click(page, f"environment-section-{section}"):
            shot(page, f"20-env-{section}", full=True)


def vault(browser):
    page = open_page(browser, m["pid"])
    click(page, "project-tab-vault")
    shot(page, "30-vault", full=True)
    for tid in ("vault-upload-open",):
        if click(page, tid):
            shot(page, "31-vault-upload-form", full=True)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
    # entry detail with facts
    entry = page.locator("[data-testid^='vault-entry-']")
    note("  entries listed:", entry.count())
    target = page.get_by_test_id(f"vault-entry-{m['doc_new']}")
    if target.count():
        target.first.click()
        page.wait_for_timeout(1500)
        shot(page, "32-vault-entry-doc-new", full=True)
    target = page.get_by_test_id(f"vault-entry-{m['src_pdf']}")
    if target.count():
        target.first.click()
        page.wait_for_timeout(2000)
        shot(page, "33-vault-entry-pdf", full=True)
        note("  pdf inline:", page.get_by_test_id("vault-file-pdf").count())
    target = page.get_by_test_id(f"vault-entry-{m['src_png']}")
    if target.count():
        target.first.click()
        page.wait_for_timeout(2000)
        shot(page, "34-vault-entry-png", full=True)
        note("  image inline:", page.get_by_test_id("vault-file-image").count())
    for name in ("Contradictions", "Reports", "Settings", "Where entries go"):
        btn = page.get_by_role("button", name=name)
        if btn.count() == 0:
            btn = page.get_by_role("tab", name=name)
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(1500)
            shot(page, f"35-vault-{name.replace(' ', '_')}", full=True)
        else:
            note("  no control named", name)


def main():
    phase = sys.argv[1]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            globals()[phase](browser)
        finally:
            browser.close()
    note(f"{len(errors)} console/page errors")
    for e in errors[:20]:
        note("  ", e[:400])
    (OUT / f"log-{phase}.txt").write_text("\n".join(log), encoding="utf-8")




def vault_actions(browser):
    page = open_page(browser, m["pid"])
    click(page, "project-tab-vault")
    rid = sc.api("GET", f"{m['base']}/vault/reports")[1]["reports"][0]["id"]
    close = page.get_by_test_id(f"vault-report-{rid}-close")
    note("  close enabled with empty note:", close.is_enabled() if close.count() else "missing")
    if close.count() and close.is_enabled():
        close.click(); page.wait_for_timeout(1500); shot(page, "40-report-close-empty")
    page.get_by_test_id(f"vault-report-{rid}-note").fill("Internal batch clients are out of scope; the guide stands as written.")
    close.click(); page.wait_for_timeout(2000)
    shot(page, "41-report-closed", full=True)
    note("  report after close:", sc.api("GET", f"{m['base']}/vault/reports")[1]["reports"][0].get("close"))
    # upload form: a PNG through the file input, dated
    click(page, "vault-upload-open")
    page.get_by_test_id("vault-upload-name").fill("Gateway screenshot via form")
    binary = page.get_by_test_id("vault-upload-binary")
    note("  binary control:", binary.count(), binary.first.evaluate("e => e.tagName + ' ' + (e.type||'')") if binary.count() else "")
    if binary.count():
        try:
            binary.first.check()
        except Exception as exc:  # noqa: BLE001
            binary.first.click()
            note("  binary click", str(exc)[:100])
    page.wait_for_timeout(500)
    f = page.get_by_test_id("vault-upload-file")
    note("  file input:", f.count())
    if f.count():
        f.set_input_files(str(SCRATCH / "note.gif"))
    page.wait_for_timeout(300)
    shot(page, "42-upload-form-filled", full=True)
    page.get_by_test_id("vault-upload-submit").click()
    page.wait_for_timeout(2500)
    shot(page, "43-upload-submitted", full=True)
    # settings: private location inside the project -> refusal on screen?
    s = page.get_by_test_id("vault-settings-location")
    note("  settings location control:", s.count())
    if s.count() == 0:
        btn = page.get_by_role("button", name="Settings")
        if btn.count():
            btn.first.click(); page.wait_for_timeout(1000)
        s = page.get_by_test_id("vault-settings-location")
    if s.count():
        s.fill(m["root"] + "\private-here")
        page.get_by_test_id("vault-settings-save").click()
        page.wait_for_timeout(1500)
        shot(page, "44-settings-refused", full=True)
        body = page.locator("body").text_content()
        note("  refusal on screen:", "inside the project" in body)


def delete(browser):
    p2 = m["p2"]
    page = open_page(browser, p2)
    gear = page.get_by_role("button", name="Configure aw-sweepD2-1018", exact=True)
    note("  gear:", gear.count())
    gear.first.click(); page.wait_for_timeout(1200)
    click(page, "environment-section-settings")
    opener = page.locator("main button, [data-testid=active-page-wrapper] button").filter(has_text="Delete project")
    note("  delete buttons:", opener.count())
    opener.first.click(); page.wait_for_timeout(800)
    active = page.evaluate("() => document.activeElement && (document.activeElement.getAttribute('aria-label') || document.activeElement.tagName)")
    note("  focus on open:", active)
    shot(page, "50-delete-dialog")
    page.keyboard.press("Escape"); page.wait_for_timeout(500)
    note("  dialog after Escape:", page.get_by_role("dialog").count())
    active = page.evaluate("() => document.activeElement && (document.activeElement.textContent || document.activeElement.tagName).slice(0,40)")
    note("  focus after Escape:", active)
    opener.first.click(); page.wait_for_timeout(800)
    box = page.get_by_label("Project name to confirm")
    box.fill("aw-sweepd2-1018")
    note("  delete enabled on wrong case:", page.get_by_role("dialog").get_by_role("button", name="Delete project").is_enabled())
    box.fill("aw-sweepD2-1018")
    box.press("Enter"); page.wait_for_timeout(2500)
    shot(page, "51-delete-shared-private")
    note("  dialog text:", (page.get_by_role("dialog").text_content() or "")[:700] if page.get_by_role("dialog").count() else "no dialog")
    note("  project still listed:", any(x["id"] == p2 for x in sc.api("GET", "/projects")[1] if isinstance(x, dict)) if isinstance(sc.api("GET", "/projects")[1], list) else sc.api("GET", "/projects")[1])


def delete2(browser):
    p2 = m["p2"]
    page = open_page(browser, p2)
    page.get_by_role("button", name="Configure aw-sweepD2-1018", exact=True).first.click(); page.wait_for_timeout(1200)
    click(page, "environment-section-settings")
    page.locator("main button, [data-testid=active-page-wrapper] button").filter(has_text="Delete project").first.click()
    page.wait_for_timeout(800)
    dlg = page.get_by_role("dialog")
    dlg.get_by_role("checkbox").uncheck()
    page.get_by_label("Project name to confirm").fill("aw-sweepD2-1018")
    dlg.get_by_role("button", name="Delete project").click()
    page.wait_for_timeout(3000)
    shot(page, "52-after-delete")
    note("  url after delete:", page.url)
    note("  dialogs:", page.get_by_role("dialog").count())


def focus_desc(page):
    return page.evaluate("""() => { const e = document.activeElement; if (!e) return 'none';
      return (e.tagName + ' ' + (e.getAttribute('data-testid') || e.getAttribute('aria-label') || (e.textContent||'').trim().slice(0,30))); }""")


def keyboard(browser):
    page = open_page(browser, m["pid"])
    page.get_by_test_id("project-tab-vault").focus()
    note("  focus before Ctrl+K:", focus_desc(page))
    page.keyboard.press("Control+k"); page.wait_for_timeout(700)
    note("  after Ctrl+K:", focus_desc(page), "dialogs:", page.get_by_role("dialog").count())
    shot(page, "60-palette")
    page.keyboard.press("Escape"); page.wait_for_timeout(500)
    note("  after Escape:", focus_desc(page), "dialogs:", page.get_by_role("dialog").count())
    # palette: type and navigate with Enter
    page.keyboard.press("Control+k"); page.wait_for_timeout(500)
    page.keyboard.type("Budgets"); page.wait_for_timeout(500)
    shot(page, "61-palette-typed")
    page.keyboard.press("Enter"); page.wait_for_timeout(1200)
    note("  after Enter on 'Budgets':", page.url, focus_desc(page), "dialogs:", page.get_by_role("dialog").count())
    # a dialog: Add agent
    page.goto(page.url.split("?")[0] + f"?project={m['pid']}&tab=overview", wait_until="domcontentloaded"); page.wait_for_timeout(2000)
    add = page.get_by_role("button", name="Add agent").last
    add.focus(); note("  opener focus:", focus_desc(page))
    page.keyboard.press("Enter"); page.wait_for_timeout(900)
    note("  dialog open:", page.get_by_role("dialog").count(), "focus:", focus_desc(page))
    shot(page, "62-add-agent-dialog")
    page.keyboard.press("Control+k"); page.wait_for_timeout(600)
    note("  Ctrl+K over dialog -> dialogs:", page.get_by_role("dialog").count(), "focus:", focus_desc(page))
    page.keyboard.press("Escape"); page.wait_for_timeout(500)
    note("  one Escape -> dialogs:", page.get_by_role("dialog").count(), "focus:", focus_desc(page))
    page.keyboard.press("Escape"); page.wait_for_timeout(500)
    note("  second Escape -> dialogs:", page.get_by_role("dialog").count(), "focus:", focus_desc(page))
    # Tab cycles inside a dialog?
    page.keyboard.press("Enter"); page.wait_for_timeout(900)
    note("  Enter on returned focus reopens:", page.get_by_role("dialog").count())
    seen = []
    for _ in range(25):
        page.keyboard.press("Tab")
        inside = page.evaluate("() => !!(document.activeElement && document.activeElement.closest('[role=dialog]'))")
        seen.append(inside)
    note("  focus stayed in dialog over 25 Tabs:", all(seen), seen.count(False))
    page.keyboard.press("Escape"); page.wait_for_timeout(400)
    # vault resolve form keyboard: Contradictions has none open now; reports none. Delete dialog Cancel focus
    note("  native dialog availability:", sc.api("GET", "/fs/native-dialog/availability"))


def dialogs(page):
    return page.evaluate("""() => [...document.querySelectorAll('[role=dialog]')].map(d => (d.getAttribute('aria-label') || d.getAttribute('aria-labelledby') || d.textContent.trim().slice(0,30)))""")


def keyboard2(browser):
    page = open_page(browser, m["pid"])
    add = page.get_by_role("button", name="Add agent").last
    add.focus(); page.keyboard.press("Enter"); page.wait_for_timeout(900)
    note("  open:", dialogs(page), focus_desc(page))
    page.keyboard.type("zed"); page.wait_for_timeout(200)
    page.keyboard.press("Control+k"); page.wait_for_timeout(700)
    note("  ctrl+k:", dialogs(page), focus_desc(page)); shot(page, "63-ctrlk-over-dialog")
    page.keyboard.press("Escape"); page.wait_for_timeout(500)
    note("  esc1:", dialogs(page), focus_desc(page)); shot(page, "64-esc1")
    page.keyboard.press("Escape"); page.wait_for_timeout(500)
    note("  esc2:", dialogs(page), focus_desc(page))


def activity_gap(browser):
    import threading
    P3 = "proj-da8de4739418"
    page = open_page(browser, m["pid"])
    click(page, "project-tab-activity")
    page.locator("[aria-label='Activity view'] button", has_text="Activity").first.click()
    page.wait_for_timeout(1500)
    # F419: events in another project
    for i in range(3):
        sc.api("POST", f"/projects/{P3}/logs", {"event_type": "other_project_marker", "agent": "zeta", "data": {"i": i}, "severity": "warn"})
    sc.api("POST", f"{m['base']}/logs", {"event_type": "this_project_marker", "agent": "alpha", "data": {"i": 0}, "severity": "warn"})
    page.wait_for_timeout(2500)
    body = page.locator("body").text_content()
    note("  F419 this project marker shown:", "this_project_marker" in body, " other project marker shown:", "other_project_marker" in body)
    shot(page, "70-activity-f419")
    # stream_gap: throttle the browser to a trickle, flood, then release
    cdp = page.context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 2000, "downloadThroughput": 200, "uploadThroughput": 200})
    pad = "y" * 800
    def post(lo, hi):
        for i in range(lo, hi):
            sc.api("POST", f"{m['base']}/logs", {"event_type": "gap_flood", "agent": "alpha", "data": {"i": i, "pad": pad}, "severity": "debug"})
    ts = [threading.Thread(target=post, args=(k * 250, (k + 1) * 250)) for k in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1})
    page.wait_for_timeout(15000)
    body = page.locator("body").text_content()
    note("  gap notice on Activity:", "were not delivered" in body or "fell behind" in body)
    shot(page, "71-activity-gap", full=True)


if __name__ == "__main__":
    main()
