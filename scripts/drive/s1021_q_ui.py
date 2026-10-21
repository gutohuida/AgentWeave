"""Questions x Conversations & composer sweep 2026-10-21 (real browser, served bundle, :8152,
profile q1021). F804 driven with a question a real Haiku turn asked, not a seeded row.

    live  -- conversation B exists; a fresh turn in A asks (wait 180 s) and is still waiting.
             In B: is A's card absent, what does the composer offer, and does typed text go out
             as B's message (question untouched)? Then in A: answer by number key + Send.
    stale -- a fresh turn in C asks (wait 30 s) and nobody answers; the run ends. In B: absent.
             In C: the placeholder, then typed text is a message in C, the question untouched.
    stopb -- a fresh turn in A asks (wait 120 s); in B, is "Stop turn" offered, and what does
             pressing it stop?
    arch  -- a fresh turn in D asks (wait 30 s), the run ends, D is archived. In B: absent.
             Overview: is D's question still listed?

    AW_P=<project> py -3.11 scripts/drive/s1021_q_ui.py live|stale|stopb|arch|composer
"""

import json
import os
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-q1021.json")
from s1020_q_lib import e2e, q, req  # noqa: E402
from uiharness import Judge  # noqa: E402

P = os.environ["AW_P"]
ASK = ("Call the AgentWeave tool ask_user with the question '{q}' and the options 'red', 'green' "
       "and 'blue'. Wait for the answer, then reply in one line naming it, or saying none came.")


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def conv_of(rid):
    return q("select conversation_id from runs where id=?", rid)[0]["conversation_id"]


def ask(question, wait):
    req("PATCH", f"/projects/{P}/agents/asker", {"question_timeout_seconds": wait})
    rid = e2e.cmd_turn(P, "asker", ASK.format(q=question), fresh=True, perm="workspace")
    for _ in range(80):
        rows = q("select id from questions where created_by_run_id=?", rid)
        if rows:
            return rid, rows[0]["id"]
        time.sleep(3)
    raise SystemExit(f"no question from {rid}: {e2e.wait_for(rid, 0.1)}")


def conv_b():
    rows = q("select conversation_id from runs where agent='asker' order by started_at limit 1")
    if rows:
        return rows[0]["conversation_id"]
    rid = e2e.cmd_turn(P, "asker", "Reply with the single word ready.", fresh=True,
                       perm="workspace")
    print("B run:", e2e.wait_for(rid, 4))
    return conv_of(rid)


def look(j, conv, qid, label, send=None):
    page = j.page(P, mode="light", query=f"agent=asker&conversation={conv}")
    page.wait_for_timeout(5000)
    ta = page.locator("textarea.composer-textarea").first
    card = page.get_by_test_id(f"agent-question-{qid}")
    print(f"[{label}] conv={conv} card={card.count()} placeholder={ta.get_attribute('placeholder')!r}")
    print(f"[{label}] any question card:", page.locator("[data-testid^='agent-question-q-']").count())
    j.shot(page, f"{label}_before")
    if send:
        ta.click()
        ta.fill(send)
        page.get_by_role("button", name="Send message").first.click()
        page.wait_for_timeout(5000)
        j.shot(page, f"{label}_after")
        print(f"[{label}] question:", q("select answered, declined, answer from questions where id=?", qid))
        print(f"[{label}] entries:", json.dumps(q(
            "select id, conversation_id, state, substr(content,1,90) c from inbound_queue_entries "
            "where agent='asker' order by sequence desc limit 2"), ensure_ascii=False))
        print(f"[{label}] queued note:", txt(page.locator("[data-testid^='queued-entry']")))
    return page


phase = sys.argv[1]
with Judge(f"s1021-q-{phase}", hub=e2e.hub(), key=e2e.key()) as j:
    b = conv_b()
    if phase == "live":
        rid, qid = ask("Which colour for the badge?", 180)
        a = conv_of(rid)
        print("A", a, "run", rid, "question", qid, "B", b)
        look(j, b, qid, "B_while_A_waits", send="Reply with the single word beta.")
        page = look(j, a, qid, "A_waiting")
        card = page.get_by_test_id(f"agent-question-{qid}")
        print("A card text:", txt(card)[:200])
        card.locator("p").first.click()
        page.keyboard.press("2")
        page.wait_for_timeout(500)
        page.get_by_role("button", name="Send message").first.click()
        page.wait_for_timeout(3000)
        print("A answered:", q("select answered, answer from questions where id=?", qid))
        print("A run:", e2e.wait_for(rid, 4))
        e2e.dump_turn(rid, tools=False)
        later = q("select id, conversation_id, status from runs where agent='asker' and "
                  "started_at > (select started_at from runs where id=?)", rid)
        print("later runs:", later)
        for r in later:
            print(r["id"], e2e.wait_for(r["id"], 4), "in B" if r["conversation_id"] == b else "NOT in B")
            e2e.dump_turn(r["id"], tools=False)
    elif phase == "composer":
        page = j.page(P, mode="light", query=f"agent=asker&conversation={b}")
        page.wait_for_timeout(5000)
        ta = page.locator("textarea.composer-textarea").first
        ta.click()
        ta.type("@note", delay=40)
        page.wait_for_timeout(1000)
        j.shot(page, "c1_completion")
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        print("after Enter on '@note':", repr(ta.input_value()))
        ta.fill("draft that should survive a reload")
        page.wait_for_timeout(1500)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        ta = page.locator("textarea.composer-textarea").first
        print("draft after reload:", repr(ta.input_value()))
        ta.fill("")
        diag = page.get_by_role("button", name="Hide diagnostics")
        print("Hide diagnostics present:", diag.count())
        if diag.count():
            diag.first.click()
            page.wait_for_timeout(800)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            print("after reload, Show diagnostics:", page.get_by_role("button", name="Show diagnostics").count())
            page.get_by_role("button", name="Show diagnostics").first.click()
            page.wait_for_timeout(500)
        page.get_by_test_id("conversation-toggle-panel").click()
        page.wait_for_timeout(1500)
        page.get_by_role("button", name="Files Browse this project").first.click()
        page.wait_for_timeout(2000)
        hit = page.get_by_test_id("files-index-tab").get_by_text("notes.txt", exact=True)
        print("notes.txt in index:", hit.count())
        if hit.count():
            hit.first.click()
            page.wait_for_timeout(2000)
            print("file tab:", txt(page.get_by_test_id("file-tab"))[:200])
            page.get_by_role("button", name="Insert into composer").first.click()
            page.wait_for_timeout(1000)
            ta = page.locator("textarea.composer-textarea").first
            print("composer after Insert:", repr(ta.input_value()))
            j.shot(page, "c2_inserted")
            ta.fill("")
    elif phase == "reason":
        rid = e2e.cmd_turn(P, "asker", "Without using any tools, think carefully step by step: "
                           "how many distinct ways can 12 be written as an ordered sum of 1s, 2s "
                           "and 3s? Reply with the number only.", fresh=True, perm="workspace")
        conv = conv_of(rid)
        page = j.page(P, mode="light", query=f"agent=asker&conversation={conv}")
        seen = []
        for i in range(60):
            page.wait_for_timeout(700)
            st = q("select status from runs where id=?", rid)[0]["status"]
            n_think = q("select count(*) n from agent_outputs where run_id=? and kind='thinking'", rid)[0]["n"]
            opened = page.locator("details[open]").count()
            vis = page.get_by_text("Thinking", exact=True).count()
            seen.append((i, st, n_think, opened, vis))
            if n_think and st == "running":
                j.shot(page, f"r{i}")
            if st != "running":
                break
        page.wait_for_timeout(2000)
        j.shot(page, "r_end")
        print("samples (i, status, thinking rows, details[open], 'Thinking' labels):")
        for s in seen:
            print(" ", s)
        print("after end: details[open]=", page.locator("details[open]").count())
        e2e.dump_turn(rid, tools=False)
    elif phase == "thinking":
        live = q("select id, conversation_id from runs where status='running' and agent='asker'")
        print("live:", live)
        if live:
            page = j.page(P, mode="light", query=f"agent=asker&conversation={live[0]['conversation_id']}")
            for i in range(4):
                page.wait_for_timeout(6000)
                body = " ".join((page.locator("main").first.text_content() or "").split())
                print(f"t{i}: Thinking shown={'Thinking' in body} Working={'Working' in body} "
                      f"run={q('select status from runs where id=?', live[0]['id'])}")
                j.shot(page, f"t{i}")
    elif phase == "stopb":
        rid, qid = ask("Which colour for the border?", 120)
        a = conv_of(rid)
        print("A", a, "run", rid, "question", qid, "B", b)
        page = look(j, b, qid, "B_stop")
        print("B header:", txt(page.locator("header, [data-testid='conversation-header']"))[:200])
        stop = page.get_by_role("button", name="Stop turn")
        print("B Stop turn buttons:", stop.count())
        if stop.count():
            stop.first.click()
            page.wait_for_timeout(6000)
            j.shot(page, "B_after_stop")
        print("A run:", q("select status, error from runs where id=?", rid))
        print("A question:", q("select answered, declined, wait_ended_at from questions where id=?", qid))
        e2e.dump_turn(rid, tools=False)
    elif phase in ("stale", "arch"):
        rid, qid = ask("Which colour for the footer?" if phase == "stale" else
                       "Which colour for the header?", 30)
        c = conv_of(rid)
        print("conv", c, "run", rid, "question", qid, "->", e2e.wait_for(rid, 5))
        e2e.dump_turn(rid, tools=False)
        st, qs = req("GET", f"/projects/{P}/questions?answered=false")
        print("listed:", [{k: x.get(k) for k in ("id", "conversation_id", "asker_waiting")}
                          for x in qs if x["id"] == qid])
        if phase == "arch":
            print("archive:", req("POST", f"/projects/{P}/agent/asker/conversations/{c}/archive")[0])
            look(j, b, qid, "B_after_archive")
            page = j.page(P, mode="light")
            page.wait_for_timeout(5000)
            j.shot(page, "overview", full_page=True)
            print("overview has it:", page.get_by_text("Which colour for the header?").count())
        else:
            look(j, b, qid, "B_stale_elsewhere")
            look(j, c, qid, "C_own_stale", send="Reply with the single word gamma.")
            for r in q("select id from runs where conversation_id=? and id != ?", c, rid):
                print(r["id"], e2e.wait_for(r["id"], 4))
                e2e.dump_turn(r["id"], tools=False)
    print("errors:", j.errors)
