"""Acceptance drive for `live-thinking-stays-open-and-diagnostics-can-be-hidden` (F572), 2026-10-10.

The change's `drive` criterion (spdoc-a56fbfe278d0 on :8010, task drive-first). Starts its own Hub on
:8108 with a fresh database (never :8000 or :8010). One Haiku agent, alice, bound to a Claude runner
with permission mode bypassPermissions, so a command never stalls on an approval card.

No Claude turn on this machine emits thinking text (F578: the thinking block's text is empty, signature
only), so the drive posts the thinking event itself through POST /agents/alice/output on alice's live
run: the route a runner's output reaches, and the one a Copilot thought chunk takes. Steps, in the
order the criterion's `when` gives:

  1. in Chromium the operator sends alice "run `sleep 20`, then reply with the single word done"; once
     her run has recorded its tool call, the drive posts a thinking event with that run's id, and
     within five seconds the turn's last work block is open and shows the thinking text;
  2. after her reply (the word done is on the page and the run has ended) that block is closed and the
     thinking text is not visible;
  3. the drive posts a diagnostic and an error event on the same run; both are shown; Hide diagnostics
     removes the diagnostic and leaves the error; a reload keeps it hidden; Show diagnostics brings it
     back.

Selectors are text and ARIA only: a work block is a <details> whose `open` attribute is its state, and
the diagnostics control is a button named "Hide diagnostics" / "Show diagnostics" beside "Fold all
turns". Check 2 reads the thinking block through the page's `details` elements.

Fails on today's Hub at check 1 (the block is closed). Stops at the first failure. One Haiku turn.

    py -3.11 scripts/drive/d1022_thinking_ui.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8108
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1022-thinking-ui" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

THOUGHT = "THOUGHT-ORCHID-4417 weighing whether the sleep is safe to run"
DIAGNOSTIC = "DIAGNOSTIC-ORCHID-4417 runner stderr noise"
ERROR = "ERROR-ORCHID-4417 the runner reported a failure"
MESSAGE = "Run the shell command `sleep 20`, then reply with the single word done."


def run_ended(run_id):
    rows = d.ro("select status from runs where id=?", (run_id,))
    return bool(rows) and rows[0][0] not in ("running", "queued", "starting", "pending")


def newest_run():
    rows = d.ro("select id from runs where agent='alice' order by rowid desc limit 1")
    return rows[0][0] if rows else None


def has_tool_call(run_id):
    return d.ro(
        "select count(*) from agent_outputs where run_id=? and kind='tool_use'", (run_id,)
    )[0][0] > 0


def blocks_with(page, text):
    """The <details> work blocks whose rendered text includes `text`, as (open, visible) pairs."""
    found = []
    for block in page.locator("details.work-disclosure").all():
        if text in block.inner_text():
            found.append((block.get_attribute("open") is not None, True))
    return found


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# thinking\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "thinking"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    d.api("PATCH", base, {"main_branch": "main"})
    _, runner = d.api(
        "POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU}
    )
    code, out = d.api("POST", f"{base}/agents", {"name": "alice", "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)
    code, out = d.api(
        "PATCH", f"{base}/agents/alice", {"default_permission_mode": "bypassPermissions"}
    )
    assert code == 200, (code, out)

    def post_event(run_id, kind, content):
        return d.api(
            "POST",
            f"{base}/agents/alice/output",
            {"content": content, "kind": kind, "run_id": run_id},
        )

    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid)
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        page.goto(d.HUB, wait_until="domcontentloaded")
        d.poll(lambda: page.get_by_text("alice", exact=True).count() > 0, 20)
        page.get_by_text("alice", exact=True).first.click()
        page.get_by_placeholder("Message alice…").fill(MESSAGE)
        page.keyboard.press("Enter")

        # 1: while the command runs, the thinking block is open and its text is on the page.
        d.poll(lambda: newest_run() is not None, 60)
        run_id = newest_run()
        d.poll(lambda: has_tool_call(run_id), 90)
        code, out = post_event(run_id, "thinking", THOUGHT)
        posted_at = time.time()
        assert code == 201, (code, out)
        d.poll(lambda: THOUGHT in page.inner_text("body"), 5)
        elapsed = time.time() - posted_at
        page.screenshot(path=str(d.SHOT) + "_live.png", full_page=True)
        live = blocks_with(page, THOUGHT)
        shown = THOUGHT in page.inner_text("body")
        d.check(
            "1 within five seconds of the thinking event the last work block is open and shows "
            "the thinking text",
            run_ended(run_id) is False and shown and bool(live) and live[-1][0] and elapsed < 5.5,
            f"run={run_id} ended={run_ended(run_id)} blocks={live} shown={shown} after={elapsed:.1f}s",
        )

        # 2: once her reply is shown, the block is closed and the thought is not visible.
        d.poll(lambda: run_ended(run_id), 180)
        d.poll(lambda: page.get_by_text("done", exact=True).count() > 0, 30)
        time.sleep(1)
        page.screenshot(path=str(d.SHOT) + "_done.png", full_page=True)
        closed = blocks_with(page, "Work")
        d.check(
            "2 once done is shown the work block is closed and the thinking text is not visible",
            run_ended(run_id)
            and page.get_by_text("done", exact=True).count() > 0
            and THOUGHT not in page.inner_text("body")
            and bool(closed)
            and not any(is_open for is_open, _ in closed),
            f"blocks={closed} thought_visible={THOUGHT in page.inner_text('body')}",
        )

        # 3: diagnostics can be hidden; errors stay; the choice survives a reload.
        post_event(run_id, "diagnostic", DIAGNOSTIC)
        post_event(run_id, "error", ERROR)
        d.poll(lambda: DIAGNOSTIC in page.inner_text("body") and ERROR in page.inner_text("body"), 10)
        both = DIAGNOSTIC in page.inner_text("body") and ERROR in page.inner_text("body")
        hide = page.get_by_role("button", name="Hide diagnostics")
        d.poll(lambda: hide.count() == 1, 5)
        if hide.count() == 1:
            hide.click()
        time.sleep(0.5)
        hidden = DIAGNOSTIC not in page.inner_text("body") and ERROR in page.inner_text("body")
        page.reload(wait_until="domcontentloaded")
        d.poll(lambda: page.get_by_text("alice", exact=True).count() > 0, 20)
        page.get_by_text("alice", exact=True).first.click()
        d.poll(lambda: ERROR in page.inner_text("body"), 15)
        kept = DIAGNOSTIC not in page.inner_text("body") and ERROR in page.inner_text("body")
        show = page.get_by_role("button", name="Show diagnostics")
        d.poll(lambda: show.count() == 1, 5)
        if show.count() == 1:
            show.click()
        d.poll(lambda: DIAGNOSTIC in page.inner_text("body"), 5)
        back = DIAGNOSTIC in page.inner_text("body") and ERROR in page.inner_text("body")
        page.screenshot(path=str(d.SHOT) + "_diagnostics.png", full_page=True)
        browser.close()
    d.check(
        "3 both shown; Hide diagnostics removes the diagnostic and leaves the error; the reload "
        "keeps it hidden; Show diagnostics brings it back",
        both and hidden and kept and back,
        f"both={both} hidden={hidden} kept_after_reload={kept} back={back}",
    )


d.drive = drive

if __name__ == "__main__":
    d.main()
