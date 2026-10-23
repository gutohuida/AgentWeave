"""Runners & models, UI 3: the runner form's refusals on screen (an over-long name), and the Edit form's
model select for a runner stored on an alias.

    AW_E2E_STATE=... py -3.11 scripts/drive/s1023_rm_ui3.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_rm_lib import PA, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


with Judge("s1023-rm", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(PA, mode="light", query="tab=environment&section=runners")
    page.wait_for_timeout(5000)
    page.get_by_role("button", name="New runner").first.click()
    page.wait_for_timeout(800)
    dlg = page.locator("[role=dialog]")
    dlg.locator("#runner-name").fill("r" * 257)
    dlg.locator("#runner-model").select_option("haiku")
    buttons = [norm(b.text_content()) for b in dlg.locator("button").all()]
    print("form buttons:", buttons)
    submit = dlg.locator("button[type=submit]")
    if not submit.count():
        submit = dlg.get_by_role("button", name="Save")
    submit.first.click()
    page.wait_for_timeout(2000)
    print("AFTER 257-char submit, dialog text:", norm(dlg.first.text_content())[:900] if dlg.count() else "(dialog closed)")
    j.shot(page, "21_runner_form_long_name")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    page.locator("button[aria-label='Edit cs']").first.click(force=True)
    page.wait_for_timeout(800)
    dlg = page.locator("[role=dialog]")
    sel = dlg.locator("#runner-model")
    print("EDIT cs model value:", sel.input_value(), "| shown:", sel.evaluate("s => s.options[s.selectedIndex].textContent"))
    print("EDIT cs model options:", sel.evaluate("s => [...s.options].map(o => o.value + ' = ' + o.textContent)"))
    j.shot(page, "22_runner_edit_alias")
    print("console errors:", j.errors[:8])
