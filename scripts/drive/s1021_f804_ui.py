"""F804 acceptance drive (real browser, served bundle, scratch Hub :8150, profile f804).

A question left open in conversation A (its run ended) must not take over conversation B's
composer, and typed text in A, where nobody waits, must go out as a message, not as the answer.

    AW_E2E_STATE=~/.agentweave/e2e-f804.json py -3.11 scripts/drive/s1021_f804_ui.py b|a
"""

import os
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-f804.json")
from s1020_q_lib import e2e, q  # noqa: E402
from uiharness import Judge  # noqa: E402

P = os.environ.get("AW_P", "proj-89d5af4a08b1")
QID = "q-f804-stale"
phase = sys.argv[1]
conv = {"b": "conv-f804-B", "a": "conv-f804-A"}[phase]

with Judge(f"s1021-f804-{phase}", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query=f"agent=asker&conversation={conv}")
    page.wait_for_timeout(4000)
    ta = page.locator("textarea.composer-textarea").first
    print("placeholder:", ta.get_attribute("placeholder"))
    print("card present:", page.get_by_test_id(f"agent-question-{QID}").count())
    ta.click()
    ta.fill("Reply with the single word ok.")
    j.shot(page, "01_typed")
    page.get_by_role("button", name="Send message").first.click()
    page.wait_for_timeout(5000)
    print("question row:", q("select answered, answer from questions where id=?", QID))
    print("runs:", q("select id, conversation_id, status, initiator from runs order by started_at"))
    j.shot(page, "02_after_send")
    print("errors:", j.errors)
