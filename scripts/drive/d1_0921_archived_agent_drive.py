"""D-1 drive, day window 2026-09-21: `an-archived-agent-holds-nothing-and-is-offered-nowhere`.

Goes past the change's own 6.3 drive: real event log (agent_archived), the F390 runner wall,
archive while a real Haiku turn is in flight, an unarchived agent running a real turn charterless,
repeat/edge calls. Never targets :8000 or :8010. Never pipe through head.

    AW_HUB=http://127.0.0.1:8097 AW_KEY=... py -3.11 -u scripts/drive/d1_0921_archived_agent_drive.py
"""
import os, pathlib, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api  # noqa: E402

HUB = os.environ.get("AW_HUB", "")
if HUB.endswith(":8000") or HUB.endswith(":8010") or not HUB:
    sys.exit("REFUSING: not this drive's port")
HAIKU = "claude-haiku-4-5-20251001"
TAG = time.strftime("%H%M%S")
root = pathlib.Path.home() / "Documents" / f"drive-0921-arch-{TAG}"
V = []


def v(label, ok, detail=""):
    V.append((label, bool(ok)))
    print("  [%s] %s  -- %s" % ("OK " if ok else "BAD", label, str(detail)[:400]))


root.mkdir(parents=True)
(root / "README.md").write_text("x\n")
for c in (["git", "init", "-b", "main"], ["git", "config", "user.email", "d@e.invalid"],
          ["git", "config", "user.name", "d"], ["git", "add", "."], ["git", "commit", "-m", "i"]):
    subprocess.run(c, cwd=root, check=True, capture_output=True)
code, proj = api("POST", "/projects/open", {"path": str(root), "name": "arch-%s" % TAG})
assert code in (200, 201), (code, proj)
A = "/projects/%s" % proj["id"]
print("project", proj["id"], root)

_, r1 = api("POST", A + "/runners", {"name": "h1", "cli": "claude", "model": HAIKU})
_, r2 = api("POST", A + "/runners", {"name": "h2", "cli": "claude", "model": HAIKU})
c, ch = api("POST", A + "/charters", {"name": "reviewer-%s" % TAG, "content": "# Terse\n\nBe terse."})
print("charter", c, str(ch)[:200])
if c not in (200, 201):
    c, chl = api("GET", A + "/charters"); print(str(chl)[:400])
CH = ch["id"]
for n, r in (("aa", r1), ("bb", r2), ("cc", r1)):
    c, b = api("POST", A + "/agents", {"name": n, "runner_id": r["id"], "charter_id": CH if n != "cc" else None})
    assert c == 201, (c, b)
    api("PATCH", "%s/agents/%s" % (A, n), {"default_permission_mode": "bypassPermissions"})

print("\n== F185: charter wall")
c, b = api("DELETE", "%s/charters/%s" % (A, CH))
v("charter held by OPEN agents refuses 409 and names holders", c == 409 and "aa" in str(b), (c, b))
c, b = api("POST", A + "/agents/aa/archive"); print("  archive aa:", c, b)
v("archive response names released charter", c == 200 and b.get("released_charter_id") == CH and b.get("message"), b)
c, b = api("DELETE", "%s/charters/%s" % (A, CH))
v("still 409 (bb open), names bb but NOT aa", c == 409 and "bb" in str(b) and "aa" not in str(b), (c, b))
api("POST", A + "/agents/bb/archive")
c, b = api("POST", A + "/agents/bb/archive"); v("second archive of same agent is benign", c in (200, 409), (c, b))
c, ev = api("GET", A + "/events/history?limit=100")
kinds = [e.get("type") for e in ev] if c == 200 else ev
print("  events:", str(kinds)[:300])
arch=[e for e in ev if e.get("type")=="agent_archived"] if c==200 else []
v("agent_archived persisted for aa and bb, aa carries released_charter_id", len(arch)>=2 and any(e["data"].get("released_charter_id")==CH for e in arch), arch[:2])
c, b = api("PATCH", A + "/agents/aa", {"charter_id": CH})
v("re-bind charter to archived agent -> 409 with remedy", c == 409 and "unarchiv" in str(b).lower(), (c, b))
c, b = api("PATCH", A + "/agents/aa", {"charter_id": None}); v("null clear permitted on archived", c == 200, (c, b))
c, b = api("DELETE", "%s/charters/%s" % (A, CH)); v("charter delete now 204", c in (200, 204), (c, b))

print("\n== F390: runner wall")
c, b = api("DELETE", "%s/runners/%s" % (A, r1["id"]))
v("runner r1 (open holder cc + archived aa) 409, aa tagged archived", c == 409 and "aa (archived)" in str(b) and "cc" in str(b), (c, b))
c, b = api("DELETE", "%s/runners/%s" % (A, r2["id"]))
v("runner r2 (only archived bb) 409 with archived remedy", c == 409 and "bb (archived)" in str(b) and "archived filter" in str(b), (c, b))

print("\n== F181: launchability vs trigger")
c, lb = api("GET", A + "/agents/launchability")
names = set((lb.get("agents") or {}).keys()) if isinstance(lb, dict) else set()
print("  launchability:", c, str(lb)[:300])
v("archived aa/bb absent from launchability, cc present", c == 200 and not ({"aa", "bb"} & names) and "cc" in names, names)
c, b = api("POST", A + "/agent/trigger", {"agent": "aa", "message": "hi"})
v("trigger archived agent refused", c in (409, 400, 403) and "archived" in str(b).lower(), (c, b))
c, lb = api("GET", A + "/agents/launchability?lifecycle=archived")
print("  launchability?lifecycle=archived:", c, str(lb)[:200])
c, b = api("GET", A + "/agents?lifecycle=archived"); v("archived filter lists aa,bb", c == 200 and {"aa", "bb"} <= {a["name"] for a in b}, [a["name"] for a in b] if isinstance(b, list) else b)

print("\n== mid-flow: archive while a real Haiku turn runs")
c, t = api("POST", A + "/agent/trigger", {"agent": "cc", "message": "Reply with the single word: pong.", "overrides": {"permission_mode": "bypassPermissions"}})
print("  trigger cc:", c, str(t)[:200])
c, b = api("POST", A + "/agents/cc/archive"); print("  archive cc mid-turn:", c, str(b)[:200])
time.sleep(40)
c, ag = api("GET", A + "/agents?lifecycle=archived")
row = [a for a in ag if a["name"] == "cc"] if isinstance(ag, list) else []
print("  cc row:", row and {k: row[0].get(k) for k in ("status", "lifecycle", "charter_id")})
v("mid-turn archive: agent ends not stuck 'running'", row and row[0].get("status") != "running", row and row[0].get("status"))

print("\n== unarchive -> charterless real turn")
c, b = api("POST", A + "/agents/cc/unarchive"); v("unarchive message present, charter_id None", c == 200 and b.get("charter_id") is None and b.get("message"), b)
c, t = api("POST", A + "/agent/trigger", {"agent": "cc", "message": "Reply with the single word: pong.", "overrides": {"permission_mode": "bypassPermissions"}})
v("unarchived agent triggers", c in (200, 201, 202), (c, str(t)[:200]))
time.sleep(35)
c, lb = api("GET", A + "/agents/launchability")
v("unarchived cc back in launchability", "cc" in (lb.get("agents") or {}), str(lb)[:200])

print("\nSUMMARY: %d/%d ok" % (sum(1 for _, o in V if o), len(V)))
for l, o in V:
    if not o:
        print("  BAD:", l)
