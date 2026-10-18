"""Sweep D vault phase 1: refusals and uploads with the distillation job off, then on with no runner."""

import json
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import SCRATCH, mine, save, say, sc  # noqa: E402

m = mine()
base = m["base"]
root = pathlib.Path(m["root"])


def upload(path, media, name, **q):
    q = {"name": name, "type": "document", **q}
    code, _, raw = sc.call("POST", f"{base}/vault/files?{urllib.parse.urlencode(q)}",
                           pathlib.Path(path).read_bytes(), content_type=media, timeout=120)
    try:
        return code, json.loads(raw or b"null")
    except ValueError:
        return code, raw.decode(errors="replace")[:600]


say("exact 10MiB pdf", upload(SCRATCH / "exact.pdf", "application/pdf", "exact10"))
say("file bad dated", upload(SCRATCH / "backoff.pdf", "application/pdf", "bd", dated="March 1"))

# private location refusals (F610)
say("loc inside repo", sc.api("PUT", f"{base}/vault/settings", {"private_location": str(root / "privvault")}))
say("loc in this repo (AgentWeave checkout)", sc.api(
    "PUT", f"{base}/vault/settings",
    {"private_location": r"C:\Users\huida\Documents\projects\AgentWeave\testbed\privD"}))
say("loc relative", sc.api("PUT", f"{base}/vault/settings", {"private_location": "relative/dir"}))

# uploads with the job off
r1 = sc.api("POST", f"{base}/vault/sources", {
    "name": "Rate limits (Feb runbook)", "type": "decision",
    "content": (SCRATCH / "rl_old.txt").read_text(encoding="utf-8"), "dated": "2026-02-01"})
say("rl_old", r1)
src_old = r1[1].get("id") if isinstance(r1[1], dict) else None
say("distil with job off", sc.api("POST", f"{base}/vault/sources/{src_old}/distil"))

# job on, no runner (F626)
say("enable distil no runner", sc.api("PATCH", f"{base}/manager/jobs/vault-distillation", {"enabled": True}))
say("distil with no runner", sc.api("POST", f"{base}/vault/sources/{src_old}/distil"))
say("activity", sc.api("GET", f"{base}/manager/activity"))
say("jobs after", sc.api("GET", f"{base}/manager/jobs"))
save({"src_old": src_old})
