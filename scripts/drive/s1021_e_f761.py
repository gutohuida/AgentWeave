"""2026-10-21 evidence sweep, F761's unmeasured case: a real agent piece recorded in a task checkout
before its first commit there (no commit, no locator), with master's HEAD an unrelated commit.
GET /spec/evidence/{id}/diff should answer no files and a reason, not HEAD's patch.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1021_e_f761.py   (after s1020_v_setup.py)
"""

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_v_lib import commit_file, evidence, memo, request, say, show, summary, wait_run  # noqa: E402

M = memo()
P, DIR, DOC, T = M["project"], M["dir"], M["doc"], M["tasks"]
BASE = f"/projects/{P}/project"

head = commit_file(DIR, "todo/items.py",
                   "ITEMS = [('milk', 3), ('bread', 1), ('eggs', 2)]\n\n\ndef names():\n    return sorted(n for n, _ in ITEMS)\n",
                   "sort names (made for FR-1)")
print("master HEAD (unrelated to FR-3):", head[:12])

msg = ("You are on task t-total. Do NOT edit, create or commit any file. Run "
       "`py -3.11 -c \"from todo.total import total; print(total())\"` once, then call the AgentWeave tool "
       "record_evidence with identifier FR-3, document " + DOC + ", summary 'total() printed 6', covers full, "
       "and NO commit and NO locator. Then reply DONE.")
out = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop/e2e.py"),
                      "turn", P, "builder", msg, "--task", T["t-total"], "--perm", "workspace", "--fresh"],
                     capture_output=True, text=True, encoding="utf-8")
print(out.stdout[-1500:], out.stderr[-800:])
run_id = next((w.split("=", 1)[-1] for w in out.stdout.split() if "run-" in w), None)
print("run:", run_id)
if run_id:
    r = wait_run(run_id.strip(",.'\""), 10)
    print("run status:", r.get("status"))

pieces = [e for e in evidence(P) if e.get("identifier") == "FR-3"]
show("FR-3 pieces", 200, pieces)
memo(f761_head=head, f761_pieces=[e["id"] for e in pieces])
for e in pieces:
    st, d = request("GET", f"{BASE}/spec/evidence/{e['id']}/diff")
    show(f"diff {e['id']}", st, d)
    files = [f.get("path") for f in d.get("files", [])] if isinstance(d, dict) else None
    say(f"agent no-commit piece {e['id']} (author {e.get('recorded_by') or e.get('actor')}) answers no files + a reason",
        st == 200 and files == [] and bool(d.get("reason")), f"files={files} reason={d.get('reason') if isinstance(d, dict) else d}")
st, rows = request("GET", f"/projects/{P}/tasks/{T['t-total']}")
print("task:", st, {k: rows.get(k) for k in ("status", "assignee")} if isinstance(rows, dict) else rows)
summary()
