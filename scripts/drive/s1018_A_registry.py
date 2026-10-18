"""Sweep A (2026-10-18): Runners & models, Agents, Charters -- refusal probes over the operator
routes, read back from the database. No agent turns.

    py -3.11 scripts/drive/s1018_A_registry.py
"""

import json
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1018_A_lib import P, q, req  # noqa: E402


def s(method, path, body=None):
    status, res = req(method, path, body)
    text = json.dumps(res, ensure_ascii=False)
    print(f"\n## {method} {path} {json.dumps(body) if body is not None else ''}\n-> {status} {text[:700]}")
    return status, res


base = f"/projects/{P}"
# --- runners -------------------------------------------------------------------------------
_, h45 = s("POST", base + "/runners", {"name": "haiku45", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
_, hal = s("POST", base + "/runners", {"name": "haiku-alias", "cli": "claude", "model": "haiku"})
_, h55 = s("POST", base + "/runners", {"name": "haiku55", "cli": "claude", "model": "claude-haiku-5-5"})
s("POST", base + "/runners", {"name": "bad", "cli": "claude", "model": "claude-haiku-4-5"})
s("POST", base + "/runners", {"name": "bad2", "cli": "gemini", "model": "x"})
s("POST", base + "/runners", {"name": "", "cli": "claude"})
_, cdx = s("POST", base + "/runners", {"name": "codex-default", "cli": "codex"})
_, cop = s("POST", base + "/runners", {"name": "copilot-auto", "cli": "copilot", "model": "auto"})
s("POST", base + "/runners", {"name": "copilot-haiku55", "cli": "copilot", "model": "claude-haiku-5.5"})
s("POST", base + "/runners", {"name": "copilot-bad", "cli": "copilot", "model": "claude-haiku-4-5-20251001"})
s("POST", base + "/runners", {"name": "dupe", "cli": "claude", "model": "haiku"})
s("POST", base + "/runners", {"name": "dupe", "cli": "claude", "model": "haiku"})
print("\nstored models:", q("select name, cli, model from runners where project_id=?", P))
s("PATCH", base + f"/runners/{hal['id']}", {"model": "sonnet-9"})
s("PATCH", base + f"/runners/{hal['id']}", {"model": "opus"})
s("GET", base + "/runners/launchability")
s("GET", base + "/runners/launchability-by-provider")
s("GET", base + "/runners/nope")
s("DELETE", base + "/runners/nope")

# --- charters ------------------------------------------------------------------------------
_, charters = s("GET", base + "/charters")
print("charters:", [(c["id"], c["name"], len(c.get("content") or "")) for c in charters])
_, ch = s("POST", base + "/charters", {"name": "Sweep charter", "content": "You are careful."})
s("POST", base + "/charters", {"name": "Sweep charter", "content": "dupe"})
_, empty = s("POST", base + "/charters", {"name": "Empty charter", "content": ""})
s("PATCH", base + f"/charters/{ch['id']}", {"content": "You are very careful."})
s("GET", base + "/charters/nope")

# --- agents --------------------------------------------------------------------------------
s("POST", base + "/agents", {"name": "alpha", "runner_id": h45["id"], "charter_id": ch["id"]})
for bad in ("operator", "user", "conflicts", "settings", "sessions", "board", "boards", "a b",
            "x" * 33, "Operator"):
    s("POST", base + "/agents", {"name": bad, "runner_id": h45["id"]})
s("POST", base + "/agents", {"name": "x" * 32, "runner_id": h45["id"]})
s("POST", base + "/agents", {"name": "norunner"})
s("POST", base + "/agents", {"name": "badrunner", "runner_id": "run-nope"})
s("POST", base + "/agents", {"name": "alpha", "runner_id": h45["id"]})
s("PATCH", base + "/agents/alpha", {"contact_mode": "x"})
s("PATCH", base + "/agents/alpha", {"self_registered": True})
s("PATCH", base + "/agents/ghost", {"runner_id": h45["id"]})
s("POST", base + "/agents/ghost/archive")
s("GET", base + "/agents/ghost/timeline")
s("GET", base + "/worktrees/ghost")
s("GET", base + "/queue/ghost")
s("POST", base + "/agent/ghost/stop")
s("GET", base + "/agent/sessions/ghost")
s("POST", base + "/agent/trigger", {"agent": "ghost", "message": "hi"})
print("conversations for ghost:", q("select id, lifecycle from conversations where project_id=? and agent='ghost'", P))
print("queue rows for ghost:", q("select count(*) n from inbound_queue_entries where project_id=? and agent='ghost'", P))

# Codex and Copilot agents: launchability says what?
s("POST", base + "/agents", {"name": "cdx", "runner_id": cdx["id"]})
s("POST", base + "/agents", {"name": "cop", "runner_id": cop["id"]})
s("GET", base + "/agents/launchability")
# a charter bound to an agent: delete it
s("DELETE", base + f"/charters/{ch['id']}")
print("alpha after charter delete:", q("select name, charter_id, runner_id from agents where project_id=? and name='alpha'", P))
# delete a runner an agent holds -> 409 naming holders
s("DELETE", base + f"/runners/{h45['id']}")
# settings checkpoint runner holds a runner
s("PUT", base + "/settings", {"checkpoint_runner_id": h55["id"]})
s("DELETE", base + f"/runners/{h55['id']}")
# archive: gone from pickers; unarchive
s("POST", base + "/agents", {"name": "temp", "runner_id": hal["id"]})
s("POST", base + "/agents/temp/archive")
_, agents = s("GET", base + "/agents")
print("agents listed:", [(a.get("name"), a.get("archived_at")) for a in (agents if isinstance(agents, list) else agents.get("agents", []))])
s("PATCH", base + "/agents/temp", {"runner_id": h55["id"]})
s("POST", base + "/agent/trigger", {"agent": "temp", "message": "hi"})
s("POST", base + "/agents", {"name": "temp", "runner_id": hal["id"]})
s("POST", base + "/agents/temp/unarchive")
s("DELETE", base + "/agents/temp")
# runner only an archived agent holds can be deleted
s("POST", base + "/agents/temp/archive")
s("DELETE", base + f"/runners/{hal['id']}")
print("temp after its runner deleted:", q("select name, runner_id, archived_at from agents where project_id=? and name='temp'", P))
s("POST", base + "/agents/temp/unarchive")
print("final agents:", q("select name, runner_id, charter_id, archived_at from agents where project_id=?", P))
