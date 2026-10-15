"""Acceptance drive for F628: under "Edit files", a call Claude Code asks permission for reaches
the operator as a card (decision fix-D12, operator 2026-10-15).

Before: Claude refused an outside Write itself -- no `permission_requests` row -- and the agent
told the operator to approve it "in the permission dialog", which did not exist. After: a card
appears; this drive denies it, so nothing is written either way.

  py -3.11 scripts/drive/d1015_f628_accept_edits_card.py <project-id> [agent]

One Haiku turn. Exit 1 when any check fails.
"""

import importlib.util
import pathlib
import sys
import time

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(project, agent="alpha"):
    outside = pathlib.Path.home() / "Documents" / "aw-f628-outside" / "written.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    if outside.exists():
        outside.unlink()
    run_id = e2e.cmd_turn(
        project, agent,
        f"Use the Write tool to create the file {outside} containing the word hello. "
        "Do not use a shell.",
        fresh=True, perm="acceptEdits",
    )
    check("the turn started", run_id is not None)
    if run_id is None:
        return
    card = None
    deadline = time.time() + 120
    while time.time() < deadline and card is None:
        rows = e2e.call("GET", f"/projects/{project}/permission-requests")
        card = next((r for r in rows if r.get("run_id") == run_id and r.get("status") == "pending"), None)
        if card is None:
            status = e2e.ro().execute("select status from runs where id=?", (run_id,)).fetchone()
            if status and status["status"] not in ("running", "queued", "starting", "pending"):
                break
            time.sleep(3)
    check("the outside Write reached the operator as a card", card is not None)
    if card is not None:
        check("the card names the tool", card.get("tool") == "Write" or "Write" in str(card), str(card)[:200])
        status, _ = e2e.request(
            "POST", f"/projects/{project}/permission-requests/{card['id']}/decide", {"allow": False}
        )
        check("the operator's deny is accepted", status == 200, str(status))
    e2e.wait_for(run_id, 5)
    check("nothing was written", not outside.exists())


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
