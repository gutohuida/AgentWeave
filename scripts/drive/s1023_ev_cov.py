"""Print a document's coverage as one line per requirement, plus open drift (2026-10-23 evidence sweep).

    AW_P=proj-... py -3.11 scripts/drive/s1023_ev_cov.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_ev_lib import B, req  # noqa: E402

PATH = sys.argv[1] if len(sys.argv) > 1 else "spec/changes/ev-main/spec.json"
st, cov = req("GET", f"{B}/project/spec/coverage?document={PATH}")
print("coverage", st, {k: v for k, v in cov.items() if k not in ("requirements",)})
for r in cov.get("requirements", []):
    print(f"  {r['identifier']:6} {r['state']:26} integ={r.get('integration')} "
          f"reason={r.get('reason') or r.get('reasons')}")
st, drift = req("GET", f"{B}/project/spec/drift?document={PATH}")
print("drift", st, drift if st != 200 else [(d['id'], d['state'], d.get('requirement') or d.get('identifier'), d.get('resolution')) for d in drift.get('drift', drift.get('candidates', []))] if isinstance(drift, dict) else drift)
