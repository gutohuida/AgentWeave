"""Task 1.2 capture: the group's second and LAST allowed Free-plan model prompt. A one-shot
(-p) call under a scratch COPILOT_HOME, no MCP, no builtin tools, no custom instructions, no
ask-user. Saves stdout to hub/tests/fixtures/copilot_acp/oneshot_ok.jsonl and records which event
carries the answer and whether any tool was offered."""
import os, subprocess, sys

EXE = r"C:\Users\huida\AppData\Roaming\npm\node_modules\@github\copilot\node_modules\@github\copilot-win32-x64\copilot.exe"
TEMP = os.environ["TEMP"]
HOME = os.path.join(TEMP, "ghcp-t1-2-home")
WS = os.path.join(TEMP, "ghcp-t1-2-ws")
os.makedirs(HOME, exist_ok=True)
os.makedirs(WS, exist_ok=True)

env = dict(os.environ)
env["COPILOT_HOME"] = HOME
for k in ("GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN"):
    env.pop(k, None)

argv = [
    EXE, "-p", "Reply with the word ok",
    "--output-format", "json",
    "--no-auto-update",
    "--disable-builtin-mcps",
    "--no-custom-instructions",
    "--no-ask-user",
    "--excluded-tools=builtin:*,mcp:*,custom:*",
    "--allow-all-tools",
]
print("ARGV", argv)
r = subprocess.run(argv, cwd=WS, env=env, capture_output=True, timeout=120)
print("RC", r.returncode)
sys.stderr.buffer.write(r.stderr)

out_path = os.path.join(
    r"C:\Users\huida\Documents\projects\AgentWeave\hub\tests\fixtures\copilot_acp", "oneshot_ok.jsonl"
)
with open(out_path, "wb") as f:
    f.write(r.stdout)
print("SAVED", out_path, len(r.stdout), "bytes")

r2 = subprocess.run([EXE, "help", "config"], cwd=WS, env=env, capture_output=True, timeout=60)
help_path = os.path.join(
    r"C:\Users\huida\Documents\projects\AgentWeave\openspec\changes\a-copilot-agent-runs-over-acp\evidence",
    "help-config.txt",
)
with open(help_path, "wb") as f:
    f.write(r2.stdout)
print("SAVED", help_path, len(r2.stdout), "bytes")
