"""2026-10-23 Traces row: one run's trace beside its events, its timeline rows, the ledger and turn_usage.

  py -3.11 scripts/drive/s1023_tc_compare.py <run_id> [<run_id> ...]
  py -3.11 scripts/drive/s1023_tc_compare.py export     # the OTLP export: secrets, logs, kinds
"""

import json
import sys
from datetime import datetime

from s1023_tc_lib import GH, HALF1, HALF2, KEY, q, req, say

NEEDLES = {"KEY": KEY, "HALF1": HALF1, "HALF2": HALF2, "GH": GH, "KEYbody": KEY[13:], "HALF1body": HALF1[13:]}


def hits(obj):
    text = json.dumps(obj, ensure_ascii=False, default=str)
    return [name for name, value in NEEDLES.items() if value in text]


def ms(a, b):
    if not a or not b:
        return None
    return round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() * 1000)


def compare(run_id):
    print(f"\n======== {run_id}")
    st, t = req("GET", f"~/traces/by-run/{run_id}")
    if st != 200:
        say(f"by-run {st}", t)
        return
    root = t["root"]
    ra = root["attributes"]
    say("root", {"status": root["status"], "status_message": root["status_message"], "run_status": ra.get("aw.run.status"),
                 "dur_ms": ms(root["start_time"], root["end_time"]), "total": t["total"]})
    say("root usage", {k: v for k, v in ra.items() if "usage" in k or k == "gen_ai.response.model"})
    for s in t["spans"]:
        a = s["attributes"]
        extra = {k: a[k] for k in ("gen_ai.tool.name", "gen_ai.tool.call.id", "process.exit.code", "aw.decision.allowed") if k in a}
        print(f"  {s['operation']:<16} {s['name'][:46]:<46} {s['status']:<6} {ms(s['start_time'], s['end_time'])!s:>7}ms "
              f"ended={s['ended']} {extra} events={[e['name'] for e in s['events']][:6]} secrets={hits(s)}")
        for e in s["events"]:
            if e["name"] == "log":
                print("      LOG:", json.dumps(e["attributes"])[:500])
    # the run row and its timeline
    run = q("select status, started_at, ended_at, exit_code, error, task_id from runs where id=?", run_id)[0]
    say("runs row", {**run, "dur_ms": ms(str(run["started_at"]).replace(" ", "T"), str(run["ended_at"]).replace(" ", "T")) if run["ended_at"] else None})
    outs = q("select sequence, kind, content, payload from agent_outputs where run_id=? order by sequence", run_id)
    tools_rows = [o for o in outs if o["kind"] == "tool_use"]
    tool_spans = [s for s in t["spans"] if s["operation"] == "execute_tool"]
    say("tool_use rows vs execute_tool spans", {"rows": len(tools_rows), "spans": len(tool_spans)})
    say("timeline secrets", [(o["sequence"], o["kind"], hits(o)) for o in outs if hits(o)])
    st, ev = req("GET", "~/events/history?limit=500")
    mine = [e for e in ev if json.dumps(e.get("data")).find(run_id) >= 0]
    say("events of the run", [(e["type"], e["timestamp"][11:23]) for e in mine])
    say("event secrets", [(e["type"], hits(e)) for e in mine if hits(e)])
    usage = q("select status, input_tokens, output_tokens, total_tokens, cache_read_tokens, cache_write_tokens, "
              "api_equivalent_usd_micros, model from turn_usage where run_id=?", run_id)
    say("turn_usage", usage)
    st, led = req("GET", "~/ledger")
    text = json.dumps(led, default=str)
    say("ledger mentions run", run_id in text)
    for lane, items in (led.items() if isinstance(led, dict) else []):
        if isinstance(items, list):
            for it in items:
                if run_id in json.dumps(it, default=str):
                    say(f"ledger[{lane}]", it)


def export():
    import urllib.request
    hub = req.__globals__["e2e"].hub()
    key = req.__globals__["e2e"].key()
    from s1023_tc_lib import B
    r = urllib.request.Request(f"{hub}/api/v1{B}/traces/export", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(r) as resp:
        raw = resp.read()
        say("export headers", dict(resp.headers))
    body = json.loads(raw)
    spans = body["resourceSpans"][0]["scopeSpans"][0]["spans"]
    logs = body["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
    say("export size/spans/logs", [len(raw), len(spans), len(logs)])
    say("export secrets", hits(body))
    for name, value in NEEDLES.items():
        if value in raw.decode("utf-8"):
            i = raw.decode("utf-8").find(value)
            print(f"  {name} at:", raw.decode("utf-8")[max(0, i - 300): i + 80])
    for rec in logs[:20]:
        print("  LOG", rec["severityText"], rec["body"]["stringValue"][:300])


if __name__ == "__main__":
    if sys.argv[1] == "export":
        export()
    else:
        for rid in sys.argv[1:]:
            compare(rid)
