"""Acceptance drive for slice project-ledger of the visibility roadmap: the ledger's lanes agree
with the database they are read from, on the Terra replica (read-only comparison).

    py -3.11 scripts/drive/terra_replica.py --up 8130
    py -3.11 scripts/drive/d1017_project_ledger.py

Exit 1 when a check fails.
"""

import json
import pathlib
import sqlite3
import sys
import urllib.error
import urllib.request

from uiharness import replica

TERRA = "proj-cd006955cbe2"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def get(hub, key, path):
    request = urllib.request.Request(f"{hub}{path}", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:200]


def main():
    hub, key, db = replica()
    con = sqlite3.connect(pathlib.Path(db).as_uri() + "?mode=ro", uri=True)
    one = lambda sql: con.execute(sql, (TERRA,)).fetchone()[0]  # noqa: E731

    code, body = get(hub, key, f"/api/v1/projects/{TERRA}/ledger")
    check("the ledger answers", code == 200, f"{code} {str(body)[:200]}")
    if code != 200:
        return
    merges = body["merges"]
    check("every integration is in the merge lane",
          len(merges) == one("select count(*) from task_integrations where project_id = ?"),
          str(len(merges)))
    check("merged and skipped are told apart",
          body["totals"]["merged"]
          == one("select count(*) from task_integrations where project_id = ? and outcome = 'merged'"),
          str(body["totals"]))
    check("newest merge first",
          [m["at"] for m in merges] == sorted((m["at"] for m in merges), reverse=True))
    check("every divergence is in its lane",
          len(body["divergences"]) == one("select count(*) from run_divergences where project_id = ?"))
    turn_micros = one(
        "select coalesce(sum(api_equivalent_usd_micros), 0) from turn_usage where project_id = ?"
    )
    worker_micros = one(
        "select coalesce(sum(cost_usd_micros), 0) from worker_invocations where project_id = ?"
    )
    total = round((turn_micros + worker_micros) / 1_000_000, 4)
    check("total spend matches turns plus workers", abs(body["spend"]["total_usd"] - total) < 0.01,
          f"{body['spend']['total_usd']} vs {total}")
    per_agent = {
        agent: round(micros / 1_000_000, 4)
        for agent, micros in con.execute(
            "select agent, coalesce(sum(api_equivalent_usd_micros), 0) from turn_usage "
            "where project_id = ? group by agent",
            (TERRA,),
        )
    }
    shown = {entry["agent"]: entry["usd"] for entry in body["spend"]["by_agent"]}
    check("spend per agent matches", all(abs(shown.get(a, 0) - v) < 0.01 for a, v in per_agent.items()),
          f"{shown} vs {per_agent}")
    check("spend by day sums to the total",
          abs(sum(d["usd"] for d in body["spend"]["by_day"]) - body["spend"]["total_usd"]) < 0.01)
    check("origins count every task",
          sum(body["origins"].values()) == one("select count(*) from tasks where project_id = ?"),
          str(body["origins"]))
    warnings = one(
        "select count(*) from event_logs where project_id = ? and event_type = 'context_warning'"
    )
    folded = [n for n in body["notices"] if n["kind"] == "context_warning"]
    check("context_warning is one counted row", len(folded) == 1 and folded[0]["count"] == warnings,
          f"{folded[:1]} vs {warnings}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
