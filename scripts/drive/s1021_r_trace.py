"""night-recheck: F776 (no divergence on a completed task's run) and F791 (no error span from the
MERGE_HEAD probes) read back from a finished run.   py -3.11 scripts/drive/s1021_r_trace.py <run>"""
import json, os, pathlib, sys
os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-r1021.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402
P = os.environ["AW_P"]; run = sys.argv[1]
c = e2e.ro()
print("divergence tables:", [r[0] for r in c.execute("select name from sqlite_master where name like '%diverg%'")])
for r in c.execute("select * from run_divergences where run_id=?", (run,)): print("DIVERGENCE", dict(r))
s, d = e2e.request("GET", f"/projects/{P}/traces/by-run/{run}?limit=2000")
print("trace", s, len(d["spans"]), "spans")
for sp in d["spans"]:
    if sp.get("status") == "error" or "MERGE_HEAD" in json.dumps(sp):
        print(" ", sp["operation"], sp.get("status"), json.dumps(sp)[:260])
print("aw.command spans:", sum(1 for sp in d["spans"] if sp["operation"] == "aw.command"))
