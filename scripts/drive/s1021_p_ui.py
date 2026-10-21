"""Projects x Runners & models x Keyboard & dialogs sweep 2026-10-21, UI (real Chromium, served
bundle, scratch Hub :8158, profile p1021). The ui-finesse screens: settings autosave, MenuSelect.

    checkpoint -- F807 on the autosaving Checkpointing group: stored claude runner + `haiku`, pick
                  r-cop in the Checkpoint runner menu; then back to a claude runner
    empty <p>  -- F808: an agentless project's Overview offers Add agent; the dialog it opens
                  creates the agent in that project
    fault      -- F197: a failed settings read and a failed instructions read (the Hub's answer
                  replaced with a 500 in the browser) -- named failure, Retry, no savable empty editor
    tabs <p>   -- a full Tab and Shift+Tab cycle of each dialog: does focus stay inside?
    runners    -- the Runners page: labels, a held delete's 409 on screen
    palette    -- keyboard only: Ctrl+K, type, Enter; where does it go and where is focus

    AW_P=<project> py -3.11 scripts/drive/s1021_p_ui.py checkpoint
"""

import json
import os
import sys

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-p1021.json")
sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1020_p_lib import P, e2e, req  # noqa: E402

ACTIVE_JS = (
    "() => { const a = document.activeElement; if (!a) return null; return (a.tagName + "
    "' [' + (a.getAttribute('aria-label') || a.getAttribute('role') || '') + '] ' + "
    "(a.textContent || a.value || '').trim()).slice(0, 80) }"
)


def active(page):
    return page.evaluate(ACTIVE_JS)


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"

from uiharness import Judge  # noqa: E402


def menu_pick(page, label, needle):
    """Open the MenuSelect named *label* and pick the first item whose text has *needle*."""
    trig = page.get_by_label(label, exact=True).first
    trig.click()
    page.wait_for_timeout(400)
    items = page.get_by_role("menuitemradio")
    texts = [" ".join((i.text_content() or "").split()) for i in items.all()]
    print(f"  {label} menu items: {texts[:14]}")
    for i, t in enumerate(texts):
        if needle in t:
            items.nth(i).click()
            page.wait_for_timeout(1500)
            return t
    page.keyboard.press("Escape")
    return None


def trig_text(page, label):
    loc = page.get_by_label(label, exact=True)
    return txt(loc) if loc.count() else "<absent>"


def settings():
    return req("GET", f"/projects/{P}/settings")[1]


def checkpoint(j):
    runners = {r["name"]: r["id"] for r in req("GET", f"/projects/{P}/runners")[1]}
    print("seed:", req("PUT", f"/projects/{P}/settings", {"checkpoint_runner_id": runners["r-haiku-id"], "checkpoint_model": "haiku"})[0])
    page = j.page(P, mode="light", query="tab=environment&section=settings")
    page.wait_for_timeout(3500)
    print("before: runner", repr(trig_text(page, "Checkpoint runner")), "| model", repr(trig_text(page, "Checkpoint model")))
    picked = menu_pick(page, "Checkpoint runner", "r-cop")
    s = settings()
    print("picked", repr(picked), "-> stored", s.get("checkpoint_runner_id"), repr(s.get("checkpoint_model")))
    print("  model shows", repr(trig_text(page, "Checkpoint model")), "| toasts:", [txt(t) for t in page.locator("[data-sonner-toast], [role=status]").all()][:4])
    print("  refusal notice:", txt(page.get_by_test_id("settings-save-refusal")))
    j.shot(page, "01_cop_picked")
    picked = menu_pick(page, "Checkpoint model", "Haiku 4.5")
    s = settings()
    print("model", repr(picked), "-> stored", repr(s.get("checkpoint_model")))
    # Back to a claude runner: claude-haiku-4.5 (Copilot's id) is not Claude's; it should clear.
    picked = menu_pick(page, "Checkpoint runner", "r-haiku-id")
    s = settings()
    print("back to", repr(picked), "-> stored", s.get("checkpoint_runner_id"), repr(s.get("checkpoint_model")), "| model shows", repr(trig_text(page, "Checkpoint model")))
    # A claude -> claude switch keeps an alias both declare.
    menu_pick(page, "Checkpoint model", "Opus 5.5")
    print("model now", repr(settings().get("checkpoint_model")))
    picked = menu_pick(page, "Checkpoint runner", "r-sonnet")
    s = settings()
    print("claude->claude", repr(picked), "-> stored", s.get("checkpoint_runner_id"), repr(s.get("checkpoint_model")))
    print("  refusal notice:", txt(page.get_by_test_id("settings-save-refusal")))
    j.shot(page, "02_after", full_page=True)


def empty(j, project):
    page = j.page(project, mode="light", query="tab=overview")
    page.wait_for_timeout(3500)
    sec = page.locator("section[aria-labelledby='ov-agents']")
    print("agents section:", txt(sec)[:300])
    print("mentions agentweave start:", "agentweave start" in (page.locator("main").first.text_content() or ""))
    btn = sec.get_by_role("button", name="Add agent")
    print("Add agent button:", btn.count())
    j.shot(page, "10_empty")
    btn.first.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    dlg = page.locator("[role=dialog][aria-labelledby='agent-create-title']")
    print("dialog:", dlg.count(), "| focus:", active(page), "| text:", txt(dlg)[:300])
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print("after Escape: dialog", dlg.count(), "| focus back:", active(page))
    btn.first.click()
    page.wait_for_timeout(800)
    dlg.locator("input").first.fill("first")
    dlg.get_by_role("button", name="Provider").first.click()
    page.wait_for_timeout(400)
    provs = dlg.get_by_role("option")
    print("provider options:", [txt(o) for o in provs.all()])
    provs.filter(has_text="Claude").first.click()
    page.wait_for_timeout(600)
    model = dlg.get_by_label("Model")
    if model.count():
        opts = [o.get_attribute("value") for o in model.locator("option").all()]
        print("model options:", opts)
        model.select_option("claude-haiku-4-5-20251001" if "claude-haiku-4-5-20251001" in opts else opts[0])
    create = dlg.get_by_role("button", name="Create")
    print("create buttons:", [txt(b) for b in dlg.get_by_role("button").all()])
    create.first.click()
    page.wait_for_timeout(2500)
    agents = req("GET", f"/projects/{project}/agents")[1]
    print("project agents:", [(a["name"], a.get("runner_id")) for a in agents])
    others = req("GET", f"/projects/{P}/agents")[1]
    print("other project has 'first':", any(a["name"] == "first" for a in others))
    print("agents section now:", txt(sec)[:300])
    print("url:", page.url)
    j.shot(page, "11_created")


def fault(j):
    body = json.dumps({"detail": "injected: the settings store raised"})
    page = j.page(P, mode="light", query="tab=overview")
    page.route("**/api/v1/projects/*/settings", lambda r: r.fulfill(status=500, body=body, content_type="application/json") if r.request.method == "GET" else r.continue_())
    page.goto(page.url.split("?")[0] + f"?project={P}&tab=environment&section=settings", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    main = page.locator("main").first
    print("SETTINGS on a failed read:", " ".join((main.text_content() or "").split())[:600])
    retry = main.get_by_role("button", name="Retry")
    print("Retry buttons:", retry.count(), "| switches on page:", main.get_by_role("switch").count())
    j.shot(page, "20_settings_failed")
    page.unroute("**/api/v1/projects/*/settings")
    if retry.count():
        retry.first.click()
        page.wait_for_timeout(2500)
        print("after Retry:", " ".join((main.text_content() or "").split())[:300])
    # Overview reads the same settings for its Collaboration block.
    page.route("**/api/v1/projects/*/settings", lambda r: r.fulfill(status=500, body=body, content_type="application/json") if r.request.method == "GET" else r.continue_())
    page.goto(page.url.split("?")[0] + f"?project={P}&tab=overview", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    print("OVERVIEW on a failed settings read:", " ".join((main.text_content() or "").split())[:700])
    j.shot(page, "21_overview_failed")
    page.unroute("**/api/v1/projects/*/settings")
    # Instructions: a failed load must not render an empty, savable editor.
    req("PUT", f"/projects/{P}/project/instructions", {"content": "Keep it brief.\nSecond line."})
    page.route("**/project/instructions*", lambda r: r.fulfill(status=500, body=json.dumps({"detail": "injected: instructions unreadable"}), content_type="application/json") if r.request.method == "GET" else r.continue_())
    page.goto(page.url.split("?")[0] + f"?project={P}&tab=environment&section=instructions", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    print("INSTRUCTIONS on a failed read:", " ".join((main.text_content() or "").split())[:600])
    areas = main.locator("textarea")
    print("textareas:", areas.count(), [a.input_value()[:40] for a in areas.all()], "| enabled:", [a.is_enabled() for a in areas.all()])
    saves = main.get_by_role("button", name="Save")
    print("Save buttons:", saves.count(), [s.is_enabled() for s in saves.all()])
    j.shot(page, "22_instructions_failed")
    page.unroute("**/project/instructions*")
    print("stored instructions still:", repr(req("GET", f"/projects/{P}/project/instructions")[1].get("content")))


def cycle(page, scope_sel, label, presses=40):
    """Tab *presses* times, then Shift+Tab as many: count the stops and any stop outside."""
    scope = page.locator(scope_sel)
    inside = lambda: page.evaluate("s => { const d = document.querySelector(s); return !!(d && d.contains(document.activeElement)) }", scope_sel)
    first = active(page)
    seen, outside = [], []
    for direction in ("Tab", "Shift+Tab"):
        for _ in range(presses):
            page.keyboard.press(direction)
            a = active(page)
            if not inside():
                outside.append((direction, a))
            if direction == "Tab" and a not in seen:
                seen.append(a)
    print(f"[{label}] open: {scope.count()} first focus: {first!r}")
    print(f"  distinct Tab stops ({len(seen)}): {seen[:16]}")
    print(f"  stops outside the dialog: {len(outside)} {outside[:4]}")


def tabs(j, project_b):
    page = j.page(P, mode="light")
    page.wait_for_timeout(3500)
    # Add agent.
    page.get_by_test_id(f"rail-add-agent-{P}").click()
    page.wait_for_timeout(700)
    cycle(page, "[role=dialog][aria-labelledby='agent-create-title']", "Add agent")
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    # Add project, then its directory picker on top.
    page.get_by_test_id("add-project").first.click()
    page.wait_for_timeout(800)
    cycle(page, "[role=dialog][aria-labelledby='project-manager-title']", "Add project")
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print("after Escape: add-project dialog", page.locator("[role=dialog][aria-labelledby='project-manager-title']").count(), "| focus:", active(page))
    # Runner edit form.
    page.goto(f"{j.hub}/?project={P}&tab=environment&section=runners", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.get_by_role("button", name="Edit r-sonnet").first.click(force=True)
    page.wait_for_timeout(700)
    cycle(page, "[role=dialog][aria-labelledby='runner-form-title']", "Runner form")
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    # Delete project dialog (on project B; nothing is confirmed).
    page.goto(f"{j.hub}/?project={project_b}&tab=environment&section=settings", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    opener = page.get_by_role("button", name="Delete project…")
    print("delete opener:", opener.count())
    if opener.count():
        opener.first.click()
        page.wait_for_timeout(700)
        dlgs = page.locator("[role=dialog], [role=alertdialog]")
        print("dialogs open:", dlgs.count(), [d.get_attribute("aria-labelledby") or d.get_attribute("aria-label") for d in dlgs.all()])
        cycle(page, "[role=dialog]:last-of-type, [role=alertdialog]", "Delete project")
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        print("after Escape: dialogs", page.locator("[role=dialog], [role=alertdialog]").count(), "| focus:", active(page))
    print("project B still:", req("GET", f"/projects/{project_b}")[0])


def runners(j):
    page = j.page(P, mode="light", query="tab=environment&section=runners")
    page.wait_for_timeout(3500)
    main = page.locator("main").first
    print("runners page:", " ".join((main.text_content() or "").split())[:1200])
    page.get_by_role("button", name="Delete r-haiku").first.click(force=True)
    page.wait_for_timeout(1500)
    still = [r["name"] for r in req("GET", f"/projects/{P}/runners")[1] if r["name"] == "r-haiku"]
    print("after Delete r-haiku: still", still, "| alerts:", [txt(a) for a in page.locator("[role=alert]").all()][:3])
    print("toasts:", [" ".join((t.text_content() or "").split()) for t in page.locator("[data-sonner-toast], li[role=status], [data-state=open][role=status]").all()][:3])
    j.shot(page, "30_held_delete", full_page=True)


def palette(j):
    page = j.page(P, mode="light")
    page.wait_for_timeout(3500)
    page.keyboard.press("Control+k")
    page.wait_for_timeout(500)
    print("Ctrl+K focus:", active(page))
    page.keyboard.type("runners")
    page.wait_for_timeout(500)
    opts = page.get_by_role("option")
    print("options:", [" ".join((o.text_content() or "").split())[:60] for o in opts.all()][:8])
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    print("after Enter url:", page.url, "| focus:", active(page))
    j.shot(page, "40_palette_enter")


phase = sys.argv[1]
with Judge(f"s1021-p-{phase}", hub=e2e.hub(), key=e2e.key()) as j:
    if phase == "checkpoint":
        checkpoint(j)
    elif phase == "empty":
        empty(j, sys.argv[2])
    elif phase == "fault":
        fault(j)
    elif phase == "tabs":
        tabs(j, sys.argv[2])
    elif phase == "runners":
        runners(j)
    elif phase == "palette":
        palette(j)
    print("page errors:", j.errors[:6])


def extra(j):
    """The checkpoint runner reads 'Unused' on the Runners page; its delete; the palette's search."""
    s = req("GET", f"/projects/{P}/settings")[1]
    by_id = {r["id"]: r["name"] for r in req("GET", f"/projects/{P}/runners")[1]}
    name = by_id.get(s.get("checkpoint_runner_id"))
    print("checkpoint runner:", name, s.get("checkpoint_runner_id"))
    page = j.page(P, mode="light", query="tab=environment&section=runners")
    page.wait_for_timeout(3500)
    row = page.locator("li").filter(has_text=name).first
    print("its row:", txt(row))
    page.get_by_role("button", name=f"Delete {name}").first.click(force=True)
    page.wait_for_timeout(1500)
    print("after Delete: still", [r["name"] for r in req("GET", f"/projects/{P}/runners")[1] if r["name"] == name], "| alerts:", [txt(a) for a in page.locator("[role=alert]").all()][:3])
    j.shot(page, "50_checkpoint_runner_delete", full_page=True)
    page.keyboard.press("Control+k")
    page.wait_for_timeout(500)
    page.keyboard.type("a-alias")
    page.wait_for_timeout(800)
    print("palette options for a-alias:", [txt(o) for o in page.get_by_role("option").all()][:6])
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    print("after Enter url:", page.url, "| dialog open:", page.locator("[role=dialog]").count())


if phase == "extra":
    with Judge("s1021-p-extra", hub=e2e.hub(), key=e2e.key()) as j:
        extra(j)
