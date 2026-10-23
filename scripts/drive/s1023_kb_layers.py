"""Keyboard & dialogs, 2026-10-23: one Escape closes one layer, and Enter in a dialog's text field
submits at most once.

  popover  a popover/select inside a dialog (Add agent's Provider, Vault Add's Kind and Storage):
           Enter opens it, one Escape -- does the dialog survive?
  rail     the rail's agent menu and the project switcher: Escape closes, focus back on the trigger
  enter    Enter in a dialog's text field (New charter name, Add check name, Add agent name,
           Vault Add's paste-text name): how many write requests go out, and does the dialog close?

    py -3.11 scripts/drive/s1023_kb_layers.py [popover|rail|enter ...]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import P, active, dialogs, fmt, open_page, shot, step  # noqa: E402

WHICH = sys.argv[1:] or ["popover", "rail", "enter"]


def popups(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('[role=listbox],[role=menu],[data-radix-popper-content-wrapper]')].length"
    )


def tab_until(page, pred, limit=25):
    for _ in range(limit):
        a = active(page)
        if pred(a):
            return a
        page.keyboard.press("Tab")
        page.wait_for_timeout(70)
    return None


def popover_in_dialog(page, label, opener, pred):
    print(f"-- {label}")
    opener.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    a = tab_until(page, pred)
    print("  control:", fmt(a) if a else None)
    if not a:
        return
    step(page, "Enter", "Enter on control", wait=500)
    print("  popups:", popups(page), "layers:", dialogs(page))
    shot(page, f"layers_{label}_open")
    step(page, "Escape", "Escape", wait=500)
    print("  popups:", popups(page), "layers:", dialogs(page))
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)


def enter_submit(page, label, opener, fill, field_pred):
    print(f"-- {label}")
    opener.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    fill(page)
    a = tab_until(page, field_pred)
    print("  field:", fmt(a) if a else None)
    before = len(page.writes)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    print("  writes on one Enter:", page.writes[before:], "layers:", dialogs(page), "focus:", fmt(active(page)))
    shot(page, f"enter_{label}")
    for _ in range(2):
        if dialogs(page):
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    if "popover" in WHICH:
        page = open_page(browser)
        popover_in_dialog(page, "add_agent_provider", page.get_by_test_id(f"rail-add-agent-{P}"),
                          lambda a: a.get("aria") == "Provider")
        page.context.close()
        page = open_page(browser, "tab=vault")
        popover_in_dialog(page, "vault_add_kind", page.get_by_test_id("vault-upload-open"),
                          lambda a: a.get("testid") == "vault-upload-type")
        popover_in_dialog(page, "vault_storage_default", page.get_by_role("button", name="Vault storage"),
                          lambda a: a.get("testid") == "vault-settings-default")
        page.context.close()
    if "rail" in WHICH:
        page = open_page(browser)
        for tid in (f"agent-menu-{P}-alpha", "project-switcher"):
            print(f"-- {tid}")
            page.get_by_test_id(tid).focus()
            step(page, "Enter", wait=500)
            print("  popups:", popups(page), "layers:", dialogs(page))
            step(page, "Escape", wait=500)
            print("  popups:", popups(page))
        cfg = page.get_by_role("button", name="Configure aw-kb1023")
        cfg.focus()
        step(page, "Enter", "Enter on Configure", wait=900)
        print("  url:", page.url, "popups:", popups(page), "layers:", dialogs(page))
        page.context.close()
    if "enter" in WHICH:
        page = open_page(browser, "tab=environment&section=charters")

        def charter(page):
            page.keyboard.type("kbcharter")
            page.keyboard.press("Tab")
            page.keyboard.type("Body of the charter.")
            page.keyboard.press("Shift+Tab")

        enter_submit(page, "new_charter_name", page.get_by_role("button", name="New charter"), charter,
                     lambda a: a.get("id") == "charter-name")
        page.context.close()
        page = open_page(browser, "tab=environment&section=settings")

        def check(page):
            page.keyboard.type("kbcheck")
            page.keyboard.press("Tab")
            page.keyboard.type("echo ok")
            page.keyboard.press("Shift+Tab")

        enter_submit(page, "add_check_name", page.get_by_role("button", name="Add check"), check,
                     lambda a: a.get("id") == "c-name")
        page.context.close()
        page = open_page(browser)
        enter_submit(page, "add_agent_name", page.get_by_test_id(f"rail-add-agent-{P}"),
                     lambda page: page.keyboard.type("kbtwo"), lambda a: a.get("tag") == "INPUT")
        page.context.close()
        page = open_page(browser, "tab=vault")

        def vault_text(page):
            a = tab_until(page, lambda a: a.get("role") == "radio" and "text" in (a.get("text") or "").lower())
            if a is None:
                # the radio group: arrow from "Files or folders" to the paste-text option
                tab_until(page, lambda a: a.get("role") == "radio")
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(200)
            print("  mode:", fmt(active(page)))
            page.keyboard.press("Space")
            page.wait_for_timeout(300)
            name = page.get_by_test_id("vault-upload-name")
            name.focus()
            page.keyboard.type("kb-enter-probe")
            page.get_by_test_id("vault-upload-content").fill("A note typed for the Enter probe.")
            name.focus()

        enter_submit(page, "vault_add_name", page.get_by_test_id("vault-upload-open"), vault_text,
                     lambda a: a.get("testid") == "vault-upload-name")
        page.context.close()
    browser.close()
