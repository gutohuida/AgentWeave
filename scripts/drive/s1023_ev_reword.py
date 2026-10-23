"""Reword one requirement of the 2026-10-23 evidence sweep's document through the operator's content
PUT (read from the document file on disk, payload only), and print what the Hub answered.

    AW_P=proj-... py -3.11 scripts/drive/s1023_ev_reword.py <key> <new statement>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_ev_lib import DOCS, e2e, show  # noqa: E402

PATH = "spec/changes/ev-main/spec.json"
f = pathlib.Path(e2e.os.environ["AW_E2E_ROOT"]) / "ev-main" / PATH
payload = json.loads(f.read_text(encoding="utf-8"))
payload.pop("hub", None)
for r in payload["requirements"]:
    if r["key"] == sys.argv[1]:
        print("was:", r["statement"])
        r["statement"] = sys.argv[2]
show("PUT", DOCS + f"/{PATH}/content", {"document": payload}, limit=2500)
