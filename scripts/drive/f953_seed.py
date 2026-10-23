"""F952 drive: seed two turn_usage rows into the scratch profile `f953` (never a real profile):
alpha one priced turn (Haiku, $0.0725), cop one measured turn with no reported cost and 0.28
AI credits. Agents are made through the API; only the usage rows are inserted.

  AW_E2E_STATE=... AW_P=proj-... py -3.11 scripts/drive/f953_seed.py
"""

import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_sp_lib import B, HAIKU, P, e2e, req  # noqa: E402

st, runner = req("POST", f"{B}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
for name in ("alpha", "cop"):
    print(name, req("POST", f"{B}/agents", {"name": name, "runner_id": runner["id"]})[0])
db = sqlite3.connect(str(e2e.db()))
rows = [
    ("tu-a", "run-a", "alpha", 265791, 72500, None, None),
    ("tu-c", "run-c", "cop", 30, None, None, 280_000_000),
]
for tid, run, agent, tokens, micros, _, nano in rows:
    db.execute(
        "insert into turn_usage (id, run_id, project_id, agent, status, runner, model, input_tokens, output_tokens,"
        " total_tokens, api_equivalent_usd_micros, ai_nano_aiu, observed_at) values (?,?,?,?, 'measured', ?, ?, ?, 0, ?, ?, ?, datetime('now'))",
        (
            tid,
            run,
            P,
            agent,
            "claude" if agent == "alpha" else "copilot",
            HAIKU,
            tokens,
            tokens,
            micros,
            nano,
        ),
    )
db.commit()
print(req("GET", f"/projects/{P}/accounting")[1]["project"])
print(req("GET", f"/projects/{P}/accounting")[1]["preferred_display"])
