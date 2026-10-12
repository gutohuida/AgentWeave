"""Drive for F177 (Tier 0), 2026-10-12: the runner and charter lists keep creation order on a tie.

Starts its own Hub from source on :8112 with a fresh database (never :8000 or :8010). No agent turn.

  1. runners and charters are created through the real routes in reverse-alphabetical order, then
     the rows are given one `created_at` (the tie Windows' ~15.6 ms timer produces) directly in the
     database; both lists must read in creation order, not name order;
  2. the same with the rows created back to back and never touched, which is the live shape (it
     only differs from step 1 when the clock really ties, so it is reported, not required).

    py -3.11 scripts/drive/d1012_f177_creation_order.py
"""

import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402

d.PORT = 8112
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1012-f177" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

NAMES = ["Z8", "Z7", "Z6", "Z5", "Z4", "Z3", "Z2", "Z1"]


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# f177\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "f177"})
    assert code in (200, 201), (code, project)
    base = f"/projects/{project['id']}"

    ids = {"runners": [], "charters": []}
    for name in NAMES:
        code, out = d.api("POST", f"{base}/runners", {"name": name, "cli": "claude"})
        d.check(f"0 runner {name} is created", code == 201, f"{code} {str(out)[:200]}")
        ids["runners"].append(out["id"])
        code, out = d.api("POST", f"{base}/charters", {"name": name, "content": name})
        d.check(f"0 charter {name} is created", code == 201, f"{code} {str(out)[:200]}")
        ids["charters"].append(out["id"])

    for table in ("runners", "charters"):
        code, out = d.api("GET", f"{base}/{table}")
        natural = [r["name"] for r in out if r["id"] in ids[table]]
        d.check(f"2 {table}, created back to back and untouched, list in creation order "
                f"(informational: a real tie is rare)", True, f"{natural}")

    con = sqlite3.connect(d.DB.as_posix())
    try:
        for table in ("runners", "charters"):
            marks = ",".join("?" * len(ids[table]))
            con.execute(f"UPDATE {table} SET created_at = '2026-10-12 01:00:00.000000' "
                        f"WHERE id IN ({marks})", ids[table])
        con.commit()
    finally:
        con.close()

    for table in ("runners", "charters"):
        code, out = d.api("GET", f"{base}/{table}")
        got = [r["name"] for r in out if r["id"] in ids[table]]
        d.check(f"1 {table} sharing one created_at list in creation order, not name order",
                code == 200 and got == NAMES, f"{got}")


if __name__ == "__main__":
    d.drive = drive
    d.main()
