"""Row 15 CHECKPOINTS -- the SECOND LINK of a chain, which row 15's cutover leg never reached.

`t_row15_cutover.py` drove one checkpoint end to end: generate, render, cut over, continue. Every
checkpoint it made was a conversation's FIRST, so `previous_checkpoint_id` was None on all of them
and `lineage_id` was always the checkpoint's own id. The lineage columns exist
(`hub/hub/checkpoints.py:412-414`) and the render prints "Previous checkpoint: ..."
(`checkpoint_generation.py:287`), but nothing had ever produced a row with the column set.

The anchor is per CONVERSATION (`latest_checkpoint`, checkpoints.py:95), not per lineage across a
cutover -- a cutover makes a NEW conversation, so its first checkpoint founds a new lineage. The
only way to reach link two is to checkpoint the SAME conversation twice.

Driven here:
  1. one real Haiku turn writing a named anchor file;
  2. checkpoint #1  -> link one:  previous is None, lineage is itself;
  3. checkpoint #2 with NO turn in between -> whatever the product does with an empty span, asserted
     as an exact status code rather than assumed;
  4. a second real turn, then checkpoint #3 -> link two/three: previous set, lineage carried,
     the render naming its predecessor, and the SPAN not re-covering the first turn.

Real surface only. No row inserts. Haiku turns. Exact status codes.
"""

import os
import sys
import time

from aw import api, show

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = os.environ.get("AW_AGENT") or "gamma"
HAIKU = os.environ.get("AW_RUNNER") or "runner-8d5eb04a4f25"

VERDICTS = []
STARTED = time.time()


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def step(label):
    print("\n" + "=" * 74)
    print(f"{label}   (+{int(time.time() - STARTED)}s)")
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
            print(f"  settled after {int(time.time() - t0)}s: {name}={s}")
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


def turn(message, label, conv_id=None):
    step(label)
    before = {x["id"] for x in conversations("all")}
    body = {"agent": AGENT, "message": message, "overrides": {"permission_mode": "workspace"}}
    if conv_id:
        # Without this the trigger opens a NEW conversation, and the checkpoint chain being driven
        # is per conversation -- the second turn would land somewhere the chain cannot see it.
        body["conversation_id"] = conv_id
    c, b = api("POST", f"/projects/{P}/agent/trigger", body, timeout=30)
    show("trigger", c, b)
    if c != 200:
        sys.exit(f"trigger refused {c}")
    wait_idle(AGENT)
    fresh = [x for x in conversations("all") if x["id"] not in before and x["agent"] == AGENT]
    return fresh[0]["id"] if fresh else None


def make_checkpoint(conv_id, label):
    step(label)
    t0 = time.time()
    c, cp = api("POST", f"/projects/{P}/conversations/{conv_id}/checkpoint", {}, timeout=420)
    show(label, c, cp)
    print(f"  took {int(time.time() - t0)}s")
    return c, cp


def rendered(cp_id):
    c, r = api("GET", f"/projects/{P}/checkpoints/{cp_id}/rendered")
    return c, (r.get("rendered", "") if isinstance(r, dict) else "")


def summarise():
    step("VERDICTS")
    bad = [v for v in VERDICTS if not v[1]]
    for label, ok, detail in VERDICTS:
        print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} held")


def main():
    step("0. Configure the checkpoint runner")
    c, settings0 = api("GET", f"/projects/{P}/settings")
    check("settings readable", c == 200, str(c))
    c, b = api("PUT", f"/projects/{P}/settings", {"checkpoint_runner_id": HAIKU})
    check("checkpoint runner set", c == 200 and b.get("checkpoint_runner_id") == HAIKU, str(c))

    conv = turn(
        "Create a file called CHAIN_ONE.txt in your working directory whose entire contents are "
        "the single word LINKONE. Then STOP. Do not create any other file. "
        "End your reply with exactly this line: NEXT ACTION: create CHAIN_TWO.txt.",
        "1. First real Haiku turn",
    )
    if not conv:
        sys.exit("no conversation for the first turn")
    print(f"  conversation {conv}")
    check("the first turn wrote its anchor file", read_in_worktree("CHAIN_ONE.txt") is not None)

    c, cp1 = make_checkpoint(conv, "2. Checkpoint #1 -- the conversation's first")
    if c != 201:
        check("checkpoint #1 generated (201)", False, str(c))
        summarise()
        return
    check("checkpoint #1 generated (exactly 201)", c == 201)
    check("#1 is ready", cp1.get("status") == "ready", repr(cp1.get("status")))
    check(
        "#1 has NO previous checkpoint -- it is link one",
        cp1.get("previous_checkpoint_id") is None,
        repr(cp1.get("previous_checkpoint_id")),
    )
    check(
        "#1 founds the lineage and names it after itself",
        cp1.get("lineage_id") == cp1.get("id"),
        f"lineage={cp1.get('lineage_id')} id={cp1.get('id')}",
    )
    print(f"  probe_status={cp1.get('probe_status')!r} findings={cp1.get('probe_findings')}")

    step("3. Checkpoint #2 with NO turn in between -- an empty span")
    c2, cp2 = make_checkpoint(conv, "checkpoint #2 (empty span)")
    check(
        "an empty span answers 201 or a named refusal, never 500",
        c2 in (201, 409, 422),
        str(c2),
    )
    second_id = cp2.get("id") if isinstance(cp2, dict) and c2 == 201 else None
    if c2 == 201:
        check(
            "#2 anchors on #1",
            cp2.get("previous_checkpoint_id") == cp1.get("id"),
            repr(cp2.get("previous_checkpoint_id")),
        )
        check(
            "#2 carries #1's lineage rather than founding a new one",
            cp2.get("lineage_id") == cp1.get("lineage_id"),
            f"{cp2.get('lineage_id')} vs {cp1.get('lineage_id')}",
        )
        rc, text = rendered(cp2["id"])
        check("#2 renders 200", rc == 200, str(rc))
        check(
            "the render names its predecessor",
            f"Previous checkpoint: {cp1.get('id')}" in text,
            text[:200].replace("\n", " | "),
        )

    anchor_for_third = second_id or cp1.get("id")

    turn(
        "Create a file called CHAIN_TWO.txt in your working directory whose entire contents are "
        "the single word LINKTWO. Then STOP. Do not create any other file.",
        "4. Second real Haiku turn -- so link three covers a real span",
        conv_id=conv,
    )
    check("the second turn wrote its file", read_in_worktree("CHAIN_TWO.txt") is not None)

    c3, cp3 = make_checkpoint(conv, "5. Checkpoint #3 -- the link that covers only new work")
    if c3 != 201:
        check("checkpoint #3 generated (201)", False, str(c3))
        summarise()
        return
    check("checkpoint #3 generated (exactly 201)", c3 == 201)
    check("#3 is ready", cp3.get("status") == "ready", repr(cp3.get("status")))
    check(
        "#3 anchors on the checkpoint before it",
        cp3.get("previous_checkpoint_id") == anchor_for_third,
        f"{cp3.get('previous_checkpoint_id')} expected {anchor_for_third}",
    )
    check(
        "#3 still carries the ORIGINAL lineage -- one chain, not three",
        cp3.get("lineage_id") == cp1.get("lineage_id"),
        f"{cp3.get('lineage_id')} vs {cp1.get('lineage_id')}",
    )
    files3 = [str(f).upper() for f in (cp3.get("files_changed") or [])]
    check(
        "#3's computed record names the file the SECOND turn wrote",
        any("CHAIN_TWO" in f for f in files3),
        str(files3)[:200],
    )
    # F130. #2 covered an empty span, so it stored covers_through_run_id = NULL
    # (checkpoints.py:367), and runs_to_cover reads NULL as "unknown, cover everything"
    # (checkpoints.py:179). #3 therefore re-covers the first turn as well. Asserted in the
    # direction the product actually behaves, so the day it is fixed this line goes red and says so.
    check(
        "F130: #3 ALSO re-covers the first turn, because #2's empty span stored NULL",
        any("CHAIN_ONE" in f for f in files3),
        str(files3)[:200],
    )
    rc, text3 = rendered(cp3["id"])
    check("#3 renders 200", rc == 200, str(rc))
    check(
        "#3's render names its predecessor",
        f"Previous checkpoint: {anchor_for_third}" in text3,
        text3[:240].replace("\n", " | "),
    )
    body3 = (cp3.get("body") or "").upper()
    check(
        "#3's written half mentions the new work at all",
        "LINKTWO" in body3 or "CHAIN_TWO" in body3,
        f"{len(body3)} chars",
    )
    print(f"  probe_status={cp3.get('probe_status')!r} findings={cp3.get('probe_findings')}")

    step("6. The chain as the list route reports it")
    c, lst = api("GET", f"/projects/{P}/conversations/{conv}/checkpoints")
    ids = [x.get("id") for x in lst] if isinstance(lst, list) else []
    prevs = {x.get("id"): x.get("previous_checkpoint_id") for x in (lst or [])}
    print(f"  {c} -> {ids}")
    print(f"  links: {prevs}")
    mine = [x for x in (lst or []) if x.get("id") in (cp1.get("id"), second_id, cp3.get("id"))]
    check("every checkpoint this run made is listed", len(mine) == (3 if second_id else 2), str(ids))
    check(
        "the chain this run made is single-lineage",
        len({x.get("lineage_id") for x in mine}) == 1,
        str({x.get("lineage_id") for x in mine}),
    )
    check(
        "exactly one of this run's checkpoints has no predecessor",
        sum(1 for x in mine if x.get("previous_checkpoint_id") is None) == 1,
        str([x.get("previous_checkpoint_id") for x in mine]),
    )

    summarise()


if __name__ == "__main__":
    try:
        main()
    finally:
        api("PUT", f"/projects/{P}/settings", {"checkpoint_runner_id": None})
        print("\n[teardown] checkpoint_runner_id reset to null")
