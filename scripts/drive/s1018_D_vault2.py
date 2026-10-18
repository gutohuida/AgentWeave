"""Sweep D vault phase 2: upload with the job on and no runner (F626), read every door."""
import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import SCRATCH, mine, save, say, sc  # noqa: E402
m = mine(); base = m["base"]
r = sc.api("POST", f"{base}/vault/sources", {
    "name": "Rate limits (June platform review)", "type": "decision",
    "content": (SCRATCH / "rl_new.txt").read_text(encoding="utf-8"), "dated": "2026-06-15"})
say("rl_new", r)
time.sleep(3)
say("activity", sc.api("GET", f"{base}/manager/activity"))
say("entry", sc.api("GET", f"{base}/vault/entries/{r[1]['id']}"))
say("events", sc.ro("select event_type, substr(data,1,400) from event_logs where project_id=? order by id desc limit 8", (m['pid'],)))
save({"src_new": r[1]["id"]})
