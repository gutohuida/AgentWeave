"""Sweep D vault phase 3: F630 model refusals, cross-project runner, F610 other project, enable, uploads."""
import json, pathlib, sys, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import SCRATCH, mine, save, say, sc  # noqa: E402
m = mine(); base = m["base"]; R = m["runner"]
P2 = "proj-3c1db4d37322"; D2 = r"C:\Users\huida\Documents\aw-sweepD2-1018"
code, r2 = sc.api("POST", f"/projects/{P2}/runners", {"name": "Haiku2", "cli": "claude", "model": "haiku"})
say("p2 runner", (code, r2.get("id")))
save({"p2": P2, "p2_runner": r2["id"], "p2_dir": D2})
say("cross-project runner", sc.api("PATCH", f"{base}/manager/jobs/vault-distillation", {"runner_id": r2["id"]}))
say("undeclared model", sc.api("PATCH", f"{base}/manager/jobs/vault-distillation", {"runner_id": R, "model": "gpt-5"}))
say("codex model on claude runner", sc.api("PATCH", f"{base}/manager/jobs/vault-distillation", {"runner_id": R, "model": "gpt-5.1-codex"}))
say("model w/o runner on titles", sc.api("PATCH", f"{base}/manager/jobs/conversation-titles", {"model": "gpt-5"}))
say("unknown job", sc.api("PATCH", f"{base}/manager/jobs/no-such-job", {"enabled": True}))
say("unknown field", sc.api("PATCH", f"{base}/manager/jobs/vault-distillation", {"bogus": 1}))
say("loc = other project dir", sc.api("PUT", f"{base}/vault/settings", {"private_location": D2 + r"\vault"}))
say("loc = other project's private vault", sc.api("PUT", f"{base}/vault/settings", {"private_location": rf"C:\Users\huida\.agentweave\hub\vaults\{P2}"}))
priv = r"C:\Users\huida\Documents\sweepD private vault ü"
say("loc space+nonascii", sc.api("PUT", f"{base}/vault/settings", {"private_location": priv}))
say("settings now", sc.api("GET", f"{base}/vault/settings"))
say("p2 loc = same folder", sc.api("PUT", f"/projects/{P2}/vault/settings", {"private_location": priv}))
say("enable distil", sc.api("PATCH", f"{base}/manager/jobs/vault-distillation", {"enabled": True, "runner_id": R, "model": "haiku"}))
save({"priv": priv})
for key in ("src_old", "src_new"):
    say(f"distil {key}", sc.api("POST", f"{base}/vault/sources/{m[key]}/distil"))
def upload(path, media, name, **q):
    q = {"name": name, "type": "document", **q}
    code, _, raw = sc.call("POST", f"{base}/vault/files?{urllib.parse.urlencode(q)}", pathlib.Path(path).read_bytes(), content_type=media, timeout=120)
    try: return code, json.loads(raw or b"null")
    except ValueError: return code, raw.decode(errors="replace")[:600]
p = upload(SCRATCH / "backoff.pdf", "application/pdf", "Client retries guide", dated="2026-03-01"); say("pdf", p)
g = upload(SCRATCH / "gateway.png", "image/png", "Gateway settings screenshot"); say("png", g)
pv = sc.api("POST", f"{base}/vault/sources", {"name": "Escalation contacts", "type": "note", "visibility": "private",
    "content": "Internal: the gateway vendor's support line is 555-0142. Escalate only after 30 minutes."}); say("private", pv)
lg = sc.api("POST", f"{base}/vault/sources", {"name": "On-call handbook", "type": "rules",
    "content": (SCRATCH / "oncall_long.txt").read_text(encoding="utf-8"), "dated": "2026-04-01"}, timeout=120); say("long", lg)
save({"src_pdf": p[1].get("id"), "src_png": g[1].get("id"), "src_priv": pv[1].get("id"), "src_long": lg[1].get("id")})
