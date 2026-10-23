"""2026-10-23 Checkpoints x Accounting sweep, API steps (scratch Hub :8112, profile ck1023).

  turn <agent> <msg> [fresh]   a real turn (Haiku, or the Copilot stub for `cop`), waited out
  acct                         /accounting and /ledger side by side, summed by hand
  budget <n|null>              PUT the project's token budget
  conv <agent>                 the agent's conversations with their checkpoint warning and usage
  events [n]                   recent event types

    AW_P=proj-... py -3.11 scripts/drive/s1023_ck_drive.py <step> [args]
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_ck_lib import B, P, e2e, q, req, show  # noqa: E402


def turn(agent, msg, fresh=""):
    rid = e2e.cmd_turn(P, agent, msg, perm="workspace", fresh=bool(fresh))
    if rid:
        print("status", e2e.wait_for(rid, 8))
        r = q("select r.id, r.status, r.conversation_id, u.status ustatus, u.total_tokens, "
              "u.api_equivalent_usd_micros usd, u.ai_nano_aiu, u.premium_requests "
              "from runs r left join turn_usage u on u.run_id=r.id where r.id=?", rid)
        print("RUN", json.dumps(r, default=str))


def acct():
    st, a = req("GET", f"{B}/accounting")
    st2, lg = req("GET", f"{B}/ledger")
    a = a if isinstance(a, dict) else {}
    print("accounting", st, json.dumps({k: a.get(k) for k in ("project", "budget", "preferred_display")}, indent=1)[:2500])
    for ag in a.get("agents", []):
        print("  agent", ag.get("agent"), ag.get("total_tokens"), ag.get("api_equivalent_usd_micros"),
              "measured", ag.get("measured_turns"), "unavail", ag.get("unavailable_turns"), "unpriced", ag.get("unpriced_turns"))
    for w in a.get("workers", []):
        print("  worker", json.dumps(w)[:300])
    sp = (lg or {}).get("spend", {}) if isinstance(lg, dict) else {}
    print("ledger", st2, json.dumps({k: sp.get(k) for k in ("total_usd", "total_tokens", "worker_usd", "by_agent", "by_day")})[:1500])
    rows = q("select agent, status, total_tokens, api_equivalent_usd_micros usd, ai_nano_aiu, premium_requests "
             "from turn_usage where project_id=?", P)
    print("turn_usage rows", json.dumps(rows))
    w = q("select * from worker_invocations where project_id=?", P) \
        if q("select 1 from sqlite_master where name='worker_invocations'") else []
    print("worker rows", json.dumps(w))


def budget(n):
    show("PATCH", f"{B}/accounting/budget", {"token_budget": None if n == "null" else int(n)}, 1500)


def conv(agent):
    st, c = req("GET", f"{B}/conversations?agent={agent}&include_archived=true")
    for row in (c.get("conversations") if isinstance(c, dict) else c) or []:
        print(json.dumps({k: row.get(k) for k in ("id", "title", "archived", "checkpoint_warning",
                                                  "context_usage", "successor_id", "cut_over_to")}, default=str)[:700])


def events(n="20"):
    st, h = req("GET", f"{B}/events/history?limit={n}")
    hist = h if isinstance(h, list) else h.get("events", [])
    for ev in hist:
        print("  ", ev.get("event_type"), json.dumps(ev.get("data") or ev.get("payload"), ensure_ascii=False)[:300])


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
