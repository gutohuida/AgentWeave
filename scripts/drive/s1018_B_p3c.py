from s1018_B_lib import *  # noqa
RM = "spec/changes/coral-griffin/spec.json"; SP = "spec/changes/cobalt-wyvern/spec.json"; CAP = "spec/capabilities/interval-arithmetic/spec.json"
req("POST", f"{SPEC}/spec/reindex", {"home": "spec/changes/nope/spec.json"}, cut=800)
c, r = req("POST", f"{SPEC}/spec/reindex", {"home": RM}, cut=200)
print("INDEX", json.dumps(r.get("index"), ensure_ascii=False)[:1500])
req("POST", f"{SPEC}/spec/documents/arrange", {"path": SP, "parent": RM}, cut=800)
req("POST", f"{SPEC}/spec/documents/arrange", {"path": SP, "parent": SP}, cut=800)
req("POST", f"{SPEC}/spec/documents/arrange", {"path": RM, "parent": SP}, cut=800)
req("POST", f"{SPEC}/spec/documents/arrange", {"path": SP, "parent": "spec/changes/nope/spec.json"}, cut=800)
req("POST", f"{SPEC}/spec/documents/arrange", {"path": "spec/changes/hand-written-fmt/spec.json", "parent": CAP}, cut=800)
print("index.json:", (DIR / "spec" / "index.json").read_text(encoding="utf-8")[:1200])
# new document after index exists: unfiled?
c, d = req("POST", f"{SPEC}/documents", {"title": "After index"}, show=False)
c, r = req("GET", f"{SPEC}/documents", show=False)
print("LIST keys", list(r.keys()))
c, s = req("GET", f"/projects/{P}/project/specs", cut=1500)
save()
