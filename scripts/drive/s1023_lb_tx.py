"""Print a Claude transcript (assistant text, tool calls, tool results) compactly.

    py -3.11 scripts/drive/s1023_lb_tx.py <session.jsonl> [maxlen]
"""
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
n = int(sys.argv[2]) if len(sys.argv) > 2 else 600
for line in open(sys.argv[1], encoding="utf-8"):
    d = json.loads(line)
    m = d.get("message") or {}
    c = m.get("content")
    if not isinstance(c, list):
        continue
    for b in c:
        t = b.get("type")
        if t == "text" and m.get("role") == "assistant":
            print("SAY:", b["text"][:n])
        elif t == "tool_use":
            print("CALL:", b["name"], json.dumps(b.get("input"), ensure_ascii=False)[:n])
        elif t == "tool_result":
            r = b.get("content")
            if isinstance(r, list):
                r = " ".join(x.get("text", "") for x in r if isinstance(x, dict))
            print("  ->", str(r)[:n].replace("\n", " | "))
