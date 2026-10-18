"""Sweep B phase 3: corpus -- adopt, reindex, arrange, delete, rendered read, refusals."""
from s1018_B_lib import *  # noqa

RM = "spec/changes/coral-griffin/spec.json"
SP = "spec/changes/cobalt-wyvern/spec.json"
CAP = "spec/capabilities/interval-arithmetic/spec.json"

c, a = req("POST", f"{SPEC}/documents/adopt", {"path": "spec/changes/with space/spec.json"}, cut=1500)
print("SPACED reqs:", rows("select identifier, key, state from spec_requirements where document_id=(select id from spec_documents where project_id=? and path=?)", P, "spec/changes/with space/spec.json"))
print("ADOPTED reqs:", rows("select identifier, key, state from spec_requirements where document_id=(select id from spec_documents where project_id=? and path=?)", P, "spec/changes/hand-written-fmt/spec.json"))
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
