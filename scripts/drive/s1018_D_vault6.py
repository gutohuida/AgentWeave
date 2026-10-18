"""Sweep D vault phase 6: a spec document citing facts (superseded one, private one), spec-vault-check on propose."""
import json, pathlib, sys, time, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import mine, save, say, sc  # noqa: E402
m = mine(); b = m["base"]; R = m["runner"]
say("enable spec-vault-check", sc.api("PATCH", f"{b}/manager/jobs/spec-vault-check", {"enabled": True, "runner_id": R, "model": "haiku"})[0])
code, doc = sc.api("POST", f"{b}/project/documents", {"title": "Client rate limiting 2"})
say("doc", (code, doc.get("path"), doc.get("phase")))
path = doc["path"]
q = urllib.parse.quote(path, safe="")
payload = {
    "title": "Client rate limiting", "summary": "Enforce the public API rate limit in the client.",
    "problem": "Clients exceed the rate limit.",
    "requirements": [
        {"key": "limit-250", "modal": "MUST", "statement": "The client MUST allow up to 250 requests per minute per key.", "facts": ["fct-e7b1af961e0a"]},
        {"key": "upload-50", "modal": "MUST", "statement": "The client MUST accept uploads of up to 50 MB through the gateway."},
        {"key": "backoff", "modal": "MUST", "statement": "The client MUST back off starting at 2 seconds.", "facts": ["fct-gone00000000"]},
    ],
    "acceptance_criteria": [{"key": "ac1", "requirement": "limit-250", "given": "g", "when": "w", "then": "t", "checked_by": "agent", "how_to_check": "pytest"}],
}
say("put content", sc.api("PUT", f"/projects/{m['pid']}/project/documents/{path}/content", {"document": payload}))
say("warnings before propose", sc.api("GET", f"{b}/vault/warnings?path={q}"))
n0 = len(sc.api("GET", f"{b}/manager/activity")[1]["firings"])
pr = sc.api("POST", f"{b}/project/documents/propose?path={q}")
say("propose", (pr[0], str(pr[1])[:800]))
sc.poll(lambda: len(sc.api("GET", f"{b}/manager/activity")[1]["firings"]) > n0, 180, 3)
time.sleep(3)
for x in sc.api("GET", f"{b}/manager/activity")[1]["firings"][:1]:
    say("f", {k: x.get(k) for k in ("job", "subject", "outcome", "detail", "answer")})
say("warnings after propose", sc.api("GET", f"{b}/vault/warnings?path={q}"))
n0 = len(sc.api("GET", f"{b}/manager/activity")[1]["firings"])
say("check now", sc.api("POST", f"{b}/vault/warnings/check?path={q}"))
sc.poll(lambda: len(sc.api("GET", f"{b}/manager/activity")[1]["firings"]) > n0, 180, 3)
time.sleep(3)
say("warnings after check", sc.api("GET", f"{b}/vault/warnings?path={q}"))
save({"doc": path})
