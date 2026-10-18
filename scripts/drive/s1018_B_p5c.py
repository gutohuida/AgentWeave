from s1018_B_lib import *  # noqa
CH = "spec/changes/scarlet-minotaur/spec.json"
f = doc_file(CH); payload = {k: v for k, v in f.items() if k != "hub"}
payload["requirements"][0]["statement"] = "Interval.overlaps MUST return true for closed intervals that share at least one point, endpoints included."
payload["tasks"][0]["description"] = "Make r1 hold under its new wording, with a test."
payload["delivery"] = {"mode": "none"}
payload["open_questions"][0]["resolved"] = True
c, w = req("PUT", f"{SPEC}/documents/{CH}/content", {"document": payload}, cut=1200)
req("POST", f"{SPEC}/documents/propose?path={CH}", cut=300)
req("POST", f"{SPEC}/documents/close-exploration?path={CH}", cut=200)
c, p = req("POST", f"{SPEC}/documents/propose?path={CH}", cut=1500)
c, a = req("POST", f"{SPEC}/documents/phase?path={CH}&to=approved", {"reason": "re-approve reworded", "approve_anyway": True}, cut=2500)
print("TASKS", rows("select id, status, assignee, title, substr(description,1,80) d from tasks"))
save()
