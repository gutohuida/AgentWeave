"""Acceptance drive for `the-agent-budget-caps-concurrent-runs` (F557), 2026-10-10.

The change's `drive` criterion (spdoc-4cd731c8dba3 on :8010, task drive-first). Starts its own Hub on
:8109 with a fresh database (never :8000 or :8010). One project, one Claude runner, two Haiku agents
alice and bob (permission mode bypassPermissions, so a command never stalls on an approval card), and
the project's agent budget set to 1 through PUT /projects/{id}/settings.

The drive sends alice and then bob, back to back through POST /agent/trigger, "run `sleep 15`, then
reply with the single word done", and checks, in order:

  1. while the first agent's run is running the other has no running run, and the other's queue
     status (GET /queue/{agent}/status, the operator's surface) is waiting with a reason naming the
     cap. Sampled every quarter second for the whole of the first run;
  2. the other's run starts after the first one ends, with no further action from the drive;
  3. both runs' replies say done.

Which agent runs first is the scheduler's; the drive asks only that one waits for the other. The
contract it fixes for the build: the waiting reason contains "cap" (the spec's sentence is
"project run cap reached (1/1)").

Fails on today's Hub at check 1 (both run at once). Stops at the first failure. Two Haiku turns.

    py -3.11 scripts/drive/d1023_run_cap.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402

d.PORT = 8109
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1023-run-cap" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

AGENTS = ("alice", "bob")
MESSAGE = "Run the shell command `sleep 15`, then reply with the single word done."
ENDED = ("running", "queued", "starting", "pending")


def runs(agent):
    """The agent's runs, oldest first, as (id, status, started_at, ended_at)."""
    return d.ro(
        "select id, status, started_at, ended_at from runs where agent=? order by rowid", (agent,)
    )


def running(agent):
    return any(row[1] == "running" for row in runs(agent))


def reply(run_id):
    rows = d.ro(
        "select content from agent_outputs where run_id=? and kind='text' order by sequence",
        (run_id,),
    )
    return "\n".join(row[0] or "" for row in rows)


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# run cap\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "runcap"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    d.api("PATCH", base, {"main_branch": "main"})
    _, runner = d.api(
        "POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU}
    )
    for name in AGENTS:
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        assert code in (200, 201), (code, out)
        code, out = d.api(
            "PATCH", f"{base}/agents/{name}", {"default_permission_mode": "bypassPermissions"}
        )
        assert code == 200, (code, out)
    code, settings = d.api("GET", f"{base}/settings")
    assert code == 200, (code, settings)
    settings["agent_budget"] = 1
    code, out = d.api("PUT", f"{base}/settings", settings)
    assert code == 200, (code, out)
    code, settings = d.api("GET", f"{base}/settings")
    assert settings.get("agent_budget") == 1, settings

    answers = {}
    for name in AGENTS:
        code, out = d.api("POST", f"{base}/agent/trigger", {"agent": name, "message": MESSAGE}, 120)
        assert code in (200, 201, 202), (name, code, out)
        answers[name] = out
    print("trigger answers:", {n: (a.get("status"), a.get("waiting_reason")) for n, a in answers.items()})

    # 1: while the first run is running, the other agent has none running and waits on the cap.
    d.poll(lambda: any(running(name) for name in AGENTS), 90)
    first = next((name for name in AGENTS if running(name)), None)
    assert first is not None, "no run started within 90 s"
    other = AGENTS[1] if first == AGENTS[0] else AGENTS[0]
    first_run = runs(first)[-1][0]
    both_running = 0
    samples = 0
    reasons = set()
    while d.ro("select status from runs where id=?", (first_run,))[0][0] == "running":
        samples += 1
        if running(other):
            both_running += 1
        code, status = d.api("GET", f"{base}/queue/{other}/status")
        if code == 200:
            reasons.add((status.get("waiting_count"), status.get("waiting_reason")))
        if both_running and samples > 8:
            break  # the cap is already broken; nothing later changes check 1's answer
        time.sleep(0.25)
    capped = any(count and reason and "cap" in reason for count, reason in reasons)
    d.check(
        "1 while the first run is running the other agent has no running run and waits on the cap",
        both_running == 0 and capped,
        f"first={first} samples={samples} both_running={both_running} other_status={sorted(map(str, reasons))}",
    )

    # 2: the other's run starts after the first ends, with no action from the drive.
    d.poll(lambda: bool(runs(other)), 120)
    first_ended = d.ro("select ended_at from runs where id=?", (first_run,))[0][0]
    other_rows = runs(other)
    d.check(
        "2 the other agent's run starts after the first one ends, with no further action",
        bool(other_rows) and first_ended is not None and other_rows[0][2] >= first_ended,
        f"first_ended={first_ended} other_runs={other_rows}",
    )

    # 3: both replies say done.
    other_run = other_rows[0][0]
    d.poll(lambda: d.ro("select status from runs where id=?", (other_run,))[0][0] not in ENDED, 180)
    replies = {first: reply(first_run), other: reply(other_run)}
    (d.TMP / "replies.txt").write_text(repr(replies), encoding="utf-8")
    d.check(
        "3 both replies say done",
        all("done" in text.lower() for text in replies.values()),
        f"replies={ {name: text[-120:] for name, text in replies.items()} }",
    )


d.drive = drive

if __name__ == "__main__":
    d.main()
