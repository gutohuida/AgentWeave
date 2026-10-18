from s1018_B_lib import *  # noqa
CH = "spec/changes/scarlet-minotaur/spec.json"; RM = "spec/changes/coral-griffin/spec.json"
req("POST", f"{SPEC}/documents/phase?path={RM}&to=approved", {"reason": "roadmap ok", "approve_anyway": True}, cut=600)
c, p = req("POST", f"{SPEC}/documents/propose?path={CH}", cut=1200)
c, a = req("POST", f"{SPEC}/documents/phase?path={CH}&to=approved", {"reason": "re-approve reworded", "approve_anyway": True}, cut=2500)
print("TASKS", rows("select id, status, assignee, title, substr(description,1,80) d from tasks"))
c, html = req("GET", f"/projects/{P}/project/spec?path={RM}", show=False)
import re
t = html["content"] if isinstance(html, dict) else html
i = t.find("touching")
print("ROADMAP RENDER around slices:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:3000])
save()
