"""2026-10-23 Checkpoints sweep: fill a Copilot stub conversation toward its window (zero spend), to
reach the `final` checkpoint warning (77% for Copilot) and Copilot's own compaction (80%). Each
turn is an operator message just under the 10,000-character cap; stops at the first `compacted`
output or when the reading falls.

  AW_P=proj-... py -3.11 scripts/drive/s1023_ck_fill.py <agent> <max-turns>
"""

import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_ck_lib import B, P, e2e, q, req  # noqa: E402

agent, n = sys.argv[1], int(sys.argv[2])
random.seed(11)
words = ["alpha", "delta", "ledger", "river", "copper", "window", "harbor", "signal", "quartz", "meadow"]
last = 0.0
for i in range(n):
    text = f"Filler {i}, reply 'ok':\n" + " ".join(random.choice(words) + str(random.randint(0, 999)) for _ in range(1100))
    text = text[:9990]
    conv = e2e.latest_conversation(P, agent)
    st, res = req("POST", f"{B}/agent/trigger", {"agent": agent, "message": text, "conversation_id": conv})
    if st >= 300:
        print("trigger", st, json.dumps(res)[:300])
        break
    status = e2e.wait_for(res["run_id"], 4)
    st, c = req("GET", f"{B}/conversations?agent={agent}")
    rows = c.get("conversations") if isinstance(c, dict) else c
    row = next(r for r in rows if r["id"] == conv)
    cu = row.get("context_usage") or {}
    comp = q("select count(*) n from agent_outputs where run_id=? and (kind like '%compact%' or content like '%compacted%')", res["run_id"])[0]["n"]
    print(i, status, cu.get("context_tokens"), cu.get("percent"), "warning", row.get("checkpoint_warning"), "compacted", comp, flush=True)
    pct = cu.get("percent") or 0
    if comp or pct < last - 5:
        print("STOP: compaction or the reading fell")
        break
    last = pct
