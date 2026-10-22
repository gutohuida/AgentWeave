"""Projects x Runners & models x Keyboard & dialogs sweep 2026-10-22, UI (Chromium, served bundle on
the scratch Hub :8119, profile pj1022).

  nav      -- Project settings: the nine sections by click, each URL, heading and testid; the
              nav's meta counts against the Hub; a deep link per section; browser Back
  runners  -- Runners: New runner dialog (focus on open, Escape, focus back to the opener), create
              with an alias, the stored model read back, the row's label; edit by keyboard only;
              a delete an agent holds (the notice), a delete with no holder (confirm or not)
  faults   -- each section with its read failing (page.route -> 500): named failure + Retry, or not

  py -3.11 scripts/drive/s1022_pj_ui.py <phase>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_pj_lib import P, e2e, req  # noqa: E402
from uiharness import Judge  # noqa: E402

SECTIONS = ["settings", "manager", "runners", "charters", "instructions", "budgets", "quality", "worktrees", "diagnostics"]
LABELS = ["General", "Manager", "Runners", "Charters", "Instructions", "Budgets", "Quality", "Worktrees", "Diagnostics"]


def norm(s):
    return " ".join((s or "").split())


def focused(page):
    return page.evaluate(
        "() => { const e = document.activeElement; if (!e) return null;"
        " return (e.tagName + ' ' + (e.getAttribute('aria-label') || e.id || '') + ' ' + (e.textContent || '').trim().slice(0, 40)); }"
    )


def nav_items(page):
    loc = page.locator("[data-slot=settings-nav-item]")
    return [norm(loc.nth(i).text_content()) for i in range(loc.count())]


def toasts(page):
    loc = page.locator("[role=alert], .aw-toast")
    return [norm(loc.nth(i).text_content())[:240] for i in range(loc.count()) if norm(loc.nth(i).text_content())]


def nav(j):
    page = j.page(P, mode="light", query="tab=environment&section=settings")
    page.wait_for_timeout(5000)
    print("URL", page.url)
    print("nav items:", nav_items(page))
    manager = req("GET", f"projects/{P}/manager/jobs")[1]
    print("hub: runners", len(req("GET", f"projects/{P}/runners")[1]), "charters",
          len(req("GET", f"projects/{P}/charters")[1]), "manager on",
          sum(1 for m in (manager if isinstance(manager, list) else manager.get("jobs", [])) if m.get("enabled")))
    for sid, label in zip(SECTIONS, LABELS):
        page.locator("[data-slot=settings-nav-item]").filter(has_text=label).first.click()
        page.wait_for_timeout(1800)
        tid = page.locator(f"[data-testid=project-settings-{sid}]").count()
        head = page.locator(".aw-settings-scroll h1, .aw-settings-scroll h2").first
        print(f"  {label:<13} url={page.url.split('?')[1]} testid={tid} heading={norm(head.text_content()) if head.count() else None}"
              f" title={page.title()!r}")
        j.shot(page, f"nav_{sid}")
    # Back walks the sections?
    page.go_back()
    page.wait_for_timeout(1500)
    print("after Back:", page.url.split("?")[1], "|", [i for i in nav_items(page)][:0],
          page.locator("[data-slot=settings-nav-item][data-active=true]").first.text_content())
    # Keyboard: Tab into the nav, Enter on an item.
    page.locator("[data-slot=settings-nav-item]").filter(has_text="Charters").first.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(1200)
    print("Enter on Charters ->", page.url.split("?")[1], "focus:", focused(page))
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    print("ArrowDown -> focus:", focused(page))
    page.keyboard.press("Tab")
    print("Tab -> focus:", focused(page))
    # Deep links.
    for sid in SECTIONS:
        p2 = j.page(P, mode="light", query=f"tab=environment&section={sid}")
        p2.wait_for_timeout(3500)
        active = p2.locator("[data-slot=settings-nav-item][data-active=true]")
        print(f"  deep {sid:<13} active={norm(active.first.text_content()) if active.count() else None}"
              f" testid={p2.locator(f'[data-testid=project-settings-{sid}]').count()}")
        p2.context.close()
    bad = j.page(P, mode="light", query="tab=environment&section=bogus")
    bad.wait_for_timeout(3500)
    act = bad.locator("[data-slot=settings-nav-item][data-active=true]")
    print("  deep bogus -> url", bad.url.split("?")[1], "active", norm(act.first.text_content()) if act.count() else None,
          "| body:", norm(bad.locator("main, #root").first.text_content())[:200])
    j.shot(bad, "nav_bogus")
    old = j.page(P, mode="light", query="tab=environment&section=permissions")
    old.wait_for_timeout(3500)
    act = old.locator("[data-slot=settings-nav-item][data-active=true]")
    print("  deep permissions (gone) -> url", old.url.split("?")[1], "active", norm(act.first.text_content()) if act.count() else None)


def runners(j):
    for r in req("GET", f"projects/{P}/runners")[1]:
        if r["name"] == "kb-haiku":
            req("DELETE", f"projects/{P}/runners/{r['id']}")
    page = j.page(P, mode="light", query="tab=environment&section=runners")
    page.wait_for_timeout(5000)
    rows = page.locator("ul[aria-label=Runners] > li")
    for i in range(rows.count()):
        print("  row:", norm(rows.nth(i).text_content()))
    j.shot(page, "runners_list")
    opener = page.get_by_role("button", name="New runner")
    opener.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    dlg = page.get_by_role("dialog")
    print("dialog open:", dlg.count(), "focus:", focused(page))
    models = page.locator("#runner-model option")
    print("model options (claude):", [norm(models.nth(i).text_content()) + "=" + models.nth(i).get_attribute("value") for i in range(models.count())])
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print("after Escape: dialog", page.get_by_role("dialog").count(), "focus:", focused(page))
    # Create by keyboard with the alias.
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    print("Enter on opener re-opened:", page.get_by_role("dialog").count())
    page.keyboard.type("kb-haiku")
    page.locator("#runner-model").select_option("haiku")
    j.shot(page, "runners_new_dialog")
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(2000)
    print("after Save: dialog", page.get_by_role("dialog").count(), "toasts", toasts(page), "focus:", focused(page))
    stored = [r for r in req("GET", f"projects/{P}/runners")[1] if r["name"] == "kb-haiku"]
    print("stored:", [(r["id"], r["model"]) for r in stored])
    for i in range(rows.count()):
        print("  row:", norm(rows.nth(i).text_content()))
    # Duplicate name, same dialog.
    opener.click()
    page.wait_for_timeout(500)
    page.keyboard.type("kb-haiku")
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(1500)
    print("duplicate name -> dialog", page.get_by_role("dialog").count(), "alert:",
          [norm(t) for t in page.get_by_role("dialog").locator("[role=alert]").all_text_contents()])
    if page.get_by_role("dialog").count():
        page.get_by_role("button", name="Cancel").click()
        page.wait_for_timeout(400)
    for r in req("GET", f"projects/{P}/runners")[1]:
        if r["name"] == "kb-haiku" and r["model"] is None:
            print("  duplicate stored (F268):", r["id"], "-> delete", req("DELETE", f"projects/{P}/runners/{r['id']}")[0])
    page.wait_for_timeout(1500)
    print("  rows after an API delete (no reload):", rows.count())
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    # A whitespace-only and a 300-character name.
    opener.click()
    page.wait_for_timeout(500)
    page.keyboard.type("   ")
    print("whitespace name -> Save enabled:", page.get_by_role("button", name="Save").is_enabled())
    page.locator("#runner-name").fill("x" * 300)
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(1500)
    print("300-char name -> dialog", page.get_by_role("dialog").count(), "alert:",
          [norm(t)[:200] for t in page.get_by_role("dialog").locator("[role=alert]").all_text_contents()])
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    # Edit by keyboard: Tab to the row's Edit button.
    kb = page.get_by_role("button", name="Edit kb-haiku")
    kb.focus()
    vis = kb.evaluate("e => getComputedStyle(e.closest('.aw-reveal')).opacity")
    print("Edit kb-haiku focused, reveal opacity:", vis)
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    print("edit dialog:", norm(page.get_by_role("dialog").locator("h2").text_content()), "focus:", focused(page),
          "cli disabled:", page.locator("#runner-cli").is_disabled(), "model:", page.locator("#runner-model").input_value())
    page.locator("#runner-model").select_option("claude-haiku-4-5-20251001")
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(1500)
    print("after edit save: focus", focused(page), "stored model",
          [r["model"] for r in req("GET", f"projects/{P}/runners")[1] if r["name"] == "kb-haiku"])
    # A delete an agent holds.
    held = [r for r in req("GET", f"projects/{P}/runners")[1] if r["name"].endswith("(e2e)")][0]
    page.get_by_role("button", name=f"Delete {held['name']}").click()
    page.wait_for_timeout(1500)
    print("held delete notices:", toasts(page)[:4])
    j.shot(page, "runners_held_delete")
    # A delete with no holder: is there a confirm step?
    page.get_by_role("button", name="Delete kb-haiku").click()
    page.wait_for_timeout(1500)
    print("unheld delete: dialog", page.get_by_role("dialog").count(), "still stored:",
          [r["name"] for r in req("GET", f"projects/{P}/runners")[1] if r["name"] == "kb-haiku"], "toasts", toasts(page)[:3])
    print("focus after delete:", focused(page))


def faults(j):
    routes = {
        "settings": "**/settings",
        "manager": "**/manager/jobs*",
        "runners": "**/runners",
        "charters": "**/charters",
        "instructions": "**/instructions*",
        "budgets": "**/accounting*",
        "quality": "**/session/sync*",
        "worktrees": "**/worktrees*",
        "diagnostics": "**/status*",
    }
    only = sys.argv[2:]
    for sid, pattern in routes.items():
        if only and sid not in only:
            continue
        page = j.page(P, mode="light", query=f"tab=environment&section={sid}")
        page.route(pattern, lambda r: r.fulfill(status=500, content_type="application/json",
                                               body=json.dumps({"detail": "drive: injected failure"})))
        page.wait_for_timeout(9000)
        body = norm(page.locator(".aw-settings-scroll").first.text_content())
        retry = page.get_by_role("button", name="Retry").count()
        print(f"  {sid:<13} retry={retry} | {body[:260]}")
        j.shot(page, f"fault_{sid}")
        page.context.close()


def general(j):
    st = req("GET", f"projects/{P}/settings")[1]
    print("hub settings:", {k: st.get(k) for k in ("hop_budget", "turn_delivery_limit", "main_branch", "checkpoint_enabled", "token_budget")})
    page = j.page(P, mode="light")
    page.wait_for_timeout(5000)
    main = " ".join(page.locator("main").first.text_content().split())
    print("Overview has a Collaboration block:", "Collaboration" in main, "| 'Hop budget' on screen:", "Hop budget" in main,
          "| 'Approval merges into':", "Approval merges into" in main)
    j.shot(page, "overview_no_collab")
    page.goto(page.url.split("?")[0] + f"?project={P}&tab=environment&section=settings", wait_until="domcontentloaded")
    page.wait_for_timeout(3500)
    # General: hop budget by keyboard.
    page.locator("[data-slot=settings-nav-item]").filter(has_text="General").first.click()
    page.wait_for_timeout(2000)
    hop = page.get_by_label("Hop budget", exact=True)
    print("hop field:", hop.count(), hop.first.input_value() if hop.count() else None)
    for value in ("9", "0", "-3", "abc", "100000"):
        hop.first.fill(value)
        hop.first.press("Enter")
        page.wait_for_timeout(1800)
        print(f"  hop={value!r}: field={hop.first.input_value()!r} stored={req('GET', f'projects/{P}/settings')[1].get('hop_budget')}"
              f" notices={toasts(page)[-2:]}")
    j.shot(page, "general_hop")
    # Main branch suggestion.
    use = page.get_by_role("button", name="Use “master”")
    if not use.count():
        use = page.get_by_role("button").filter(has_text="Use “")
    print("main-branch suggestion buttons:", [norm(t) for t in use.all_text_contents()])
    if use.count():
        use.first.click()
        page.wait_for_timeout(1800)
        print("  after Use: stored", req("GET", f"projects/{P}/settings")[1].get("main_branch"), toasts(page)[-1:])
    mb = page.get_by_label("Main branch", exact=True)
    if mb.count():
        mb.first.fill("no-such-branch")
        mb.first.press("Enter")
        page.wait_for_timeout(1800)
        print("  main_branch=no-such-branch: stored", req("GET", f"projects/{P}/settings")[1].get("main_branch"),
              "field", mb.first.input_value(), "notices", toasts(page)[-2:])
        mb.first.press("Escape")
        page.wait_for_timeout(500)
        print("  Escape on refused field -> field", mb.first.input_value(), "url", page.url.split("?")[1])
    j.shot(page, "general_branch")


def instructions(j):
    page = j.page(P, mode="light", query="tab=environment&section=instructions")
    page.wait_for_timeout(4500)
    box = page.locator(".aw-settings-scroll textarea").first
    print("editor:", box.count(), repr(box.input_value()[:80]))
    box.fill("Use type hints.\nKeep functions small.")
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(1800)
    print("saved:", repr(req("GET", f"projects/{P}/project/instructions")[1].get("content")), toasts(page)[-1:])
    box.fill("")
    save = page.get_by_role("button", name="Save")
    save.click()
    page.wait_for_timeout(800)
    dlg = page.get_by_role("dialog")
    print("clear -> dialog:", dlg.count(), norm(dlg.first.text_content())[:300] if dlg.count() else None, "focus:", focused(page))
    j.shot(page, "instructions_clear_dialog")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print("Escape -> dialog", page.get_by_role("dialog").count(), "focus:", focused(page), "editor:", repr(box.input_value()),
          "stored:", repr(req("GET", f"projects/{P}/project/instructions")[1].get("content")))
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    print("Enter after Escape -> dialog", page.get_by_role("dialog").count(), "focus:", focused(page))
    if page.get_by_role("dialog").count():
        d = page.get_by_role("dialog")
        inp = d.locator("input")
        if inp.count():
            inp.first.fill("clear")
        btns = [norm(t) for t in d.get_by_role("button").all_text_contents()]
        print("  dialog buttons:", btns)
        d.get_by_role("button").filter(has_text="Clear").last.click()
        page.wait_for_timeout(1500)
        print("  confirmed -> stored", repr(req("GET", f"projects/{P}/project/instructions")[1].get("content")), "focus", focused(page), toasts(page)[-1:])


def palette(j):
    page = j.page(P, mode="light")
    page.wait_for_timeout(4500)
    page.keyboard.press("Control+k")
    page.wait_for_timeout(700)
    print("Ctrl+K -> dialog", page.get_by_role("dialog").count(), "focus:", focused(page))
    page.keyboard.type("settings")
    page.wait_for_timeout(500)
    print("  'settings' ->", norm(page.get_by_role("dialog").first.text_content())[:200])
    page.keyboard.press("Control+a"); page.keyboard.type("runner")
    page.wait_for_timeout(500)
    print("  'runner' ->", norm(page.get_by_role("dialog").first.text_content())[:200])
    page.keyboard.press("Control+a"); page.keyboard.type("alpha")
    page.wait_for_timeout(500)
    print("  'alpha' ->", norm(page.get_by_role("dialog").first.text_content())[:200])
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print("Escape -> dialog", page.get_by_role("dialog").count(), "focus:", focused(page))
    # Runner selects: the Add agent dialog.
    add = page.get_by_role("button", name="Add agent")
    print("Add agent buttons:", add.count())
    if add.count():
        add.first.click()
        page.wait_for_timeout(1000)
        d = page.get_by_role("dialog")
        print("  dialog:", norm(d.first.locator("h2").first.text_content()) if d.count() else None, "focus:", focused(page))
        sel = d.locator("select")
        for i in range(sel.count()):
            opts = sel.nth(i).locator("option")
            print(f"  select {i}:", [norm(opts.nth(k).text_content()) for k in range(min(opts.count(), 12))])
        j.shot(page, "add_agent_dialog")
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        print("  Escape -> dialog", page.get_by_role("dialog").count(), "focus:", focused(page))


def menu_dump(page, trigger_name, label):
    trig = page.get_by_role("button", name=trigger_name, exact=True)
    if not trig.count():
        print(f"  {label}: no trigger '{trigger_name}'")
        return None
    trig.first.scroll_into_view_if_needed()
    print(f"  {label} closed trigger: {norm(trig.first.text_content())!r}")
    trig.first.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    items = page.get_by_role("menuitemradio")
    print(f"  {label} options:", [norm(items.nth(i).text_content()) for i in range(items.count())], "focus:", focused(page))
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print(f"  {label} Escape -> menu open {page.get_by_role('menuitemradio').count() > 0}, focus: {focused(page)}, url {page.url.split('?')[1]}")
    return trig.first


def pickers(j):
    for name, model in (("Twin", "claude-haiku-4-5-20251001"), ("Twin", None)):
        print("create Twin:", req("POST", f"projects/{P}/runners", {"name": name, "cli": "claude", "model": model})[0])
    page = j.page(P, mode="light", query="tab=environment&section=settings")
    page.wait_for_timeout(4500)
    menu_dump(page, "Checkpoint runner", "checkpoint runner")
    j.shot(page, "pickers_checkpoint")
    page2 = j.page(P, mode="light", query="agent=alpha&settings=execution")
    page2.wait_for_timeout(4500)
    print("agent settings url:", page2.url.split("?")[1])
    menu_dump(page2, "Runner", "agent runner")
    j.shot(page2, "pickers_agent")
    page3 = j.page(P, mode="light", query="tab=environment&section=manager")
    page3.wait_for_timeout(4500)
    trig = page3.locator("button[aria-label*=unner]")
    print("manager runner triggers:", [t.get_attribute("aria-label") for t in trig.all()][:6])
    if trig.count():
        menu_dump(page3, trig.first.get_attribute("aria-label"), "manager runner")
    j.shot(page3, "pickers_manager")
    for r in req("GET", f"projects/{P}/runners")[1]:
        if r["name"] == "Twin":
            req("DELETE", f"projects/{P}/runners/{r['id']}")


def tab_cycle(page, n=14):
    seen = []
    for _ in range(n):
        page.keyboard.press("Tab")
        f = page.evaluate("() => { const e = document.activeElement; const d = e && e.closest('[role=dialog]'); return [d ? 'in' : 'OUT', (e.getAttribute('aria-label') || e.textContent || e.tagName).trim().slice(0, 30)] }")
        seen.append(f"{f[0]}:{f[1]}")
    return seen


def dialogs(j):
    page = j.page(P, mode="light")
    page.wait_for_timeout(4500)
    opener = page.get_by_role("button", name="Add project").last
    opener.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    print("Add project -> dialog", page.get_by_role("dialog").count(), "focus:", focused(page))
    print("  Tab cycle:", tab_cycle(page))
    j.shot(page, "dialog_add_project")
    inner = page.get_by_role("button", name="Open directory browser")
    print("  in-Hub browser button:", inner.count())
    if inner.count():
        inner.first.click()
        page.wait_for_timeout(1500)
        print("  browser open; text:", norm(page.get_by_role("dialog").first.text_content())[:300])
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        print("  Escape #1 -> dialogs", page.get_by_role("dialog").count(), "browser expanded:",
              inner.first.get_attribute("aria-expanded"), "focus:", focused(page))
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print("  Escape #2 -> dialogs", page.get_by_role("dialog").count(), "focus:", focused(page))
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    print("  Enter after close -> dialogs", page.get_by_role("dialog").count())
    page.keyboard.press("Escape")
    # Delete pj-two from its own General page.
    two = [x for x in req("GET", "projects")[1] if x["name"] == "pj-two"][0]["id"]
    p2 = j.page(two, mode="light", query="tab=environment&section=settings")
    p2.wait_for_timeout(4500)
    btn = p2.get_by_role("button", name="Delete project…")
    btn.scroll_into_view_if_needed()
    btn.focus()
    p2.keyboard.press("Enter")
    p2.wait_for_timeout(700)
    d = p2.get_by_role("dialog")
    print("Delete project -> dialog", d.count(), "focus:", focused(p2), "|", norm(d.first.text_content())[:400])
    print("  Tab cycle:", tab_cycle(p2, 8))
    p2.keyboard.press("Escape")
    p2.wait_for_timeout(400)
    print("  Escape -> dialog", p2.get_by_role("dialog").count(), "focus:", focused(p2))
    p2.keyboard.press("Enter")
    p2.wait_for_timeout(600)
    d = p2.get_by_role("dialog")
    d.get_by_label("Project name to confirm").fill("pj-tw")
    print("  wrong name -> Delete enabled:", d.get_by_role("button").filter(has_text="Delete").last.is_enabled())
    d.get_by_label("Project name to confirm").fill("pj-two")
    d.get_by_role("button").filter(has_text="Delete").last.click()
    p2.wait_for_timeout(3000)
    print("  deleted -> url", p2.url.split("?")[1], "focus:", focused(p2), "toasts", toasts(p2)[-2:])
    print("  screen:", norm(p2.locator("main, #root").first.text_content())[:300])
    print("  hub projects:", [x["name"] for x in req("GET", "projects")[1]])
    j.shot(p2, "after_delete_project")


def extra(j):
    page = j.page(P, mode="light")
    page.wait_for_timeout(4500)
    page.get_by_role("button", name="Add project").last.click()
    page.wait_for_timeout(700)
    page.get_by_role("button", name="Browse within the Hub instead").click()
    page.wait_for_timeout(2000)
    d = page.get_by_role("dialog")
    print("in-Hub browser:", norm(d.first.text_content())[:500])
    print("  focus:", focused(page))
    print("  Tab cycle:", tab_cycle(page, 10))
    j.shot(page, "inhub_browser")
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print("  Escape #1 -> dialogs", page.get_by_role("dialog").count(), "focus:", focused(page),
          "| still showing browser:", "Hide the in-Hub browser" in norm(page.locator("body").text_content()))
    page.keyboard.press("Escape")
    # Codex and Copilot runner dialogs.
    page = j.page(P, mode="light", query="tab=environment&section=runners")
    page.wait_for_timeout(4500)
    page.get_by_role("button", name="New runner").click()
    page.wait_for_timeout(600)
    page.locator("#runner-name").fill("cx")
    page.locator("#runner-cli").select_option("codex")
    page.wait_for_timeout(500)
    opts = page.locator("#runner-model option")
    print("codex models:", [norm(opts.nth(i).text_content()) for i in range(opts.count())])
    print("  source line:", [norm(t) for t in page.get_by_role("dialog").locator("p").all_text_contents()])
    page.locator("#runner-cli").select_option("copilot")
    page.wait_for_timeout(500)
    page.locator("#runner-name").fill("cp-byok")
    page.get_by_role("dialog").get_by_role("checkbox").check()
    page.wait_for_timeout(400)
    page.locator("#runner-provider-key-var").fill("AW_DRIVE_NOT_SET_1022")
    opts = page.locator("#runner-model option")
    vals = [opts.nth(i).get_attribute("value") for i in range(opts.count())]
    print("copilot provider models:", vals)
    real = [v for v in vals if v]
    if real:
        page.locator("#runner-model").select_option(real[-1])
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(2000)
    d = page.get_by_role("dialog")
    print("  save -> dialog", d.count(), "alert:", [norm(t)[:300] for t in d.locator("[role=alert]").all_text_contents()] if d.count() else None)
    stored = [r for r in req("GET", f"projects/{P}/runners")[1] if r["name"] == "cp-byok"]
    print("  stored:", [(r["id"], r["model"], r["provider_config"]) for r in stored])
    j.shot(page, "copilot_byok")
    if d.count():
        page.keyboard.press("Escape")
    page.locator("#runner-key-var-x").count()
    page.wait_for_timeout(400)
    rows = page.locator("ul[aria-label=Runners] > li")
    for i in range(rows.count()):
        print("  row:", norm(rows.nth(i).text_content()))
    for r in stored:
        req("DELETE", f"projects/{P}/runners/{r['id']}")


with Judge("s1022-projects", hub=e2e.hub(), key=e2e.key()) as j:
    {"nav": nav, "runners": runners, "faults": faults, "general": general, "instructions": instructions, "palette": palette, "pickers": pickers, "dialogs": dialogs, "extra": extra}[sys.argv[1]](j)
