"""Row 13's other half: let a question EXPIRE rather than answering it.

Every previous sweep drove the answered path -- `ask_user` blocks, the operator answers, the run
resumes. The unanswered path was recorded "not reached" three sweeps running, and it is the one
that decides whether an unattended project is safe: an operator who is asleep is the normal case,
not the exceptional one.

`mcp_server.py:854` bounds the wait at `AW_QUESTION_TIMEOUT` (default 240s, clamped to 10..600),
which the Hub fills from the agent's own `question_timeout_seconds`. On expiry the tool returns
rather than hanging, with a note (`mcp_server.py:448-455`):

    "N of M question(s) went unanswered within Xs. Continue as best you can and say plainly which
     decisions you made without an answer."

So the contract to drive is four claims, and each is asserted separately because they fail
separately:

  1. the question reaches the operator, blocking, with someone waiting on it;
  2. the wait ENDS on its own -- the run finishes without an answer, near the deadline rather than
     at the provider's own timeout minutes later;
  3. afterwards the question is legible: not answered, not declined, and nobody waiting;
  4. the agent says which decision it made without an answer, because that is what it was told to
     do and it is the only record the operator gets.

The agent's timeout is set for the run and RESTORED on the way out, including on failure.

Real surface only. No row inserts. One Haiku turn.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or ""
AGENT = os.environ.get("AW_AGENT") or ""
# The floor the Hub itself enforces is 10s (`mcp_server.py:821`); anything outside 10..600 is
# ignored and the 240s default is used instead, which would make this file wait four minutes and
# then report on the default rather than on the setting.
TIMEOUT = int(os.environ.get("AW_TIMEOUT") or "60")
RUN = os.environ.get("AW_RUN") or time.strftime("%H%M%S")

VERDICTS = []


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def step(label):
    print("\n" + "=" * 76)
    print(label)
    print("=" * 76)


def blob(x, limit=1200):
    return json.dumps(x, indent=1, default=str)[:limit]


def agent_row():
    c, rows = api("GET", f"/projects/{P}/agents")
    if c != 200:
        return None
    return next((a for a in rows if a["name"] == AGENT), None)


def questions(answered=None):
    path = f"/projects/{P}/questions"
    if answered is not None:
        path += f"?answered={'true' if answered else 'false'}"
    c, rows = api("GET", path)
    return rows if isinstance(rows, list) else []


def outputs(limit=40):
    c, rows = api("GET", f"/projects/{P}/agents/{AGENT}/output?limit={limit}")
    return rows if isinstance(rows, list) else []


def preflight():
    step("PRE. Preconditions")
    if not P or not AGENT:
        sys.exit("set AW_PROJECT and AW_AGENT")
    row = agent_row()
    if row is None:
        sys.exit(f"agent {AGENT!r} does not exist on {P}")
    if row.get("archived") or not row.get("runner_id"):
        sys.exit(f"agent {AGENT!r} must be open and bound to a runner")
    if row.get("status") != "idle":
        sys.exit(f"agent {AGENT!r} is {row.get('status')!r}, not idle")
    if not (10 <= TIMEOUT <= 600):
        sys.exit(f"AW_TIMEOUT={TIMEOUT} is outside the Hub's own 10..600 band and would be ignored")
    open_now = [q for q in questions(answered=False) if not q.get("declined")]
    if open_now:
        sys.exit(
            f"{len(open_now)} question(s) are already open on this project "
            f"({[q['id'] for q in open_now]}); this file cannot tell them from its own"
        )
    print(f"  [OK ] {AGENT} idle and bound; no open question; timeout to set {TIMEOUT}s")
    return row.get("question_timeout_seconds")


def main():
    original = preflight()
    print(f"  original question_timeout_seconds = {original!r}")

    try:
        step(f"1. Set this agent's question timeout to {TIMEOUT}s")
        c, b = api(
            "PATCH", f"/projects/{P}/agents/{AGENT}", {"question_timeout_seconds": TIMEOUT}
        )
        check("the setting is accepted", c == 200, f"{c} {str(b)[:200]}")
        row = agent_row()
        check(
            "...and reads back on the roster",
            row and row.get("question_timeout_seconds") == TIMEOUT,
            repr(row and row.get("question_timeout_seconds")),
        )

        step("2. A turn that must ask, and must not guess")
        msg = (
            "Before doing anything else, call mcp__agentweave__ask_user with exactly one "
            "question: 'Should the report be named "
            f"summary_{RUN}.md or report_{RUN}.md?', with those two as the options. "
            "This is a real fork and you must not pick one without asking. "
            "Whatever comes back, write a file called "
            f"decision_{RUN}.txt in your working directory whose first line is the name you "
            "chose and whose second line says whether the operator answered you. Then stop."
        )
        t0 = time.time()
        c, b = api(
            "POST",
            f"/projects/{P}/agent/trigger",
            {"agent": AGENT, "message": msg, "overrides": {"permission_mode": "workspace"}},
            timeout=30,
        )
        print("  " + blob(b, 500))
        if c >= 300:
            check("the turn started", False, str(c))
            return
        check("the turn started", c == 200, str(c))

        step("3. The question reaches the operator")
        q = None
        while time.time() - t0 < 180:
            fresh = [x for x in questions(answered=False) if not x.get("declined")]
            if fresh:
                q = fresh[0]
                break
            time.sleep(3)
        check("a question appeared", q is not None, f"after {int(time.time() - t0)}s")
        if q is None:
            return
        asked_at = time.time()
        print("  " + blob(q, 900))
        check("it is attributed to the asking agent", q.get("from_agent") == AGENT,
              repr(q.get("from_agent")))
        check("it is blocking", q.get("blocking") is True, repr(q.get("blocking")))
        check("it carries options rather than free text alone", bool(q.get("options")),
              str(q.get("options"))[:200])
        check("and somebody is recorded as waiting on it", q.get("asker_waiting") is True,
              repr(q.get("asker_waiting")))

        step(f"4. Answer NOTHING. The wait must end on its own within about {TIMEOUT}s.")
        deadline = asked_at + TIMEOUT + 120
        settled = None
        while time.time() < deadline:
            row = agent_row()
            if row and row.get("status") in ("idle", "error", "offline"):
                settled = row.get("status")
                break
            time.sleep(5)
        waited = int(time.time() - asked_at)
        check(
            "the run ended without an answer rather than hanging",
            settled is not None,
            f"agent={settled!r} after {waited}s",
        )
        check(
            "...and it ended near the agent's own deadline, not the provider's",
            settled is not None and waited <= TIMEOUT + 90,
            f"{waited}s vs a {TIMEOUT}s timeout",
        )
        check("...and it ended cleanly, not in error", settled == "idle", repr(settled))

        step("5. What the question looks like afterwards")
        c, after = api("GET", f"/projects/{P}/questions/{q['id']}")
        print("  " + blob(after, 900))
        check("the question is still readable", c == 200, str(c))
        check("it is NOT marked answered", after.get("answered") is False,
              repr(after.get("answered")))
        check(
            "it is NOT marked declined -- nobody chose not to answer, nobody was there",
            after.get("declined") is False,
            repr(after.get("declined")),
        )
        check(
            "and nobody is waiting on it any more, so the panel does not send the operator to it",
            after.get("asker_waiting") is False,
            repr(after.get("asker_waiting")),
        )

        step("6. Did the agent say what it decided without an answer?")
        text = "\n".join(str(o.get("content") or "") for o in outputs(60))
        tail = text[-2500:]
        print("  " + tail[-1200:].replace(chr(10), chr(10) + "  "))
        # The note itself is NOT assertable from here, and looking for it was this file's own
        # first wrong turn (F144). `/output` -- and `/agent/{name}/chat`, which is built from the
        # same rows -- record every tool result as the literal string "tool completed" (F139), so
        # `ask_user`'s `note` reaches the agent and no operator surface at all. Searching the
        # transcript for "unanswered" therefore reports a fact about the transcript's shape as a
        # product defect.
        #
        # What IS assertable is the one thing the agent could only have learned from the note: the
        # size of the window. The turn prompt never names it, the charter never names it, and the
        # only place AW_QUESTION_TIMEOUT's value is ever spoken in words is
        # `mcp_server.py:448-455`. So the agent repeating it back is proof of delivery.
        said_window = str(TIMEOUT) in text
        check(
            "the expiry reached the agent as a stated window, not as an empty answer",
            said_window,
            f"the agent repeated the {TIMEOUT}s window back"
            if said_window
            else f"the agent never names {TIMEOUT}s, so the note may not have been delivered",
        )
        check(
            "the agent named the choice it made without one",
            f"summary_{RUN}" in text or f"report_{RUN}" in text,
            "named" if (f"summary_{RUN}" in text or f"report_{RUN}" in text) else "never named",
        )
    finally:
        step("Z. Restore the agent's timeout")
        c, b = api(
            "PATCH", f"/projects/{P}/agents/{AGENT}", {"question_timeout_seconds": original}
        )
        row = agent_row()
        print(f"  restore: {c}; now {row and row.get('question_timeout_seconds')!r} "
              f"(was {original!r})")
        left = [x for x in questions(answered=False) if not x.get("declined")]
        for x in left:
            dc, _ = api("POST", f"/projects/{P}/questions/{x['id']}/decline", {})
            print(f"  declined leftover {x['id']}: {dc}")

        step("VERDICTS")
        bad = [v for v in VERDICTS if not v[1]]
        for label, ok, detail in VERDICTS:
            print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
        print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} held")


if __name__ == "__main__":
    main()
