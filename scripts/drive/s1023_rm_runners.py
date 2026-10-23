"""Runners & models phase 1: per-CLI create, launchability, alias doors, undeclared models, edges.

    py -3.11 scripts/drive/s1023_rm_runners.py
"""

import json
import pathlib

from s1023_rm_lib import B, PA, PB, q, req, show

R = f"{B()}/runners"
created = {}


def mk(label, body, p=None):
    status, res = show(label, "POST", f"{B(p)}/runners", body)
    if status == 201:
        created[label] = res["id"]
    return status, res


print("=== 1. one runner per CLI")
mk("claude-sonnet-alias", {"name": "cs", "cli": "claude", "model": "sonnet"})
mk("claude-haiku-alias", {"name": "ch", "cli": "claude", "model": "haiku"})
mk("claude-haiku45", {"name": "ch45", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
mk("claude-nomodel", {"name": "cnone", "cli": "claude"})
mk("copilot", {"name": "cop", "cli": "copilot"})
mk("codex", {"name": "cdx", "cli": "codex"})
mk("codex-optout", {"name": "cdx-optout", "cli": "codex", "flags": ["--no-app-server"]})
show("launchability", "GET", f"{R}/launchability", limit=4000)
show("launchability-by-provider", "GET", f"{R}/launchability-by-provider", limit=4000)

print("=== stored as written (API + DB)")
for lbl in ("claude-sonnet-alias", "claude-haiku-alias"):
    s, r = req("GET", f"{R}/{created[lbl]}")
    print("  api", lbl, r.get("model"), "unrecognised:", r.get("model_unrecognised"))
print("  db", q("select id,name,cli,model from runners where project_id=?", PA))

print("=== 2. undeclared model refused on runner create / patch")
mk("undeclared-create", {"name": "bad", "cli": "claude", "model": "gpt-9"})
mk("undeclared-copilot", {"name": "bad2", "cli": "copilot", "model": "claude-sonnet-99"})
show("undeclared-patch", "PATCH", f"{R}/{created['claude-nomodel']}", {"model": "claude-3-opus"})
show("alias-patch", "PATCH", f"{R}/{created['claude-nomodel']}", {"model": "opus"})
print("  db after alias patch", q("select model from runners where id=?", created["claude-nomodel"]))
show("patch-cli", "PATCH", f"{R}/{created['claude-nomodel']}", {"cli": "copilot"})
show("alias-other-cli", "POST", f"{R}", {"name": "copsonnet", "cli": "copilot", "model": "sonnet"})

print("=== 5. edges")
mk("name-32", {"name": "n" * 32, "cli": "claude", "model": "haiku"})
mk("name-33", {"name": "n" * 33, "cli": "claude", "model": "haiku"})
mk("name-256", {"name": "n" * 256, "cli": "claude", "model": "haiku"})
mk("name-257", {"name": "n" * 257, "cli": "claude", "model": "haiku"})
mk("dup-name", {"name": "ch", "cli": "claude", "model": "haiku"})
mk("blank-name", {"name": "   ", "cli": "claude", "model": "haiku"})
mk("bad-cli", {"name": "x", "cli": "gemini"})

print("=== Add-agent door")
show("agent-provider-alias", "POST", f"{B()}/agents", {"name": "a-alias", "provider": "claude", "model": "haiku"})
show("agent-provider-undeclared", "POST", f"{B()}/agents", {"name": "a-bad", "provider": "claude", "model": "gpt-9"})
show("agent-runner", "POST", f"{B()}/agents", {"name": "a-run", "runner_id": created["claude-haiku-alias"]})
show("agent-cop", "POST", f"{B()}/agents", {"name": "a-cop", "runner_id": created["copilot"]})
show("agent-cdx-optout", "POST", f"{B()}/agents", {"name": "a-cdx", "runner_id": created["codex-optout"]})
print("  db agents", q("select name,runner_id from agents where project_id=?", PA))
print("  db runners after provider+alias", q("select id,name,model from runners where project_id=? and model='haiku'", PA))

print("=== cross-project runner")
s, rb = mk("b-runner", {"name": "b-only", "cli": "claude", "model": "haiku"}, p=PB)
show("agent-xproj", "POST", f"{B()}/agents", {"name": "a-x", "runner_id": rb["id"]})
show("patch-agent-xproj", "PATCH", f"{B()}/agents/a-run", {"runner_id": rb["id"]})
show("manager-xproj", "PATCH", f"{B()}/manager/jobs/conversation-titles", {"runner_id": rb["id"]})
show("settings-checkpoint-xproj", "PUT", f"{B()}/settings", {"checkpoint_runner_id": rb["id"]})
show("settings-title-xproj", "PUT", f"{B()}/settings", {"conversation_title_runner_id": rb["id"]})
show("get-xproj", "GET", f"{R}/{rb['id']}")
show("delete-xproj", "DELETE", f"{R}/{rb['id']}")

show("agents-launchability", "GET", f"{B()}/agents/launchability", limit=5000)
show("manager-jobs", "GET", f"{B()}/manager/jobs", limit=3000)
json.dump(created, open(pathlib.Path(__file__).resolve().parents[2] / "testbed/rm1023/created.json", "w"))
