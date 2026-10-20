"""Questions x Conversations & composer sweep 2026-10-20, UI (real browser, served bundle, :8146).

    ask   -- a live ask card: is it reachable by number keys on arrival, and does Send confirm?
    stale -- the left-open question (asker_waiting false) in its conversation and on Overview
    files -- composer `@` completion over /workspace/paths; the side panel's files tab for a
             huge file, a binary, a latin-1 file

    py -3.11 scripts/drive/s1020_q_ui.py ask|stale|files [question-id]
"""

import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1020_q_lib import P, e2e, q, req  # noqa: E402
from uiharness import Judge  # noqa: E402

ACTIVE_JS = (
    "() => { const a = document.activeElement; if (!a) return null; "
    "return (a.tagName + '#' + a.id + '.' + a.className).slice(0, 120) }"
)


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def active(page):
    return page.evaluate(ACTIVE_JS)


def ask(j):
    req("PATCH", f"/projects/{P}/agents/asker", {"question_timeout_seconds": 180})
    rid = e2e.cmd_turn(
        P,
        "asker",
        "Call the AgentWeave tool ask_user with the question 'Which colour for the badge?' and "
        "the options 'red', 'green' and 'blue'. Wait for the answer, then reply in one line "
        "naming it.",
        fresh=True,
        perm="workspace",
    )
    qid = None
    for _ in range(60):
        rows = q("select id from questions where created_by_run_id=? and answered=0", rid)
        if rows:
            qid = rows[0]["id"]
            break
        time.sleep(3)
    conv = q("select conversation_id from runs where id=?", rid)[0]["conversation_id"]
    print("question", qid, "conversation", conv)
    page = j.page(P, mode="light", query=f"agent=asker&conversation={conv}")
    page.wait_for_timeout(5000)
    card = page.get_by_test_id(f"agent-question-{qid}")
    print("CARD present:", card.count(), "| text:", txt(card)[:300])
    print("FOCUS on arrival:", active(page))
    j.shot(page, "01_card")
    page.keyboard.press("2")
    page.wait_for_timeout(500)
    opts = [card.get_by_test_id(f"agent-question-option-{qid}-{i}") for i in range(3)]
    print("AFTER '2' selected:", [o.get_attribute("data-selected") for o in opts])
    ta = page.locator("textarea.composer-textarea")
    print("composer value after '2':", repr(ta.first.input_value()) if ta.count() else "<none>")
    print("FOCUS after '2':", active(page))
    if not any(o.get_attribute("data-selected") for o in opts):
        # The composer held focus, so the key went into it: click out and retry.
        ta.first.fill("")
        card.locator("p").first.click()
        page.keyboard.press("2")
        page.wait_for_timeout(500)
        print("AFTER click-out + '2':", [o.get_attribute("data-selected") for o in opts])
    send = page.get_by_role("button", name="Send message")
    print("SEND enabled:", send.first.is_enabled() if send.count() else "<none>")
    j.shot(page, "02_selected")
    send.first.click()
    page.wait_for_timeout(3000)
    print("ROW:", q("select answered, answer, answer_labels from questions where id=?", qid))
    print("run:", e2e.wait_for(rid, 4))
    e2e.dump_turn(rid, tools=False)
    page.wait_for_timeout(2000)
    j.shot(page, "03_after")


def stale(j, qid):
    conv = q("select conversation_id from questions where id=?", qid)[0]["conversation_id"]
    page = j.page(P, mode="light", query=f"agent=asker&conversation={conv}")
    page.wait_for_timeout(5000)
    card = page.get_by_test_id(f"agent-question-{qid}")
    print("CARD:", card.count(), txt(card)[:300])
    st = page.get_by_test_id("agent-question-stale")
    print("STALE chip:", txt(st), "| title:", st.first.get_attribute("title") if st.count() else None)
    print("placeholder:", page.locator("textarea.composer-textarea").first.get_attribute("placeholder"))
    j.shot(page, "01_conv_stale")
    page = j.page(P, mode="light", query="tab=overview")
    page.wait_for_timeout(5000)
    body = txt(page.locator("body"))
    print("OVERVIEW 'Blocking':", "Blocking" in body, "| 'no longer waiting':", "no longer waiting" in body)
    print("question-stale:", txt(page.get_by_test_id(f"question-stale-{qid}")))
    j.shot(page, "02_overview", full_page=True)


def files(j):
    conv = q("select conversation_id from runs where agent='asker' order by started_at desc limit 1")[0][
        "conversation_id"
    ]
    page = j.page(P, mode="light", query=f"agent=asker&conversation={conv}")
    page.wait_for_timeout(5000)
    ta = page.locator("textarea.composer-textarea").first
    ta.click()
    for probe in ["@hug", "@ação", "@dir with", "@../", "@secret", "@blob"]:
        ta.fill("")
        ta.type(probe, delay=30)
        page.wait_for_timeout(800)
        lb = page.get_by_role("listbox")
        found = (
            [" ".join(t.split()) for t in lb.get_by_role("option").all_text_contents()][:8]
            if lb.count()
            else "<no listbox>"
        )
        print(f"COMPLETION {probe!r}:", found)
    ta.fill("")
    ta.type("@hug", delay=30)
    page.wait_for_timeout(800)
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    print("after Enter on '@hug':", repr(ta.input_value()))
    j.shot(page, "01_completion")
    ta.fill("")
    page.get_by_test_id("conversation-toggle-panel").click()
    page.wait_for_timeout(2000)
    j.shot(page, "02_panel")
    # The empty panel offers "Open a panel" cards (Specs, Files, Loops), not tabs.
    files_tab = page.get_by_role("button", name="Files Browse this project")
    print("Files card:", files_tab.count())
    if files_tab.count():
        files_tab.first.click()
        page.wait_for_timeout(1500)
    j.shot(page, "02b_files_index")
    idx = page.get_by_test_id("files-index-tab")
    print("FILES index:", txt(idx)[:400])
    for path in ["huge.txt", "blob.bin", "latin1.txt"]:
        idx = page.get_by_test_id("files-index-tab")
        hit = page.get_by_test_id(f"files-search-result-{path}")
        if not hit.count():
            hit = idx.get_by_text(path, exact=True)
        print(f"open {path}: found={hit.count()}")
        if not hit.count():
            continue
        hit.first.click()
        page.wait_for_timeout(2500)
        print(f"  error: {txt(page.get_by_test_id('file-tab-error'))}")
        print(f"  binary: {txt(page.get_by_test_id('file-tab-binary'))}")
        print(f"  tab text: {txt(page.get_by_test_id('file-tab'))[:200]}")
        j.shot(page, f"03_{path.replace('.', '_')}")
        # Back to the index: a fresh load, the panel, the Files card.
        page = j.page(P, mode="light", query=f"agent=asker&conversation={conv}")
        page.wait_for_timeout(4000)
        page.get_by_test_id("conversation-toggle-panel").click()
        page.wait_for_timeout(1500)
        page.get_by_role("button", name="Files Browse this project").first.click()
        page.wait_for_timeout(1500)


def capture(j, qid):
    """A stale question from conversation A, and the operator typing a new instruction in B."""
    qconv = q("select conversation_id from questions where id=?", qid)[0]["conversation_id"]
    conv = q(
        "select conversation_id from runs where agent='asker' and conversation_id != ? "
        "order by started_at desc limit 1",
        qconv,
    )[0]["conversation_id"]
    print("question", qid, "in", qconv, "| typing in", conv)
    before = {r["id"] for r in q("select id from runs where agent='asker'")}
    page = j.page(P, mode="light", query=f"agent=asker&conversation={conv}")
    page.wait_for_timeout(5000)
    ta = page.locator("textarea.composer-textarea").first
    print("placeholder:", ta.get_attribute("placeholder"))
    print("card in B:", txt(page.get_by_test_id(f"agent-question-{qid}"))[:160])
    ta.click()
    ta.fill("New task: add a subtract(a, b) function to src/calc.py and reply in one line.")
    j.shot(page, "01_typed")
    page.get_by_role("button", name="Send message").first.click()
    page.wait_for_timeout(4000)
    print("QUESTION row:", q("select answered, answer, answered_at from questions where id=?", qid))
    print("URL now:", page.url)
    j.shot(page, "02_after_send")
    time.sleep(5)
    new = [r for r in q("select id, conversation_id, status from runs where agent='asker'")
           if r["id"] not in before]
    print("NEW runs:", new, "| B is", conv, "| A is", qconv)
    for r in new:
        e2e.wait_for(r["id"], 4)
        e2e.dump_turn(r["id"], tools=False)
    page.wait_for_timeout(2000)
    j.shot(page, "03_B_after_turn")
    print("B tail:", txt(page.get_by_test_id("conversation-output"))[-400:])


phase = sys.argv[1]
with Judge(f"s1020-q-{phase}", hub=e2e.hub(), key=e2e.key()) as j:
    if phase == "ask":
        ask(j)
    elif phase == "stale":
        stale(j, sys.argv[2])
    elif phase == "files":
        files(j)
    elif phase == "capture":
        capture(j, sys.argv[2])
