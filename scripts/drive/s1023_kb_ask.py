"""Keyboard & dialogs, 2026-10-23: the ask_user card, keyboard only (checklist Questions row:
number keys pick options). Open the conversation that asked, read where focus is, press 2, then
Enter, and read what the Hub recorded.

    py -3.11 scripts/drive/s1023_kb_ask.py <conversation-id> [answer]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import active, fmt, open_page, q, shot  # noqa: E402

CONV = sys.argv[1]
ANSWER = len(sys.argv) > 2 and sys.argv[2] == "answer"

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = open_page(browser, f"agent=alpha&conversation={CONV}")
    page.wait_for_timeout(3000)
    print("on load:", fmt(active(page)))
    card = page.locator("[data-testid^=agent-question]").first
    print("card count:", page.locator("[data-testid^=agent-question]").count())
    shot(page, "ask_card_load")
    opts = page.evaluate(
        "() => [...document.querySelectorAll('[data-testid^=agent-question] [role=radio], [data-testid^=agent-question] button')]"
        ".map(e => [e.getAttribute('data-testid'), e.getAttribute('aria-checked') || e.getAttribute('aria-pressed') || e.getAttribute('data-selected'), (e.textContent||'').trim().slice(0,30)])"
    )
    print("options:", opts)
    # Focus: where does a keyboard user start? Tab from the body into the card.
    page.keyboard.press("2")
    page.wait_for_timeout(500)
    opts2 = page.evaluate(
        "() => [...document.querySelectorAll('[data-testid^=agent-question] [role=radio], [data-testid^=agent-question] button')]"
        ".map(e => [e.getAttribute('data-testid'), e.getAttribute('aria-checked') || e.getAttribute('aria-pressed') || e.getAttribute('data-selected'), (e.textContent||'').trim().slice(0,30)])"
    )
    print("after '2' with focus", fmt(active(page)), ":", opts2)
    comp = page.locator("textarea").first
    print("composer value:", repr(comp.input_value()) if comp.count() else None)
    shot(page, "ask_card_after_2")
    if ANSWER:
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        print("after Enter:", fmt(active(page)), "writes:", page.writes)
        shot(page, "ask_card_after_enter")
        print(q("select answer, answer_labels, answered from questions where conversation_id=?", CONV))
    print("errors:", page.errors[:4])
    browser.close()
