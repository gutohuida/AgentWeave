"""Row 15 CHECKPOINTS -- the cutover leg, driven end to end.

F89 came out of row 15's *generation* half (an automatic checkpoint held the database lock and
killed the turn, fixed 7cecd71). The cutover half -- render, cut over, continue -- has never been
driven live. This drives it: a real Haiku turn leaves a named next action, the operator generates
a checkpoint, reads it as the successor will receive it, cuts over, and continues. The relay
assertion is the one that matters: a file the PREDECESSOR was told not to write, written by the
SUCCESSOR, is proof the checkpoint carried the work across.

Real surface only. No row inserts. Haiku turns.
"""

import os
import sys
import time

from aw import api, show

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = "gamma"
HAIKU = "runner-8d5eb04a4f25"

VERDICTS = []


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def step(label):
    print("\n" + "=" * 74)
    print(label)
    print("=" * 74)


def agent_status(name):
    c, b = api("GET", f"/projects/{P}/agents")
    if c != 200:
        return "?"
    for a in b:
        if a["name"] == name:
            return a["status"]
    return "?"


def wait_idle(name, limit=360):
    t0 = time.time()
    while time.time() - t0 < limit:
        s = agent_status(name)
        if s in ("idle", "error", "offline"):
            print(f"  settled after {int(time.time()-t0)}s: {name}={s}")
            return s
        time.sleep(5)
    print(f"  TIMEOUT after {limit}s: {name}={agent_status(name)}")
    return None


def worktree_dir():
    c, b = api("GET", f"/projects/{P}/worktrees/{AGENT}")
    if c != 200 or not isinstance(b, dict):
        return None
    return b.get("working_dir")


def read_in_worktree(filename):
    d = worktree_dir()
    if not d:
        return None
    p = os.path.join(d, filename)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read().strip()


def conversations(lifecycle="all"):
    c, b = api("GET", f"/projects/{P}/conversations?lifecycle={lifecycle}")
    if c != 200:
        return []
    return b.get("conversations", []) if isinstance(b, dict) else b


def summarise():
    step("VERDICTS")
    bad = [v for v in VERDICTS if not v[1]]
    for label, ok, detail in VERDICTS:
        print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} held")


def main():
    step("0. Baseline -- no checkpoint runner is configured")
    c, settings0 = api("GET", f"/projects/{P}/settings")
    show("settings", c, settings0)
    check(
        "project starts with no checkpoint runner",
        settings0.get("checkpoint_runner_id") is None,
        repr(settings0.get("checkpoint_runner_id")),
    )
    before_ids = {x["id"] for x in conversations("all")}

    step("1. A real Haiku turn that leaves a named next action it is told NOT to do")
    msg = (
        "Create a file called CHECKPOINT_A.txt in your working directory whose entire contents "
        "are the single word ANCHORONE. Then STOP. "
        "Do not create any other file. In particular do NOT create CHECKPOINT_B.txt now. "
        "End your reply with exactly this line so the next step is on the record: "
        "NEXT ACTION: create CHECKPOINT_B.txt containing the single word RELAYTWO."
    )
    c, b = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": AGENT, "message": msg, "overrides": {"permission_mode": "workspace"}},
        timeout=30,
    )
    show("trigger", c, b)
    if c >= 300:
        sys.exit(f"trigger refused {c}")
    wait_idle(AGENT)

    a_text = read_in_worktree("CHECKPOINT_A.txt")
    check("predecessor wrote CHECKPOINT_A.txt", a_text is not None, repr(a_text))
    check("...with the anchor content", "ANCHORONE" in (a_text or "").upper(), repr(a_text))
    check(
        "predecessor did NOT write CHECKPOINT_B.txt",
        read_in_worktree("CHECKPOINT_B.txt") is None,
    )

    after = conversations("all")
    fresh = [x for x in after if x["id"] not in before_ids and x["agent"] == AGENT]
    if not fresh:
        sys.exit("no new conversation for the turn")
    pred = fresh[0]
    pred_id = pred["id"]
    print(f"  predecessor conversation {pred_id} title={pred.get('title')!r}")

    step("2. Checkpoint refused while no runner is configured")
    c, b = api("POST", f"/projects/{P}/conversations/{pred_id}/checkpoint", {}, timeout=240)
    show("checkpoint (no runner)", c, b)
    check("exactly 409, not 500 and not a silent fallback", c == 409, str(c))
    check(
        "the refusal names what to do about it",
        isinstance(b, dict) and "checkpoint runner" in str(b.get("detail", "")).lower(),
        str(b)[:160],
    )

    step("3. Configure the checkpoint runner, then generate")
    c, b = api("PUT", f"/projects/{P}/settings", {"checkpoint_runner_id": HAIKU})
    show("settings PUT", c, b)
    check("settings accepted the runner", c == 200 and b.get("checkpoint_runner_id") == HAIKU)
    check(
        "the partial PUT did not reset the rest",
        c == 200
        and b.get("hop_budget") == settings0.get("hop_budget")
        and b.get("checkpoint_mode") == settings0.get("checkpoint_mode"),
        f"hop_budget={b.get('hop_budget')} mode={b.get('checkpoint_mode')}",
    )

    t0 = time.time()
    c, cp = api("POST", f"/projects/{P}/conversations/{pred_id}/checkpoint", {}, timeout=300)
    show("checkpoint", c, cp)
    print(f"  generation took {int(time.time() - t0)}s")
    if c != 201:
        check("checkpoint generated (201)", False, str(c))
        summarise()
        return
    check("checkpoint generated (exactly 201)", c == 201)
    cp_id = cp["id"]
    body = (cp.get("body") or "").upper()
    check("status is 'ready'", cp.get("status") == "ready", repr(cp.get("status")))
    check("no generation error", not cp.get("generation_error"), repr(cp.get("generation_error")))
    check("it has a body", bool(body.strip()), f"{len(body)} chars")
    check(
        "the body carries the next action across",
        "RELAYTWO" in body,
        "RELAYTWO present" if "RELAYTWO" in body else "ABSENT",
    )
    check(
        "files_changed names the file the turn wrote",
        any("CHECKPOINT_A" in str(f).upper() for f in (cp.get("files_changed") or [])),
        str(cp.get("files_changed"))[:200],
    )

    step("4. Rendered -- exactly what the successor receives")
    c, r = api("GET", f"/projects/{P}/checkpoints/{cp_id}/rendered")
    rendered = r.get("rendered", "") if isinstance(r, dict) else ""
    print(rendered[:1600])
    check("rendered returns 200", c == 200, str(c))
    check("rendered is non-empty", bool(rendered.strip()), f"{len(rendered)} chars")
    check("rendered names the agent", AGENT in rendered, "")
    check("rendered carries the next action", "RELAYTWO" in rendered.upper())

    step("5. Cut over")
    c, co = api("POST", f"/projects/{P}/checkpoints/{cp_id}/cutover", {})
    show("cutover", c, co)
    check("cutover returns exactly 200", c == 200, str(c))
    if c != 200:
        summarise()
        return
    succ_id = co.get("successor_conversation_id")
    entry_id = co.get("queue_entry_id")
    check("it names a successor", bool(succ_id), str(succ_id))
    check("it names the queue entry that carries the checkpoint", bool(entry_id), str(entry_id))
    check("the successor is a different conversation", succ_id != pred_id)

    allc = {x["id"]: x for x in conversations("all")}
    check(
        "predecessor is archived",
        allc.get(pred_id, {}).get("lifecycle") == "archived",
        repr(allc.get(pred_id, {}).get("lifecycle")),
    )
    succ = allc.get(succ_id, {})
    check("successor is open", succ.get("lifecycle") == "open", repr(succ.get("lifecycle")))
    check("successor origin is 'handoff'", succ.get("origin") == "handoff", repr(succ.get("origin")))
    check(
        "successor title derives from the predecessor's",
        str(succ.get("title") or "").startswith("Continued: "),
        repr(succ.get("title")),
    )

    c, q = api("GET", f"/projects/{P}/queue/{AGENT}")
    show("queue", c, q)
    entries = q if isinstance(q, list) else []
    mine = [e for e in entries if e.get("id") == entry_id]
    check("the entry is really on the agent's queue", bool(mine), f"{len(entries)} entries")
    if mine:
        e = mine[0]
        check(
            "entry origin_type is 'checkpoint'",
            e.get("origin_type") == "checkpoint",
            repr(e.get("origin_type")),
        )
        check(
            "entry is addressed to the successor",
            e.get("conversation_id") == succ_id,
            repr(e.get("conversation_id")),
        )
        check(
            "entry content is the framed checkpoint, not a bare summary",
            "This conversation continues earlier work" in str(e.get("content", "")),
            str(e.get("content", ""))[:80],
        )

    step("6. Press cutover a second time on the same checkpoint")
    c2, co2 = api("POST", f"/projects/{P}/checkpoints/{cp_id}/cutover", {})
    show("cutover again", c2, co2)
    second = co2.get("successor_conversation_id") if isinstance(co2, dict) else None
    check(
        "a second cutover on a spent checkpoint is refused",
        c2 == 409,
        f"got {c2}; second successor={second}",
    )

    step("7. Continue the successor -- does the relay actually happen?")
    c, cont = api("POST", f"/projects/{P}/conversations/{succ_id}/continue", {}, timeout=60)
    show("continue", c, cont)
    check("continue returns 200", c == 200, str(c))
    check("it reports the turn started", cont.get("started") is True, str(cont))
    wait_idle(AGENT, limit=420)

    b_text = read_in_worktree("CHECKPOINT_B.txt")
    check(
        "the SUCCESSOR did the next action the checkpoint carried",
        b_text is not None,
        repr(b_text),
    )
    check("...with the relay content", "RELAYTWO" in (b_text or "").upper(), repr(b_text))

    c, q2 = api("GET", f"/projects/{P}/queue/{AGENT}")
    left = [e for e in (q2 if isinstance(q2, list) else []) if e.get("state") == "queued"]
    check("the checkpoint entry was consumed, not left queued", not left, str(left)[:200])

    summarise()


if __name__ == "__main__":
    try:
        main()
    finally:
        # Leave the project's checkpoint runner as it was found.
        api("PUT", f"/projects/{P}/settings", {"checkpoint_runner_id": None})
        print("\n[teardown] checkpoint_runner_id reset to null")
