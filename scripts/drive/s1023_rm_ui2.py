"""Runners & models, UI 2: the Manager runner and model menus, and the conversation a CLI rebind broke.

    AW_E2E_STATE=... py -3.11 scripts/drive/s1023_rm_ui2.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_rm_lib import PA, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


def open_menu(page, label):
    trig = page.locator(f"button[aria-label='{label}']")
    if not trig.count():
        print(f"  no trigger '{label}'")
        return None, []
    text = norm(trig.first.text_content())
    trig.first.click()
    page.wait_for_timeout(700)
    return text, [norm(o.text_content()) for o in page.locator("[role=menuitemradio]").all()]


with Judge("s1023-rm", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(PA, mode="light", query="tab=environment&section=manager")
    page.wait_for_timeout(5000)
    shown, opts = open_menu(page, "Vault distillation runner")
    print("MANAGER runner trigger reads:", repr(shown))
    print("MANAGER runner options:", opts)
    j.shot(page, "11_manager_runner_menu")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    shown, opts = open_menu(page, "Vault distillation model")
    print("MANAGER model trigger reads:", repr(shown))
    print("MANAGER model options:", opts)
    j.shot(page, "12_manager_model_menu")
    page.keyboard.press("Escape")

    page.goto(f"{e2e.hub()}/?project={PA}&agent=a-run&conversation=conv-f45e1b5b2180", wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    main = norm(page.locator("main").first.text_content())
    k = main.find("No conversation found")
    print("CONVERSATION failure text:", main[max(0, k - 200):k + 400] if k >= 0 else "(not on screen)")
    pills = [norm(b.text_content()) for b in page.locator("button[data-pill='true'], [data-pill='true']").all()]
    print("COMPOSER pills:", pills[:12])
    j.shot(page, "13_conversation_after_cli_rebind")
    print("console errors:", j.errors[:8])
