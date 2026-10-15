"""Acceptance drive for F607: an agent's own worktree is brought up to main before its turn.

Before: an agent's worktree was cut at its first turn and never moved, so a later turn read stale
code -- a reconcile recorded three false "missing" gaps against shipped code, and a turn could not
find a file committed to master after the worktree existed. After: an untasked turn's checkout
takes in what main has that it lacks, without touching uncommitted work.

  py -3.11 scripts/drive/d1015_f607_worktree_catch_up.py <project-id> [agent]

Two Haiku turns. Exit 1 when any check fails.
"""

import importlib.util
import pathlib
import subprocess
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

MARKER = "the release codename is TANGERINE-41"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def git(directory, *args):
    return subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True)


def reply(run_id):
    return " ".join(
        r["content"] or ""
        for r in e2e.ro().execute(
            "select content from agent_outputs where run_id=? and kind='text'", (run_id,)
        )
    )


def main(project, agent="alpha"):
    directory = pathlib.Path(
        e2e.ro().execute("select working_directory from projects where id=?", (project,)).fetchone()[0]
    )
    first = e2e.cmd_turn(project, agent, "Reply with the single word READY.", fresh=True)
    check("the first turn started (it cuts the worktree)", first is not None)
    if first is None:
        return
    e2e.wait_for(first, 5)
    worktree = directory / ".agentweave" / "worktrees" / agent
    check("the agent has its own worktree", worktree.is_dir(), str(worktree))

    (directory / "RELEASE.txt").write_text(MARKER + "\n", encoding="utf-8")
    git(directory, "add", "RELEASE.txt")
    git(directory, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "release notes")
    master = git(directory, "rev-parse", "HEAD").stdout.strip()

    second = e2e.cmd_turn(
        project, agent,
        "Read RELEASE.txt in your workspace and reply with its one line exactly.", fresh=True,
    )
    check("the second turn started", second is not None)
    if second is None:
        return
    e2e.wait_for(second, 5)
    contains = git(worktree, "merge-base", "--is-ancestor", master, "HEAD").returncode == 0
    check("the worktree now contains master's commit", contains)
    text = reply(second)
    check("the agent read the file committed after its worktree was cut", "TANGERINE-41" in text, text[:200])


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
