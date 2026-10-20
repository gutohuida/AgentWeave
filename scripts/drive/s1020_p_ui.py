"""Projects x Keyboard & dialogs sweep 2026-10-20, UI (real Chromium, served bundle, :8147).

    picker -- Add project -> the in-Hub folder browser: focus on open, arrows/Enter/Backspace,
              one Escape closes one layer, the toggle closes what it opened, choose fills the
              path, a refusal on screen, the pending label while a slow path is checked
    keys   -- Ctrl+K, Add agent, the Runners page (labels, a held delete, the edit form), an
              agent's runner select, Manager/checkpoint selects, clearing instructions asks first
    delete -- the Delete-project dialog on a throwaway project with a private vault entry:
              focus, Escape, focus back on the opener, Enter on a wrong name, what is left

    py -3.11 scripts/drive/s1020_p_ui.py picker
    py -3.11 scripts/drive/s1020_p_ui.py delete <project-id> <project-name> <dir>
"""

import pathlib
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1020_p_lib import P, e2e, req  # noqa: E402
from uiharness import Judge  # noqa: E402

ACTIVE_JS = (
    "() => { const a = document.activeElement; if (!a) return null; return (a.tagName + "
    "' [' + (a.getAttribute('aria-label') || a.getAttribute('role') || '') + '] ' + "
    "(a.textContent || a.value || '').trim()).slice(0, 100) }"
)
PICKER = "[role=dialog][aria-label='Browse for a directory']"
MODAL = "[role=dialog][aria-labelledby='project-manager-title']"


def active(page):
    return page.evaluate(ACTIVE_JS)


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def open_modal(j):
    page = j.page(P, mode="light")
    page.wait_for_timeout(3500)
    page.get_by_test_id("add-project").first.click()
    page.wait_for_timeout(800)
    print("MODAL open:", page.locator(MODAL).count(), "| focus on open:", active(page))
    return page


def picker_toggle(page):
    """The control that opens the in-Hub browser, whichever the native-dialog check left."""
    native_link = page.get_by_role("button", name="Browse within the Hub instead")
    if native_link.count():
        return native_link.first, "link 'Browse within the Hub instead'"
    return page.get_by_role("button", name="Open directory browser").first, "button 'Browse…'"


def picker(j):
    print("native dialog availability:", req("GET", "/fs/native-dialog/availability"))
    page = open_modal(j)
    path_input = page.locator(MODAL).locator("input").first
    path_input.fill("C:\\Users\\huida\\Documents")
    toggle, which = picker_toggle(page)
    print("toggle is", which)
    toggle.click()
    page.wait_for_timeout(1200)
    print("PICKER open:", page.locator(PICKER).count(), "| focus:", active(page))
    j.shot(page, "01_picker_open")
    rows = page.locator(PICKER).get_by_role("option")
    print("entries:", rows.count(), "| first:", txt(rows), "| crumbs:", txt(page.locator(PICKER).locator("div").nth(1)))
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    hl = page.locator(PICKER).locator("[data-highlighted=true]")
    print("highlighted after 2x ArrowDown:", txt(hl))
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    print("after Enter, crumbs:", txt(page.locator(PICKER).locator("div").nth(1)), "| focus:", active(page))
    page.keyboard.press("Backspace")
    page.wait_for_timeout(1000)
    print("after Backspace, crumbs:", txt(page.locator(PICKER).locator("div").nth(1)))
    # One Escape closes one layer: the picker, not the modal.
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print("after Escape: picker", page.locator(PICKER).count(), "modal", page.locator(MODAL).count(), "| focus:", active(page))
    # The toggle closes what it opened.
    toggle, _ = picker_toggle(page)
    toggle.click()
    page.wait_for_timeout(800)
    print("toggle click #1 -> picker", page.locator(PICKER).count(), "| toggle text:", txt(page.locator(MODAL).get_by_role("button", name="Hide the in-Hub browser")))
    hide = page.get_by_role("button", name="Hide the in-Hub browser")
    if hide.count():
        box = hide.first.bounding_box()
        top = page.evaluate(
            "([x, y]) => { const e = document.elementFromPoint(x, y); return e && (e.tagName + ' ' + "
            "(e.textContent || '').trim().slice(0, 40) + ' in picker=' + !!e.closest(\"[aria-label='Browse for a directory']\")) }",
            [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
        )
        print("'Hide the in-Hub browser' at", box, "-> element on top there:", top)
        j.shot(page, "02_hide_link_covered")
        page.locator(MODAL).locator("h2").click()
    else:
        page.get_by_role("button", name="Open directory browser").first.click()
    page.wait_for_timeout(800)
    print("toggle #2 / outside click -> picker", page.locator(PICKER).count())
    if page.locator(PICKER).count() == 0:
        picker_toggle(page)[0].click()
        page.wait_for_timeout(800)
    # Choose fills the path.
    page.locator(PICKER).get_by_role("option").filter(has_text="aw-p-1020").first.click()
    page.wait_for_timeout(1000)
    page.locator(PICKER).get_by_role("button", name="Choose this directory").click()
    page.wait_for_timeout(500)
    print("chosen path:", repr(path_input.input_value()), "| picker", page.locator(PICKER).count(), "| focus:", active(page))
    print("preview:", txt(page.get_by_test_id("project-path-preview")))
    # A refusal on screen: a folder that does not exist.
    path_input.fill("C:\\does\\not\\exist")
    picker_toggle(page)[0].click()
    page.wait_for_timeout(1200)
    print("missing-path picker says:", txt(page.locator(PICKER).locator("[role=status]")))
    j.shot(page, "03_missing_reason")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    # Submit the missing path: what refusal reaches the modal?
    page.get_by_test_id("confirm-project-action").click()
    page.wait_for_timeout(1500)
    print("submit missing ->", txt(page.locator(MODAL).locator("[role=alert]")) or txt(page.locator(MODAL)))
    j.shot(page, "04_missing_refusal")
    # The pending label while a slow path is checked (an unreachable share takes ~21 s).
    path_input.fill("\\\\10.255.255.9\\share\\proj")
    page.get_by_test_id("confirm-project-action").click()
    page.wait_for_timeout(1500)
    print("pending label:", repr(txt(page.get_by_test_id("confirm-project-action"))))
    j.shot(page, "05_pending")
    page.wait_for_timeout(23000)
    print("after the slow refusal:", txt(page.locator(MODAL))[-300:])
    # Escape closes the modal, and focus goes back to the opener.
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print("after Escape: modal", page.locator(MODAL).count(), "| focus:", active(page))


def delete(j, pid, name, d):
    page = j.page(pid, mode="light")
    page.wait_for_timeout(3500)
    page.locator(f"[aria-label='Configure {name}']").first.click()
    page.wait_for_timeout(1500)
    page.locator("nav[aria-label='Environment sections']").get_by_text("Settings", exact=True).first.click()
    page.wait_for_timeout(1500)
    opener = page.get_by_role("button", name="Delete project…")
    opener.scroll_into_view_if_needed()
    opener.click()
    page.wait_for_timeout(600)
    dialog = page.locator("[role=dialog][aria-labelledby='delete-project-title']")
    print("dialog:", dialog.count(), "| focus on open:", active(page))
    print("text:", txt(dialog)[:600])
    j.shot(page, "10_delete_open")
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print("after Escape: dialog", dialog.count(), "| focus:", active(page))
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    print("Enter on the returned focus re-opens? dialog", dialog.count())
    if not dialog.count():
        opener.click()
        page.wait_for_timeout(400)
    page.keyboard.type(name[:-1])
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    print("Enter with a wrong name -> project still there:", req("GET", f"/projects/{pid}")[0])
    box = dialog.locator("input[type=checkbox]")
    print("remove-private checkbox:", box.count(), "checked:", box.first.is_checked() if box.count() else None)
    page.keyboard.type(name[-1])
    j.shot(page, "11_delete_ready")
    page.keyboard.press("Enter")
    page.wait_for_timeout(2500)
    j.shot(page, "12_after_delete")
    print("after delete GET:", req("GET", f"/projects/{pid}")[0], "| url:", page.url)
    print("page now:", txt(page.locator("main"))[:300])
    vault = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "p1020" / "vaults" / pid
    alt = pathlib.Path.home() / ".agentweave" / "hub" / "vaults" / pid
    for p in (vault, alt):
        print("private vault", p, "exists:", p.exists(), sorted(x.name for x in p.rglob("*"))[:10] if p.exists() else "")
    left = d / ".agentweave"
    print("left in the folder:", sorted(x.name for x in left.iterdir()) if left.exists() else "nothing")


def options(select):
    return [" ".join((o.text_content() or "").split()) for o in select.locator("option").all()]


def keys(j):
    runners = req("GET", f"/projects/{P}/runners")[1]
    sonnet = next(r for r in runners if r["name"] == "r-sonnet")
    print("seed: agent k-held on r-sonnet ->", req("POST", f"/projects/{P}/agents", {"name": "k-held", "runner_id": sonnet["id"]})[0])
    print("seed: instructions ->", req("PUT", f"/projects/{P}/project/instructions", {"content": "Be brief."})[0])
    page = j.page(P, mode="light")
    page.wait_for_timeout(3500)
    # Ctrl+K: the palette takes focus; one Escape closes it and focus comes back.
    page.locator("body").click(position={"x": 700, "y": 600})
    before = active(page)
    page.keyboard.press("Control+k")
    page.wait_for_timeout(500)
    print("Ctrl+K focus:", active(page))
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    print("after Escape focus:", active(page), "| before was:", before)
    # Add agent: focus on open, its model choices, Escape, focus back on the opener.
    opener = page.get_by_test_id(f"rail-add-agent-{P}")
    opener.click()
    page.wait_for_timeout(700)
    dlg = page.locator("[role=dialog][aria-labelledby='agent-create-title']")
    print("Add agent dialog:", dlg.count(), "| focus on open:", active(page))
    prov = dlg.get_by_label("Provider")
    print("provider control:", prov.count(), prov.first.evaluate("e => e.tagName") if prov.count() else "")
    model = dlg.get_by_label("Model")
    if model.count():
        print("Model options:", options(model.first))
    j.shot(page, "20_add_agent")
    page.keyboard.press("Tab")
    print("after Tab focus:", active(page))
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print("after Escape: dialog", dlg.count(), "| focus:", active(page))
    # Runners page: every label; delete a held runner (the 409 on screen); the edit form's focus.
    page.goto(f"{j.hub}/?project={P}&tab=environment&section=runners", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    main = page.locator("main")
    print("runners page text:", " ".join((main.first.text_content() or "").split())[:900])
    page.get_by_role("button", name="Delete r-sonnet").click()
    page.wait_for_timeout(1500)
    print("after Delete r-sonnet (held by k-held):", [r["name"] for r in req("GET", f"/projects/{P}/runners")[1] if r["name"] == "r-sonnet"],
          "| alert:", txt(main.locator("[role=alert]")))
    j.shot(page, "21_runner_delete_refused")
    edit = page.get_by_role("button", name="Edit r-sonnet")
    edit.click()
    page.wait_for_timeout(600)
    form = page.locator("[role=dialog][aria-labelledby='runner-form-title']")
    print("runner form:", form.count(), "| focus on open:", active(page))
    for sel in form.locator("select").all():
        print("  form select", sel.get_attribute("aria-label"), options(sel)[:12])
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print("after Escape: form", form.count(), "| focus:", active(page))
    # An agent's runner select.
    page.goto(f"{j.hub}/?project={P}&agent=k-held&settings=execution", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    sel = page.get_by_label("Runner for k-held")
    print("agent runner select:", options(sel.first) if sel.count() else "<absent>")
    print("agent page status lines:", [txt(s) for s in page.locator("[role=status]").all()][:6])
    j.shot(page, "22_agent_runner")
    # Manager and checkpoint selects.
    for section in ("manager", "settings"):
        page.goto(f"{j.hub}/?project={P}&tab=environment&section={section}", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        for s in page.locator("main select").all():
            opts = options(s)
            if any("(claude)" in o or "(copilot)" in o for o in opts):
                print(f"{section} select {s.get_attribute('aria-label')!r}:", opts[:12])
    # Instructions: clearing asks first; focus on Cancel; Enter cancels; Escape cancels.
    page.goto(f"{j.hub}/?project={P}&tab=environment&section=instructions", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    area = page.locator("main textarea").first
    print("instructions loaded:", repr(area.input_value()))
    area.fill("")
    save = page.locator("main").get_by_role("button", name="Save")
    save.first.click()
    page.wait_for_timeout(600)
    clear = page.locator("[role=dialog][aria-labelledby='clear-instructions-title']")
    print("clear dialog:", clear.count(), "| focus on open:", active(page), "| text:", txt(clear)[:300])
    j.shot(page, "23_clear_confirm")
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    print("after Enter: dialog", clear.count(), "| stored:", req("GET", f"/projects/{P}/project/instructions")[1].get("content"), "| focus:", active(page))
    save.first.click()
    page.wait_for_timeout(500)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print("after Escape: dialog", clear.count(), "| stored:", req("GET", f"/projects/{P}/project/instructions")[1].get("content"), "| focus:", active(page))


def checkpoint(j):
    """Switch the checkpoint runner from a Claude runner to a Copilot one, with a Claude alias
    stored as the checkpoint model, and save, as the operator would."""
    runners = {r["name"]: r["id"] for r in req("GET", f"/projects/{P}/runners")[1]}
    print("seed:", req("PUT", f"/projects/{P}/settings", {"checkpoint_runner_id": runners["r-haiku-id"], "checkpoint_model": "haiku"})[0])
    page = j.page(P, mode="light", query="tab=environment&section=settings")
    page.wait_for_timeout(3500)
    run_sel = page.get_by_label("Checkpoint runner").first
    model_sel = page.get_by_label("Checkpoint model").first
    shown = lambda s: s.evaluate("e => e.options[e.selectedIndex] ? e.options[e.selectedIndex].text : '<none>'")
    print("before: runner shows", repr(shown(run_sel)), "| model shows", repr(shown(model_sel)), "value", repr(model_sel.input_value()))
    run_sel.select_option(runners["r-cop"])
    page.wait_for_timeout(500)
    print("after picking r-cop: runner shows", repr(shown(run_sel)), "| model shows", repr(shown(model_sel)), "value", repr(model_sel.input_value()))
    print("model options now:", options(model_sel)[:8])
    save = page.locator("main").get_by_role("button", name="Save")
    print("save buttons:", save.count())
    save.first.click()
    page.wait_for_timeout(1500)
    s, res = req("GET", f"/projects/{P}/settings")
    print("stored after save:", res.get("checkpoint_runner_id"), res.get("checkpoint_model"))
    alerts = [txt(a) for a in page.locator("main [role=alert], main [role=status]").all()]
    print("on screen:", alerts[:6])
    j.shot(page, "30_checkpoint_switch", full_page=True)


def overview(j):
    """The Overview's Collaboration block shows live values: change two settings elsewhere and
    read the block again without a reload; then the settings page's group headings."""
    page = j.page(P, mode="light", query="tab=overview")
    page.wait_for_timeout(3500)
    block = page.locator("section").filter(has_text="Collaboration").first
    print("before:", txt(block)[:400])
    print("PUT hop_budget 9, allow_agent_jobs on:", req("PUT", f"/projects/{P}/settings", {"hop_budget": 9, "allow_agent_jobs": True})[0])
    page.wait_for_timeout(4000)
    print("after 4 s, no reload:", txt(block)[:400])
    j.shot(page, "40_overview_live")
    req("PUT", f"/projects/{P}/settings", {"hop_budget": 6, "allow_agent_jobs": False})
    page.goto(f"{j.hub}/?project={P}&tab=environment&section=settings", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    print("settings groups:", [txt(h) for h in page.get_by_test_id("settings-group-heading").all()])


phase = sys.argv[1]
with Judge(f"s1020-p-{phase}", hub=e2e.hub(), key=e2e.key()) as j:
    if phase == "picker":
        picker(j)
    elif phase == "keys":
        keys(j)
    elif phase == "checkpoint":
        checkpoint(j)
    elif phase == "overview":
        overview(j)
    elif phase == "delete":
        delete(j, sys.argv[2], sys.argv[3], pathlib.Path(sys.argv[4]))
