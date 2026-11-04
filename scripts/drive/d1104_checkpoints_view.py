"""Acceptance drive for `every-checkpoint-findable-and-readable` (ECFR), 2026-11-04.

The change's `drive-checkpoint-end-to-end` criterion, written before the build. It drives a trial
Hub on AW_DRIVE_PORT (default 8010), reusing one that already answers there and otherwise starting
one from this checkout's `hub/` (never :8000), with real Haiku turns. A scratch git repository is
opened as a project with two Haiku-bound agents, Alpha and Beta. Then, in order:

  setup  Alpha holds a conversation with two finished runs, Beta one of its own with one run; the
         checkpoint runner is a Haiku runner.
  1      the operator takes a checkpoint of Alpha's conversation and carries it over to a successor
  2      the project has a Checkpoints tab (the first step master fails: there is none)
  3      the tab lists the checkpoint with a title and summary its generation wrote, its agent,
         "the operator asked" in place of "operator", and its conversation
  4      narrowing to Alpha keeps Alpha's checkpoint and hides Beta's
  5      opening it shows formatted text and the runs it covers
  6      the successor conversation shows it as the checkpoint it started from

Setup and step 1 use routes master has, so on master they pass and step 2 fails; the later steps
are skipped once the tab is not there. Costs four Haiku turns and two checkpoint generations.

    py -3.11 scripts/drive/d1104_checkpoints_view.py

AW_DRIVE_DB names the database of an already-running Hub when it is not the trial profile's.
Needs playwright (`py -3.11 -m playwright install chromium`).

Master, recorded at the end of this file.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import d1029_build_plan_in_spec as base  # noqa: E402  -- its Hub helpers (F1121: AW_DRIVE_PORT)

api, ro, poll, check, git = base.api, base.ro, base.poll, base.check, base.git
HUB, KEY, HAIKU, STAMP = base.HUB, base.KEY, base.HAIKU, base.STAMP
ALPHA, BETA = "Alpha", "Beta"
TURN_WAIT = 5 * 60
SHOTS = base.TMP / "shots"


def wait_run(run_id):
    done = ("running", "queued", "starting", "pending")
    ok = poll(
        lambda: ro("select status from runs where id=?", (run_id,))[0][0] not in done,
        TURN_WAIT, 3,
    )
    return ro("select status from runs where id=?", (run_id,))[0][0] if ok else "still-running"


def turn(pid, agent, message, conversation=None):
    body = {"agent": agent, "message": message}
    if conversation:
        body["conversation_id"] = conversation
    code, res = api("POST", f"/projects/{pid}/agent/trigger", body)
    if code >= 300 or not isinstance(res, dict) or not res.get("run_id"):
        base.check("a turn started", False, f"{agent}: {code} {res}", fatal=True)
    status = wait_run(res["run_id"])
    check(f"{agent}'s turn finished", status == "completed", f"{res['run_id']} {status}", fatal=True)
    return res["run_id"], ro("select conversation_id from runs where id=?", (res["run_id"],))[0][0]


def browser_steps(pid, alpha_conv, beta_checkpoint, alpha_checkpoint, successor):
    from playwright.sync_api import sync_playwright

    seed = (
        f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, "
        f"hubUrl: {HUB!r}}})); localStorage.setItem('agentweave-selected-project', {pid!r});"
    )
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(seed)
        page.goto(HUB, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        tab = page.get_by_role("tab", name=re.compile(r"^Checkpoints")).or_(
            page.get_by_text("Checkpoints", exact=True)
        )
        has_tab = tab.count() > 0
        check("the project has a Checkpoints tab", has_tab, "no tab named Checkpoints", fatal=False)
        if not has_tab:
            page.screenshot(path=str(SHOTS / "no-tab.png"))
            browser.close()
            return False
        tab.first.click()
        page.wait_for_timeout(2500)
        page.screenshot(path=str(SHOTS / "tab.png"))
        text = page.inner_text("body")
        row = page.locator("[data-testid^='checkpoint-row-']")
        got = row.filter(has_text=ALPHA)
        check("the checkpoint is listed", got.count() >= 1, f"{row.count()} rows")
        stored = ro("select title, summary from checkpoints where id=?", (alpha_checkpoint,))[0]
        check("it shows the title its generation wrote", bool(stored[0]) and stored[0] in text, repr(stored[0]))
        check("it shows the summary its generation wrote", bool(stored[1]) and stored[1][:40] in text, repr(stored[1])[:80])
        check("it names its agent and conversation", ALPHA in text and alpha_conv[:8] in text)
        check("'the operator asked' replaces 'operator'", "the operator asked" in text.lower())
        check("both agents' checkpoints are listed unnarrowed", BETA in text)

        agent_filter = page.get_by_test_id("checkpoints-filter-agent")
        agent_filter.select_option(ALPHA)
        page.wait_for_timeout(1500)
        narrowed = page.inner_text("body")
        check("narrowing to Alpha hides Beta's checkpoints", BETA not in narrowed.split("Checkpoints", 1)[-1])
        page.locator("[data-testid^='checkpoint-row-']").filter(has_text=ALPHA).first.click()
        page.wait_for_timeout(2000)
        page.screenshot(path=str(SHOTS / "open.png"))
        opened = page.inner_text("body")
        check("opening it shows formatted text", page.locator("[data-testid='checkpoint-body'] h2, [data-testid='checkpoint-body'] li").count() > 0)
        runs = [r[0] for r in ro("select id from runs where conversation_id=? order by started_at", (alpha_conv,))]
        check("opening it shows the runs it covers", all(r[:8] in opened for r in runs), f"{len(runs)} runs")

        page.goto(f"{HUB}/#/conversations/{successor}", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(SHOTS / "successor.png"))
        check("the successor shows the checkpoint it started from",
              "started from" in page.inner_text("body").lower(), successor)
        browser.close()
    return True


def main():
    hub = base.start_hub()
    pid = None
    try:
        base.TMP.mkdir(parents=True, exist_ok=True)
        root = base.TMP / "project"
        root.mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("# d1104\n\nChecked by the checkpoints drive.\n", encoding="utf-8")
        git(root, "init", "-q", "-b", "master")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "init")
        code, project = api("POST", "/projects/open", {"path": str(root)})
        base.check("the project opened", code < 300, f"{code} {project}", fatal=True)
        pid = project["id"]
        code, runner = api("POST", f"/projects/{pid}/runners",
                           {"name": f"haiku {STAMP}", "cli": "claude", "model": HAIKU})
        base.check("a Haiku runner", code < 300, f"{code} {runner}", fatal=True)
        for name in (ALPHA, BETA):
            code, res = api("POST", f"/projects/{pid}/agents", {"name": name, "runner_id": runner["id"]})
            base.check(f"agent {name}", code < 300, f"{code} {res}", fatal=True)
        code, settings = api("GET", f"/projects/{pid}/settings")
        settings.update(checkpoint_mode="off", checkpoint_runner_id=runner["id"],
                        checkpoint_model=HAIKU, checkpoint_auto_continue=False)
        code, _ = api("PUT", f"/projects/{pid}/settings", settings)
        base.check("checkpoint runner set", code == 200, str(code), fatal=True)

        _, alpha_conv = turn(pid, ALPHA, "Read README.md and reply with its first line, nothing else.")
        turn(pid, ALPHA, "Now say in one sentence what that file is for.", alpha_conv)
        turn(pid, BETA, "Read README.md and reply with the word 'seen'.")

        # Step 1: a checkpoint of each conversation, Alpha's carried over to a successor.
        code, cp = api("POST", f"/projects/{pid}/conversations/{alpha_conv}/checkpoint", timeout=300)
        check("Alpha's checkpoint was taken", code == 201 and cp.get("status") == "ready", f"{code} {str(cp)[:200]}", fatal=True)
        beta_conv = ro("select conversation_id from runs where project_id=? and agent=? limit 1", (pid, BETA))[0][0]
        code, bcp = api("POST", f"/projects/{pid}/conversations/{beta_conv}/checkpoint", timeout=300)
        check("Beta's checkpoint was taken", code == 201, f"{code} {str(bcp)[:200]}", fatal=True)
        code, cut = api("POST", f"/projects/{pid}/checkpoints/{cp['id']}/cutover")
        check("Alpha's checkpoint was carried over", code == 200, f"{code} {cut}", fatal=True)

        browser_steps(pid, alpha_conv, bcp["id"], cp["id"], cut["successor_conversation_id"])
    except base.Stop:
        pass
    finally:
        base.stop_hub(hub)
    failed = [n for n, ok in base.results if not ok]
    print("FAILED: " + ", ".join(failed) if failed else "ALL PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

# On master (2026-11-04, AW_DRIVE_PORT=8044): setup, both checkpoints and the cutover pass; then
#   FAIL the project has a Checkpoints tab -- no tab named Checkpoints
#   FAILED: the project has a Checkpoints tab          (exit 1)
