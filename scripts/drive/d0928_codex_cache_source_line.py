"""Drive step for the-codex-models-offered-are-the-ones-its-cli-lists, tasks.md 3.3.

On the trial Hub `:8010`, opens the New Runner form in project proj-cca6cd55e14e, chooses Codex,
and reads the rendered source line beneath the model select, against the served bundle (no dev
server).

Run: py -3.11 scripts/drive/d0928_codex_cache_source_line.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = "http://127.0.0.1:8010"
KEY = os.environ["AW_KEY"]
P = "proj-cca6cd55e14e"

SEED = (
    "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r})); "
    "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, P)
)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.add_init_script(SEED)

    pg.goto(HUB + f"/?project={P}&tab=environment&section=runners", wait_until="domcontentloaded")
    pg.wait_for_timeout(2000)

    pg.get_by_role("button", name="New Runner").click()
    pg.wait_for_timeout(500)

    cli_select = pg.get_by_label("CLI")
    cli_select.select_option(value="codex")
    pg.wait_for_timeout(1000)

    dialog = pg.get_by_role("dialog")
    print("== dialog text after choosing Codex ==")
    print(dialog.inner_text())

    b.close()
