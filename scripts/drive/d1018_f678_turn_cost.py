"""Acceptance drive for F678 (spdoc-7f874f103d5b): two turns of one Claude conversation each
record their own cost, on a live Hub with a real CLI (Haiku).

Before: the second turn recorded `total_cost_usd`, the session's running total, as its own cost,
and no run said which CLI version produced it.

  py -3.11 scripts/drive/d1018_f678_turn_cost.py <project-id> <agent>

The agent must be bound to a Claude Haiku runner on the Hub `e2e.py hub-up` started. Exit 1 when
any check fails.
"""

import importlib.util
import json
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _row(run_id):
    return e2e.ro().execute(
        "select r.session_id, r.runner_version, u.api_equivalent_usd_micros cost, "
        "u.output_tokens, u.cache_write_tokens, u.session_totals "
        "from runs r join turn_usage u on u.run_id = r.id where r.id=?",
        (run_id,),
    ).fetchone()


def main(project, agent):
    runs = []
    for index, message in enumerate(("Reply with the word ONE.", "Reply with the word TWO.")):
        run_id = e2e.cmd_turn(project, agent, message, fresh=index == 0)
        check(f"turn {index + 1} started", bool(run_id))
        if not run_id:
            return
        check(f"turn {index + 1} completed", e2e.wait_for(run_id, 5) == "completed")
        runs.append(run_id)
    first, second = (_row(run_id) for run_id in runs)
    for name, row in (("turn 1", first), ("turn 2", second)):
        print(name, dict(row))
    totals = [json.loads(row["session_totals"]) for row in (first, second)]
    check("both turns are one session", first["session_id"] == second["session_id"])
    check(
        "each run records the CLI version",
        first["runner_version"] and first["runner_version"] == second["runner_version"],
        f"{first['runner_version']!r}",
    )
    check(
        "the session totals grew (the CLI reports them cumulatively)",
        totals[1]["api_equivalent_usd_micros"] > totals[0]["api_equivalent_usd_micros"],
    )
    check("turn 1's cost is its totals", first["cost"] == totals[0]["api_equivalent_usd_micros"])
    check(
        "turn 2's cost is the CLI's turn-2 total minus its turn-1 total",
        second["cost"]
        == totals[1]["api_equivalent_usd_micros"] - totals[0]["api_equivalent_usd_micros"],
        f"{second['cost']} vs session total {totals[1]['api_equivalent_usd_micros']}",
    )
    check(
        "turn 2's output tokens are its own",
        second["output_tokens"] == totals[1]["output_tokens"] - totals[0]["output_tokens"],
        f"{second['output_tokens']}",
    )


if __name__ == "__main__":
    try:
        main(*sys.argv[1:3])
    finally:
        print("FAILED: " + "; ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
