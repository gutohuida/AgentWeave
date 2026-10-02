"""Drive `a-copilot-run-shows-its-credits` group 7 on the trial Hub, one phase per invocation.

    setup   no model call: a throwaway project, a Copilot agent (model Auto) pinned to `acptee.exe`,
            a Claude agent on Haiku, checkpoint mode `offered`
    t1      7.1   Copilot turn 1: "Reply with the word OK."
    cl      7.2   the Claude (Haiku) agent's turn, for the "shows no credits" half of 7.2
    t2      7.3/7.4  Copilot turn 2, same conversation (a resumed session)
    compact 7.5   Copilot turn 3, same conversation: "/compact"
    ctx     7.6   synthetic 66% readings for both agents (no model call)
    refuse  7.7   `acptee` answers the prompt with 1.15(a)'s quota refusal (no model call)
    show    the accounting snapshot and every turn_usage row, again

Copilot is on the Free plan: model Auto, one-sentence prompts, at most four model-calling turns.
The Copilot agent's `config.cli` is `scripts/drive/acptee.cs` compiled into
`testbed/scratch/credits-drive/bin/` (see that file): Copilot does not persist `assistant.usage`,
so the tee's log is the only record of a run's per-call sum. Needs AW_HUB, AW_KEY and AW_DB (read
`mode=ro`). State is kept in `testbed/scratch/credits-drive/state.json`.
"""

import glob
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, show  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
BASE = REPO / "testbed" / "scratch" / "credits-drive"
BIN = BASE / "bin"
STATE = BASE / "state.json"
DB = os.environ["AW_DB"]
COP = "cop-c"
CL = "cl-c"
HAIKU = "claude-haiku-4-5-20251001"
PROMPT = "Reply with the word OK."


def load():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def save(state):
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def ro(query, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try:
        return con.execute(query, args).fetchall()
    finally:
        con.close()


def wait_idle(pid, agent, timeout=600):
    time.sleep(3)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not ro(
            "select id from runs where project_id=? and agent=? and status='running'", (pid, agent)
        ):
            return
        time.sleep(3)
    raise SystemExit(f"{agent} still running after {timeout}s")


def last_run(pid, agent):
    rows = ro(
        "select id, status, session_id, conversation_id, error from runs "
        "where project_id=? and agent=? order by started_at desc limit 1",
        (pid, agent),
    )
    return dict(zip(("id", "status", "session_id", "conversation_id", "error"), rows[0]))


def usage_row(run_id):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("select * from turn_usage where run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def accounting(A):
    code, snap = api("GET", f"{A}/accounting")
    if code != 200:
        show("accounting", code, snap)
        return {}
    return snap


def brief(snap):
    return {
        "budget.used_tokens": (snap.get("budget") or {}).get("used_tokens"),
        "project": {
            k: v
            for k, v in (snap.get("project") or {}).items()
            if k in ("total_tokens", "ai_nano_aiu", "premium_requests", "turns")
        },
        "allowances": snap.get("allowances") or snap.get("allowance"),
    }


def tee_logs_since(stamp):
    """The tee's out/in logs written by spawns at or after `stamp` (epoch seconds)."""
    found = []
    for out in sorted(glob.glob(str(BIN / "logs" / "*.out.jsonl"))):
        if os.path.getmtime(out) >= stamp:
            found.append((out, out.replace(".out.jsonl", ".in.jsonl")))
    return found


def read_tee(stamp):
    """What the ACP stream carried: the per-call sum, checkpoints, the prompt result's usage."""
    calls, checkpoints, compactions, errors = [], [], [], []
    prompt_results = []
    for out_path, in_path in tee_logs_since(stamp):
        prompt_ids = set()
        for line in open(in_path, encoding="utf-8", errors="replace"):
            if line.startswith("//acptee-out "):
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("method") == "session/prompt":
                prompt_ids.add(msg.get("id"))
        for line in open(out_path, encoding="utf-8", errors="replace"):
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("method") == "github.com/copilot/sessionEvent":
                params = msg.get("params") or {}
                kind, data = params.get("type"), params.get("data") or {}
                if kind == "assistant.usage":
                    calls.append(data)
                elif kind == "session.usage_checkpoint":
                    checkpoints.append(
                        {k: data.get(k) for k in ("totalNanoAiu", "totalPremiumRequests")}
                    )
                elif kind == "session.compaction_complete":
                    compactions.append(data)
                elif kind == "session.error":
                    errors.append(data)
            elif "id" in msg and msg.get("id") in prompt_ids and "method" not in msg:
                prompt_results.append(msg.get("result") or msg.get("error"))
    per_call_tokens = sum((c.get("inputTokens") or 0) + (c.get("outputTokens") or 0) for c in calls)
    per_call_nano = sum(
        ((c.get("copilotUsage") or {}).get("totalNanoAiu") or 0) for c in calls
    )
    print(f"tee: {len(calls)} assistant.usage call(s)")
    for c in calls:
        print(
            "  call",
            json.dumps(
                {
                    k: c.get(k)
                    for k in (
                        "model",
                        "inputTokens",
                        "outputTokens",
                        "cacheReadTokens",
                        "cacheWriteTokens",
                        "providerCallId",
                        "apiCallId",
                        "initiator",
                    )
                }
            ),
            "nanoAiu=",
            (c.get("copilotUsage") or {}).get("totalNanoAiu"),
        )
        snaps = c.get("quotaSnapshots")
        if isinstance(snaps, dict):
            print("    quotaSnapshots:", json.dumps(snaps)[:900])
    print("tee: per-call tokens sum =", per_call_tokens, " per-call nanoAiu sum =", per_call_nano)
    print("tee: usage_checkpoints =", checkpoints)
    print("tee: prompt result(s) =", json.dumps(prompt_results)[:800])
    if compactions:
        print("tee: compactions =", json.dumps(compactions)[:800])
    if errors:
        print("tee: session.errors =", json.dumps(errors)[:800])
    return {
        "per_call_tokens": per_call_tokens,
        "per_call_nano": per_call_nano,
        "checkpoints": checkpoints,
        "prompt_results": prompt_results,
        "quota_snapshots": [c.get("quotaSnapshots") for c in calls if c.get("quotaSnapshots")],
    }


def trigger(A, agent, message, conversation_id=None):
    body = {"agent": agent, "message": message}
    if conversation_id:
        body["conversation_id"] = conversation_id
    code, resp = api("POST", f"{A}/agent/trigger", body, timeout=120)
    show("trigger", code, resp)
    return resp if isinstance(resp, dict) else {}


def setup():
    BASE.mkdir(parents=True, exist_ok=True)
    tee = BIN / "acptee.exe"
    if not tee.is_file():
        raise SystemExit(f"build {tee} first (see scripts/drive/acptee.cs)")
    root = BASE / time.strftime("proj-%H%M%S")
    root.mkdir()
    (root / "README.md").write_text("credits drive\n", encoding="utf-8")
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "d@example.invalid"],
        ["git", "config", "user.name", "d"],
        ["git", "add", "README.md"],
        ["git", "commit", "-m", "x"],
    ):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)
    code, proj = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    show("project", code, proj)
    pid = proj["id"]
    A = f"/projects/{pid}"
    code, cop_runner = api("POST", f"{A}/runners", {"name": "Copilot credits", "cli": "copilot"})
    show("copilot runner (model Auto: none set)", code, cop_runner)
    code, cl_runner = api(
        "POST", f"{A}/runners", {"name": "Haiku credits", "cli": "claude", "model": HAIKU}
    )
    show("claude runner", code, cl_runner)
    for name, runner in ((COP, cop_runner), (CL, cl_runner)):
        code, agent = api("POST", f"{A}/agents", {"name": name, "runner_id": runner["id"]})
        show(f"agent {name}", code, agent)
    code, patched = api("PATCH", f"{A}/agents/{COP}", {"config": {"cli": str(tee)}})
    show("pin acptee", code, patched)
    code, settings = api("GET", f"/projects/{pid}/settings")
    if code == 200:
        settings["checkpoint_mode"] = "offered"
        code, settings = api("PUT", f"/projects/{pid}/settings", settings)
    show("settings (checkpoint_mode offered)", code, settings)
    code, by_provider = api("GET", f"{A}/runners/launchability-by-provider")
    print("launchability(copilot):", json.dumps((by_provider or {}).get("providers", {}).get("copilot")))
    save({"pid": pid, "root": str(root)})


def copilot_turn(label, conversation_id=None, message=PROMPT):
    s = load()
    A = f"/projects/{s['pid']}"
    before = accounting(A)
    print("accounting before:", json.dumps(brief(before)))
    stamp = time.time()
    resp = trigger(A, COP, message, conversation_id)
    wait_idle(s["pid"], COP)
    run = last_run(s["pid"], COP)
    print("run:", run)
    row = usage_row(run["id"])
    print("turn_usage:", json.dumps(row))
    tee = read_tee(stamp)
    after = accounting(A)
    print("accounting after:", json.dumps(brief(after)))
    b = (before.get("budget") or {}).get("used_tokens") or 0
    a = (after.get("budget") or {}).get("used_tokens") or 0
    if row:
        print("CHECK total_tokens == per-call sum:", row["total_tokens"], tee["per_call_tokens"],
              row["total_tokens"] == tee["per_call_tokens"])
        print("CHECK budget.used_tokens rose by the row's tokens:", a - b, row["total_tokens"],
              a - b == row["total_tokens"])
    conv = ro(
        "select id, provider_session_id from conversations where id=?", (run["conversation_id"],)
    )
    print("conversation:", conv)
    s[label] = {
        "run_id": run["id"],
        "conversation_id": run["conversation_id"] or resp.get("conversation_id"),
        "session_id": run["session_id"],
        "row": row,
        "tee": tee,
        "accounting_after": brief(after),
    }
    save(s)


def t1():
    copilot_turn("t1")


def t2():
    s = load()
    copilot_turn("t2", s["t1"]["conversation_id"])
    s = load()
    r1, r2 = s["t1"]["row"], s["t2"]["row"]
    k1 = r1.get("session_nano_aiu_total")
    k2 = r2.get("session_nano_aiu_total")
    print("7.3: t1 checkpoint", k1, " t2 checkpoint", k2, " t2 ai_nano_aiu", r2.get("ai_nano_aiu"))
    if k1 is not None and k2 is not None:
        print("7.3: K2 - K1 =", k2 - k1, " equals t2 ai_nano_aiu:", k2 - k1 == r2.get("ai_nano_aiu"))
        print("7.3: checkpoint", "CONTINUED" if k2 > k1 else "RESTARTED (or did not grow)",
              "across session/load")
    print("7.3: t2 per-call nano sum =", s["t2"]["tee"]["per_call_nano"])
    print("Q10: t2 prompt result =", s["t2"]["tee"]["prompt_results"],
          " t2 per-call tokens =", s["t2"]["tee"]["per_call_tokens"],
          " t1 per-call tokens =", s["t1"]["tee"]["per_call_tokens"])


def compact():
    s = load()
    copilot_turn("t3", s["t1"]["conversation_id"], "/compact")
    s = load()
    r2, r3 = s["t2"]["row"], s["t3"]["row"] or {}
    print("7.5: t3 ai_nano_aiu", r3.get("ai_nano_aiu"), " checkpoint", r3.get("session_nano_aiu_total"),
          " K3 - K2 =", (r3.get("session_nano_aiu_total") or 0) - (r2.get("session_nano_aiu_total") or 0))


def cl():
    s = load()
    A = f"/projects/{s['pid']}"
    resp = trigger(A, CL, PROMPT)
    wait_idle(s["pid"], CL)
    run = last_run(s["pid"], CL)
    print("run:", run)
    print("turn_usage:", json.dumps(usage_row(run["id"])))
    s["cl"] = {"run_id": run["id"], "conversation_id": run["conversation_id"] or resp.get("conversation_id"),
               "session_id": run["session_id"]}
    save(s)


def ctx():
    s = load()
    A = f"/projects/{s['pid']}"
    for agent, key in ((COP, "t1"), (CL, "cl")):
        session_id = s[key]["session_id"]
        body = {
            "status": "measured",
            "source": "drive-7.6",
            "basis": "provider_context",
            "context_tokens": 66000,
            "limit_tokens": 100000,
            "percent": 66,
            "session_id": session_id,
            "observed_at": time.time(),
        }
        code, resp = api("POST", f"{A}/agents/{agent}/context-usage", body)
        show(f"context-usage {agent} (session {session_id})", code, resp)
    time.sleep(3)
    # Under `offered` a reading over the threshold sets `checkpoint_warning = 'due'` and broadcasts
    # `checkpoint_due` (checkpoint_trigger.consider); that column is what the banner shows from.
    for agent, key in ((COP, "t1"), (CL, "cl")):
        print(
            f"{agent} conversation checkpoint_warning:",
            ro("select checkpoint_warning from conversations where id=?", (s[key]["conversation_id"],)),
        )


def refuse():
    s = load()
    A = f"/projects/{s['pid']}"
    flag = BIN / "refuse.flag"
    flag.write_text("7.7\n", encoding="utf-8")
    try:
        stamp = time.time()
        trigger(A, COP, PROMPT, s["t1"]["conversation_id"])
        wait_idle(s["pid"], COP, timeout=180)
    finally:
        flag.unlink()
    run = last_run(s["pid"], COP)
    print("run:", run)
    print("turn_usage:", json.dumps(usage_row(run["id"])))
    read_tee(stamp)
    code, status = api("GET", f"{A}/queue/{COP}/status")
    show("GET /queue/cop-c/status", code, status)
    s["refuse"] = {"run_id": run["id"]}
    save(s)


def show_all():
    s = load()
    A = f"/projects/{s['pid']}"
    print(json.dumps(brief(accounting(A)), indent=2))
    for row in ro(
        "select agent, status, total_tokens, ai_nano_aiu, premium_requests, session_nano_aiu_total, "
        "session_premium_requests_total, allowance from turn_usage where project_id=? order by id",
        (s["pid"],),
    ):
        print(row)


if __name__ == "__main__":
    {"setup": setup, "t1": t1, "t2": t2, "cl": cl, "compact": compact, "ctx": ctx, "refuse": refuse, "show": show_all}[
        sys.argv[1]
    ]()
