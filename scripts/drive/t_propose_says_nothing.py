"""Does `propose` answer 200 without proposing?

The sweep saw `POST /project/documents/propose` return 200 twice on a document that was still in
`exploring` afterwards — `approve` then refused with "a document cannot move from exploring to
approved". If the 200 carries no account of why nothing moved, that is F108's shape on the
specification surface: a request answered as success that changed nothing.

Run: AW_PROJECT=<proj> AW_KEY=<key> py -3.11 scripts/drive/t_propose_says_nothing.py
"""

import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

BASE = f"/projects/{P}/project"

code, doc = api("POST", f"{BASE}/documents", {"title": "Propose probe"})
path = doc["path"]
q = urllib.parse.quote(path, safe="")
print(f"created {path}  phase={doc['phase']!r} explore_closed={doc['explore_closed']!r}")


def phase_now(label):
    code, out = api("GET", f"{BASE}/documents")
    docs = out if isinstance(out, list) else out.get("documents", [])
    row = next((d for d in docs if d.get("path") == path), None)
    print(f"  {label}: phase={row.get('phase')!r} explore_closed={row.get('explore_closed')!r}")
    return row


print()
print("--- propose while the exploration is still open")
code, out = api("POST", f"{BASE}/documents/propose?path={q}", {"reason": "probe"})
print(f"  HTTP {code}")
print(f"  body: {json.dumps(out, indent=1, default=str)[:900]}")
phase_now("after propose")

print()
print("--- close the exploration, then propose again")
code, out = api("POST", f"{BASE}/documents/close-exploration?path={q}", {"reason": "probe"})
print(f"  close: HTTP {code}  body: {json.dumps(out, default=str)[:300]}")
phase_now("after close")

code, out = api("POST", f"{BASE}/documents/propose?path={q}", {"reason": "probe"})
print(f"  propose: HTTP {code}")
print(f"  body: {json.dumps(out, indent=1, default=str)[:900]}")
phase_now("after second propose")

print()
print("--- and what does approve say now?")
code, out = api("POST", f"{BASE}/documents/phase?path={q}&to=approved", {"reason": "probe"})
print(f"  HTTP {code}  {json.dumps(out, default=str)[:400]}")
