"""Runners & models phase 2: model doors on manager job / settings / trigger, and delete-409 holders.

    py -3.11 scripts/drive/s1023_rm_holders.py
No real turn is started here: every trigger probe is one the Hub must refuse before a process starts.
"""

import json
import pathlib

from s1023_rm_lib import B, PA, q, req, show

C = json.loads((pathlib.Path(__file__).resolve().parents[2] / "testbed/rm1023/created.json").read_text())
R = f"{B()}/runners"
CH = C["claude-haiku-alias"]

print("=== manager-job door (model as written, undeclared refused) -- enabled stays false")
show("mgr-runner+alias", "PATCH", f"{B()}/manager/jobs/vault-distillation", {"runner_id": CH, "model": "sonnet"})
print("  db", q("select job,enabled,runner_id,model from manager_jobs where project_id=?", PA))
show("mgr-undeclared", "PATCH", f"{B()}/manager/jobs/vault-distillation", {"model": "gpt-9"})
show("mgr-model-no-runner", "PATCH", f"{B()}/manager/jobs/vault-reports", {"model": "haiku"})
show("mgr-copilot-alias", "PATCH", f"{B()}/manager/jobs/vault-reports", {"runner_id": C["copilot"], "model": "sonnet"})
show("mgr-model-then-runner-swap", "PATCH", f"{B()}/manager/jobs/vault-distillation", {"runner_id": C["copilot"]})
print("  db after swap", q("select job,enabled,runner_id,model from manager_jobs where project_id=? and job='vault-distillation'", PA))
show("mgr-back", "PATCH", f"{B()}/manager/jobs/vault-distillation", {"runner_id": CH, "model": "sonnet"})

print("=== settings checkpoint door")
show("ckpt-alias", "PUT", f"{B()}/settings", {"checkpoint_runner_id": CH, "checkpoint_model": "haiku"})
print("  db", q("select checkpoint_runner_id,checkpoint_model,conversation_title_runner_id from projects where id=?", PA))
show("ckpt-undeclared", "PUT", f"{B()}/settings", {"checkpoint_model": "gpt-9"})
show("ckpt-copilot-model-on-claude", "PUT", f"{B()}/settings", {"checkpoint_model": "claude-haiku-4.5"})
show("title-runner", "PUT", f"{B()}/settings", {"conversation_title_runner_id": CH})
print("  db mgr", q("select job,enabled,runner_id,model from manager_jobs where project_id=?", PA))

print("=== per-run door (refusals only)")
show("trigger-undeclared", "POST", f"{B()}/agent/trigger", {"agent": "a-run", "message": "hi", "overrides": {"model": "gpt-9"}})
show("trigger-copilot-id-on-claude", "POST", f"{B()}/agent/trigger", {"agent": "a-run", "message": "hi", "overrides": {"model": "claude-haiku-4.5"}})
print("  runs", q("select id,agent,status from runs where project_id=?", PA))

print("=== a job holds the runner through its agent (disabled job)")
s, job = show("job-create", "POST", f"{B()}/jobs", {"name": "hold-ch", "agent": "a-run", "message": "noop", "cron": "0 3 1 1 *", "enabled": False})
JOB = job.get("id") if isinstance(job, dict) else None

print("=== delete a runner held by agent + job + manager job + checkpoint + title")
show("delete-held", "DELETE", f"{R}/{CH}")

print("=== a runner held only by the checkpoint setting / only a manager job")
show("ckpt-only-set", "PUT", f"{B()}/settings", {"checkpoint_runner_id": C["claude-haiku45"], "checkpoint_model": None})
show("delete-ckpt-only", "DELETE", f"{R}/{C['claude-haiku45']}")
show("mgr-only-set", "PATCH", f"{B()}/manager/jobs/spec-vault-check", {"runner_id": C["claude-sonnet-alias"]})
show("delete-mgr-only", "DELETE", f"{R}/{C['claude-sonnet-alias']}")

print("=== a runner held only by an archived agent")
show("archive-a-cop", "POST", f"{B()}/agents/a-cop/archive", {})
show("delete-archived-only", "DELETE", f"{R}/{C['copilot']}")
show("delete-again", "DELETE", f"{R}/{C['copilot']}")
print("  db a-cop", q("select name,lifecycle,runner_id from agents where project_id=? and name='a-cop'", PA))
print("  db mgr after copilot delete", q("select job,runner_id,model from manager_jobs where project_id=?", PA))
show("unarchive-a-cop", "POST", f"{B()}/agents/a-cop/unarchive", {})
s, la = req("GET", f"{B()}/agents/launchability")
print("  launchability a-cop", json.dumps(la.get("agents", {}).get("a-cop")))
s, ag = req("GET", f"{B()}/agents")
print("  agents list a-cop", [a for a in (ag if isinstance(ag, list) else ag.get("agents", [])) if a.get("name") == "a-cop"])
json.dump({"job": JOB}, open(pathlib.Path(__file__).resolve().parents[2] / "testbed/rm1023/job.json", "w"))
