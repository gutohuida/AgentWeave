"""Acceptance drive for `an-exploring-turn-asks-its-questions-in-its-reply` (F545), 2026-10-10.

The change's `drive` criterion (spdoc-a56fa9bf6cdd on :8010, task drive-first). Starts its own Hub on
:8106 with a fresh database (never :8000 or :8010). One Haiku agent, alice, bound to a Claude runner.
The operator starts an exploration (POST /project/documents with no path: a change-spec at step
intake) and sends alice, on that document, a deliberately underspecified request. Then, in order:

  1. the composed context the run was given (`.agentweave/context/alice.md` in the run's workspace,
     read as soon as the trigger has written it) carries the prose-interview rule and its precedence
     line, no "reach nobody" or "not a way to finish" sentence, and its step duty (from
     `[step: intake]` to the open-agents line) names no ask_user;
  2. the run completed;
  3. the project has no question row created by that run;
  4. the run's reply (its `text` outputs) contains at least one question.

Contract it fixes for the build: the exploring context says "ask your questions in your reply" (the
bare "in your reply" is already in ask_user's tool text, so it tells nothing apart) and that this
"overrides any charter or tool description" naming ask_user (requirement exploring-asks-in-prose).
Checks 2-4 are model-dependent (the spec's evidence limit); check 1 is deterministic.

Fails on today's Hub at check 1 (the context carries "reach nobody"). Stops at the first failure.
One Haiku turn.

    py -3.11 scripts/drive/d1020_exploring_prose.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402

d.PORT = 8106
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1020-exploring-prose" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

REQUEST = "make the board easier to scan"
PROSE_RULE = "ask your questions in your reply"
PRECEDENCE = "overrides any charter or tool description"
FORBIDDEN = ("reach nobody", "not a way to finish")


def step_duty(context):
    """The intake duty: from its marker to the open-agents line that follows it."""
    start = context.find("[step: intake]")
    if start < 0:
        return ""
    end = context.find("- Open agents on this project", start)
    return context[start : end if end > 0 else len(context)]


def wait_ended(run_id, secs=600):
    end = time.time() + secs
    while time.time() < end:
        rows = d.ro("select status from runs where id=?", (run_id,))
        if rows and rows[0][0] not in ("running", "queued", "starting"):
            return rows[0][0]
        time.sleep(3)
    return None


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text(
        "# board\n\nA task board: one column per status, a card per task.\n", encoding="utf-8"
    )
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "prose"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    _, runner = d.api(
        "POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU}
    )
    code, out = d.api("POST", f"{base}/agents", {"name": "alice", "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)

    # The operator starts an exploration: the Hub mints the path, the document starts at intake.
    code, doc = d.api("POST", f"{base}/project/documents", {"kind": "change-spec"})
    assert code == 201, (code, doc)
    path = doc["path"]
    step = d.ro("select phase, step from spec_documents where path=?", (path,))
    print(f"  document {path} {step}", flush=True)

    started = time.time()
    code, run = d.api(
        "POST",
        f"{base}/agent/trigger",
        {"agent": "alice", "message": REQUEST, "spec_document": path},
    )
    assert code in (200, 202), (code, run)
    run_id = run["run_id"]

    # 1: the context the run was given, read as soon as the trigger has written it (a later
    # rewrite for a decided surface would replace it, line 200 of agent_trigger.py).
    def context_file():
        rows = d.ro("select workspace_dir from runs where id=?", (run_id,))
        work = pathlib.Path(rows[0][0]) if rows and rows[0][0] else root
        return work / ".agentweave" / "context" / "alice.md"

    d.poll(lambda: context_file().exists() and context_file().stat().st_mtime >= started - 1, 60)
    context = context_file().read_text(encoding="utf-8") if context_file().exists() else ""
    (d.TMP / "context.md").write_text(context, encoding="utf-8")
    lowered = context.lower()
    duty = step_duty(context)
    found = [s for s in FORBIDDEN if s in lowered]
    d.check(
        "1 the run's context asks in the reply with the precedence line, says nothing reaches "
        "nobody, and its intake duty names no ask_user",
        context
        and PROSE_RULE in lowered
        and PRECEDENCE in lowered
        and not found
        and duty
        and "ask_user" not in duty,
        f"len={len(context)} prose={PROSE_RULE in lowered} precedence={PRECEDENCE in lowered} "
        f"forbidden={found} duty_len={len(duty)} duty_ask_user={'ask_user' in duty} "
        f"(saved {d.TMP / 'context.md'})",
    )

    # 2: the run ends on its own.
    state = wait_ended(run_id)
    d.check("2 the run completed", state == "completed", f"run={run_id} status={state}")

    # 3: it asked through no question row.
    asked = d.ro(
        "select id, question from questions where project_id=? and created_by_run_id=?",
        (pid, run_id),
    )
    d.check("3 the run created no question row", not asked, f"questions={asked}")

    # 4: its questions are in its reply.
    texts = d.ro(
        "select content from agent_outputs where run_id=? and kind='text' order by sequence",
        (run_id,),
    )
    reply = "\n".join(t[0] for t in texts)
    (d.TMP / "reply.md").write_text(reply, encoding="utf-8")
    d.check(
        "4 the run's reply asks at least one question",
        "?" in reply,
        f"reply={reply[-400:]!r}",
    )


d.drive = drive

if __name__ == "__main__":
    d.main()
