"""Sweep D vault phase 7: a document citing facts, written properly, then proposed (spec-vault-check)."""
import pathlib, sys, time, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import mine, save, say, sc  # noqa: E402
m = mine(); b = m["base"]
code, doc = sc.api("POST", f"{b}/project/documents", {"title": "Client rate limiting 5"})
path = doc["path"]; q = urllib.parse.quote(path, safe="")
payload = {"schema_version": 1, "kind": "change-spec", "title": "Client rate limiting 5", "summary": "Enforce the API rate limit in the client.",
    "problem": "Clients exceed the rate limit.",
    "requirements": [
        {"key": "limit-250", "modal": "MUST", "statement": "The client MUST allow up to 250 requests per minute per key.", "facts": ["fct-e7b1af961e0a"]},
        {"key": "upload-50", "modal": "MUST", "statement": "The client MUST accept uploads of up to 50 MB through the gateway."},
        {"key": "backoff", "modal": "MUST", "statement": "The client MUST back off starting at 2 seconds.", "facts": ["fct-fb32e8f38742"]},
        {"key": "vendor", "modal": "MUST", "statement": "The runbook MUST name the vendor support line.", "facts": ["fct-28b8f60a6440"]}]}
say("put", sc.api("PUT", f"/projects/{m['pid']}/project/documents/{path}/content", {"document": payload}))
say("warnings before propose", sc.api("GET", f"{b}/vault/warnings?path={q}"))
n0 = len(sc.api("GET", f"{b}/manager/activity")[1]["firings"])
pr = sc.api("POST", f"{b}/project/documents/propose?path={q}")
say("propose", (pr[0], pr[1].get("phase") if isinstance(pr[1], dict) else pr[1], pr[1].get("blocking") if isinstance(pr[1], dict) else ""))
sc.poll(lambda: len(sc.api("GET", f"{b}/manager/activity")[1]["firings"]) > n0, 240, 3)
time.sleep(3)
for x in sc.api("GET", f"{b}/manager/activity")[1]["firings"][:1]:
    say("f", {k: x.get(k) for k in ("job", "subject", "outcome", "detail", "answer")})
say("warnings after propose", sc.api("GET", f"{b}/vault/warnings?path={q}"))
save({"doc": path})
