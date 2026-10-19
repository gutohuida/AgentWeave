"""F755 acceptance check: every example the change `the-shell-judges-text-rules-are-specified`
states is decided by the real judge (`hub.mcp_server._decide`) as the change says.

Spec-only change: no code moves, so the check is that the stated rules match the judge. Runs in
a throwaway workspace with a link out of it, no Hub needed.

  py -3.11 scripts/drive/d1019_f755_judge_rules_check.py
"""

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "hub"))
from hub.mcp_server import _decide  # noqa: E402

ALLOW, REFUSE = True, False
CONFIG = "configures your runner"

ROWS = [
    # runner-configuration-is-not-written-by-a-tool-call
    ("Write", {"file_path": ".claude/settings.local.json"}, REFUSE, CONFIG),
    ("Edit", {"file_path": ".mcp.json"}, REFUSE, CONFIG),
    ("NotebookEdit", {"notebook_path": ".codex/x.ipynb"}, REFUSE, CONFIG),
    ("Write", {"file_path": ".github/hooks/hooks.json"}, REFUSE, CONFIG),
    ("Bash", {"command": "cp allow.json .claude/settings.json"}, REFUSE, CONFIG),
    (
        "Bash",
        {"command": "mkdir -p .claude/hooks && printf x > .claude/hooks/a.sh"},
        REFUSE,
        CONFIG,
    ),
    ("Bash", {"command": "touch .codex"}, REFUSE, CONFIG),
    ("Bash", {"command": "cat .claude/settings.json"}, REFUSE, CONFIG),
    (
        "PowerShell",
        {"command": "Set-Content -Path .claude/settings.local.json -Value '{}'"},
        REFUSE,
        CONFIG,
    ),
    ("Read", {"file_path": ".claude/settings.json"}, ALLOW, None),
    ("Write", {"file_path": "CLAUDE.md"}, ALLOW, None),
    ("Write", {"file_path": ".claude/skills/x/SKILL.md"}, ALLOW, None),
    ("Write", {"file_path": "sub/.claude/settings.json"}, ALLOW, None),
    ("Bash", {"command": "printf x > .claude/notes.md"}, ALLOW, None),
    ("Bash", {"command": "ls .claude"}, ALLOW, None),
    # a-text-tools-script-is-not-a-path
    ("Bash", {"command": "sed 's|/usr|x|' a.txt"}, ALLOW, None),
    ("Bash", {"command": "awk -F/ '{print $1}' a.txt"}, ALLOW, None),
    ("Bash", {"command": "cut -d/ -f2 a.txt"}, ALLOW, None),
    ("Bash", {"command": "tr / _ < a.txt"}, ALLOW, None),
    ("Bash", {"command": "grep -rn '\\.\\./' src"}, ALLOW, None),
    ("Bash", {"command": "grep '$HOME' a.txt"}, ALLOW, None),
    ("Bash", {"command": "sed 's/x/y/w ../out' a.txt"}, REFUSE, None),
    ("Bash", {"command": "awk '{print > \"../out\"}' a.txt"}, REFUSE, None),
    ("Bash", {"command": "awk '$1 > 5' ../a.txt"}, REFUSE, None),
    ("Bash", {"command": "sed s/a/b/ ../a.txt"}, REFUSE, None),
    ("Bash", {"command": "grep -f ../patterns a.txt"}, REFUSE, None),
    ("Bash", {"command": "grep x ../a.txt"}, REFUSE, None),
    ("Bash", {"command": "grep x --exclude-from ../x a.txt"}, REFUSE, None),
    ("Bash", {"command": 'sed "s/x/$(cat ../y)/" a.txt'}, REFUSE, None),
    # the-working-directory-by-name-is-judged-as-the-workspace-root
    ("Bash", {"command": "echo $PWD"}, ALLOW, None),
    ("Bash", {"command": 'ls "${PWD}"'}, ALLOW, None),
    ("Bash", {"command": "ls $(pwd)"}, ALLOW, None),
    ("Bash", {"command": "ls `pwd`"}, ALLOW, None),
    ("PowerShell", {"command": "Get-ChildItem $(Get-Location)"}, ALLOW, None),
    ("Bash", {"command": "ls $PWD/.."}, REFUSE, None),
    ("Bash", {"command": "ls ${PWD%/*}"}, REFUSE, None),
    ("Bash", {"command": "x=$PWD; ls $x"}, REFUSE, None),
    ("Bash", {"command": "PWD=/ cp x $PWD"}, REFUSE, None),
    ("Bash", {"command": "ls $(dirname $(pwd))"}, REFUSE, None),
    ("Bash", {"command": "d=$(pwd); ls $d"}, REFUSE, None),
    ("Bash", {"command": "pwd() { echo /; }; ls $(pwd)"}, REFUSE, None),
    ("PowerShell", {"command": "ls (Split-Path (pwd))"}, REFUSE, None),
    ("PowerShell", {"command": "$d = Get-Location; ls $d"}, REFUSE, None),
    ("PowerShell", {"command": "ls (Split-Path $PWD)"}, REFUSE, None),
]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        ws = pathlib.Path(tmp) / "work"
        (ws / "sub").mkdir(parents=True)
        os.environ["AW_WORKSPACE_DIR"] = str(ws)
        os.environ.pop("AW_RUN_TOKEN", None)
        failed = 0
        for tool, tool_input, allow, reason in ROWS:
            decision = _decide(tool, tool_input)
            ok = decision["allow"] is allow and (reason is None or reason in decision["reason"])
            if reason == CONFIG and ok:
                ok = "ask_user" in decision["reason"]
            failed += not ok
            print(f"{'ok  ' if ok else 'FAIL'} {tool:<12} {tool_input}  -> {decision}")
        print(f"{len(ROWS) - failed}/{len(ROWS)} as the change states")
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
