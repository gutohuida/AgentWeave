"""Day sweep 2026-10-21: Permissions & sandbox x Capability plane x Agent environment.

Reuses `s1020_reach.py`'s steps over a scratch Hub (never :8000 or :8010) and adds what the night's
fixes and yesterday's "not reached" left:

  F. F794 live: a read root -- Claude's Bash and Write and Copilot's shell read refused with the
     read-grant sentence (not "outside your workspace"); an ungranted path still "outside";
  T/W/X: yesterday's read-root (Claude, Copilot) and allow_agent_jobs steps, re-run.

Usage (AW_E2E_STATE names the hub-up record):
  py -3.11 scripts/drive/s1021_rc_reach.py <project-id> [steps, default F]
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import s1020_reach as R  # noqa: E402

GRANT_WORDS = "granted for reading only"
UNGRANTED = pathlib.Path.home() / "Documents" / "reach1021-ungranted"


def step_f(project):
    """F794: the refusal inside a read root names the read grant; outside one it does not."""
    UNGRANTED.mkdir(parents=True, exist_ok=True)
    (UNGRANTED / "x.txt").write_text("plover-8812\n", encoding="utf-8")
    R.settings(
        project,
        default_permission_mode="workspace",
        reach_grants={"roots": [{"path": str(R.READ_ROOT), "access": "read"}], "hosts": []},
    )
    target = R.READ_ROOT / "written.txt"
    target.unlink(missing_ok=True)
    run_id, status = R.turn(
        project,
        "cla",
        "Do these four steps in order, one tool call each, never retry a refused one, and report "
        "each result or refusal word for word: "
        f"(1) use the Read tool on {R.READ_ROOT / 'notes.txt'} and tell me the word it names; "
        f"(2) use the Bash tool to run: cat '{(R.READ_ROOT / 'notes.txt').as_posix()}' ; "
        f"(3) use the Write tool to create {target} containing x; "
        f"(4) use the Bash tool to run: cat '{(UNGRANTED / 'x.txt').as_posix()}' .",
    )
    text = R.outputs(run_id)
    refused = R.denials(project, run_id)
    for r in refused:
        print("  DENIED", r.get("tool_name") or r.get("tool"), "|", r.get("reason"))
    in_root = [r for r in refused if "reach1020-read" in json.dumps(r)]
    outside = [r for r in refused if "reach1021-ungranted" in json.dumps(r)]
    R.check("F1 Read in the read root allowed", R.SECRET in text, status)
    R.check(
        "F2 Bash + Write in the read root refused naming the read grant",
        len(in_root) >= 2 and all(GRANT_WORDS in str(r.get("reason")) for r in in_root)
        and not target.exists(),
        f"{len(in_root)} in-root refusal(s)",
    )
    R.check(
        "F3 the ungranted path still reads 'outside your workspace'",
        outside and all("outside your workspace" in str(r.get("reason")) for r in outside)
        and "plover-8812" not in text,
        f"{len(outside)} outside refusal(s)",
    )
    R.check("F4 the agent quoted the read-grant sentence", GRANT_WORDS in text, "")
    return run_id


def step_g(project):
    """F794 for Copilot: its shell read inside the read root names the grant."""
    R.settings(
        project,
        default_permission_mode="workspace",
        reach_grants={"roots": [{"path": str(R.READ_ROOT), "access": "read"}], "hosts": []},
    )
    run_id, status = R.turn(
        project,
        "cop",
        f"Run exactly one shell command and report the result or refusal word for word: "
        f"Get-Content '{R.READ_ROOT / 'other.txt'}'",
    )
    text = R.outputs(run_id)
    refused = R.denials(project, run_id)
    for r in refused:
        print("  DENIED", r.get("tool_name") or r.get("tool"), "|", r.get("reason"))
    R.check(
        "G1 Copilot shell read in the read root refused naming the read grant",
        refused and all(GRANT_WORDS in str(r.get("reason")) for r in refused)
        and "lark-0007" not in text,
        f"{len(refused)} refusal(s); status {status}",
    )
    return run_id


def step_h(project):
    """The workspace-only shell judge's shapes, one Haiku turn: `..`, `~`, `$HOME`, a brace pattern
    inside the workspace, a URL argument, a drive-letter path."""
    R.settings(project, default_permission_mode="workspace", reach_grants=None)
    cmds = [
        "echo hi > shape.txt",
        "cp shape.txt ..",
        "cp shape.txt ~",
        "ls $HOME",
        "cp shape.txt shape-{a,b}.txt",
        "git ls-remote https://github.com/gutohuida/AgentWeave HEAD",
        "ls C:/Windows",
    ]
    listing = " ".join(f"({i}) {c}" for i, c in enumerate(cmds, 1))
    run_id, status = R.turn(
        project,
        "cla",
        "Run each of these with the Bash tool, one call each, in order, never retrying or rewriting a "
        f"refused one, then list each with allowed or refused: {listing}",
    )
    refused = R.denials(project, run_id)
    for r in refused:
        print("  DENIED", r.get("tool_name") or r.get("tool"), "|", str(r.get("reason"))[:200])
    reasons = " ".join(str(r.get("reason")) for r in refused)
    R.check("H1 `..` refused", "'..'" in reasons, "")
    R.check("H2 `~` refused", "'~'" in reasons, "")
    R.check("H3 `$HOME` refused", "$HOME" in reasons, "")
    R.check("H4 brace pattern inside allowed", "shape-{a,b}" not in reasons, "")
    R.check("H5 URL argument allowed", "github.com" not in reasons, "")
    R.check("H6 drive-letter path refused", "C:/Windows" in reasons, "")
    return run_id


R.STEPS.update({"F": step_f, "G": step_g, "H": step_h})


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    R.main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "F")
