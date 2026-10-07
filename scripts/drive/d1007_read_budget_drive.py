"""Drive `a-specification-is-read-in-results-that-fit` task 3.1 on the trial Hub `:8010`.

A fresh project under `testbed/drive1007-read/` holds a copy of this repository's
`spec/capabilities/agent-conversation-workspace/spec.html` (about 66 KB of default view before the
change), adopted into the Hub. A Haiku agent is told to read every requirement with
`read_spec_document`. Its Claude transcript is then read for the number of read calls, and for a
`tool-results/` spill, which is F363's signature.

Usage: py -3.11 scripts/drive/d1007_read_budget_drive.py
"""

import json
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

HUB = "http://127.0.0.1:8010/api/v1"
KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
DB = pathlib.Path.home() / ".agentweave/hub/profiles/trial/agentweave.db"
REPO = pathlib.Path(__file__).resolve().parents[2]
SOURCE = REPO / "spec/capabilities/agent-conversation-workspace/spec.html"
DOC = "spec/capabilities/agent-conversation-workspace/spec.html"
HAIKU = "claude-haiku-4-5-20251001"


def api(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + path,
        data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]


def ro(sql, args=()):
    connection = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return connection.execute(sql, args).fetchall()
    finally:
        connection.close()


def main():
    root = REPO / "testbed/drive1007-read" / time.strftime("proj-%H%M%S")
    (root / DOC).parent.mkdir(parents=True)
    shutil.copyfile(SOURCE, root / DOC)
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "d@example.invalid"],
        ["git", "config", "user.name", "d"],
        ["git", "add", "."],
        ["git", "commit", "-m", "spec copy"],
    ):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)

    code, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    print("project", code, project if code != 200 and code != 201 else project["id"])
    pid = project["id"]
    A = f"/projects/{pid}"
    code, adopted = api("POST", f"{A}/project/documents/adopt", {"path": DOC})
    print("adopt", code, adopted if isinstance(adopted, str) else adopted.get("id"))
    _, runner = api("POST", f"{A}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    code, agent = api("POST", f"{A}/agents", {"name": "reader", "runner_id": runner["id"]})
    print("agent", code)

    message = (
        f"Use the read_spec_document tool to read `{DOC}`. Read every requirement: if a result "
        "says it is truncated, follow its continue_with until nothing remains. Do not open the "
        "file any other way. Then reply with two numbers: how many distinct requirement "
        "identifiers you read, and how many read_spec_document calls you made."
    )
    code, run = api(
        "POST", f"{A}/agent/trigger", {"agent": "reader", "message": message, "session_mode": "new"}
    )
    print("trigger", code, run)
    run_id = run["run_id"]
    for _ in range(120):
        time.sleep(5)
        (status,) = ro("select status from runs where id=?", (run_id,))[0]
        if status not in ("running", "queued", "starting"):
            break
    (status, session_id) = ro("select status, session_id from runs where id=?", (run_id,))[0]
    print("run", run_id, status, "session", session_id)

    requirements = ro(
        "select count(*) from spec_requirements r join spec_documents d on r.document_id = d.id "
        "where d.project_id=? and d.path=?",
        (pid, DOC),
    )[0][0]
    print("requirements indexed:", requirements)

    transcripts = list((pathlib.Path.home() / ".claude/projects").glob(f"*/{session_id}.jsonl"))
    if not transcripts:
        print("no transcript found for", session_id)
        return 1
    text = transcripts[0].read_text(encoding="utf-8")
    print("transcript", transcripts[0])
    # Either access path: the MCP tool, or `aw-tool read_spec_document` through a shell tool. The
    # first drive (2026-10-07) found the agent used the second, whose spill threshold is lower.
    mcp_calls = shell_calls = spills = 0
    for line in text.splitlines():
        entry = json.loads(line)
        content = entry.get("message", {}).get("content")
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_use":
                if block.get("name") == "mcp__agentweave__read_spec_document":
                    mcp_calls += 1
                elif "aw-tool read_spec_document" in json.dumps(block.get("input")):
                    shell_calls += 1
            if block.get("type") == "tool_result" and "<persisted-output>" in json.dumps(
                block.get("content")
            ):
                spills += 1
    print("read_spec_document calls: mcp", mcp_calls, "aw-tool", shell_calls)
    print("results spilled to tool-results/:", spills)
    final = [json.loads(line) for line in text.splitlines() if '"type":"assistant"' in line]
    if final:
        content = final[-1].get("message", {}).get("content", [])
        print("final reply:", " ".join(c.get("text", "") for c in content if c.get("type") == "text"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
