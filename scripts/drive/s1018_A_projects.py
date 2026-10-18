"""Sweep A (2026-10-18): runner holders, Projects settings, relocate, instructions, nested and
non-ASCII project paths. Operator routes only; read back from the database.

    py -3.11 scripts/drive/s1018_A_projects.py
"""

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1018_A_lib import P, q, req  # noqa: E402


def s(method, path, body=None):
    status, res = req(method, path, body)
    text = json.dumps(res, ensure_ascii=False)
    print(f"\n## {method} {path} {json.dumps(body, ensure_ascii=False) if body is not None else ''}\n-> {status} {text[:900]}")
    return status, res


base = f"/projects/{P}"
# runner held by an agent AND the checkpoint setting: does the 409 name both?
runners = {r["name"]: r for r in req("GET", base + "/runners")[1]}
h55 = runners["haiku55"]["id"]
s("DELETE", base + f"/runners/{h55}")
# runner only an archived agent holds
_, rx = s("POST", base + "/runners", {"name": "only-archived", "cli": "claude", "model": "haiku"})
s("POST", base + "/agents", {"name": "arch1", "runner_id": rx["id"]})
s("POST", base + "/agents/arch1/archive")
s("DELETE", base + f"/runners/{rx['id']}")
print("arch1 after:", q("select name, runner_id, archived_at from agents where project_id=? and name='arch1'", P))
s("POST", base + "/agents/arch1/unarchive")
s("GET", base + "/agents/launchability")

# --- settings ------------------------------------------------------------------------------
s("GET", base + "/settings")
s("PUT", base + "/settings", {"hop_budget": -1})
s("PUT", base + "/settings", {"hop_budget": "x"})
s("PUT", base + "/settings", {"agent_budget": 0})
s("PUT", base + "/settings", {"nonsense_key": 1})
s("PUT", base + "/settings", {"main_branch": "does-not-exist"})
s("PUT", base + "/settings", {"main_branch": "master"})
s("PUT", base + "/settings", {"checkpoint_runner_id": "runner-nope"})
s("PUT", base + "/settings", {"conversation_title_mode": "bogus"})
s("PUT", base + "/settings", {"checks": [{"name": "tests", "command": "py -3.11 -m pytest -q"}]})
s("PUT", base + "/settings", {"allow_agent_jobs": None})
print("settings row:", q("select * from projects where id=?", P))
s("GET", base + "/queue/settings")

# --- instructions --------------------------------------------------------------------------
s("GET", base + "/project/instructions")
s("PUT", base + "/project/instructions", {"content": "Always answer in English. Prefer small diffs. Café ✓"})
s("GET", base + "/project/instructions")
s("PUT", base + "/project/instructions", {})
s("GET", base + "/project/instructions")
s("PUT", base + "/project/instructions", {"content": ""})
s("GET", base + "/project/instructions")
s("PUT", base + "/project/instructions", {"content": "Always answer in English. Prefer small diffs. Café ✓"})
s("PUT", base + "/project/instructions", {"content": "x" * 300000})
s("GET", "/projects/proj-nope/project/instructions")

# --- relocate --------------------------------------------------------------------------------
docs = pathlib.Path.home() / "Documents"
other = docs / "aw-sweepA-1018-other"
other.mkdir(exist_ok=True)
subprocess.run(["git", "-C", str(other), "init", "-q", "-b", "master"])
_, op = s("POST", "/projects/open", {"path": str(other)})
s("POST", base + "/relocate", {"path": str(other)})
s("POST", base + "/relocate", {"path": str(docs / "does-not-exist-xyz")})
s("POST", base + "/relocate", {"path": str(docs / "aw-sweepA-1018" / ".agentweave")})
# nested project (F646)
nested = docs / "aw-sweepA-1018" / "sub"
nested.mkdir(exist_ok=True)
s("POST", "/projects/open", {"path": str(nested)})
s("POST", "/projects/open", {"path": str(docs / "aw-sweepA-1018")})
s("POST", "/projects/open", {"path": str(docs)})
s("POST", "/projects/open", {"path": "relative/path"})
s("POST", "/projects/open", {"path": "C:\\Windows"})
# Step 6: a path with a space and non-ASCII characters
weird = docs / "aw sweepA ü 1018"
weird.mkdir(exist_ok=True)
(weird / "README.md").write_text("# weird\n", encoding="utf-8")
subprocess.run(["git", "-C", str(weird), "init", "-q", "-b", "master"])
subprocess.run(["git", "-C", str(weird), "add", "-A"])
subprocess.run(["git", "-C", str(weird), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "i"])
_, wp = s("POST", "/projects/open", {"path": str(weird)})
print("projects:", q("select id, name, working_directory from projects"))
pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepA\ids.json").write_text(
    json.dumps({"other": op.get("id") if isinstance(op, dict) else None, "weird": wp.get("id") if isinstance(wp, dict) else None}))
