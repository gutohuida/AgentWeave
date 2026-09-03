"""a-turn phase 7 — does a stopped turn ever reach the F269 shape?

7.1a asks for a turn that "produced nothing" and checks it carries both the terminal label and
the "Worked for Xs" line. That check only tests F269's fix if the turn's FIRST agent output is
the `status` row — `firstAgentBlockId` picks the first work-or-`agent_output` block, and any
`thinking` row ahead of the status row takes the slot, so the line renders for reasons that have
nothing to do with task 4.5a.

The phase 7 stopfast leg saw the status row at `sequence: 1`, which means something was at 0.
This script stops runs at several delays and prints every output row in order, so the answer is
measured rather than inferred from a sequence number.

    AW_HUB=http://127.0.0.1:8011 AW_PROJECT=proj-... AGENT=p6driverp7b \
        py -3.11 scripts/drive/t_aturn_p7_f269.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import aturn_model  # noqa: E402
from aw import P, api  # noqa: E402

AGENT = os.environ.get("AGENT", "driver")
PROMPT = (
    "Write a 3000 word essay about the history of the bicycle, in full prose, "
    "one paragraph at a time. Use no tools and read no files."
)


def one(delay):
    code, out = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": AGENT, "session_mode": "new", "message": PROMPT},
    )
    run = out.get("run_id") if isinstance(out, dict) else None
    print(f"\n=== stop after {delay}s   trigger={code} run={run}")
    time.sleep(delay)
    code, _ = api("POST", f"/projects/{P}/agent/{AGENT}/stop")
    print(f"    stop -> {code}")
    aturn_model.wait_idle(AGENT, limit=60)
    time.sleep(2)
    rows = [r for r in aturn_model.output_rows(AGENT) if r.get("run_id") == run]
    rows.sort(key=lambda r: r.get("sequence") if r.get("sequence") is not None else -1)
    for r in rows:
        print(
            f"    seq={r.get('sequence')!s:<4} kind={r.get('kind')!s:<10} "
            f"payload={json.dumps(r.get('payload'), default=str)[:70]:<60} "
            f"content={str(r.get('content'))[:60]!r}"
        )
    first = rows[0] if rows else None
    print(
        f"    -> first agent output for this run is kind={first and first.get('kind')!r}; "
        f"F269 shape (status row is the first) = {bool(first) and first.get('kind') == 'status'}"
    )
    return rows


if __name__ == "__main__":
    for d in (0.3, 1.0, 3.0):
        one(d)
