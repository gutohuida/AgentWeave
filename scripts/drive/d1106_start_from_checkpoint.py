"""Acceptance drive for `start-a-conversation-from-any-checkpoint-with-any-agent` (SCACA), 2026-11-06.

The change's `ac-drive` and `ac-lineage` criteria, written before the build. It drives a trial Hub on
AW_DRIVE_PORT (default 8010), reusing one that already answers there and otherwise starting one from
this checkout's `hub/` (never :8000), with real Haiku turns. A scratch git repository is opened as a
project (under the temp directory, removed at the end) with two Haiku-bound agents, Alpha and Beta,
each on a runner of its own. Then, in order:

  setup  Alpha holds a conversation with two finished runs; a checkpoint of it is taken and carried
         over to a successor
  1      in the browser: on the Checkpoints page the operator opens that checkpoint, chooses Beta in
         the agent picker (Alpha is offered first) and confirms           (master fails here: no start)
  2      a new conversation of Beta exists whose first delivered queue input is that checkpoint, with
         the note naming Alpha as its author
  3      Beta's turn ran, on Beta's runner's model (Haiku)
  4      Alpha's conversation and its successor are unchanged: same lifecycle, same runs, same queue
         entries and states
  5      the operator route starts a second conversation from the same checkpoint (for Alpha)
  6      in the browser the checkpoint shows the carry-over and lists both started conversations with
         agent and time; each started conversation links back to the checkpoint

The route contract the drive holds the build to (the Hub task `start` and the UI task `ui` meet it):
`POST /projects/{pid}/checkpoints/{checkpoint}/start {"agent": ..., "message": optional}` answering 2xx.
Browser test ids: `checkpoint-start-open` (opens the form), `checkpoint-start-agent` (a native select
whose first option is the checkpoint's agent), `checkpoint-start-confirm`, `checkpoint-detail-started`
(the list) with one `checkpoint-started-<conversation id>` item per conversation; the conversation
view says it "started from the checkpoint" and offers "View checkpoint".

On master the setup passes and step 1 fails (no start action), so the later steps are skipped. Costs
three Haiku turns and one checkpoint generation.

    py -3.11 scripts/drive/d1106_start_from_checkpoint.py

AW_DRIVE_DB names the database of an already-running Hub when it is not the trial profile's.
Needs playwright (`py -3.11 -m playwright install chromium`).

Master, recorded at the end of this file.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import d1029_build_plan_in_spec as base  # noqa: E402  -- its Hub helpers (F1121: AW_DRIVE_PORT)

api, ro, poll, check, git = base.api, base.ro, base.poll, base.check, base.git
HUB, KEY, HAIKU, STAMP = base.HUB, base.KEY, base.HAIKU, base.STAMP
ALPHA, BETA = "Alpha", "Beta"
TURN_WAIT = 5 * 60
SHOTS = base.TMP / "shots"
BUSY = ("running", "queued", "starting", "pending")


def wait_run(run_id):
    ok = poll(lambda: ro("select status from runs where id=?", (run_id,))[0][0] not in BUSY, TURN_WAIT, 3)
    return ro("select status from runs where id=?", (run_id,))[0][0] if ok else "still-running"


def turn(pid, agent, message, conversation=None):
    body = {"agent": agent, "message": message}
    if conversation:
        body["conversation_id"] = conversation
    code, res = api("POST", f"/projects/{pid}/agent/trigger", body)
    if code >= 300 or not isinstance(res, dict) or not res.get("run_id"):
        check("a turn started", False, f"{agent}: {code} {res}", fatal=True)
    status = wait_run(res["run_id"])
    check(f"{agent}'s turn finished", status == "completed", f"{res['run_id']} {status}", fatal=True)
    return res["run_id"], ro("select conversation_id from runs where id=?", (res["run_id"],))[0][0]


def snapshot(conversation):
    """Everything FR-6 says a start must leave alone about one conversation."""
    return {
        "lifecycle": ro("select lifecycle from conversations where id=?", (conversation,))[0][0],
        "runs": ro("select id, status from runs where conversation_id=? order by id", (conversation,)),
        "queue": ro("select id, state from inbound_queue_entries where conversation_id=? order by id", (conversation,)),
    }


def conversations_of(pid, agent):
    return {r[0] for r in ro("select id from conversations where project_id=? and agent=?", (pid, agent))}


def first_input(conversation):
    rows = ro("select content from inbound_queue_entries where conversation_id=? order by sequence limit 1", (conversation,))
    return rows[0][0] if rows else ""


def browser_start(page, pid, checkpoint):
    """Step 1: the operator starts Beta from the checkpoint. False when the page offers no start."""
    page.goto(f"{HUB}/?project={pid}&checkpoint={checkpoint}", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    tab = page.get_by_test_id("project-tab-checkpoints")
    if tab.count():
        tab.first.click()
        page.wait_for_timeout(1500)
    row = page.get_by_test_id(f"checkpoint-row-{checkpoint}")
    if row.count():
        row.click()
        page.wait_for_timeout(1500)
    page.screenshot(path=str(SHOTS / "detail.png"))
    opener = page.get_by_test_id("checkpoint-start-open")
    if not check("the checkpoint offers a start action", opener.count() > 0, "no checkpoint-start-open on the detail"):
        return False
    opener.first.click()
    picker = page.get_by_test_id("checkpoint-start-agent")
    options = picker.locator("option")
    first = options.first.inner_text() if options.count() else ""
    check("the checkpoint's own agent is offered first", ALPHA in first, repr(first))
    picker.select_option(label=BETA)
    page.screenshot(path=str(SHOTS / "picker.png"))
    page.get_by_test_id("checkpoint-start-confirm").click()
    page.wait_for_timeout(2500)
    page.screenshot(path=str(SHOTS / "started.png"))
    return True


def lineage_steps(page, pid, checkpoint, started):
    """Step 6: the checkpoint lists both started conversations; each links back."""
    page.goto(f"{HUB}/?project={pid}&checkpoint={checkpoint}", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    tab = page.get_by_test_id("project-tab-checkpoints")
    if tab.count():
        tab.first.click()
        page.wait_for_timeout(1500)
    page.get_by_test_id(f"checkpoint-row-{checkpoint}").click()
    page.wait_for_timeout(1500)
    page.screenshot(path=str(SHOTS / "lineage.png"))
    lineage = page.get_by_test_id("checkpoint-detail-lineage")
    check("the checkpoint shows the carry-over", lineage.count() > 0 and "Carried over into" in lineage.inner_text(),
          lineage.inner_text() if lineage.count() else "no lineage block")
    listing = page.get_by_test_id("checkpoint-detail-started")
    check("the checkpoint lists the conversations started from it", listing.count() > 0, "no checkpoint-detail-started")
    for conversation, agent in started:
        item = page.get_by_test_id(f"checkpoint-started-{conversation}")
        text = item.inner_text() if item.count() else ""
        check(f"it lists {agent}'s started conversation with agent and time",
              item.count() == 1 and agent in text
              and (any(ch.isdigit() for ch in text) or "ago" in text or "now" in text.lower()),
              repr(text))
    for conversation, agent in started:
        page.goto(f"{HUB}/?project={pid}&agent={agent}&conversation={conversation}", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        banner = page.get_by_test_id("conversation-banner")
        text = banner.inner_text() if banner.count() else ""
        check(f"{agent}'s started conversation says where it started from",
              "started from the checkpoint" in text.lower() and "View checkpoint" in text, repr(text))
        link = page.get_by_text("View checkpoint")
        if link.count():
            link.first.click()
            page.wait_for_timeout(1500)
            check(f"{agent}'s conversation links back to the checkpoint",
                  f"checkpoint={checkpoint}" in page.url, page.url)


def drive(pid, root):
    code, runner_a = api("POST", f"/projects/{pid}/runners", {"name": f"haiku-a {STAMP}", "cli": "claude", "model": HAIKU})
    check("a Haiku runner for Alpha", code < 300, f"{code} {runner_a}", fatal=True)
    code, runner_b = api("POST", f"/projects/{pid}/runners", {"name": f"haiku-b {STAMP}", "cli": "claude", "model": HAIKU})
    check("a Haiku runner for Beta", code < 300, f"{code} {runner_b}", fatal=True)
    for name, runner in ((ALPHA, runner_a), (BETA, runner_b)):
        code, res = api("POST", f"/projects/{pid}/agents", {"name": name, "runner_id": runner["id"]})
        check(f"agent {name}", code < 300, f"{code} {res}", fatal=True)
    code, settings = api("GET", f"/projects/{pid}/settings")
    settings.update(checkpoint_mode="off", checkpoint_runner_id=runner_a["id"],
                    checkpoint_model=HAIKU, checkpoint_auto_continue=False)
    code, _ = api("PUT", f"/projects/{pid}/settings", settings)
    check("checkpoint runner set", code == 200, str(code), fatal=True)

    _, alpha_conv = turn(pid, ALPHA, "Read README.md and reply with its first line, nothing else.")
    turn(pid, ALPHA, "Now say in one sentence what that file is for.", alpha_conv)
    code, cp = api("POST", f"/projects/{pid}/conversations/{alpha_conv}/checkpoint", timeout=300)
    check("Alpha's checkpoint was taken", code == 201 and cp.get("status") == "ready", f"{code} {str(cp)[:200]}", fatal=True)
    code, cut = api("POST", f"/projects/{pid}/checkpoints/{cp['id']}/cutover")
    check("the checkpoint was carried over", code == 200, f"{code} {cut}", fatal=True)
    successor = cut["successor_conversation_id"]
    # The successor's own first turn is not wanted: carry-over waits for Continue (auto_continue off).
    before = {alpha_conv: snapshot(alpha_conv), successor: snapshot(successor)}
    beta_before = conversations_of(pid, BETA)

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
        check("1 the operator starts Beta from the checkpoint in the browser",
              browser_start(page, pid, cp["id"]), f"see {SHOTS}", fatal=True)
        new = poll(lambda: conversations_of(pid, BETA) - beta_before, 30)
        created = conversations_of(pid, BETA) - beta_before
        check("2 a new conversation of Beta exists", new and len(created) == 1, str(created), fatal=True)
        beta_conv = created.pop()
        entry = first_input(beta_conv)
        check("2 its first delivered input is the checkpoint", cp["id"] in entry or (cp.get("title") or "\0") in entry, entry[:160])
        check("2 the input's note names Alpha as the author", ALPHA in entry[:600], entry[:300])
        runs = ro("select id from runs where conversation_id=? order by started_at", (beta_conv,))
        check("3 Beta's turn started", poll(lambda: ro("select 1 from runs where conversation_id=?", (beta_conv,)), 60, 2), "no run")
        runs = ro("select id from runs where conversation_id=? order by started_at", (beta_conv,))
        status = wait_run(runs[0][0])
        check("3 Beta's turn finished", status == "completed", status)
        used = ro("select model from turn_usage where run_id=?", (runs[0][0],))
        check("3 it ran on Beta's runner's model", bool(used) and used[0][0] == HAIKU, str(used))

        after = {alpha_conv: snapshot(alpha_conv), successor: snapshot(successor)}
        check("4 Alpha's original conversation is unchanged", after[alpha_conv] == before[alpha_conv],
              f"{before[alpha_conv]} -> {after[alpha_conv]}")
        check("4 its successor is unchanged", after[successor] == before[successor], f"{before[successor]} -> {after[successor]}")

        alpha_before = conversations_of(pid, ALPHA)
        code, res = api("POST", f"/projects/{pid}/checkpoints/{cp['id']}/start", {"agent": ALPHA})
        check("5 the operator route starts a second conversation", code < 300, f"{code} {str(res)[:200]}", fatal=True)
        poll(lambda: conversations_of(pid, ALPHA) - alpha_before, 30)
        second = conversations_of(pid, ALPHA) - alpha_before
        check("5 it is a new conversation of Alpha", len(second) == 1, str(second), fatal=True)
        alpha_second = second.pop()
        check("5 its first input is the checkpoint without an authorship note",
              ALPHA not in first_input(alpha_second)[:200].replace(cp.get("title") or "", ""), first_input(alpha_second)[:200])
        wait_run_ids = ro("select id from runs where conversation_id=?", (alpha_second,))
        for (run_id,) in wait_run_ids:
            wait_run(run_id)

        lineage_steps(page, pid, cp["id"], [(beta_conv, BETA), (alpha_second, ALPHA)])
        browser.close()


def main():
    hub = base.start_hub()
    pid = None
    try:
        base.TMP.mkdir(parents=True, exist_ok=True)
        root = base.TMP / "project"
        root.mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("# d1106\n\nChecked by the start-from-a-checkpoint drive.\n", encoding="utf-8")
        git(root, "init", "-q", "-b", "master")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "init")
        code, project = api("POST", "/projects/open", {"path": str(root)})
        check("the project opened", code < 300, f"{code} {project}", fatal=True)
        pid = project["id"]
        drive(pid, root)
    except base.Stop:
        pass
    finally:
        # Per-run scratch: the project's row stays in the trial database, the checkout does not.
        if pid:
            api("DELETE", f"/projects/{pid}")
        shutil.rmtree(base.TMP / "project", ignore_errors=True)
        base.stop_hub(hub)
    failed = [n for n, ok in base.results if not ok]
    print("FAILED: " + ", ".join(failed) if failed else "ALL PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

# On master (2026-11-06, AW_DRIVE_PORT=8046, real Haiku turns): setup, the checkpoint and its cutover pass; then
#   FAIL the checkpoint offers a start action -- no checkpoint-start-open on the detail
#   FAILED: the checkpoint offers a start action, 1 the operator starts Beta from the checkpoint in the browser   (exit 1)
# Steps 2-6 have not yet run against a build; the first run on the finished change confirms the test ids and
# the first-input note wording.
