"""Reconcile `a-codex-app-server-spec-turn-keeps-no-write-tools` (F462) into the
`spec-document-authority` capability document, through the trial Hub (the corpus is Hub-owned;
never edit the HTML).

F4's requirement already states the behaviour, including the calls-directory exception; F462 made
Codex app-server conform to it. So this adds one acceptance criterion naming that transport rather
than a requirement.

Run from hub/ so `hub.spec_payload` is importable:
  cd hub && AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
      MSYS_NO_PATHCONV=1 py -3.11 ../scripts/drive/reconcile_f462.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402

from hub.spec_payload import extract_payload  # noqa: E402

PATH = "spec/capabilities/spec-document-authority/spec.html"
REPO = pathlib.Path(__file__).resolve().parents[2]
REQUIREMENT = "authoring-assistance-is-scoped-away-from-performing-discover"
KEY = "a-codex-app-server-spec-turn-keeps-no-write-tools"

payload = extract_payload((REPO / PATH).read_text(encoding="utf-8"))
if any(c["key"] == KEY for c in payload["acceptance_criteria"]):
    raise SystemExit("already reconciled")
assert any(r["key"] == REQUIREMENT for r in payload["requirements"]), "F4's requirement moved"
payload["acceptance_criteria"].append(
    {
        "key": KEY,
        "requirement": REQUIREMENT,
        "given": "a Codex agent on its default app-server transport, in any permission posture",
        "when": "its turn is triggered with a specification document open",
        "then": (
            "its thread starts read-only and never under the never approval policy; a file change "
            "or a sandbox escape it asks for is declined (under Ask me a command still goes to the "
            "operator), except a .json arguments file in its calls directory and exactly one "
            "aw-tool invocation, which are accepted; its MCP tool calls to the Hub are unchanged"
        ),
    }
)
code, res = api("PUT", f"/projects/{P}/project/documents/{PATH}/content", {"document": payload})
print(code, json.dumps(res)[:400])
