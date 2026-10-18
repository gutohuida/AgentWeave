"""Sweep D vault phase 4: the two disagreeing sources as documents; wait for the firings."""
import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import SCRATCH, mine, save, say, sc  # noqa: E402
m = mine(); base = m["base"]
a = sc.api("POST", f"{base}/vault/sources", {"name": "Ops runbook: rate limits (Feb)", "type": "document",
    "content": (SCRATCH / "rl_old.txt").read_text(encoding="utf-8"), "dated": "2026-02-01"})
time.sleep(2)
b = sc.api("POST", f"{base}/vault/sources", {"name": "Platform review: rate limits (June)", "type": "document",
    "content": (SCRATCH / "rl_new.txt").read_text(encoding="utf-8"), "dated": "2026-06-15"})
say("a", a[0]); say("b", b[0])
save({"doc_old": a[1]["id"], "doc_new": b[1]["id"]})
end = time.time() + 600
while time.time() < end:
    f = sc.api("GET", f"{base}/manager/activity")[1]["firings"]
    done = [x for x in f if x["job"] == "vault-distillation" and x["outcome"] != "failed" or x.get("runner_id")]
    if len(done) >= 6:
        break
    time.sleep(10)
for x in sc.api("GET", f"{base}/manager/activity")[1]["firings"]:
    say("firing", {k: x.get(k) for k in ("job", "subject", "outcome", "detail", "duration_ms", "usage", "answer", "model")})
say("contradictions", sc.api("GET", f"{base}/vault/contradictions"))
