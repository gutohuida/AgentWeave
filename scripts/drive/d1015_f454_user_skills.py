"""Acceptance drive for F454: a Hub-launched Claude agent does not load the operator's own skills.

Before: an agent ran with every skill in `~/.claude/skills` (a loop firing ran `e2e-loop` and
started loops and commits nobody asked for), because the Hub spawns Claude Code with all its
setting sources. After: `--setting-sources project,local` -- the project's own CLAUDE.md, settings
and skills, not the operator's. Measured by hand first (2026-10-15): the flag drops `e2e-loop`,
`handoff`, `resume` and plugin skills, and keeps project CLAUDE.md and project skills.

  py -3.11 scripts/drive/d1015_f454_user_skills.py <project-id> [agent]

The operator's machine must have a personal skill named `e2e-loop` (this one does). One Haiku turn.
"""

import importlib.util
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

USER_SKILLS = ("e2e-loop", "handoff", "resume")
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(project, agent="alpha"):
    home_skill = pathlib.Path.home() / ".claude" / "skills" / "e2e-loop" / "SKILL.md"
    check("the operator has a personal e2e-loop skill to leak", home_skill.exists(), str(home_skill))
    run_id = e2e.cmd_turn(
        project,
        agent,
        "List the names of every skill available to you through the Skill tool, comma-separated, "
        "and nothing else. If there are none, write NONE.",
        fresh=True,
    )
    check("the turn started", run_id is not None)
    if run_id is None:
        return
    e2e.wait_for(run_id, 5)
    reply = " ".join(
        row["content"] or ""
        for row in e2e.ro().execute(
            "select content from agent_outputs where run_id=? and kind='text'", (run_id,)
        )
    )
    check("the agent replied", bool(reply.strip()), reply[:300])
    for skill in USER_SKILLS:
        check(f"the operator's {skill} skill is not offered to the agent", skill not in reply)
    command = e2e.ro().execute(
        "select payload from agent_outputs where run_id=? and kind='status' order by timestamp limit 1",
        (run_id,),
    ).fetchone()
    print("first status row:", (command["payload"] if command else "")[:200])


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
