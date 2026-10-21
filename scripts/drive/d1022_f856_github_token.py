"""Acceptance drive for F856: a GitHub token in prose is redacted like an `sk-` key beside it.

Before: an operator message and an agent reply carrying `ghp_...` stored it verbatim in the run's
trace (`aw.queue.content`, `gen_ai.input.messages`, `gen_ai.output.messages`), the export and the
`text` row, while an `sk-` key in the same string read `<redacted>`. The fake values below are
not credentials.

  py -3.11 scripts/drive/d1022_f856_github_token.py <project-id> [agent]

On a scratch Hub that `e2e.py hub-up` started, with a Haiku agent. One Haiku turn.
"""

import importlib.util
import json
import pathlib
import sys
import time

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

GHP = "ghp_" + "Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2"
PAT = "github_pat_" + "11FAKE0123456789abcdefgh_" + "Fake0123456789" * 4 + "abc"
SK = "sk-" + "fakeOpenAI0123456789abcd"
SHA = "3b3aff3c6d5e8f9a0b1c2d3e4f5a6b7c8d9e0f1a"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(project, agent="alpha"):
    # Quoted from a committed file, as F602's drive does: a model declines to echo
    # credential-shaped text on request, but quotes a file it was asked to read.
    directory = pathlib.Path(
        e2e.ro().execute("select working_directory from projects where id=?", (project,))
        .fetchone()[0]
    )
    (directory / "DEPLOY-NOTES.txt").write_text(
        f"mirror token: {GHP}\nci token: {PAT}\nlast deploy: {SHA}\n", encoding="utf-8"
    )
    for args in (
        ["add", "DEPLOY-NOTES.txt"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "notes"],
    ):
        e2e.subprocess.run(["git", "-C", str(directory), *args])
    # Two turns: a model shown a token in the request declines the whole task (measured on the
    # first run of this drive), so the reply quotes the file, and a second turn carries the
    # operator's own message with a token in it.
    run_id = e2e.cmd_turn(
        project,
        agent,
        "Open DEPLOY-NOTES.txt and quote its three lines back to me exactly, in a code block.",
        fresh=True,
    )
    check("the turn started", run_id is not None)
    if run_id is None:
        return
    e2e.wait_for(run_id, 5)
    said_id = e2e.cmd_turn(
        project, agent, f"For the record, my token is {GHP} and my key is {SK}. Reply only OK.",
        fresh=True,
    )
    check("the second turn started", said_id is not None)
    if said_id is None:
        return
    e2e.wait_for(said_id, 5)
    time.sleep(3)

    rows = e2e.ro().execute(
        "select kind, content, payload from agent_outputs where run_id=? and kind in "
        "('text', 'thinking')",
        (run_id,),
    ).fetchall()
    stored = "\n".join((r["content"] or "") + (r["payload"] or "") for r in rows)
    check("the reply was recorded", bool(rows))
    for label, value in (("ghp_", GHP), ("github_pat_", PAT)):
        check(f"no {label} value in the stored text rows", value[12:] not in stored)
    check("the commit SHA is kept in the text rows", SHA in stored, stored[:200])

    blob, trace_ids = "", set()
    for run in (run_id, said_id):
        status, trace = e2e.request("GET", f"/projects/{project}/traces/by-run/{run}?limit=2000")
        check(f"the trace of {run} answers", status == 200, str(status))
        blob += json.dumps(trace, ensure_ascii=False)
        trace_ids.add(trace.get("trace_id") if isinstance(trace, dict) else None)
    check("the operator's message reached the trace", "my token is" in blob)
    check("the sk- key is not in the traces (the baseline)", SK not in blob)
    check("no ghp_ value in the traces", GHP[4:] not in blob)
    check("no github_pat_ value in the traces", PAT[12:] not in blob)
    check("the commit SHA is kept in the traces", SHA in blob)
    # Only this drive's traces: the export holds every trace the project has, and rows stored
    # before the fix keep what they stored (no backfill).
    status, export = e2e.request("GET", f"/projects/{project}/traces/export")
    ours = [
        span
        for resource in (export.get("resourceSpans", []) if isinstance(export, dict) else [])
        for scope in resource.get("scopeSpans", [])
        for span in scope.get("spans", [])
        if span.get("traceId") in trace_ids
    ]
    xb = json.dumps(ours, ensure_ascii=False)
    check("the export carries this drive's traces", status == 200 and bool(ours), str(status))
    check("no ghp_ value in the export", GHP[4:] not in xb)
    check("no github_pat_ value in the export", PAT[12:] not in xb)

    status, res = e2e.request(
        "POST", f"/projects/{project}/agents/{agent}/output",
        {"kind": "text", "content": f"pushed {SHA} with {GHP}"},
    )
    check("the operator output route accepts it", status in (200, 201), f"{status} {str(res)[:120]}")
    latest = e2e.ro().execute(
        "select content from agent_outputs where agent=? order by timestamp desc limit 1", (agent,)
    ).fetchone()["content"]
    check("the operator route stores no ghp_ value", GHP[4:] not in latest, latest[:120])
    check("and keeps the SHA", SHA in latest, latest[:120])


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
