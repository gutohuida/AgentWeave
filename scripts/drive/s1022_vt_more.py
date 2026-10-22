"""2026-10-22 vault sweep, second API pass (after s1022_vt_drive.py): a private entry (stub vs body),
a source past one page (paging), and a change document citing a superseded and a disputed fact
(Vault warnings and the approve gaps). Manager jobs are switched off first: nothing here spends.

  py -3.11 scripts/drive/s1022_vt_more.py
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import s1022_vt_drive as d  # noqa: E402

for key in d.JOBS:
    d.job(key, enabled=False)
st, e = d.api("POST", "~/vault/sources", {"name": "Private pay rates", "type": "note", "visibility": "private",
                                          "content": "Contractor day rate is 640 EUR."})
d.say("private add", (st, {k: e.get(k) for k in ("id", "visibility", "holder", "available")}))
pid = e["id"]
root = pathlib.Path(d.S["DIR"])
stubs = list(root.rglob(f"{pid}*"))
d.say("files under the project", [str(p.relative_to(root)) for p in stubs])
for p in stubs:
    if p.suffix == ".json":
        d.say("stub", p.read_text(encoding="utf-8")[:400])
priv = pathlib.Path(d.api("GET", "~/vault/settings")[1]["effective_private_location"])
d.say("private location files", [str(p.relative_to(priv)) for p in priv.rglob(f"{pid}*")])
long_text = "".join(f"Line {i:05d}: the export log entry number {i} reads ok.\n" for i in range(1, 2201))
long_text += "FINAL LINE: the last export failed on 2026-10-20.\n"
st, e = d.api("POST", "~/vault/sources", {"name": "Long export log", "type": "transcript", "content": long_text})
d.say("long add", (st, e.get("id"), len(long_text)))
d.S["long"] = e["id"]
d.save()
st, p1 = d.api("GET", f"~/vault/entries/{e['id']}")
d.say("page 1", {k: p1.get(k) for k in ("offset", "next_offset", "total_chars", "more", "truncated")} | {"len": len(p1.get("content") or "")})
nxt = p1.get("next_offset")
if nxt:
    st, p2 = d.api("GET", f"~/vault/entries/{e['id']}?offset={nxt}")
    d.say("page 2", {k: p2.get(k) for k in ("offset", "next_offset", "total_chars")} | {"tail": (p2.get("content") or "")[-60:]})
st, p9 = d.api("GET", f"~/vault/entries/{e['id']}?offset=99999999")
d.say("offset past end", (st, {k: p9.get(k) for k in ("offset", "next_offset", "detail")}, len(p9.get("content") or "")))
st, pn = d.api("GET", f"~/vault/entries/{e['id']}?offset=-5")
d.say("negative offset", (st, pn if st != 200 else {k: pn.get(k) for k in ("offset",)}))
ctr = d.api("GET", "~/vault/contradictions")[1]["contradictions"]
resolved = next(c for c in ctr if c["status"] == "resolved")
open_c = next(c for c in ctr if c["status"] == "open")
loser = next(f for f in resolved["facts"] if f != resolved["resolution"]["stands"])
DOC = "spec/changes/export-names/spec.json"
doc = {
    "schema_version": 1, "kind": "change-spec", "title": "Export names",
    "scope": {"in_scope": ["export"], "non_goals": ["scheduling"]},
    "requirements": [
        {"key": "names", "statement": "The export MUST keep original file names.", "modal": "MUST", "facts": [loser]},
        {"key": "time", "statement": "The export MUST run at 02:00.", "modal": "MUST", "facts": [open_c["facts"][0]]},
        {"key": "ghost", "statement": "The export MUST log.", "modal": "MUST", "facts": ["fct-000000000000"]},
    ],
    "acceptance_criteria": [{"key": f"c-{k}", "requirement": k, "given": "g", "when": "w", "then": "t", "how_to_check": "look"}
                            for k in ("names", "time", "ghost")],
    "tasks": [{"key": "t1", "title": "Export", "description": "d", "requirements": ["names", "time", "ghost"]}],
    "delivery": {"mode": "none"},
}
d.api("POST", "~/project/documents", {"path": DOC, "title": "Export names"})
st, out = d.api("PUT", f"~/project/documents/{DOC}/content", {"document": doc})
d.say("doc write", (st, {k: out.get(k) for k in ("blocking", "warnings")} if isinstance(out, dict) else out))
st, w = d.api("GET", f"~/vault/warnings?path={DOC}")
d.say("vault warnings", (st, w))
st, out = d.api("POST", f"~/vault/warnings/check?path={DOC}")
d.say("check now (job off)", (st, out))
d.api("POST", f"~/project/documents/close-exploration?path={DOC}")
st, out = d.api("POST", f"~/project/documents/propose?path={DOC}")
d.say("propose", (st, {k: out.get(k) for k in ("phase", "blocking")} if isinstance(out, dict) else out))
st, out = d.api("POST", f"~/project/documents/phase?path={DOC}&to=approved", {"reason": "drive"})
d.say("approve", (st, json.dumps(out)[:1500]))
d.S["doc"] = DOC
d.save()
