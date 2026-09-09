"""Build the 2026-09-09 D-1 fixture: one Hub carrying all three of last night's changes.

Deliberately *one* project and *one* Hub, because the three changes were each driven singly by the
night window and what is untested is them together:

* `2026-09-07-a-dead-connection-is-never-handed-back-out` (F295)
* `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`
* `2026-09-05-the-conversation-carries-its-own-run-facts` (F274)

Three agents, all Haiku:

* `ok<tag>`    -- the ordinary agent every turn runs on
* `ghost<tag>` -- CLI pinned at an ordinary text file, which is the F291 pre-spawn reproduction
                  (`launchability.py:83` checks `os.access(x, X_OK)`, true on Windows for any file)

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/setup_d1_0909.py <project-id>
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

PID = sys.argv[1]
TAG = time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"
A = f"/projects/{PID}"

code, r = api("POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU})
show("POST /runners", code, r, limit=300)
if code not in (200, 201):
    sys.exit(1)
RUNNER = r["id"]

OK = f"ok{TAG}"
GHOST = f"ghost{TAG}"

for name in (OK, GHOST):
    code, body = api("POST", f"{A}/agents", {"name": name, "runner_id": RUNNER})
    print(f"POST /agents {name}: [{code}] {str(body)[:160]}")

# The working agent runs unattended, so nothing may wait on an operator approval.
code, body = api("PATCH", f"{A}/agents/{OK}", {"default_permission_mode": "bypassPermissions"})
print(f"PATCH {OK} permission: [{code}] {str(body)[:160]}")

# The ghost's CLI is pinned at a text file. `probe_agent` accepts it (isfile + X_OK), the spawn
# then dies with WinError 193, which is the pre-spawn `except` block F291 is about.
#
# Both agents are named in the payload deliberately: `sync_session`'s own docstring says the
# roster it carries is authoritative and *deletes* any agent omitted from it, so a payload
# carrying only the ghost would take the working agent with it.
pin = os.path.join(os.environ.get("AW_FIXTURE_ROOT", "."), "README.md").replace("\\", "/")
code, body = api(
    "POST",
    f"{A}/session/sync",
    {"data": {"agents": {OK: {}, GHOST: {"runner": "claude", "cli": pin, "model": HAIKU}}}},
)
print(f"POST /session/sync pin={pin}: [{code}] {str(body)[:300]}")

code, probe = api("GET", f"{A}/agents/{GHOST}")
print(f"GET  /agents/{GHOST}: [{code}] {str(probe)[:400]}")

print()
print(f"AW_PROJECT={PID}")
print(f"AW_AGENT_OK={OK}")
print(f"AW_AGENT_GHOST={GHOST}")
