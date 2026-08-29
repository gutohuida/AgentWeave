"""Does the refusal reach the operator's screen?

F108's server half answers a request it will never honour with the refusal's own sentence. That is
worth nothing if the dashboard renders "Trigger failed with status 409" over it — which is exactly
what `AgentOutputPanel` did before this change, and why the UI was in scope rather than a follow-up.
A route returning the right body says nothing about whether a person can read it.

The refusal driven here is an **archived agent**. It is a pre-queue guard rather than F108's new
carrier, and that is deliberate: it is the request-level refusal reachable from the composer without
spawning a provider run. What it exercises is the half this change edited — the non-2xx branch,
`ApiError`, and `readableRefusal` — which is what decides whether the sentence reaches a person.

**Both call sites, because they are different components.** An agent with no conversations opens
`NewConversationSurface`; one with a conversation opens `AgentOutputPanel`. They had the same defect
and were fixed separately, so a run that only reached one would leave the other unverified — and the
first version of this script reached one and claimed the other.

**Order matters, and getting it wrong is why the first version of this script proved nothing.** The
panel has to be opened *before* the agent is archived: an archived agent is not offered in the
sidebar, so archiving first leaves nothing to click, and the send never happens. Open, then archive
underneath it, then send — which is also the real operator's sequence, since the archiving is
usually somebody else's doing.

Nothing here spawns an agent: the probe agent is bound to no runner.

`scripts/uishot.py` cannot do any of this — it has no credential injection and lands on the setup
modal. The session is seeded through `add_init_script` instead.

Run: AW_PROJECT=<proj> AW_KEY=<key> AW_SHOTS=<dir> py -3.11 scripts/drive/t_ui_refusal.py
"""

import json
import os
import pathlib
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8010")
KEY = os.environ["AW_KEY"]
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)
# Fresh per run, for the same reason `t_queue_attrition.py` mints one: a reused name carries the
# previous run's conversations and archived state into this one's screen.
AGENT = f"uiprobe-{int(time.time()) % 100000}"

from playwright.sync_api import sync_playwright  # noqa: E402

print(f"agent {AGENT}")
api("POST", f"/projects/{P}/agents/register", {"name": AGENT, "contact_mode": "poll"})

SEED = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(P)});
"""

failures = []

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

    def drive(surface, shot):
        """Open the agent, archive it underneath the open panel, send, read the screen."""
        # The Hub UI has no router — navigation is Zustand state, so there is no deep link. Click.
        page.get_by_text(AGENT, exact=True).first.click()
        page.wait_for_timeout(2500)
        # Archived *after* the panel is open: an archived agent is not offered in the sidebar, so
        # archiving first would leave nothing to click and the send would never happen.
        code, _ = api("POST", f"/projects/{P}/agents/{AGENT}/archive")
        print(f"  archive agent: {code}")

        box = page.query_selector("textarea") or page.query_selector("[role=textbox]")
        if box is None:
            failures.append(f"{surface}: no composer on screen")
            page.screenshot(path=str(OUT / f"{shot}-no-composer.png"), full_page=True)
            return
        box.fill("this should be refused, and the reason should be readable")
        page.get_by_role("button", name="Send message").click()
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT / f"{shot}.png"), full_page=True)

        text = page.inner_text("body")
        expected = "archived and cannot be triggered"
        print(f"  {surface}: the Hub's own sentence on screen: "
              f"{'YES' if expected in text else 'NO'}")
        if expected not in text:
            failures.append(f"{surface}: the refusal's sentence never reached the screen")
        for stale in ("Failed to send message", "Trigger failed with status"):
            if stale in text:
                failures.append(f"{surface}: the pre-F108 message is still rendered: {stale!r}")
        for node in page.query_selector_all("[role=alert]"):
            print(f"    alert: {node.inner_text()[:200]!r}")
        api("POST", f"/projects/{P}/agents/{AGENT}/unarchive")

    # An agent with no conversations lands on the new-conversation surface.
    print("NewConversationSurface (the agent has no conversation yet)")
    drive("NewConversationSurface", "ui-01-new-conversation")

    # Give it one, so the same click opens the conversation panel instead. It queues and nothing
    # spawns, because the agent has no runner bound — and then the entry has to go, because
    # `agent_lifecycle.archivable` refuses to archive an agent still holding undelivered input.
    # That refusal is correct and the setup has to respect it rather than work around it.
    code, out = api("POST", f"/projects/{P}/agent/trigger",
                    {"agent": AGENT, "message": "something to open", "session_mode": "new"})
    withdrawn, _ = api("DELETE", f"/projects/{P}/queue/entries/{out['queue_entry_id']}")
    print(f"seed a conversation: {code}, withdraw its entry: {withdrawn}")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    print("AgentOutputPanel (the agent now has a conversation)")
    drive("AgentOutputPanel", "ui-02-output-panel")

    print()
    print("console:")
    for line in console[-10:]:
        print("  " + line)
    browser.close()

print()
if failures:
    print("FAILURES:")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)
print(f"the operator reads the refusal. screenshots in {OUT.resolve()}")
