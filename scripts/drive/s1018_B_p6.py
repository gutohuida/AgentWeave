from s1018_B_lib import *  # noqa
c, d = req("POST", f"{SPEC}/documents", {"title": "Large interval catalogue"}, show=False)
BIG = d["path"]
reqs = [{"key": f"big{i}", "statement": f"The catalogue MUST describe interval family {i} — naïve, ½-open, and “closed” forms — with an example and its edge cases spelled out at length so that the requirement text is long enough to matter for paging ({'x' * 300}).", "modal": "MUST"} for i in range(1, 61)]
p = base_payload("change-spec", "Large interval catalogue", n=1)
p["requirements"] = reqs
p["acceptance_criteria"] = [{"key": f"bc{i}", "requirement": f"big{i}", "given": "g", "when": "w", "then": "t"} for i in range(1, 61)]
p["tasks"] = [{"key": "bt1", "title": "Write the catalogue", "description": "d", "requirements": [f"big{i}" for i in range(1, 61)]}]
p["design"] = "Design notes. " + ("Ünïcode design paragraph about intervals and their closure. " * 600)
c, w = req("PUT", f"{SPEC}/documents/{BIG}/content", {"document": p}, cut=400)
size = len((DIR / BIG).read_text(encoding="utf-8"))
print("BIG", BIG, "file chars", size)
c, h = req("GET", f"/projects/{P}/project/spec?path={BIG}", show=False)
print("render chars", len(h["content"]) if isinstance(h, dict) else h)
save()
