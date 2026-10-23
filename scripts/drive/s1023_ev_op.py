"""Operator-side evidence probes for the 2026-10-23 evidence sweep: record on FR-3, decide/overturn
refusals. Each call prints status and body.

    AW_P=proj-... py -3.11 scripts/drive/s1023_ev_op.py record <sha> | decide <id> <decision> [reason] |
        overturn <id> [reason] | list [identifier] | diff <id> | reviews <id> | req <identifier>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_ev_lib import B, show  # noqa: E402

S = f"{B}/project/spec"
DOCP = "spec/changes/ev-main/spec.json"
a = sys.argv[1:]
if a[0] == "record":
    show("POST", f"{S}/evidence", {"identifier": "FR-3", "document": DOCP, "kind": "manual_observation",
                                   "locator": "README.md", "commit": a[1], "task_id": "task-af0661c54c21",
                                   "summary": "README.md documents count_words (operator read it).",
                                   "covers": "full"}, limit=2500)
elif a[0] == "decide":
    body = {"decision": a[2]}
    if len(a) > 3:
        body["reason"] = a[3]
    show("POST", f"{S}/evidence/{a[1]}/decision", body, limit=1500)
elif a[0] == "overturn":
    show("POST", f"{S}/evidence/{a[1]}/overturn", {"reason": a[2]} if len(a) > 2 else {}, limit=1500)
elif a[0] == "list":
    q = f"?identifier={a[1]}&document={DOCP}" if len(a) > 1 else f"?document={DOCP}"
    show("GET", f"{S}/evidence{q}", limit=6000)
elif a[0] == "diff":
    show("GET", f"{S}/evidence/{a[1]}/diff", limit=3000)
elif a[0] == "reviews":
    show("GET", f"{S}/evidence/{a[1]}/reviews", limit=3000)
elif a[0] == "req":
    show("GET", f"{S}/requirements/{a[1]}?document={DOCP}", limit=5000)
