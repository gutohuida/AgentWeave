"""Sweep B phase 3: corpus -- adopt, reindex, arrange, delete, rendered read, refusals."""
from s1018_B_lib import *  # noqa

RM = "spec/changes/coral-griffin/spec.json"
SP = "spec/changes/cobalt-wyvern/spec.json"
CAP = "spec/capabilities/interval-arithmetic/spec.json"

# untracked files beneath spec/
hand = DIR / "spec" / "changes" / "hand-written-fmt" / "spec.json"
hand.parent.mkdir(parents=True, exist_ok=True)
p = base_payload("change-spec", "Hand written format change", n=1)
p["requirements"] = [{"key": "fmt1", "statement": "show MUST print an interval as [lo, hi].", "modal": "MUST"},
                     {"statement": "show MUST accept a unicode flag é.", "modal": "SHOULD"}]
p["acceptance_criteria"] = []
p["tasks"] = []
hand.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
junk = DIR / "spec" / "changes" / "junk" / "spec.json"
junk.parent.mkdir(parents=True, exist_ok=True)
junk.write_text("{not json", encoding="utf-8")
noid = DIR / "spec" / "areas" / "noid" / "spec.json"
noid.parent.mkdir(parents=True, exist_ok=True)
noid.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
md = DIR / "spec" / "notes.md"
md.write_text("# notes\n", encoding="utf-8")
spaced = DIR / "spec" / "changes" / "with space" / "spec.json"
spaced.parent.mkdir(parents=True, exist_ok=True)
spaced.write_text(json.dumps(base_payload("change-spec", "Spaced path", n=1)), encoding="utf-8")

c, docs = req("GET", f"{SPEC}/documents", show=False)
print("DOCUMENTS LIST keys:", list(docs.keys()))
for k, v in docs.items():
    if k != "documents":
        print("  ", k, json.dumps(v, ensure_ascii=False)[:1500])

req("POST", f"{SPEC}/documents/adopt", {"path": "spec/changes/junk/spec.json"}, cut=600)
req("POST", f"{SPEC}/documents/adopt", {"path": "spec/areas/noid/spec.json"}, cut=600)
req("POST", f"{SPEC}/documents/adopt", {"path": "spec/notes.md"}, cut=600)
req("POST", f"{SPEC}/documents/adopt", {"path": "spec/changes/missing/spec.json"}, cut=600)
req("POST", f"{SPEC}/documents/adopt", {"path": "../outside/spec.json"}, cut=600)
req("POST", f"{SPEC}/documents/adopt", {"path": CAP}, cut=600)
c, a = req("POST", f"{SPEC}/documents/adopt", {"path": "spec/changes/hand-written-fmt/spec.json"}, cut=1500)
print("ADOPTED reqs:", rows("select identifier, statement from spec_requirements where document_id=(select id from spec_documents where project_id=? and path=?)", P, "spec/changes/hand-written-fmt/spec.json"))
c, a = req("POST", f"{SPEC}/spec/adopt", None, cut=2500)
c, r = req("POST", f"{SPEC}/spec/reindex", {}, cut=2500)

# arrange (place under)
req("POST", f"{SPEC}/spec/documents/arrange", {"path": SP, "parent": RM}, cut=800)
req("POST", f"{SPEC}/spec/documents/arrange", {"path": SP, "parent": SP}, cut=800)
req("POST", f"{SPEC}/spec/documents/arrange", {"path": RM, "parent": SP}, cut=800)
req("POST", f"{SPEC}/spec/documents/arrange", {"path": SP, "parent": "spec/changes/nope/spec.json"}, cut=800)
req("POST", f"{SPEC}/spec/documents/arrange", {"path": SP, "parent": None}, cut=800)
req("POST", f"{SPEC}/spec/documents/arrange", {"path": SP, "parent": CAP}, cut=800)
print("index.json:", (DIR / "spec" / "index.json").read_text(encoding="utf-8")[:1500] if (DIR / "spec" / "index.json").exists() else "absent")

# rendered read of the roadmap (slice states)
c, html = req("GET", f"/projects/{P}/project/spec?path={RM}", show=False)
print("SPEC READ", c, (json.dumps(html)[:300] if not isinstance(html, str) else html[:300]))
save()
