"""T-HOP: watch hop depths propagate and see whether the budget actually bounds delivery."""

import sys
import time

from aw import api

P = "proj-18e5d4e0"
AGENTS = ("builder", "relay", "critic")


def snapshot():
    c, ag = api("GET", f"/projects/{P}/agents")
    st = {a["name"]: a.get("status") for a in ag} if c == 200 else {}
    lines = []
    for name in AGENTS:
        c2, q = api("GET", f"/projects/{P}/queue/{name}")
        rows = q if isinstance(q, list) else []
        if rows:
            parts = []
            for e in rows:
                parts.append("%s@%s/%s" % (e.get("origin_type", "?")[:3], e.get("hop_depth"), e.get("state")))
            lines.append(name + ":" + ",".join(parts))
    return st, lines


def messages():
    c, m = api("GET", f"/projects/{P}/messages")
    rows = m if isinstance(m, list) else []
    return [(x.get("sender"), x.get("recipient"), (x.get("subject") or "")[:20]) for x in rows]


if __name__ == "__main__":
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    for i in range(rounds):
        st, lines = snapshot()
        print("%4ds %s | %s" % (i * 8, st, " ".join(lines) or "(no queued/delivered entries)"))
        sys.stdout.flush()
        if i > 2 and all(v != "running" for v in st.values()):
            break
        time.sleep(8)
    print("messages:", messages())
