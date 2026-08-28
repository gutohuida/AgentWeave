"""Full-surface sweep, part 2: the spec flow's operator gates, and the refusals guarding them.

Row 9 of the coverage matrix, plus rows 10 (evidence and drift) and 11 (jobs and loops) as far as
they go without spending an agent turn. The skill's rule 6 is the point: most of this product is
gates, and a gate that refuses correctly but says only "forbidden" is a defect.

Routes come from the running Hub's `/openapi.json`.

Run: AW_PROJECT=<proj> AW_KEY=<key> py -3.11 scripts/drive/t_sweep_spec.py
"""

import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

RESULTS = []


def probe(row, label, method, path, body=None, expect=None):
    code, out = api(method, path, body)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    detail = out.get("detail") if isinstance(out, dict) else None
    RESULTS.append((row, label, code, ok, detail if isinstance(detail, str) else None))
    print(f"[{row}] {label}: {code}{'' if ok else '  <-- UNEXPECTED'}")
    if isinstance(detail, str):
        print(f"      refusal: {detail[:300]}")
    elif not ok:
        print(f"      body: {json.dumps(out, default=str)[:400]}")
    return code, out


BASE = f"/projects/{P}/project"

print("=" * 78)
print("ROW 9 — the spec flow: documents, phases, and every gate between them")
print("=" * 78)
probe(9, "list documents", "GET", f"{BASE}/documents", expect=200)
probe(9, "read the spec surface", "GET", f"{BASE}/spec", expect=200)
probe(9, "list requirements", "GET", f"{BASE}/spec/requirements", expect=200)

code, doc = probe(9, "create a document", "POST", f"{BASE}/documents",
                  {"title": "Sweep specification", "kind": "change"}, expect=(200, 201))
path = None
if isinstance(doc, dict):
    path = doc.get("path") or (doc.get("document") or {}).get("path")
print(f"      document path: {path!r}")

if path:
    q = urllib.parse.quote(path, safe="")
    probe(9, "propose from an exploration that was never closed", "POST",
          f"{BASE}/documents/propose", {"path": path, "reason": "sweep"})
    probe(9, "approve straight from exploring", "POST", f"{BASE}/documents/phase",
          {"path": path, "phase": "approved", "reason": "sweep"})
    probe(9, "move to a phase that does not exist", "POST", f"{BASE}/documents/phase",
          {"path": path, "phase": "banana", "reason": "sweep"})
    probe(9, "close the exploration", "POST", f"{BASE}/documents/close-exploration",
          {"path": path, "reason": "sweep"})
    probe(9, "propose it now", "POST", f"{BASE}/documents/propose",
          {"path": path, "reason": "sweep"}, expect=(200, 201))
    probe(9, "approve it", "POST", f"{BASE}/documents/phase",
          {"path": path, "phase": "approved", "reason": "sweep"}, expect=(200, 201))
    probe(9, "approve it a second time", "POST", f"{BASE}/documents/phase",
          {"path": path, "phase": "approved", "reason": "sweep again"})
    probe(9, "edit an approved document's content", "PUT", f"{BASE}/documents/{q}/content",
          {"content": "# Rewritten after approval\n"})
    probe(9, "demote rigor on an approved document", "POST", f"{BASE}/documents/{q}/rigor",
          {"rigor": "low", "reason": "sweep"})
    probe(9, "coverage", "GET", f"{BASE}/spec/coverage?path={q}")

probe(9, "phase a document that does not exist", "POST", f"{BASE}/documents/phase",
      {"path": "spec/nope.md", "phase": "approved", "reason": "sweep"})
probe(9, "propose a document that does not exist", "POST", f"{BASE}/documents/propose",
      {"path": "spec/nope.md", "reason": "sweep"})

print()
print("=" * 78)
print("ROW 10 — evidence, its decision, and drift")
print("=" * 78)
probe(10, "list evidence", "GET", f"{BASE}/spec/evidence", expect=200)
probe(10, "record evidence for a requirement that does not exist", "POST",
      f"{BASE}/spec/evidence",
      {"requirement": "REQ-nope", "kind": "test", "summary": "sweep", "commit": "a" * 40})
probe(10, "decide evidence that does not exist", "POST",
      f"{BASE}/spec/evidence/ev-nope/decision", {"decision": "accepted", "reason": "sweep"})
probe(10, "read drift", "GET", f"{BASE}/spec/drift", expect=200)
probe(10, "detect drift", "POST", f"{BASE}/spec/drift/detect", {}, expect=(200, 201))

print()
print("=" * 78)
print("ROW 11 — jobs and loops (created disabled, archived at the end — never left enabled)")
print("=" * 78)
probe(11, "list jobs", "GET", f"/projects/{P}/jobs", expect=200)
probe(11, "list loops", "GET", f"/projects/{P}/loops", expect=200)
code, job = probe(11, "create a job naming an agent that does not exist", "POST",
                  f"/projects/{P}/jobs",
                  {"name": "sweep-ghost-job", "agent": "ghost-agent",
                   "prompt": "do something", "schedule": "*/5 * * * *", "enabled": False})
jid = job.get("id") if isinstance(job, dict) else None
print(f"      job id: {jid!r}")
if jid:
    probe(11, "  its history", "GET", f"/projects/{P}/jobs/{jid}/history", expect=200)
    probe(11, "  delete it (jobs are archived, not deleted)", "DELETE",
          f"/projects/{P}/jobs/{jid}")
    probe(11, "  archive it", "POST", f"/projects/{P}/jobs/{jid}/archive", expect=(200, 201))
probe(11, "create a job with an invalid schedule", "POST", f"/projects/{P}/jobs",
      {"name": "sweep-bad-cron", "agent": "driver", "prompt": "x", "schedule": "not a cron",
       "enabled": False})

print()
print("=" * 78)
print("SUMMARY")
print("=" * 78)
unexpected = [r for r in RESULTS if not r[3]]
print(f"unexpected statuses: {len(unexpected)}")
for row, label, code, ok, detail in unexpected:
    print(f"  [{row}] {label} -> {code}  {(detail or '')[:140]}")

print()
print("Gates that ACCEPTED something a gate should refuse (2xx where a refusal was expected):")
for row, label, code, ok, detail in RESULTS:
    if 200 <= code < 300 and any(
        w in label for w in ("does not exist", "never closed", "straight from", "second time",
                             "after approval", "Demote", "demote", "invalid")
    ):
        print(f"  [{row}] {code} {label}")
