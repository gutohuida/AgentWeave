"""Sweep D resilience: concurrent triggers for one agent (F349), unknown routes, odd methods."""
import pathlib, sys, threading
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import mine, say, sc  # noqa: E402
m = mine(); b = m["base"]
out = []
def fire(i, agent):
    out.append((i, agent) + tuple(sc.api("POST", f"{b}/agent/trigger", {"agent": agent, "message": f"Concurrent {i}: reply ok only, no tools.", "overrides": {"permission_mode": "workspace"}})))
ts = [threading.Thread(target=fire, args=(i, "alpha")) for i in range(4)] + [threading.Thread(target=fire, args=(9, "beta"))]
[t.start() for t in ts]; [t.join() for t in ts]
for r in out:
    say(f"trigger {r[0]} {r[1]}", (r[2], {k: r[3].get(k) for k in ("status", "run_id", "waiting_reason", "message", "detail")} if isinstance(r[3], dict) else r[3]))
for meth, path in (("GET", "/no/such/route"), ("GET", f"{b}/no-such"), ("DELETE", f"{b}/vault/map"), ("POST", "/projects/proj-000000000000/agent/trigger"), ("GET", f"{b}/vault/entries/src-000000000000"), ("GET", f"{b}/vault/entries/../../etc"), ("POST", f"{b}/vault/reports/rpt-000000000000/close")):
    say(f"{meth} {path}", sc.api(meth, path, {} if meth == "POST" else None))
