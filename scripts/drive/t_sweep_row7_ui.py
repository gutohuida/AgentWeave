"""Row 7's screen half — what an operator sees of the inbound queue, and of the one setting
the queue router lets them write that no other surface accepts.

Two questions the API half cannot answer:

  1. `PATCH /queue/settings` carries **no upper bound** (`inbound_queue.py:48-52`, `Field(ge=1)`),
     while `ProjectSettings` — the model behind `GET`/`PUT /projects/{id}/settings` — declares
     `Field(ge=1, le=1000)` (`projects.py:76-78`) for the same four columns. Writing 1001 through
     the queue route is accepted with a 200. What does the *project settings page* then do?

  2. an agent with input waiting and no runner bound: the status route has a good sentence for it
     (*"No runner is bound to this agent. Bind one in the Hub UI before it can run."*). Does the
     operator ever read it, or does the conversation just look empty?

The project's `hop_budget` is restored on the way out, including on failure.

Run: AW_HUB=... AW_KEY=... AW_PROJECT=... AW_AGENT_UNBOUND=... AW_SHOTS=<dir>
     py -3.11 scripts/drive/t_sweep_row7_ui.py
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ["AW_KEY"]
PROJECT = os.environ["AW_PROJECT"]
UNBOUND = os.environ["AW_AGENT_UNBOUND"]
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)

A = f"/projects/{PROJECT}"
SETTINGS_URL = f"{HUB}/?project={PROJECT}&tab=environment&section=settings"

SEED = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(PROJECT)});
localStorage.setItem('aw.railView', {json.dumps("tree")});
"""

results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    shown = detail if len(detail) <= 260 else detail[:260] + f"... ({len(detail)} chars)"
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {shown}" if shown else ""))


_, ORIGINAL = api("GET", f"{A}/queue/settings")
ORIGINAL = dict(ORIGINAL)
print(f"queue settings on entry: {ORIGINAL}")


def set_hop(value):
    code, body = api("PATCH", f"{A}/queue/settings", {**ORIGINAL, "hop_budget": value})
    print(f"  PATCH /queue/settings hop_budget={value} -> {code} {body}")
    return code


# The unbound agent needs something waiting, or question 2 has no condition to look at.
code, trig = api(
    "POST",
    f"{A}/agent/trigger",
    {"agent": UNBOUND, "message": "row7: this agent has no runner and this input is waiting."},
)
CONV = trig.get("conversation_id") if isinstance(trig, dict) else None
print(f"  parked input on {UNBOUND}: {trig.get('status')!r} conv={CONV}")
CONV_URL = f"{HUB}/?project={PROJECT}&agent={UNBOUND}" + (f"&conversation={CONV}" if CONV else "")

try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        failed = []
        page.on(
            "response",
            lambda r: (
                failed.append((r.request.method, r.url.split("/api/v1")[-1], r.status))
                if r.status >= 500
                else None
            ),
        )
        page.add_init_script(SEED)

        # ---------------------------------------------------------------- control
        print("\n--- control: the settings page with an in-range hop budget")
        set_hop(ORIGINAL["hop_budget"])
        page.goto(SETTINGS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        page.screenshot(path=str(OUT / "row7-01-settings-ok.png"))
        text = page.inner_text("body")
        check("the project settings form renders at all", "Hop budget" in text, text[:200])
        check(
            "and it is not the loading skeleton",
            page.locator('[aria-label="Loading project settings"]').count() == 0,
            "skeleton present",
        )

        # ---------------------------------------------------------------- the write
        print("\n--- after PATCH /queue/settings hop_budget=1001, which the queue route accepts")
        check("the queue route accepts a hop budget of 1001", set_hop(1001) == 200)
        _, echo = api("GET", f"{A}/queue/settings")
        check("and stores it", echo.get("hop_budget") == 1001, str(echo))
        code, _ = api("GET", f"{A}/settings")
        check(
            "GET /projects/{id}/settings still answers",
            code == 200,
            f"{code} — the response model rejects the value the queue route stored",
        )
        page.goto(SETTINGS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        page.screenshot(path=str(OUT / "row7-02-settings-wedged.png"))
        text = page.inner_text("body")
        skeleton = page.locator('[aria-label="Loading project settings"]').count()
        print(f"    skeleton present: {skeleton};  body starts: {text[:120]!r}")
        check("the settings form still renders", "Hop budget" in text, text[:200])
        check(
            "or, failing that, the operator is TOLD the settings could not be loaded",
            any(
                word in text.lower()
                for word in ("could not", "failed", "unavailable", "error", "try again")
            ),
            f"skeleton={skeleton} body={text[:200]!r}",
        )
        print(f"    5xx responses the page received: {failed}")

        # ---------------------------------------------------------------- the repair
        print("\n--- can the operator undo it from the screen that broke?")
        code, body = api("PUT", f"{A}/settings", {"hop_budget": ORIGINAL["hop_budget"]})
        check(
            "PUT /projects/{id}/settings can put the value back",
            code == 200,
            f"{code} {str(body)[:140]} — the read the handler starts with rejects the stored value",
        )
        set_hop(ORIGINAL["hop_budget"])
        page.goto(SETTINGS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        text = page.inner_text("body")
        check(
            "the settings page recovers once the value is back in range",
            "Hop budget" in text,
            text[:160],
        )
        page.screenshot(path=str(OUT / "row7-03-settings-recovered.png"))

        # ---------------------------------------------------------------- queued, unlaunchable
        print("\n--- an agent with input waiting and no runner bound")
        page.goto(CONV_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        page.screenshot(path=str(OUT / "row7-04-unbound-waiting.png"))
        # Row 6's fifth lesson: scope the assertion to the panel under test. The sidebar carries
        # an Environment link literally labelled "Runners", so `inner_text("body")` matches
        # "runner" on every page in the product and reports an explanation that is not there.
        workspace = page.locator('[data-testid="conversation-workspace"]')
        text = workspace.inner_text() if workspace.count() else page.inner_text("body")
        check("the conversation panel rendered", workspace.count() > 0, "no conversation-workspace")
        st = api("GET", f"{A}/queue/{UNBOUND}/status")[1]
        print(f"    status route says: {st}")
        print(f"    conversation panel text: {text[:400]!r}")
        check(
            "the screen says the message is waiting",
            "waiting" in text.lower() or "queued" in text.lower(),
            text[:220],
        )
        check(
            "the screen gives the reason the status route already knows",
            "runner" in text.lower(),
            f"status_reason={st.get('waiting_reason')!r} screen={text[:220]!r}",
        )
        check(
            "and names the repair",
            "bind" in text.lower(),
            text[:220],
        )

        real_errors = [e for e in console_errors if "500" not in e and "Failed to load" not in e]
        print(f"\n  console errors (500s filtered, they were provoked): {real_errors[:4]}")
        browser.close()
finally:
    set_hop(ORIGINAL["hop_budget"])
    api("PATCH", f"{A}/queue/settings", ORIGINAL)
    for e in api("GET", f"{A}/queue/{UNBOUND}")[1] or []:
        if isinstance(e, dict) and e.get("state") == "queued":
            api("DELETE", f"{A}/queue/entries/{e['id']}")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{'=' * 70}\n{passed}/{len(results)} passed\n{'=' * 70}")
    for label, ok, detail in results:
        if not ok:
            print(f"  FAIL {label}  {detail[:180]}")
    print(f"screenshots in {OUT}")
