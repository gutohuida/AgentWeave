"""Sweep B phase 1: documents, journey, capability from the app, refusals (no agent turns)."""
from s1018_B_lib import *  # noqa

# capability from the app (F644)
c, cap = req("POST", f"{SPEC}/documents", {"title": "Interval arithmetic", "kind": "capability"})
print("CAP PATH", cap.get("path"), cap.get("phase"))
# change document
c, ch = req("POST", f"{SPEC}/documents", {"title": "Touching intervals merge"})
CH = ch["path"]
print("CHANGE PATH", CH, ch.get("phase"), "journey:", ch.get("journey"))
# journey: read project journey, set size, step
req("GET", f"{SPEC}/journey")
req("POST", f"{SPEC}/documents/journey?path={CH}", {"size": "huge", "reason": "probe"})
req("POST", f"{SPEC}/documents/journey?path={CH}", {"step": "nonexistent-step"})
req("POST", f"{SPEC}/documents/journey?path={CH}", {"size": "small", "reason": "a one-line fix"})
req("POST", f"{SPEC}/documents/journey?path={CH}", {"size": "large", "reason": "grew"})
# bad path probes
req("POST", f"{SPEC}/documents/journey?path=spec/changes/../../etc/spec.json", {"size": "small"})
req("POST", f"{SPEC}/documents/journey?path=spec/changes/nope/spec.json", {"size": "small"})
# list documents
c, docs = req("GET", f"{SPEC}/documents", cut=2000)
# content write
payload = base_payload("change-spec", "Touching intervals merge", n=2,
                       extra={"open_questions": [{"question": "Should open intervals be in scope later?",
                                                  "resolved": False}]})
c, w = req("PUT", f"{SPEC}/documents/{CH}/content", {"document": payload}, cut=1500)
# close exploration, propose, approve without anyway
req("POST", f"{SPEC}/documents/close-exploration?path={CH}", cut=1500)
req("POST", f"{SPEC}/documents/propose?path={CH}", cut=2500)
req("POST", f"{SPEC}/documents/propose?path={CH}", cut=600)
req("POST", f"{SPEC}/documents/phase?path={CH}&to=approved", {"reason": "first try"}, cut=3000)
req("POST", f"{SPEC}/documents/phase?path={CH}&to=nonsense", {"reason": "x"})
print("CH=", CH, "CAP=", cap.get("path"))
save()
