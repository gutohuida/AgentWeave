from s1018_B_lib import *  # noqa
import urllib.parse
CH = "spec/changes/scarlet-minotaur/spec.json"; q = urllib.parse.quote(CH, safe="")
c, am = req("GET", f"{SPEC}/documents/{CH}/amendments", cut=3000)
c, cov = req("GET", f"{SPEC}/spec/coverage?document={q}", cut=2500)
print("FILE criteria", [ (x["key"], x.get("requirement")) for x in doc_file(CH)["acceptance_criteria"]])
print("TASK blocked", rows("select id,status,assignee from tasks where id='task-26c07baafa80'"))
# review a nonexistent id, then review all
req("POST", f"{SPEC}/documents/{CH}/amendments/review", {"ids": ["amd-nope"]}, cut=600)
c, r = req("POST", f"{SPEC}/documents/{CH}/amendments/review", {}, cut=1500)
c, am = req("GET", f"{SPEC}/documents/{CH}/amendments", cut=1500)
c, cov = req("GET", f"{SPEC}/spec/coverage?document={q}", cut=600)
print("TASK after review", rows("select id,status,assignee from tasks where id='task-26c07baafa80'"))
save()
