"""Dependencies sweep 2026-10-23: which declared-path spellings the same-file warning sees.

One exploring document rewritten per case through PUT content (the operator's write door);
prints the warning codes each save answers with. No agent turns.
"""

from s1023_dp_common import BASE, make_doc, q, sc

CASES = {
    "same spelling": (["lib.py"], ["lib.py"]),
    "dot-slash": (["lib.py"], ["./lib.py"]),
    "backslash": (["pkg/lib.py"], ["pkg\\lib.py"]),
    "directory covers": (["pkg"], ["pkg/lib.py"]),
    "case differs": (["Lib.py"], ["lib.py"]),
    "parent segment": (["pkg/lib.py"], ["pkg/../pkg/lib.py"]),
    "doubled slash": (["pkg/lib.py"], ["pkg//lib.py"]),
}

path, code, res, payload = make_doc("Overlap spellings", [
    {"key": "t1", "description": "one", "requirements": ["r1"], "files": ["x.py"]},
    {"key": "t2", "description": "two", "requirements": ["r2"], "files": ["y.py"]},
])
print("DOC", path, code)
for name, (a, b) in CASES.items():
    payload["tasks"][0]["files"] = a
    payload["tasks"][1]["files"] = b
    code, res = sc.api("PUT", f"{BASE}/project/documents/{q(path)}/content",
                       {"document": payload})
    codes = [w["code"] for w in res.get("warnings", [])] if isinstance(res, dict) else res
    msg = res.get("detail") if isinstance(res, dict) and "detail" in res else ""
    print(f"{name:18} {a} vs {b}: {code} {codes} {msg}")
