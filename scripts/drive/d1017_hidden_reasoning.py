"""Drive for vis-D10 (F578's 5.x half), 2026-10-17: a Claude 5.x turn that reasons shows it did.

Starts its own Hub on :8131 with a fresh database (never :8000 or :8010). One agent, alice, on a
Claude runner bound to Haiku 5.5, which sends a signed thinking block with no text (CLI 2.1.301).
In Chromium the operator asks a question worth reasoning over; once the run ends:

  1. the run recorded at least one `thinking` row with `payload.hidden` and no content;
  2. the conversation shows a "Reasoned" line or row, and no empty "Thinking" row.

Fails before the fix at check 1 (the parser dropped an empty block, so nothing was recorded). One
Haiku 5.5 turn. Screenshots under testbed/drive1017-hidden-reasoning/.

    py -3.11 scripts/drive/d1017_hidden_reasoning.py
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8131
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1017-hidden-reasoning" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

MODEL = "claude-haiku-5-5"
MESSAGE = (
    "Think carefully before answering: a train leaves at 14:35 and the trip takes 2 h 50 min. "
    "When does it arrive? Reply with only the time, like 17:25."
)


def run_ended(run_id):
    rows = d.ro("select status from runs where id=?", (run_id,))
    return bool(rows) and rows[0][0] not in ("running", "queued", "starting", "pending")


def newest_run():
    rows = d.ro("select id from runs where agent='alice' order by rowid desc limit 1")
    return rows[0][0] if rows else None


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# reasoning\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "reasoning"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    d.api("PATCH", base, {"main_branch": "main"})
    code, runner = d.api(
        "POST", f"{base}/runners", {"name": "Haiku 5.5", "cli": "claude", "model": MODEL}
    )
    assert code in (200, 201), (code, runner)
    code, out = d.api("POST", f"{base}/agents", {"name": "alice", "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)

    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid)
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1300, "height": 900})
        page.add_init_script(seed)
        page.goto(d.HUB, wait_until="domcontentloaded")
        d.poll(lambda: page.get_by_text("alice", exact=True).count() > 0, 20)
        page.get_by_text("alice", exact=True).first.click()
        page.get_by_placeholder("Message alice…").fill(MESSAGE)
        page.keyboard.press("Enter")

        d.poll(lambda: newest_run() is not None, 60)
        run_id = newest_run()
        d.poll(lambda: run_ended(run_id), 180)
        rows = d.ro(
            "select content, payload from agent_outputs where run_id=? and kind='thinking'",
            (run_id,),
        )
        hidden = [
            r for r in rows if not (r[0] or "").strip() and json.loads(r[1] or "{}").get("hidden")
        ]
        d.check(
            "1 the Haiku 5.5 run recorded a hidden thinking row",
            bool(hidden),
            f"run={run_id} thinking_rows={[(c[:40], p) for c, p in rows]}",
        )

        time.sleep(2)
        page.screenshot(path=str(d.SHOT) + "_ended.png", full_page=True)
        line = page.get_by_test_id("hidden-reasoning")
        if line.count() == 0:
            # Mixed with tool calls it is a row inside the block: open the block to see it.
            for summary in page.locator("details.work-disclosure > summary").all():
                summary.click()
        shown = line.count() + page.get_by_test_id("hidden-reasoning-row").count()
        empty_thinking = page.get_by_text("Thinking", exact=True).count()
        if line.count():
            line.first.scroll_into_view_if_needed()
            line.first.screenshot(path=str(d.SHOT) + "_line.png")
        page.screenshot(path=str(d.SHOT) + "_shown.png", full_page=True)
        browser.close()
    d.check(
        "2 the conversation shows that alice reasoned, and no empty Thinking row",
        shown > 0 and empty_thinking == 0,
        f"reasoned={shown} thinking_rows={empty_thinking}",
    )


d.drive = drive

if __name__ == "__main__":
    d.main()
