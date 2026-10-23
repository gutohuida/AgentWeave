"""What the logs / events routes answer on bad input (scratch Hub :8119, profile ev1023).

    py -3.11 scripts/drive/s1023_ev_sse_probe.py
"""

import json
import urllib.parse

from s1023_ev_sse_lib import B, P, q, req


def probe(method, path, body=None, note=""):
    st, res = req(method, path, body, timeout=20)
    text = json.dumps(res, ensure_ascii=False)
    shape = f"list[{len(res)}]" if isinstance(res, list) else text[:240]
    print(f"{st} {method} {path} {note}\n     {shape}")
    return st, res


H = f"{B}/events/history"
for qs in ("limit=0", "limit=501", "limit=abc", "limit=500", "severity=bogus", "severity=warn", "severity=all",
           "limit=-1"):
    probe("GET", f"{H}?{qs}")
probe("GET", "/projects/proj-doesnotexist/events/history")
probe("GET", "/projects/proj-doesnotexist/logs")
probe("GET", "/projects/proj-doesnotexist/ledger")
probe("GET", "/projects/proj-doesnotexist/events/ticket")

L = f"{B}/logs"
for qs in ("offset=-1", "limit=1000", "limit=0", "since=garbage", "event_type=nope", "agent=nobody",
           "severity=bogus", "offset=99999"):
    probe("GET", f"{L}?{qs}")

# `since` with an explicit offset: 13:00+02:00 is 11:00Z. Every event in this project is after
# 11:52Z, so both must return the same set; a string comparison against naive UTC stored
# timestamps would treat 13:00+02:00 as 13:00.
rows = q("select timestamp from event_logs where project_id=? order by timestamp", P)
print("events stored:", len(rows), "first", rows[0]["timestamp"], "last", rows[-1]["timestamp"])
for since in ("2026-10-23T11:00:00Z", "2026-10-23T13:00:00+02:00", "2026-10-23T11:00:00", "2026-10-23T06:00:00-05:00",
              "2026-10-23T12:30:00Z", "2026-10-23T14:30:00+02:00", "2026-10-23T12:30:00"):
    st, res = req("GET", f"{L}?limit=500&since={urllib.parse.quote(since)}")
    n_db = q("select count(*) n from event_logs where project_id=? and timestamp > ?", P,
             since.replace("T", " ")[:19])[0]["n"]
    print(f"since {since:28s} -> {st} {len(res) if isinstance(res, list) else res}  (naive-UTC count {n_db})")

# Writes.
probe("POST", L, {"event_type": "x" * 65}, "event_type 65 chars")
probe("POST", L, {"event_type": ""}, "empty event_type")
probe("POST", L, {"event_type": "probe_sev", "severity": "critical"}, "unknown severity")
probe("POST", L, {"event_type": "probe_list", "data": [1, 2, 3]}, "list data")
probe("POST", L, {"event_type": "probe_big", "data": {"blob": "y" * 2_000_000}}, "2 MB data")
probe("POST", L, {"event_type": "probe_agent", "agent": "ghost-agent"}, "unknown agent")
probe("POST", L, {"event_type": "probe_secret", "data": {"note": "key aw_live_" + "a1B2" * 8,
                                                       "path": "C:/Users/huida/Documents/aw-ev1023/README.md"}},
      "secret + path in data")
print(q("select event_type, severity, agent, substr(data,1,200) d from event_logs where project_id=? and event_type like 'probe_%'", P))
st, res = probe("GET", f"{H}?limit=3")
print("     history tail:", json.dumps(res)[:600])
