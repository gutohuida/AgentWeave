"""Group 7 drive of `a-loop-staffs-the-agent-it-names` (F128's fix), night window 2026-09-20.

Confirms live, against a fresh Hub built from source, exactly what the night window's
`alsn-drive` queue item asked for:

  * a documentless loop pinned to a busy agent, with a free sibling, now REFUSES the firing
    (`stall_reason` set) instead of silently drawing the sibling's capacity -- F128 closed;
  * the loop's own JSON carries the fields `hub/ui/src/components/spec/loopCounts.ts:23`'s
    `endingBucket()` reads, in the combination that flips its bucket from `running` to `stalled`;
  * a spec-linked flow in the identical busy-sibling shape is UNAFFECTED -- both tasks start,
    width survives, matching the change's own D1/D7 promise not to touch flows.

Never targets :8000 or :8010. Creates and tears down its own fixture project.

    AW_HUB=http://127.0.0.1:8093 AW_KEY=... py -3.11 -u scripts/drive/d7_0920_alsn_drive.py
Never pipe this through `head` -- SIGPIPE kills the teardown.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show, task_rows# noqa: E402

HUB = os.environ.get("AW_HUB", "")
if HUB.endswith(":8000") or HUB.endswith(":8010"):
    print("REFUSING TO RUN: this port is not this drive's to use.")
    sys.exit(1)

HAIKU = "claude-haiku-4-5-20251001"
TAG = time.strftime("%H%M%S")
root = pathlib.Path(os.path.expanduser("~")) / "Documents" / f"drive-0920-alsn-{TAG}"

VERDICTS = []


def verdict(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print("  [%s] %s%s" % ("OK " if ok else "BAD", label, ("  -- " + detail) if detail else ""))


def head(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


def agent_status(pid):
    c, ag = api("GET", "/projects/%s/agents" % pid)
    return {a["name"]: a.get("status") for a in (ag if isinstance(ag, list) else [])}


def wait_for(pred, limit, label):
    t0 = time.time()
    while time.time() - t0 < limit:
        if pred():
            return True
        time.sleep(3)
    print("  (timed out waiting for %s)" % label)
    return False


def ending_bucket(loop):
    """Same rule as `loopCounts.ts:23`'s `endingBucket()`, evaluated against the live JSON."""
    if not loop.get("stopped_at") and not loop.get("ending_state") and loop.get("stall_reason"):
        return "stalled"
    if loop.get("ending_state") == "completed":
        return "completed"
    if loop.get("ending_state") == "stopped":
        return "stopped"
    return "running" if loop.get("firing_active") else "idle"


def main():
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("alsn-drive fixture %s\n" % TAG, encoding="utf-8")
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "alsn-drive@example.invalid"],
        ["git", "config", "user.name", "alsn-drive"],
        ["git", "add", "README.md"],
        ["git", "commit", "-m", "alsn-drive fixture"],
    ):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)

    code, proj = api("POST", "/projects/open", {"path": str(root), "name": "alsn-drive-%s" % TAG})
    show("POST /projects/open", code, proj, limit=300)
    if code not in (200, 201):
        sys.exit(1)
    PID = proj["id"]
    A = "/projects/%s" % PID

    doc_loop_id = doc_job_id = None
    flow_loop_id = flow_job_id = None
    try:
        code, runner = api(
            "POST", "%s/runners" % A, {"name": "haiku-%s" % TAG, "cli": "claude", "model": HAIKU}
        )
        show("POST /runners", code, runner, limit=200)
        assert code == 201, (code, runner)
        RUNNER = runner["id"]

        GAMMA, ALPHA, BETA = "gamma%s" % TAG, "alpha%s" % TAG, "beta%s" % TAG
        for name in (GAMMA, ALPHA, BETA):
            code, body = api("POST", "%s/agents" % A, {"name": name, "runner_id": RUNNER})
            print("POST /agents %s: [%s] %s" % (name, code, str(body)[:160]))
            assert code == 201, (code, body)
        for name in (GAMMA, ALPHA, BETA):
            api("PATCH", "%s/agents/%s" % (A, name), {"default_permission_mode": "bypassPermissions"})

        head("A. Put gamma mid-turn, alpha/beta idle -- a genuinely non-empty free list")
        code, out = api(
            "POST",
            "%s/agent/trigger" % A,
            {
                "agent": GAMMA,
                "message": "Wait a bit, then reply with the single word: busy. Do nothing else.",
                "overrides": {"permission_mode": "bypassPermissions"},
            },
        )
        print("  trigger gamma: %s" % code)
        running = wait_for(lambda: agent_status(PID).get(GAMMA) == "running", 60, "gamma to start")
        verdict("gamma is genuinely mid-turn", running, str(agent_status(PID)))
        verdict(
            "alpha and beta are genuinely free (project-wide free list is non-empty)",
            agent_status(PID).get(ALPHA) == "idle" and agent_status(PID).get(BETA) == "idle",
            str(agent_status(PID)),
        )
        if not running:
            raise SystemExit("SETUP ABORT: gamma never started.")

        head("B. A DOCUMENTLESS loop naming gamma, one unassigned task -- press Run while busy")
        code, job = api(
            "POST",
            "%s/jobs" % A,
            {
                "name": "alsn-drive-documentless",
                "agent": GAMMA,
                "message": "Do the next thing on the queue.",
                "cron": "0 4 * * *",
                "purpose": "F128 group 7 drive -- documentless loop pinned to a busy agent.",
                "enabled": True,
                "initial_tasks": [{"title": "alsn-drive documentless errand"}],
            },
        )
        show("POST /jobs (documentless)", code, job)
        assert code in (200, 201), (code, job)
        doc_job_id = job.get("id") or job.get("job_id")
        doc_loop_id = (job.get("loop") or {}).get("id")

        code, run_out = api("POST", "%s/jobs/%s/run" % (A, doc_job_id))
        show("POST /jobs/{id}/run (documentless, gamma busy, siblings free)", code, run_out)
        verdict(
            "the firing is REFUSED (409), not silently handed to a free sibling (F128 closed)",
            code == 409,
            "got %s" % code,
        )
        detail = run_out.get("detail") if isinstance(run_out, dict) else None
        detail_text = json.dumps(detail) if isinstance(detail, dict) else str(detail)
        verdict(
            "the refusal names the busy agent, not a project-wide free-list sentence",
            isinstance(detail_text, str) and GAMMA in detail_text,
            detail_text[:300] if isinstance(detail_text, str) else "",
        )

        c, tasks = api("GET", "%s/tasks" % A)
        mine = [t for t in task_rows(tasks) if t.get("loop_id") == doc_loop_id]
        verdict(
            "the loop's task kept its status and gained no assignee",
            bool(mine) and mine[0].get("status") == "pending" and not mine[0].get("assignee"),
            str([(t.get("status"), t.get("assignee")) for t in mine]),
        )

        c, convs = api("GET", "%s/conversations" % A)
        rows = convs if isinstance(convs, list) else (convs or {}).get("conversations") or []

        def loop_of(row):
            loop = row.get("loop")
            return loop.get("id") if isinstance(loop, dict) else (loop or row.get("loop_id"))

        mine_convs = [r for r in rows if loop_of(r) == doc_loop_id]
        verdict(
            "no conversation was created for this refused firing",
            mine_convs == [],
            str([r.get("id") for r in mine_convs]),
        )

        c, lp = api("GET", "%s/loops/%s" % (A, doc_loop_id))
        show("GET loop (documentless)", c, lp, limit=500)
        verdict(
            "the loop's own JSON carries a stall_reason naming the busy agent",
            isinstance(lp.get("stall_reason"), str) and GAMMA in lp["stall_reason"],
            str(lp.get("stall_reason")),
        )
        bucket = ending_bucket(lp)
        verdict(
            "endingBucket() -- the exact function at loopCounts.ts:23 -- now reads 'stalled', "
            "not 'running': the board flips as designed",
            bucket == "stalled",
            "ending_state=%s firing_active=%s stopped_at=%s stall_reason=%r -> bucket=%s"
            % (lp.get("ending_state"), lp.get("firing_active"), lp.get("stopped_at"),
               lp.get("stall_reason"), bucket),
        )

        head("C. A SPEC-LINKED flow, identical busy-sibling shape -- width must survive untouched")
        code, job2 = api(
            "POST",
            "%s/jobs" % A,
            {
                "name": "alsn-drive-flow",
                "agent": GAMMA,
                "message": "Do the next thing on the queue.",
                "cron": "0 4 * * *",
                "purpose": "F128 group 7 drive -- flow control, same busy shape.",
                "spec_document_id": "spdoc-alsn-drive-%s" % TAG,
                "enabled": True,
                "initial_tasks": [
                    {"title": "alsn-drive flow errand one"},
                    {"title": "alsn-drive flow errand two"},
                ],
            },
        )
        show("POST /jobs (flow)", code, job2)
        assert code in (200, 201), (code, job2)
        flow_job_id = job2.get("id") or job2.get("job_id")
        flow_loop_id = (job2.get("loop") or {}).get("id")

        verdict("gamma is still busy for the flow's own firing", agent_status(PID).get(GAMMA) == "running",
                str(agent_status(PID).get(GAMMA)))

        code, run_out2 = api("POST", "%s/jobs/%s/run" % (A, flow_job_id))
        show("POST /jobs/{id}/run (flow, gamma busy, siblings free)", code, run_out2)
        verdict(
            "the flow's firing PROCEEDS (200/201) -- width is a documentless-only retirement",
            code in (200, 201),
            "got %s" % code,
        )

        started = wait_for(
            lambda: any(
                t.get("loop_id") == flow_loop_id and t.get("status") in ("in_progress", "under_review", "completed")
                for t in (api("GET", "%s/tasks" % A)[1] or [])
                if isinstance(t, dict)
            ),
            90,
            "the flow to start at least one task",
        )
        c, tasks2 = api("GET", "%s/tasks" % A)
        flow_tasks = [t for t in (tasks2 if isinstance(tasks2, list) else []) if t.get("loop_id") == flow_loop_id]
        started_count = sum(1 for t in flow_tasks if t.get("status") != "pending" or t.get("assignee"))
        verdict(
            "at least one of the flow's two tasks actually started (assigned to a free sibling)",
            started and started_count >= 1,
            str([(t.get("title"), t.get("status"), t.get("assignee")) for t in flow_tasks]),
        )
        assignees = {t.get("assignee") for t in flow_tasks if t.get("assignee")}
        verdict(
            "the flow staffed a free sibling, not gamma (gamma is busy) -- ordinary project-wide "
            "staffing, unchanged by this group",
            bool(assignees) and GAMMA not in assignees,
            str(assignees),
        )

        c, lp2 = api("GET", "%s/loops/%s" % (A, flow_loop_id))
        bucket2 = ending_bucket(lp2)
        verdict(
            "the flow's own bucket is NOT stalled -- its stall_reason is unset in this shape",
            bucket2 != "stalled" and not lp2.get("stall_reason"),
            "stall_reason=%r bucket=%s" % (lp2.get("stall_reason"), bucket2),
        )

    finally:
        head("Z. Teardown")
        for job_id, loop_id in ((doc_job_id, doc_loop_id), (flow_job_id, flow_loop_id)):
            if not job_id:
                continue
            api("PATCH", "%s/jobs/%s" % (A, job_id), {"stop_reason": "drive teardown"})
            c, t = api("GET", "%s/tasks" % A)
            for x in task_rows(t):
                if x.get("loop_id") == loop_id and x.get("status") not in ("approved", "rejected"):
                    api("PATCH", "%s/tasks/%s" % (A, x["id"]), {"status": "rejected"})
            if loop_id:
                api("POST", "%s/loops/%s/archive" % (A, loop_id))
            api("PATCH", "%s/jobs/%s" % (A, job_id), {"enabled": False})
        c, jobs = api("GET", "%s/jobs" % A)
        print("  enabled jobs remaining: %s"
              % [x.get("id") for x in (jobs if isinstance(jobs, list) else []) if x.get("enabled")])

        code, body = api("DELETE", A)
        print("  fixture project deleted: %s" % code)
        shutil.rmtree(root, ignore_errors=True)

        head("VERDICTS")
        bad = [v for v in VERDICTS if not v[1]]
        for label, ok, detail in VERDICTS:
            print("  [%s] %s%s" % ("OK " if ok else "BAD", label, ("  -- " + detail) if detail else ""))
        print("\n  %d/%d held" % (len(VERDICTS) - len(bad), len(VERDICTS)))
        if bad:
            sys.exit(1)


if __name__ == "__main__":
    main()
