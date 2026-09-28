"""Drive step for a-model-alias-is-a-model-choice, tasks.md 3.1.

On the trial Hub `:8010` (per the task's explicit instruction, not a fresh drive Hub): create a
runner whose model is the alias `haiku`, bind an agent to it, and run one real turn. Records
`turn_usage.model` (read via `GET /accounting`'s `recent_turns`) against `runners.model`, which
D1 says stays the alias as submitted while the turn's recorded model is the full id the CLI
resolved.

Creates its own fixture project outside the repo and deletes it afterward.

    AW_HUB=http://127.0.0.1:8010 AW_KEY=... py -3.11 scripts/drive/d0928_alias_turn_usage.py
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, require_hub, require_key, show  # noqa: E402

require_hub()
require_key()
if os.environ.get("AW_HUB", "").endswith(":8000"):
    print("REFUSING TO RUN: 8000 is the operator's real usage.")
    sys.exit(1)

PASS, FAIL = [], []


def check(ok, label):
    (PASS if ok else FAIL).append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


TAG = time.strftime("%H%M%S")
root = pathlib.Path(tempfile.gettempdir()) / f"alias-turn-usage-{TAG}"
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text(f"alias turn usage fixture {TAG}\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "alias-drive@example.invalid"],
    ["git", "config", "user.name", "alias-drive"],
    ["git", "add", "README.md"],
    ["git", "commit", "-m", "alias-turn-usage fixture"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"alias-turn-usage-{TAG}"})
show("POST /projects/open", code, proj, limit=300)
if code not in (200, 201):
    sys.exit(1)
PID = proj["id"]
A = f"/projects/{PID}"

try:
    code, runner = api(
        "POST", f"{A}/runners", {"name": f"alias-haiku-{TAG}", "cli": "claude", "model": "haiku"}
    )
    show("POST /runners (model=haiku alias)", code, runner, limit=300)
    check(code == 201, f"runner created with alias model ({code})")
    check(runner.get("model") == "haiku", f"runners.model stored as submitted ({runner.get('model')!r})")
    check(runner.get("model_unrecognised") is False, f"alias is recognised ({runner.get('model_unrecognised')!r})")
    RID = runner["id"]

    AGENT = f"aliasdriver{TAG}"
    code, agent = api("POST", f"{A}/agents", {"name": AGENT, "runner_id": RID})
    show("POST /agents", code, agent, limit=300)
    check(code == 201, f"agent created and bound ({code})")

    code, trig = api(
        "POST",
        f"{A}/agent/trigger",
        {"agent": AGENT, "session_mode": "new", "message": "Say the single word: ok."},
    )
    show("POST /agent/trigger", code, trig, limit=300)
    conv = trig.get("conversation_id") if isinstance(trig, dict) else None
    run_id = trig.get("run_id") if isinstance(trig, dict) else None
    check(code == 200 and conv, f"turn triggered ({code})")

    print("\n  polling /accounting until the turn lands...")
    t0 = time.time()
    row = None
    while time.time() - t0 < 90:
        code, acc = api("GET", f"{A}/accounting")
        if code == 200 and isinstance(acc, dict):
            candidates = [r for r in acc.get("recent_turns", []) if r.get("run_id") == run_id]
            if candidates and candidates[0].get("status") in ("measured", "unavailable", "failed"):
                row = candidates[0]
                break
        time.sleep(1.5)

    if row is None:
        print("  TIMED OUT waiting for the turn to settle in /accounting")
        check(False, "turn_usage row observed within 90s")
    else:
        print(f"  turn_usage row: {json.dumps(row, default=str)}")
        check(row.get("status") == "measured", f"turn is measured, not unavailable/failed ({row.get('status')!r})")
        check(row.get("runner") == "haiku", f"turn_usage.runner records the alias as stored ({row.get('runner')!r})")
        model = row.get("model")
        check(
            bool(model) and model != "haiku" and "haiku" in model,
            f"turn_usage.model is the full resolved id, not the alias ({model!r})",
        )

    code, after = api("GET", f"{A}/runners/{RID}")
    check(after.get("model") == "haiku", f"runners.model still reads the alias after the run ({after.get('model')!r})")

finally:
    api("DELETE", f"{PID}" if PID.startswith("/") else f"/projects/{PID}")
    import shutil

    shutil.rmtree(root, ignore_errors=True)

print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
