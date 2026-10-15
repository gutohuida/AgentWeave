"""Acceptance drive for F602: a secret pattern in an agent's reply text is redacted before storage.

Before: tool rows carried `<redacted>` while the turn's `text` row stored a fake `aw_live_` key
verbatim, and `POST /agents/{name}/output` stored `sk-...` and an `api_key` value as written.
The fake values below are not credentials.

  py -3.11 scripts/drive/d1015_f602_text_redaction.py <project-id> [agent]

On a scratch Hub that `e2e.py hub-up` started, with a Haiku agent. One Haiku turn.
"""

import importlib.util
import json
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

LIVE = "aw_live_" + "Fake0123456789abcdefghijABCDEFGH"
RUN = "aw_run_" + "fakeRunToken0123456789"
SK = "sk-" + "fakeOpenAI0123456789abcd"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def rows(run_id):
    return e2e.ro().execute(
        "select kind, content, payload from agent_outputs where run_id=? order by timestamp, sequence",
        (run_id,),
    ).fetchall()


def main(project, agent="alpha"):
    # A model declines to echo credential-shaped text on request, so the values reach the reply
    # the way they do in real work: quoted from a file in the project. Committed before the
    # agent's first turn: an existing agent's worktree is not brought up to master (F607).
    directory = pathlib.Path(
        e2e.ro().execute("select working_directory from projects where id=?", (project,))
        .fetchone()[0]
    )
    (directory / "BUILD-NOTES.txt").write_text(
        f"release tag: {LIVE}\nbuild ref: {RUN}\nmirror ref: {SK}\n", encoding="utf-8"
    )
    for args in (
        ["add", "BUILD-NOTES.txt"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "notes"],
    ):
        e2e.subprocess.run(["git", "-C", str(directory), *args])
    run_id = e2e.cmd_turn(
        project,
        agent,
        "Open BUILD-NOTES.txt and quote its three lines back to me exactly, in a code block.",
        fresh=True,
    )
    check("the turn started", run_id is not None)
    if run_id is None:
        return
    e2e.wait_for(run_id, 5)
    text = [r for r in rows(run_id) if r["kind"] in ("text", "thinking")]
    stored = "\n".join((r["content"] or "") + (r["payload"] or "") for r in text)
    check("the reply was recorded", bool(text))
    for label, value in (("aw_live_", LIVE), ("aw_run_", RUN), ("sk-", SK)):
        check(f"no {label} value in the stored text rows", value not in stored,
              "verbatim" if value in stored else "")
    check("the redaction marker is there", "<redacted>" in stored)

    status, res = e2e.request(
        "POST", f"/projects/{project}/agents/{agent}/output",
        {"kind": "text", "content": f"key {SK} and {json.dumps({'api_key': 'hunter2-fake'})}"},
    )
    check("the operator output route accepts it", status in (200, 201), f"{status} {str(res)[:120]}")
    latest = e2e.ro().execute(
        "select content from agent_outputs where agent=? order by timestamp desc limit 1", (agent,)
    ).fetchone()["content"]
    check("the operator route stores no sk- value", SK not in latest, latest[:120])
    check("nor the api_key value", "hunter2-fake" not in latest, latest[:120])


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
