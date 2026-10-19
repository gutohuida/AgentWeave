"""Acceptance drive for `an-operator-sets-how-far-an-agent-reaches` (reach-1019).

Drives a scratch Hub (never :8000 or :8010) through its real routes with real agents: a Copilot
agent `cop` on claude-haiku-4.5 (three Copilot turns: A, B, D) and a Claude agent `cla` on Haiku.
Proves:

  A. project Full access reaches a Copilot run: it writes outside the workspace, and the write is
     recorded on the run row (reach-4);
  B. a Copilot specification turn under project Full access reads outside the workspace;
  C. an agent's own default (Workspace only) narrows the project's Full access: refused (Claude);
  D. the middle setting -- project Workspace only plus a granted root and host -- allows the
     granted root and host and still refuses an ungranted root (Copilot);
  E. the same middle setting for Claude: granted root written, ungranted root and host refused.

Usage (the Hub must already be up on AW_HUB, with AW_HUB_DB set):
  py -3.11 scripts/drive/d1019_reach.py <project-id> [steps, default A,B,C,D,E]
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("e2e", ROOT / ".claude/skills/e2e-loop/e2e.py")
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)  # type: ignore[union-attr]

HOME = pathlib.Path.home()
OUTSIDE = HOME / "Documents" / "reach1019-granted"
OTHER = HOME / "Documents" / "reach1019-ungranted"
SECRET = "pelican-4417"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""))


def settings(project, **body):
    return e2e.call("PUT", f"/projects/{project}/settings", body)


def patch_agent(project, agent, **body):
    return e2e.call("PATCH", f"/projects/{project}/agents/{agent}", body)


def turn(project, agent, message, *, doc=None):
    run_id = e2e.cmd_turn(project, agent, message, doc=doc, fresh=True)
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


def outside_record(run_id):
    row = e2e.ro().execute(
        "select outside_workspace_writes from runs where id=?", (run_id,)
    ).fetchone()
    return json.loads(row[0]) if row and row[0] else None


def step_a(project):
    """Project Full access reaches a Copilot run; its outside write is on the run row."""
    target = OUTSIDE / "cop-full.txt"
    target.unlink(missing_ok=True)
    saved = settings(project, default_permission_mode="bypassPermissions", reach_grants=None)
    check("A0 project default saved", saved["default_permission_mode"] == "bypassPermissions")
    roster = {a["name"]: a for a in e2e.call("GET", f"/projects/{project}/agents")}
    check(
        "A0 roster at-rest posture is the project's",
        roster["cop"]["permission_mode_at_rest"] == "bypassPermissions",
        roster["cop"]["permission_mode_at_rest"],
    )
    run_id, status = turn(
        project,
        "cop",
        f"Create the file {target} containing exactly the text full-access-ok. Use your file "
        "editing tool, then reply DONE.",
    )
    check("A1 Copilot run under project Full access completed", status == "completed", status)
    check("A2 Copilot wrote outside the workspace", target.exists())
    record = outside_record(run_id)
    check(
        "A3 the outside write is recorded on the run row",
        bool(record)
        and any(str(target).lower() == str(e.get("path", "")).lower() for e in record),
        json.dumps(record)[:300],
    )
    return run_id


def step_b(project):
    """A Copilot spec turn under project Full access reads outside the workspace."""
    settings(project, default_permission_mode="bypassPermissions", reach_grants=None)
    doc = e2e.cmd_doc_new(project, "Reach drive notes")
    run_id, status = turn(
        project,
        "cop",
        f"Read the file {OUTSIDE / 'notes.txt'} and tell me the word it names. Do not edit any "
        "file.",
        doc=doc,
    )
    check("B1 spec turn read outside under Full access", SECRET in outputs(run_id), status)
    check("B2 spec turn had no refusal", not denials(project, run_id))
    return run_id


def step_c(project):
    """An agent's own Workspace only narrows the project's Full access (Claude: no premium)."""
    settings(project, default_permission_mode="bypassPermissions", reach_grants=None)
    patch_agent(project, "cla", default_permission_mode="workspace")
    try:
        run_id, status = turn(
            project,
            "cla",
            f"Use the Bash tool to run: cat '{(OTHER / 'private.txt').as_posix()}' and report what "
            "it printed or why it was refused.",
        )
    finally:
        patch_agent(project, "cla", default_permission_mode=None)
    refused = denials(project, run_id)
    check(
        "C1 per-agent Workspace only refuses an outside read under project Full access",
        "ungranted-otter" not in outputs(run_id) and refused,
        f"{len(refused)} refusal(s)",
    )
    return run_id


def _middle(project):
    settings(
        project,
        default_permission_mode="workspace",
        reach_grants={
            "roots": [{"path": str(OUTSIDE), "access": "readwrite"}],
            "hosts": ["localhost:*"],
        },
    )


def step_d(project):
    """The middle setting reaches a Copilot run: granted root and host, ungranted root refused."""
    _middle(project)
    port = e2e.hub().rsplit(":", 1)[1]
    run_id, status = turn(
        project,
        "cop",
        "Run these three shell commands, one at a time, and report each result or refusal: "
        f"(1) Get-Content '{OUTSIDE / 'notes.txt'}'  "
        f"(2) curl.exe -s http://localhost:{port}/health  "
        f"(3) Get-Content '{OTHER / 'private.txt'}'",
    )
    text = outputs(run_id)
    refused = denials(project, run_id)
    check("D1 Copilot read the granted root", SECRET in text)
    # The tool's own output is not kept verbatim; the reply reporting the Hub's answer (ok, and its
    # stale-UI note, which only the response carries) and no refusal naming the host are the proof.
    check(
        "D2 Copilot reached the granted host",
        "localhost" not in json.dumps(refused) and ("stale" in text.lower() or '"ok"' in text),
    )
    check(
        "D3 Copilot was refused the ungranted root",
        "ungranted-otter" not in text
        and any(str(OTHER).lower() in json.dumps(r).lower().replace("\\\\", "\\") for r in refused),
        f"{len(refused)} refusal(s)",
    )
    return run_id


def step_e(project):
    """The same middle setting for Claude."""
    _middle(project)
    mid = OUTSIDE / "cla-mid.txt"
    mid.unlink(missing_ok=True)
    run_id, status = turn(
        project,
        "cla",
        f"Use the Bash tool to run: echo granted > '{mid.as_posix()}' ; then run: "
        f"cat '{(OTHER / 'private.txt').as_posix()}' ; then run: curl -s https://example.com/ ; "
        "report what each did.",
    )
    refused = denials(project, run_id)
    check("E1 Claude wrote in the granted root", mid.exists())
    check(
        "E2 Claude refused the ungranted root and host",
        "ungranted-otter" not in outputs(run_id) and len(refused) >= 2,
        f"{len(refused)} refusal(s): " + "; ".join(str(r.get("reason"))[:80] for r in refused),
    )
    return run_id


STEPS = {"A": step_a, "B": step_b, "C": step_c, "D": step_d, "E": step_e}


def main(project, steps="A,B,C,D,E"):
    OUTSIDE.mkdir(parents=True, exist_ok=True)
    OTHER.mkdir(parents=True, exist_ok=True)
    (OUTSIDE / "notes.txt").write_text(f"The word is {SECRET}.\n", encoding="utf-8")
    (OTHER / "private.txt").write_text("ungranted-otter\n", encoding="utf-8")
    runs = {name: STEPS[name](project) for name in steps.split(",")}
    print("\nSUMMARY")
    for name, ok in results:
        print(("  PASS " if ok else "  FAIL ") + name)
    print(f"{sum(ok for _, ok in results)}/{len(results)} passed; runs: {runs}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
