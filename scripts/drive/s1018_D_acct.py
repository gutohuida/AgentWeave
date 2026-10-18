"""Sweep D: print the accounting budget, workers, newest firings, conversation titles."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import mine, say, sc  # noqa: E402
m = mine(); b = m["base"]
d = sc.api("GET", f"{b}/accounting")[1]
say("budget", d["budget"]); say("project", d["project"])
say("workers", [(w["kind"], w["measured_calls"], w.get("unmeasured_calls"), w["total_tokens"]) for w in d["workers"]])
for x in sc.api("GET", f"{b}/manager/activity")[1]["firings"][:int(sys.argv[1]) if len(sys.argv) > 1 else 3]:
    say("firing", {k: x.get(k) for k in ("job", "subject", "outcome", "detail", "answer", "at")})
say("convs", sc.ro("select id, agent, title, created_at from conversations where project_id=? order by created_at desc limit 4", (m["pid"],)))
say("worker_invocations tail", sc.ro("select kind, outcome, total_tokens, error, created_at from worker_invocations order by created_at desc limit 4"))
