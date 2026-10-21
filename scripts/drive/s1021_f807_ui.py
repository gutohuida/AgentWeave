"""F807 acceptance drive (real browser, served bundle, scratch Hub :8151, profile f807).

Stored checkpoint runner = a claude runner, model `haiku`. Picking a copilot runner must clear the
model on screen and Save must store the runner (not be refused naming `haiku`).

    AW_E2E_STATE=~/.agentweave/e2e-f807.json AW_P=<project> py -3.11 scripts/drive/s1021_f807_ui.py
"""

import os
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-f807.json")
from s1020_q_lib import e2e, req  # noqa: E402
from uiharness import Judge  # noqa: E402

P = os.environ["AW_P"]

with Judge("s1021-f807", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=environment&section=settings")
    page.wait_for_timeout(3000)
    runner = page.get_by_label("Checkpoint runner")
    model = page.get_by_label("Checkpoint model")
    print("before: runner", runner.input_value(), "| model", repr(model.input_value()))
    print("options:", [o.text_content() for o in runner.locator("option").all()])
    runner.select_option(label=[o.text_content() for o in runner.locator("option").all() if "r-cop" in o.text_content()][0])
    print("after pick: model", repr(model.input_value()))
    j.shot(page, "01_picked")
    page.get_by_text("Save settings").first.click()
    page.wait_for_timeout(1500)
    print("alert:", page.get_by_role("alert").all_text_contents())
    print("status:", page.get_by_role("status").all_text_contents())
    print("stored:", {k: v for k, v in req("GET", f"/projects/{P}/settings")[1].items() if k.startswith("checkpoint_r") or k == "checkpoint_model"})
    print("errors:", j.errors)
