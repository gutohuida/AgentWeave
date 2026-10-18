from s1018_B_lib import *  # noqa
CAP = "spec/capabilities/interval-arithmetic/spec.json"; SP = "spec/changes/cobalt-wyvern/spec.json"; CH = "spec/changes/scarlet-minotaur/spec.json"
c, c2 = req("POST", f"{SPEC}/documents", {"title": "Interval formatting", "kind": "capability"}, cut=200)
C2 = c2["path"]
req("POST", f"{SPEC}/documents/{C2}/merge", {"payload": {"schema_version": 1, "kind": "capability", "title": "Interval formatting",
    "summary": "s", "scope": {"in_scope": ["fmt"], "non_goals": ["x"]},
    "requirements": [{"key": "show", "statement": "show MUST print [lo, hi].", "modal": "MUST"}], "lifecycle": "living"}}, cut=300)
req("POST", f"{SPEC}/documents/phase?path={C2}&to=archived", {"reason": "absorbed", "absorbed_by": C2}, cut=600)
req("POST", f"{SPEC}/documents/phase?path={C2}&to=archived", {"reason": "absorbed", "absorbed_by": SP}, cut=600)
req("POST", f"{SPEC}/documents/phase?path={SP}&to=proposed", {"reason": "x", "absorbed_by": CAP}, cut=600)
req("POST", f"{SPEC}/documents/phase?path={C2}&to=archived", {"reason": "absorbed into arithmetic", "absorbed_by": CAP}, cut=1200)
print("C2 reqs", rows("select identifier, state from spec_requirements where document_id=(select id from spec_documents where path=?)", C2))
req("POST", f"{SPEC}/documents/phase?path={C2}&to=exploring", {"reason": "reopen retired cap"}, cut=600)
# delete
req("DELETE", f"{SPEC}/documents/{CH}", cut=600)
req("DELETE", f"{SPEC}/documents/spec/changes/nope/spec.json", cut=300)
c, d = req("DELETE", f"{SPEC}/documents/{SP}", cut=800)
print("SP file exists after delete:", (DIR / SP).exists(), "row:", rows("select id from spec_documents where path=?", SP))
print("index mentions SP:", SP in (DIR / "spec" / "index.json").read_text(encoding="utf-8"))
save()
