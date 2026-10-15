"""Drive F668: two agents started together on one task never share its checkout at once.

Before: design D8's refusal read "who is running on this task" and the first turn's `Run` row was
committed several awaits later, under a lock that is per agent; two agents triggered together on
one task both read "nobody" and both started in its checkout. After: the read and that commit hold
one lock per task, so the second waits (queued, not failed) and starts when the first ends.

  py -3.11 scripts/drive/d1015_f668_two_agents_one_task.py <project-id> [agent-a] [agent-b]

Two Haiku turns. Exit 1 when any check fails.
"""

import importlib.util
import pathlib
import sys
import threading
import time

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def running_on(task_id):
    return [
        (row["id"], row["agent"])
        for row in e2e.ro().execute(
            "select id, agent from runs where task_id=? and status='running'", (task_id,)
        )
    ]


def main(project, agent_a="alpha", agent_b="beta"):
    task_id = e2e.call("POST", f"/projects/{project}/tasks", {"title": "Write SHARED.txt"})["id"]
    answers = {}
    barrier = threading.Barrier(2)

    def start(agent):
        barrier.wait()
        answers[agent] = e2e.request(
            "POST",
            f"/projects/{project}/agent/trigger",
            {
                "agent": agent,
                "task_id": task_id,
                "message": f"Append the line '{agent}' to SHARED.txt in your workspace, "
                "then reply DONE.",
            },
        )

    threads = [threading.Thread(target=start, args=(a,)) for a in (agent_a, agent_b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for agent, (code, body) in answers.items():
        print(f"  {agent}: HTTP {code} status={body.get('status')} "
              f"reason={(body.get('waiting_reason') or '')[:120]}")
    check("both requests were accepted", all(code == 200 for code, _ in answers.values()),
          str({a: c for a, (c, _) in answers.items()}))

    started = [a for a, (_, body) in answers.items() if body.get("status") == "running"]
    waiting = [a for a, (_, body) in answers.items() if body.get("status") == "queued"]
    check("exactly one turn started", len(started) == 1, f"started={started}")
    check("the other waits, naming the holder",
          len(waiting) == 1 and started and started[0] in (answers[waiting[0]][1].get("waiting_reason") or ""),
          f"waiting={waiting}")

    # Sample while the first turn runs: never two running turns on the task.
    most = 0
    deadline = time.time() + 600
    seen = set()
    while time.time() < deadline:
        now = running_on(task_id)
        most = max(most, len(now))
        seen.update(agent for _, agent in now)
        if len(seen) == 2 and not now:
            break
        time.sleep(1)
    check("never two running turns on the task at once", most <= 1, f"max={most}")
    check("the waiting agent started after the first ended", seen == {agent_a, agent_b},
          f"seen={sorted(seen)}")


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
