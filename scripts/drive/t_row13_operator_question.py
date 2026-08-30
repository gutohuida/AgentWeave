"""The question an *operator* posts, and what happens to the answer.

`POST /projects/{p}/questions` is the operator-facing half of row 13. Every sweep so far has
reached row 13 through `ask_user`, which is the agent-facing half and goes to a different route
(`agent_actions.py:545`, `/questions/batch`). The two differ in exactly one argument:

    agent route     created_by_run_id = actor.run_id
    operator route  created_by_run_id = None            (`questions.py:225`)

and that argument is what decides whether the operator's answer is ever delivered. On answer
(`questions.py:346`):

    asker_still_waiting = question.blocking and not await _asking_run_has_ended(session, question)
    ...
    if not asker_still_waiting:
        delivered = await _deliver_batch_if_complete(...)     # queue it, wake the agent

and `_asking_run_has_ended` (`questions.py:42-43`) returns **False** whenever
`created_by_run_id` is unset -- deliberately, so a question whose asker is genuinely unknown is
presumed to still be waiting. For an operator-route question that presumption is knowably false:
nothing was ever waiting, because no run created it.

So the prediction under test, stated before the drive:

    blocking=True  posted by the operator -> answering delivers NOTHING and wakes nobody
    blocking=False posted by the operator -> answering queues an entry and wakes the agent

Both are driven, on one bound idle agent, in that order. The second is the control: if it also
queues nothing then the delivery path is broken for a different reason and the first proves
nothing.

Costs at most one Haiku turn (the control's). Real surface only, no row inserts except to READ
`inbound_queue_entries`, which no route exposes.
"""

import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or ""
AGENT = os.environ.get("AW_AGENT") or ""
DB = os.environ.get("AW_DB") or ""
RUN = time.strftime("%H%M%S")

VERDICTS = []


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def step(label):
    print("\n" + "=" * 76)
    print(label)
    print("=" * 76)


def agent_row():
    c, rows = api("GET", f"/projects/{P}/agents")
    if c != 200 or not isinstance(rows, list):
        return None
    return next((a for a in rows if a["name"] == AGENT), None)


def entry_ids():
    """Every inbound queue entry for this agent, by id. No route lists them, so read the table."""
    conn = sqlite3.connect(DB.split("///", 1)[1])
    try:
        cur = conn.execute(
            "SELECT id, state, origin_type, substr(content, 1, 60) AS head "
            "FROM inbound_queue_entries WHERE project_id = ? AND agent = ?",
            (P, AGENT),
        )
        cols = [c[0] for c in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}
    finally:
        conn.close()


def open_questions():
    c, rows = api("GET", f"/projects/{P}/questions?answered=false")
    return [q for q in (rows or []) if not q.get("declined")] if isinstance(rows, list) else []


def settle(question_id, answer):
    return api("PATCH", f"/projects/{P}/questions/{question_id}", {"answer": answer,
                                                                   "labels": [answer]})


def drive(blocking, expect_delivery):
    kind = "blocking" if blocking else "non-blocking"
    step(f"{kind.upper()} — the operator posts a question, then answers it")
    before = entry_ids()
    text = f"[{RUN}] Operator-posted {kind}: which colour?"
    c, q = api(
        "POST",
        f"/projects/{P}/questions",
        {
            "from_agent": AGENT,
            "question": text,
            # `header` is REQUIRED on this route -- the 422 names it, which is the good half of a
            # refusal, and it is why the first attempt at this file created nothing.
            "header": f"Colour ({kind})",
            "multi_select": False,
            "blocking": blocking,
            "options": [
                {"label": "red", "description": "Red"},
                {"label": "blue", "description": "Blue"},
            ],
        },
    )
    if not check(f"the {kind} question is created", c == 201, f"{c} {str(q)[:200]}"):
        return None
    qid = q["id"]
    print(f"  {qid}  asker_waiting={q.get('asker_waiting')!r}  blocking={q.get('blocking')!r}")
    # `asker_waiting` is True on BOTH -- measured. That is correct for the non-blocking one, where
    # the field is inert: `QuestionsPanel.tsx:151` partitions on `!blocking || !stillWaiting`, so a
    # non-blocking row never enters the "agents are waiting" banner whatever this says. Asserting
    # False here was this file's own wrong turn on its first green run. What matters is the
    # blocking row, where the field IS load-bearing and is wrong (F146).
    if blocking:
        check(
            "…and the panel is told somebody is waiting on a question no run ever asked",
            q.get("asker_waiting") is True,
            f"asker_waiting={q.get('asker_waiting')!r} -- this is what puts the row in the red "
            "banner, and nothing is on the other end",
        )
    else:
        print(f"  (asker_waiting={q.get('asker_waiting')!r}; inert on a non-blocking row)")

    c, answered = settle(qid, "blue")
    check(f"answering the {kind} question is accepted", c == 200, str(c))

    # The delivery is committed inside the same request, so one read after it returns is enough.
    after = entry_ids()
    fresh = [v for k, v in after.items() if k not in before]
    for row in fresh:
        print(f"  new queue entry: {row}")
    got = any(RUN in (row.get("head") or "") or "Answer" in (row.get("head") or "")
              for row in fresh)
    check(
        f"the answer to a {kind} question {'reaches' if expect_delivery else 'does NOT reach'} "
        "the agent as queued input",
        got is expect_delivery,
        f"{len(fresh)} new entr(y|ies) queued" if fresh else "nothing queued",
    )
    return qid


def main():
    step("PRE. Preconditions")
    if not P or not AGENT or not DB:
        sys.exit("set AW_PROJECT, AW_AGENT and AW_DB")
    row = agent_row()
    if row is None or row.get("archived") or not row.get("runner_id"):
        sys.exit(f"agent {AGENT!r} must exist, be open, and be bound to a runner")
    if row.get("status") != "idle":
        sys.exit(f"agent {AGENT!r} is {row.get('status')!r}, not idle")
    stale = open_questions()
    if stale:
        sys.exit(f"{len(stale)} question(s) already open ({[q['id'] for q in stale]}); "
                 "this file cannot tell them from its own")
    print(f"  [OK ] {AGENT} idle and bound; no open question")

    created = []
    try:
        # The control runs FIRST, so a broken delivery path is caught before the finding is read
        # into a passing one.
        created.append(drive(blocking=False, expect_delivery=True))
        # The non-blocking answer wakes the agent; wait it out so the blocking half starts from
        # the same idle state the preconditions asserted.
        end = time.time() + 180
        while time.time() < end:
            r = agent_row()
            if r and r.get("status") == "idle":
                break
            time.sleep(4)
        print(f"  agent back to {agent_row().get('status')!r} before the second half")
        created.append(drive(blocking=True, expect_delivery=False))
    finally:
        step("Z. Leave nothing open")
        for qid in [x for x in created if x]:
            c, _ = api("GET", f"/projects/{P}/questions/{qid}")
            print(f"  {qid}: GET -> {c}")
        for q in open_questions():
            c, _ = api("POST", f"/projects/{P}/questions/{q['id']}/decline", {})
            print(f"  declined leftover {q['id']}: {c}")

        step("VERDICTS")
        bad = [v for v in VERDICTS if not v[1]]
        for label, ok, detail in VERDICTS:
            print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
        print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} held")


if __name__ == "__main__":
    main()
