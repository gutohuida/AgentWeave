from s1018_B_lib import *  # noqa
import urllib.parse
CH = "spec/changes/scarlet-minotaur/spec.json"; CAP = "spec/capabilities/interval-arithmetic/spec.json"; q = urllib.parse.quote(CH, safe="")
c, cov = req("GET", f"{SPEC}/spec/coverage?document={q}", cut=1200)
c, d = req("GET", f"{SPEC}/documents/{CH}/fold-draft", cut=2500)
req("POST", f"{SPEC}/documents/{CH}/fold", {"into": "spec/capabilities/nope/spec.json"}, cut=800)
req("POST", f"{SPEC}/documents/{CH}/fold", {"into": CH}, cut=800)
req("POST", f"{SPEC}/documents/{CH}/fold", {"into": CAP}, cut=2500)
print("TASKS", rows("select id,status,assignee from tasks"))
save()
