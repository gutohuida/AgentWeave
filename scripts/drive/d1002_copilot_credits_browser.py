"""Browser half of `a-copilot-run-shows-its-credits` drive tasks 7.2 and 7.6, against the served bundle.

Reads `testbed/scratch/credits-drive/state.json` (written by d1002_copilot_credits.py) and visits:
the Copilot conversation (header credits, "Worked for" credits, the checkpoint-due banner), the
Claude conversation (no credits, no banner), the Overview, Environment > Budgets, Environment >
Settings, and the Copilot agent's Context settings (the "compacts at about 80%" line). Screenshots go
to `testbed/scratch/credits-drive/shots/`. Needs AW_HUB and AW_KEY. Makes no model call.
"""

import json
import os
import pathlib
import sys
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import require_hub, require_key  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
BASE = REPO / "testbed" / "scratch" / "credits-drive"
SHOTS = BASE / "shots"
HUB = require_hub()
KEY = require_key()
S = json.loads((BASE / "state.json").read_text(encoding="utf-8"))
P = S["pid"]
SEED = (
    "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
    "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, P)
)


def lines_with(text, *needles):
    return [ln.strip() for ln in text.splitlines() if any(n in ln for n in needles)]


def visit(browser, name, params, needles=("AI credit", "credits", "compacts at about", "Checkpoint", "checkpoint")):
    page = browser.new_page(viewport={"width": 1600, "height": 1100})
    page.add_init_script(SEED)
    page.goto(HUB + "/?" + urlencode({"project": P, **params}), wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)
    text = page.inner_text("body")
    print(f"== {name}  {params}")
    for ln in lines_with(text, *needles):
        print("   ", ln[:240])
    page.close()
    return text


SHOTS.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    cop = visit(b, "01_copilot_conversation", {"agent": "cop-c", "conversation": S["t1"]["conversation_id"]})
    cl = visit(b, "02_claude_conversation", {"agent": "cl-c", "conversation": S["cl"]["conversation_id"]})
    visit(b, "03_overview", {"tab": "overview"})
    visit(b, "04_budgets", {"tab": "environment", "section": "budgets"}, ("AI credit", "credits", "cop-c", "cl-c", "Copilot", "Monthly", "token"))
    visit(b, "05_project_settings", {"tab": "environment", "section": "settings"}, ("compacts at about", "Lowered", "threshold"))
    visit(b, "06_copilot_context_settings", {"agent": "cop-c", "settings": "context"}, ("compacts at about", "fires by", "lowered"))
    visit(b, "07_claude_context_settings", {"agent": "cl-c", "settings": "context"}, ("compacts at about", "fires by", "lowered"))
    print("copilot conversation mentions AI credits:", "AI credit" in cop)
    print("claude conversation mentions AI credits:", "AI credit" in cl)
    b.close()
