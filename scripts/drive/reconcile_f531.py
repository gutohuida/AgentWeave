"""Reconcile `a-hub-claude-run-gets-only-the-hubs-tool-server` (F531) into the `agent-run-sandboxing`
capability document, through the trial Hub (the corpus is Hub-owned; never edit the HTML).

Run from hub/ so `hub.spec_payload` is importable:
  cd hub && AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
      MSYS_NO_PATHCONV=1 py -3.11 ../scripts/drive/reconcile_f531.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402

from hub.spec_payload import extract_payload  # noqa: E402

PATH = "spec/capabilities/agent-run-sandboxing/spec.html"
REPO = pathlib.Path(__file__).resolve().parents[2]
KEY = "a-hub-claude-run-gets-only-the-hubs-tool-server"

payload = extract_payload((REPO / PATH).read_text(encoding="utf-8"))
if any(r["key"] == KEY for r in payload["requirements"]):
    raise SystemExit("already reconciled")
payload["requirements"].append({
    "key": KEY,
    "modal": "SHALL",
    "statement": (
        "Every Claude agent run the Hub spawns SHALL load only the MCP servers named on its own "
        "command line, by passing --strict-mcp-config whether or not the Hub's own server is "
        "injected; a server a runner's flags name with --mcp-config SHALL still load."
    ),
    "rationale": (
        "F531: without it Claude Code merged the operator's claude.ai account connectors (Gmail, "
        "Drive, Calendar, Docs) and user/project servers into every agent run, tools no Hub "
        "surface granted, described or recorded."
    ),
})
payload["acceptance_criteria"] += [
    {"key": f"{KEY}-drive", "requirement": KEY,
     "given": "an operator account carrying claude.ai connectors",
     "when": "a Hub agent turn runs",
     "then": "its argv carries --strict-mcp-config and it names no mcp__claude_ai tool"},
    {"key": f"{KEY}-runner-flag", "requirement": KEY,
     "given": "a runner whose flags carry --mcp-config naming another server",
     "when": "its run starts",
     "then": "it loads exactly the Hub's server and that one"},
]
code, res = api("PUT", f"/projects/{P}/project/documents/{PATH}/content", {"document": payload})
print(code, json.dumps(res)[:400])
