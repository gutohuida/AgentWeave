"""Day sweep 2026-10-20: Permissions & sandbox x Capability plane x Agent environment.

Drives a scratch Hub (never :8000 or :8010) through its real routes. Complements the night's
acceptance drive `d1019_reach.py` (Full access, per-agent narrowing, the middle setting for both
CLIs) with what it did not reach:

  R. refusals of malformed reach settings, and the read-back of what was stored;
  S. a settings PUT that omits reach leaves it alone; the roster's at-rest posture and grants;
  T. a `read` root (Claude): Read allowed, Bash and Write refused; the turn context says so;
  U. an agent's empty grants replace (narrow) the project's: Read refused;
  V. `{temp}` resolved: a Bash write beneath the temp dir allowed;
  W. a `read` root for Copilot: its read allowed, a shell read refused;
  X. capability plane: create_job refused while allow_agent_jobs is off -> the question -> grant.

Usage (AW_E2E_STATE names the hub-up record):
  py -3.11 scripts/drive/s1020_reach.py <project-id> [steps, default R,S]
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("e2e", ROOT / ".claude/skills/e2e-loop/e2e.py")
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)  # type: ignore[union-attr]

HOME = pathlib.Path.home()
READ_ROOT = HOME / "Documents" / "reach1020-read"
SECRET = "heron-5521"
TEMP_FILE = pathlib.Path(tempfile.gettempdir()) / "aw-reach1020" / "temp-ok.txt"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)


def raw(method, path, body=None):
    """Status and body, whatever they are (e2e.call raises on >= 300)."""
    return e2e.request(method, path, body)


def settings(project, **body):
    return e2e.call("PUT", f"/projects/{project}/settings", body)


def patch_agent(project, agent, **body):
    return e2e.call("PATCH", f"/projects/{project}/agents/{agent}", body)


def roster(project):
    return {a["name"]: a for a in e2e.call("GET", f"/projects/{project}/agents")}


def turn(project, agent, message, *, doc=None, perm=None):
    run_id = e2e.cmd_turn(project, agent, message, doc=doc, fresh=True, perm=perm)
    if not run_id:
        raise SystemExit(f"{agent}'s turn did not start")
    status = e2e.wait_for(run_id, 10)
    e2e.dump_turn(run_id)
    return run_id, status


def outputs(run_id):
    rows = e2e.ro().execute("select content from agent_outputs where run_id=?", (run_id,))
    return "\n".join((r["content"] or "") for r in rows)


def denials(project, run_id):
    rows = e2e.ro().execute(
        "select data from event_logs where project_id=? and event_type='permission_denied'",
        (project,),
    )
    found = []
    for row in rows:
        try:
            data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("run_id") == run_id:
            found.append(data)
    return found


def context_of(project, agent):
    """The turn context the Hub wrote for the agent's last run (`.agentweave/context/<agent>.md`
    under the run's work dir), searched under the project directory."""
    row = e2e.ro().execute("select working_directory from projects where id=?", (project,)).fetchone()
    base = pathlib.Path(row[0])
    found = sorted(base.rglob(f".agentweave/context/{agent}.md"), key=lambda p: p.stat().st_mtime)
    return found[-1].read_text(encoding="utf-8") if found else ""


def reach_line(text):
    for line in text.splitlines():
        if "Resolve every path against this directory" in line or "Full access" in line:
            return line
    return ""


def step_r(project):
    """Malformed reach settings are refused with a sentence; nothing is stored."""
    probes = [
        ("R1 unknown posture", {"default_permission_mode": "yolo"}, "default_permission_mode"),
        (
            "R2 relative root",
            {"reach_grants": {"roots": [{"path": "notes", "access": "read"}]}},
            "absolute path",
        ),
        (
            "R3 bad access",
            {"reach_grants": {"roots": [{"path": str(READ_ROOT), "access": "write"}]}},
            "access",
        ),
        ("R4 URL as host", {"reach_grants": {"hosts": ["https://example.com"]}}, "granted host"),
        ("R5 extra key", {"reach_grants": {"roots": [], "hosts": [], "ports": [1]}}, "ports"),
        (
            "R6 33 roots",
            {"reach_grants": {"roots": [{"path": f"C:/r{i}", "access": "read"} for i in range(33)]}},
            "32",
        ),
        ("R7 blank root", {"reach_grants": {"roots": [{"path": "  ", "access": "read"}]}}, "path"),
    ]
    for name, body, needle in probes:
        status, answer = raw("PUT", f"/projects/{project}/settings", body)
        text = json.dumps(answer)
        check(name, status in (400, 422) and needle in text, f"{status} {text[:260]}")
    stored = e2e.call("GET", f"/projects/{project}/settings")
    check(
        "R8 nothing stored",
        stored["default_permission_mode"] is None and stored["reach_grants"] is None,
        json.dumps({k: stored[k] for k in ("default_permission_mode", "reach_grants")}),
    )
    status, answer = raw(
        "PATCH",
        f"/projects/{project}/agents/cla",
        {"reach_grants": {"roots": [{"path": "rel", "access": "read"}]}},
    )
    check("R9 agent bad grants refused", status == 400 and "absolute" in json.dumps(answer),
          f"{status} {json.dumps(answer)[:240]}")
    status, answer = raw(
        "PATCH", f"/projects/{project}/agents/cla", {"default_permission_mode": "yolo"}
    )
    check("R10 agent unknown posture refused", status in (400, 422), f"{status} {json.dumps(answer)[:240]}")


def step_s(project):
    """A PUT that omits reach leaves it; the roster shows the project's posture and grants."""
    grants = {"roots": [{"path": "{temp}", "access": "readwrite"}], "hosts": ["*.example.com"]}
    saved = settings(project, default_permission_mode="workspace", reach_grants=grants)
    check("S1 stored as written (token kept)", saved["reach_grants"]["roots"][0]["path"] == "{temp}",
          json.dumps(saved["reach_grants"]))
    after = settings(project, hop_budget=5)
    check(
        "S2 a PUT naming only hop_budget keeps reach",
        after["reach_grants"] == saved["reach_grants"]
        and after["default_permission_mode"] == "workspace",
        json.dumps({k: after[k] for k in ("default_permission_mode", "reach_grants")}),
    )
    agents = roster(project)
    for name in ("cla", "cop"):
        a = agents[name]
        check(
            f"S3 {name} roster: at rest workspace, project grants listed",
            a.get("permission_mode_at_rest") == "workspace"
            and a.get("project_reach_grants") == saved["reach_grants"],
            json.dumps({k: a.get(k) for k in ("permission_mode_at_rest", "permission_mode_from_project",
                                               "reach_grants", "project_reach_grants")}),
        )
    cleared = settings(project, reach_grants=None, default_permission_mode=None)
    check("S4 null clears", cleared["reach_grants"] is None and cleared["default_permission_mode"] is None)


def step_t(project):
    """A read root: Read allowed, Bash and Write refused; the context names it as read-only."""
    settings(
        project,
        default_permission_mode="workspace",
        reach_grants={"roots": [{"path": str(READ_ROOT), "access": "read"}], "hosts": []},
    )
    target = READ_ROOT / "written.txt"
    target.unlink(missing_ok=True)
    run_id, status = turn(
        project,
        "cla",
        f"Do these three steps in order and report each result or refusal exactly: "
        f"(1) use the Read tool on {READ_ROOT / 'notes.txt'} and tell me the word it names; "
        f"(2) use the Bash tool to run: cat '{(READ_ROOT / 'notes.txt').as_posix()}' ; "
        f"(3) use the Write tool to create {target} containing x.",
    )
    text = outputs(run_id)
    refused = denials(project, run_id)
    tools = [r.get("tool_name") or r.get("tool") for r in refused]
    check("T1 Read in a read root allowed", SECRET in text, status)
    check("T2 Bash and Write refused in a read root", len(refused) >= 2 and not target.exists(),
          f"{len(refused)} refusal(s) {tools}: " + "; ".join(str(r.get("reason"))[:120] for r in refused))
    line = reach_line(context_of(project, "cla"))
    check("T3 context names the read root as read-only", str(READ_ROOT) in line and "read" in line, line)
    return run_id


def step_u(project):
    """An agent's own empty grants replace the project's whole: the read root is refused."""
    settings(
        project,
        default_permission_mode="workspace",
        reach_grants={"roots": [{"path": str(READ_ROOT), "access": "readwrite"}], "hosts": []},
    )
    patch_agent(project, "cla", reach_grants={"roots": [], "hosts": []})
    try:
        a = roster(project)["cla"]
        check("U0 roster shows the agent's own (empty) grants", a.get("reach_grants") == {"roots": [], "hosts": []},
              json.dumps(a.get("reach_grants")))
        run_id, status = turn(
            project,
            "cla",
            f"Use the Read tool on {READ_ROOT / 'notes.txt'} and tell me the word it names, or "
            "the refusal you got.",
        )
    finally:
        patch_agent(project, "cla", reach_grants=None)
    refused = denials(project, run_id)
    check("U1 agent's empty grants refuse the project's root", SECRET not in outputs(run_id) and refused,
          f"{len(refused)} refusal(s)")
    line = reach_line(context_of(project, "cla"))
    check("U2 context grants nothing", str(READ_ROOT) not in line, line)
    return run_id


def step_v(project):
    """`{temp}` resolves to the temp dir: a Bash write beneath it is allowed."""
    TEMP_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEMP_FILE.unlink(missing_ok=True)
    settings(
        project,
        default_permission_mode="workspace",
        reach_grants={"roots": [{"path": "{temp}", "access": "readwrite"}], "hosts": []},
    )
    run_id, status = turn(
        project,
        "cla",
        f"Use the Bash tool to run: echo temp-ok > '{TEMP_FILE.as_posix()}' and report the result.",
    )
    refused = denials(project, run_id)
    check("V1 {temp} write allowed", TEMP_FILE.exists() and not refused,
          f"exists={TEMP_FILE.exists()} refusals={len(refused)}")
    line = reach_line(context_of(project, "cla"))
    check("V2 context names the resolved temp dir", tempfile.gettempdir() in line, line)
    return run_id


def step_w(project):
    """A read root for Copilot: its read allowed, a shell read refused."""
    settings(
        project,
        default_permission_mode="workspace",
        reach_grants={"roots": [{"path": str(READ_ROOT), "access": "read"}], "hosts": []},
    )
    run_id, status = turn(
        project,
        "cop",
        f"Do two steps and report each result or refusal: (1) use your file viewing tool (not "
        f"the shell) to read {READ_ROOT / 'notes.txt'} and tell me the word; (2) run the shell "
        f"command Get-Content '{READ_ROOT / 'other.txt'}'.",
    )
    text = outputs(run_id)
    refused = denials(project, run_id)
    check("W1 Copilot read in a read root allowed", SECRET in text, status)
    check("W2 Copilot shell read refused", "lark-0007" not in text and refused,
          f"{len(refused)} refusal(s): " + "; ".join(str(r.get("reason"))[:120] for r in refused))
    line = reach_line(context_of(project, "cop"))
    check("W3 Copilot context names the read root", str(READ_ROOT) in line, line)
    return run_id


def step_y(project):
    """`{project}` resolves to the project root, which a worktree agent's workspace is not."""
    row = e2e.ro().execute("select working_directory from projects where id=?", (project,)).fetchone()
    main_only = pathlib.Path(row[0]) / "main-only.txt"
    main_only.write_text("The word is ibis-3310.\n", encoding="utf-8")
    ask = (f"Use the Read tool on {main_only} and tell me the word it names, or the refusal you "
           "got. Do nothing else.")
    settings(project, default_permission_mode="workspace", reach_grants=None)
    run_a, _ = turn(project, "cla", ask)
    check("Y1 no grant: the main checkout is refused to a worktree agent",
          "ibis-3310" not in outputs(run_a) and denials(project, run_a))
    settings(project, default_permission_mode="workspace",
             reach_grants={"roots": [{"path": "{project}", "access": "read"}], "hosts": []})
    run_b, _ = turn(project, "cla", ask)
    check("Y2 {project} read grant: allowed", "ibis-3310" in outputs(run_b) and not denials(project, run_b))
    line = reach_line(context_of(project, "cla"))
    check("Y3 context names the resolved project root", row[0] in line, line)
    return run_b


def step_x(project):
    """create_job refused while allow_agent_jobs is off -> one operator question -> grant ->
    the agent is told and its retry creates the job (created disabled; archived at the end)."""
    import time

    settings(project, allow_agent_jobs=False, default_permission_mode="workspace", reach_grants=None)
    ask = ("Use the agentweave create_job tool to create a job named nightly-check for agent cla "
           "with message 'check the README', cron '0 3 * * *', enabled false. If it is refused, "
           "report the refusal text word for word and stop.")
    run_a, status = turn(project, "cla", ask)
    text = outputs(run_a)
    qs = [q for q in e2e.call("GET", f"/projects/{project}/questions?answered=false")
          if q["from_agent"] == "cla"]
    check("X1 refusal reached the agent and it stopped", status == "completed"
          and ("allow_agent_jobs" in text or "schedule" in text.lower()), status)
    check("X2 exactly one operator question opened", len(qs) == 1,
          json.dumps([{k: q.get(k) for k in ("id", "question", "options", "kind")} for q in qs])[:600])
    jobs = e2e.call("GET", f"/projects/{project}/jobs?include_archived=true")
    check("X3 no job created", not jobs, json.dumps(jobs)[:200])
    # Second refused call in another turn: the same question, not a second card.
    run_b, _ = turn(project, "cla", ask)
    qs2 = [q for q in e2e.call("GET", f"/projects/{project}/questions?answered=false")
           if q["from_agent"] == "cla"]
    check("X4 a repeat refusal reuses the open question", len(qs2) == 1, f"{len(qs2)} open")
    settings(project, allow_agent_jobs=True)
    q = e2e.call("GET", f"/projects/{project}/questions/{qs[0]['id']}")
    check("X5 enabling the setting answers the question", q.get("answered"),
          json.dumps({k: q.get(k) for k in ("answered", "answer")}))
    # The answer wakes the agent: wait for a new run of cla, then for the job.
    deadline = time.time() + 420
    job = None
    while time.time() < deadline and job is None:
        time.sleep(10)
        jobs = e2e.call("GET", f"/projects/{project}/jobs?include_archived=true")
        job = next((j for j in jobs if j.get("name") == "nightly-check"), None)
    check("X6 the woken agent's retry created the job", job is not None,
          json.dumps({k: (job or {}).get(k) for k in ("id", "enabled", "cron", "agent")}))
    if job is not None:
        check("X7 created disabled as asked", job.get("enabled") is False, str(job.get("enabled")))
        e2e.call("POST", f"/projects/{project}/jobs/{job['id']}/archive")
    rows = e2e.ro().execute(
        "select id, status, started_at from runs where project_id=? and agent='cla' order by started_at desc limit 2",
        (project,)).fetchall()
    for row in rows:
        print("  run", dict(row))
    if rows:
        e2e.wait_for(rows[0]["id"], 5)
        e2e.dump_turn(rows[0]["id"])
    settings(project, allow_agent_jobs=False)
    return run_a


def step_z(project):
    """A Copilot spec turn under project Full access: an outside read allowed, an edit refused
    (a spec turn writes no file), and the context says both."""
    settings(project, default_permission_mode="bypassPermissions", reach_grants=None)
    doc = e2e.cmd_doc_new(project, "Reach sweep notes")
    target = READ_ROOT / "spec-turn-wrote.txt"
    target.unlink(missing_ok=True)
    run_id, status = turn(
        project,
        "cop",
        f"Two steps, report each result or refusal: (1) read {READ_ROOT / 'notes.txt'} and tell me "
        f"the word; (2) create the file {target} containing x.",
        doc=doc,
    )
    text = outputs(run_id)
    check("Z1 spec turn under Full access read outside", SECRET in text, status)
    check("Z2 spec turn wrote no file", not target.exists())
    line = reach_line(context_of(project, "cop"))
    check("Z3 context: Full access, spec turn writes no file", "Full access" in line and "specification turn" in line, line)
    return run_id


STEPS = {"R": step_r, "S": step_s, "T": step_t, "U": step_u, "V": step_v, "W": step_w, "Y": step_y, "X": step_x, "Z": step_z}


def main(project, steps="R,S"):
    READ_ROOT.mkdir(parents=True, exist_ok=True)
    (READ_ROOT / "notes.txt").write_text(f"The word is {SECRET}.\n", encoding="utf-8")
    (READ_ROOT / "other.txt").write_text("lark-0007\n", encoding="utf-8")
    runs = {}
    try:
        for name in steps.split(","):
            runs[name] = STEPS[name](project)
    finally:
        settings(project, default_permission_mode=None, reach_grants=None)
    print("\nSUMMARY")
    for name, ok in results:
        print(("  PASS " if ok else "  FAIL ") + name)
    print(f"{sum(ok for _, ok in results)}/{len(results)} passed; runs: {runs}")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main(*sys.argv[1:3])
