"""Acceptance drive for F599 + F600: a runner's flags cannot override its model or the posture,
and Add-agent never hands out a flagged runner.

Before: `POST /runners` stored `--dangerously-skip-permissions` and `--model` in `flags`, which the
command builder appended after the Hub's own `--permission-mode`/`--model`, so they won (a turn on
such a runner wrote outside the workspace while the roster said `workspace`); and Add-agent's
find-or-create bound the first runner with the same cli and model, flagged or not.

  py -3.11 scripts/drive/d1015_f599_runner_flags.py <project-id>

API only, no turn. Exit 1 when any check fails.
"""

import importlib.util
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(project):
    base = f"/projects/{project}"
    for cli, flags, owner in (
        ("claude", ["--dangerously-skip-permissions"], "permission"),
        ("claude", ["--permission-mode", "bypassPermissions"], "permission"),
        ("claude", ["--model=opus"], "model"),
        ("claude", ["--model", "claude-opus-5-5"], "model"),
        ("codex", ["--dangerously-bypass-approvals-and-sandbox"], "permission"),
        ("codex", ["-c", "sandbox_mode=danger-full-access"], "permission"),
        ("copilot", ["--model", "gpt-5"], "model"),
    ):
        status, body = e2e.request(
            "POST", f"{base}/runners",
            {"name": f"f599 {cli} {' '.join(flags)}"[:60], "cli": cli, "model": None, "flags": flags},
        )
        check(f"{cli} {flags} is refused", status in (400, 422), f"{status} {str(body)[:140]}")
        if status in (400, 422):
            check(f"  and names what owns it ({owner})", owner in str(body).lower(), str(body)[:140])

    # F600: a runner with an allowed flag exists first; Add-agent must not hand it out.
    status, flagged = e2e.request(
        "POST", f"{base}/runners",
        {"name": "f600 mcp-flagged haiku", "cli": "claude", "model": "haiku",
         "flags": ["--mcp-config", "extra.json"]},
    )
    check("an allowed flag is still accepted", status == 201, f"{status} {str(flagged)[:120]}")
    status, agent = e2e.request(
        "POST", f"{base}/agents", {"name": "f600probe", "provider": "claude", "model": "haiku"}
    )
    check("Add-agent by provider and model succeeds", status in (200, 201), f"{status} {str(agent)[:120]}")
    bound = e2e.ro().execute(
        "select r.id, r.flags from agents a join runners r on r.id = a.runner_id "
        "where a.project_id=? and a.name='f600probe'", (project,)
    ).fetchone()
    check("it is bound to a runner with no flags",
          bound is not None and bound["flags"] in (None, "null", "[]"),
          f"{dict(bound) if bound else None}")
    e2e.request("POST", f"{base}/agents/f600probe/archive")


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    finally:
        print("FAILED: " + "; ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
