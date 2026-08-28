"""Does the refusal reach the operator's screen?

F108's server half answers a request it will never honour with the refusal's own sentence. That is
worth nothing if the dashboard renders "Trigger failed with status 409" over it — which is exactly
what `AgentOutputPanel` did before this change, and why the UI was in scope rather than a follow-up.
A route returning the right body says nothing about whether a person can read it.

The refusal driven here is an archived conversation. It is a *pre-queue* guard rather than F108's
new carrier, and that is deliberate: it is the one request-level refusal reachable from the composer
without spawning a provider run, and it exercises exactly the code path this change edited —
`postTrigger`'s non-2xx branch and `readableRefusal`. Before tonight it rendered
"Failed to send message".

Nothing here spawns an agent. The probe agent is bound to no runner, so its input queues and no
provider is ever started.

`scripts/uishot.py` cannot do any of this — it has no credential injection and lands on the setup
modal. The session is seeded through `add_init_script` instead.

Run: AW_PROJECT=<proj> AW_KEY=<key> AW_SHOTS=<dir> py -3.11 scripts/drive/t_ui_refusal.py
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8010")
KEY = os.environ["AW_KEY"]
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)
AGENT = "ui-probe"

from playwright.sync_api import sync_playwright  # noqa: E402

# ---- set the situation up through the real API, no row inserts -------------------------------
api("POST", f"/projects/{P}/agents/register", {"name": AGENT, "contact_mode": "poll"})
code, out = api("POST", f"/projects/{P}/agent/trigger",
                {"agent": AGENT, "message": "opening message", "session_mode": "new"})
conversation = out.get("conversation_id")
entry = out.get("queue_entry_id")
print(f"conversation {conversation} (trigger {code}), entry {entry}")

# The entry has to go before the conversation can be archived — archiving one that still holds
# undelivered input is refused, and rightly (`conversations.archivable`).
print(f"withdraw entry: {api('DELETE', f'/projects/{P}/queue/entries/{entry}')[0]}")
code, _ = api(
    "POST", f"/projects/{P}/agent/{AGENT}/conversations/{conversation}/archive"
)
print(f"archive conversation: {code}")

SEED = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(P)});
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.add_init_script(SEED)
    console = []
    page.on("console", lambda m: console.append(f"{m.type}: {m.text}"[:160]))
    page.on("pageerror", lambda e: console.append(f"pageerror: {e}"[:160]))

    # `networkidle` never settles: the dashboard holds an SSE stream open by design.
    page.goto(HUB, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # The Hub UI has no router — navigation is Zustand state, so there is no deep link. Click.
    page.get_by_text(AGENT, exact=True).first.click()
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT / "ui-01-agent.png"))
    print(f"opened {AGENT}")

    box = page.query_selector("textarea") or page.query_selector("[role=textbox]")
    if box is None:
        print("NO COMPOSER FOUND — screenshotting and stopping")
        page.screenshot(path=str(OUT / "ui-02-no-composer.png"), full_page=True)
    else:
        box.fill("this should be refused, and the reason should be readable")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "ui-02-typed.png"))
        send = page.get_by_role("button", name="Send message")
        send.click()
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT / "ui-03-after-send.png"), full_page=True)

        text = page.inner_text("body")
        print()
        print("Did the Hub's own sentence reach the screen?")
        for needle in ("Conversation is unavailable", "archived", "Failed to send message",
                       "Trigger failed with status"):
            print(f"  {needle!r}: {'YES' if needle in text else 'no'}")
        alerts = page.query_selector_all("[role=alert]")
        for a in alerts:
            print(f"  alert: {a.inner_text()[:200]!r}")

    print()
    print("console:")
    for line in console[-12:]:
        print("  " + line)
    browser.close()

print()
print(f"screenshots in {OUT.resolve()}")
