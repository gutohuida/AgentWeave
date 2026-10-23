"""Runners & models, UI: every runner choice in Chromium against the served bundle, the cannot-collaborate
line, the Add-agent model select, and a held runner's delete refusal on the Runners screen.

    AW_E2E_STATE=... py -3.11 scripts/drive/s1023_rm_ui.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_rm_lib import PA, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


def menu_options(page, label):
    """Open a MenuSelect by its aria-label and return each option's text."""
    trig = page.locator(f"button[aria-label='{label}']")
    print(f"  trigger '{label}' count:", trig.count())
    if not trig.count():
        return []
    trig.first.click()
    page.wait_for_timeout(700)
    opts = [norm(o.text_content()) for o in page.locator("[role=menuitemradio]").all()]
    return opts


with Judge("s1023-rm", hub=e2e.hub(), key=e2e.key()) as j:
    # 1. Runners screen.
    page = j.page(PA, mode="light", query="tab=environment&section=runners")
    page.wait_for_timeout(5000)
    rows = page.locator("ul[aria-label=Runners] > li")
    print("RUNNERS rows:", rows.count())
    for i in range(rows.count()):
        print("   ", norm(rows.nth(i).text_content())[:160])
    j.shot(page, "01_runners", full_page=True)
    page.locator("button[aria-label='Delete ch']").first.click()
    page.wait_for_timeout(2500)
    main = norm(page.locator("main").first.text_content())
    i = main.find("was not deleted")
    print("DELETE ch notice:", main[i - 20:i + 400] if i >= 0 else "(none)")
    j.shot(page, "02_runner_delete_refused")

    # 2. Manager section runner menu.
    page.goto(f"{e2e.hub()}/?project={PA}&tab=environment&section=manager", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    j.shot(page, "03_manager", full_page=True)
    trig = page.locator("[data-testid=manager-job-vault-distillation-runner]")
    print("MANAGER runner trigger:", trig.count(), norm(trig.first.text_content()) if trig.count() else "")
    if trig.count():
        trig.first.click()
        page.wait_for_timeout(700)
        print("MANAGER options:", [norm(o.text_content()) for o in page.locator("[role=menuitemradio]").all()])
        j.shot(page, "04_manager_runner_menu")
        page.keyboard.press("Escape")
    mtrig = page.locator("[data-testid=manager-job-vault-distillation-model]")
    print("MANAGER model trigger:", mtrig.count(), norm(mtrig.first.text_content()) if mtrig.count() else "")

    # 3. Checkpoint runner setting.
    page.goto(f"{e2e.hub()}/?project={PA}&tab=environment&section=settings", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    print("CHECKPOINT options:", menu_options(page, "Checkpoint runner"))
    j.shot(page, "05_checkpoint_runner_menu")
    page.keyboard.press("Escape")

    # 4. Agent settings, execution: runner menu + cannot-collaborate line.
    for agent in ("a-cdx", "a-run", "a-cop"):
        page.goto(f"{e2e.hub()}/?project={PA}&agent={agent}&settings=execution", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        body = norm(page.locator("body").text_content())
        for needle in ("cannot collaborate", "cannot run", "cannot run until"):
            k = body.find(needle)
            if k >= 0:
                print(f"AGENT {agent} '{needle}':", body[max(0, k - 30):k + 330])
        j.shot(page, f"06_agent_{agent}_execution", full_page=True)
        labels = [norm(b.get_attribute("aria-label")) for b in page.locator("button[aria-label]").all()]
        runner_labels = [x for x in labels if "unner" in x]
        print(f"AGENT {agent} runner-ish triggers:", runner_labels)
        if runner_labels:
            print(f"AGENT {agent} runner options:", menu_options(page, runner_labels[0]))
            j.shot(page, f"07_agent_{agent}_runner_menu")
            page.keyboard.press("Escape")

    # 5. Add-agent dialog: provider Claude, model select.
    page.goto(f"{e2e.hub()}/?project={PA}", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    add = page.locator("[aria-label='Add agent to this project'], [aria-label='Add agent']")
    print("ADD-AGENT triggers:", add.count())
    if add.count():
        add.first.click()
        page.wait_for_timeout(1500)
        dlg = page.locator("[role=dialog]")
        print("dialog:", dlg.count())
        prov = dlg.locator("[aria-label=Provider]")
        if prov.count():
            prov.first.click()
            page.wait_for_timeout(600)
            items = page.locator("[role=menuitemradio], [role=option], [role=menuitem]")
            print("PROVIDER items:", [norm(x.text_content()) for x in items.all()])
            claude = items.filter(has_text="Claude")
            if claude.count():
                claude.first.click()
                page.wait_for_timeout(600)
        sel = dlg.locator("select[aria-label=Model]")
        if sel.count():
            print("MODEL default selected:", sel.first.input_value())
            print("MODEL options:", sel.first.evaluate(
                "s => [...s.options].map(o => (o.parentElement.tagName === 'OPTGROUP' ? o.parentElement.label + ': ' : '') + o.value + ' = ' + o.textContent)"))
        j.shot(page, "08_add_agent_dialog")
    print("console errors:", j.errors[:8])
