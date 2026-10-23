"""Runners & models phase 4: model spellings, find-or-create naming, flags vs model, runner-less trigger,
the unarchive answer for an agent whose runner went while it was archived.

    py -3.11 scripts/drive/s1023_rm_edges.py
No probe here starts a turn: each trigger targets an agent with no runner.
"""

from s1023_rm_lib import B, PA, q, show

R = f"{B()}/runners"

print("=== model spellings on runner create")
for m in ("", " haiku", "Haiku", "HAIKU", "claude-haiku-5-5[1m]", "claude-sonnet-5-5[1m]", "claude-haiku-4-5"):
    show(f"model={m!r}", "POST", R, {"name": f"sp-{len(m)}", "cli": "claude", "model": m}, limit=300)
print("  db", q("select name,model from runners where project_id=? and name like 'sp-%'", PA))

print("=== Add-agent find-or-create: what a runner the Hub makes for an alias is called")
show("agent-fable-alias", "POST", f"{B()}/agents", {"name": "a-fable", "provider": "claude", "model": "fable"})
show("agent-fable-id", "POST", f"{B()}/agents", {"name": "a-fable2", "provider": "claude", "model": "claude-fable-5-1"})
print("  db", q("select r.id,r.name,r.model,a.name agent from runners r join agents a on a.runner_id=r.id where r.project_id=? and a.name like 'a-fable%'", PA))
show("agent-copilot-auto", "POST", f"{B()}/agents", {"name": "a-cauto", "provider": "copilot", "model": "auto"})
show("agent-codex-model", "POST", f"{B()}/agents", {"name": "a-cdxm", "provider": "codex", "model": "gpt-5.5"})
show("agent-provider-only", "POST", f"{B()}/agents", {"name": "a-ponly", "provider": "claude"})

print("=== flags that name a model")
show("flags-model", "POST", R, {"name": "fm", "cli": "claude", "model": "haiku", "flags": ["--model", "opus"]})
show("flags-model-eq", "POST", R, {"name": "fm2", "cli": "claude", "model": "haiku", "flags": ["--model=opus"]})

print("=== runner-less agent: trigger and unarchive answer")
show("trigger-a-cop-norunner", "POST", f"{B()}/agent/trigger", {"agent": "a-cop", "message": "hi"})
s, r = show("arch-runner", "POST", R, {"name": "arch2", "cli": "claude", "model": "haiku"})
show("a-arch2", "POST", f"{B()}/agents", {"name": "a-arch2", "runner_id": r["id"]})
show("archive-a-arch2", "POST", f"{B()}/agents/a-arch2/archive", {})
show("delete-arch2-runner", "DELETE", f"{R}/{r['id']}")
show("unarchive-a-arch2", "POST", f"{B()}/agents/a-arch2/unarchive", {})
s, la = show("launch-a-arch2", "GET", f"{B()}/agents/launchability", limit=0)
print("  a-arch2 verdict", la["agents"].get("a-arch2"))
print("  events", q("select event_type,data from event_logs where project_id=? and (event_type like 'runner%' or data like '%a-arch2%') order by id", PA))
