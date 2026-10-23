"""2026-10-23 Spec documents x Corpus & folding sweep, the API rows (scratch Hub :8114, profile
sp1023): a roadmap and a capability to fold into (`prep`); then fold the flow's change into the
capability retiring the requirement it supersedes, read the capability's coverage, and link the
archived change to a roadmap slice after the fact (`fold`, F674); delete a document (`delete`).

    AW_P=proj-... py -3.11 scripts/drive/s1023_sp_corpus.py prep|fold <change>|delete <path>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_sp_lib import B, DOCS, e2e, req, show  # noqa: E402

RM = "spec/changes/sp-roadmap/spec.json"
CAP = "spec/capabilities/textkit/spec.json"
ROOT = pathlib.Path(e2e.os.environ["AW_E2E_ROOT"]) / "sp-main"


def on_disk(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def prep():
    show("POST", DOCS, {"path": RM, "title": "Textkit roadmap", "kind": "roadmap"}, limit=200)
    show("PUT", f"{DOCS}/{RM}/content", {"document": {
        "schema_version": 1, "kind": "roadmap", "title": "Textkit roadmap",
        "scope": {"in_scope": ["textkit"], "non_goals": ["i18n"]},
        "slices": [
            {"key": "words", "title": "Words", "intent": "Count words right.", "done": "word counts are right"},
            {"key": "case", "title": "Case", "intent": "Case helpers.", "done": "case helpers ship",
             "builds_after": ["words"]}]}}, limit=400)
    for step in ("close-exploration", "propose"):
        req("POST", f"{DOCS}/{step}?path={RM}")
    show("POST", f"{DOCS}/phase?path={RM}&to=approved", {"reason": "drive", "approve_anyway": True}, limit=200)
    show("POST", DOCS, {"path": CAP, "title": "Textkit", "kind": "capability"}, limit=200)
    show("POST", f"{DOCS}/{CAP}/merge", {"payload": {
        "schema_version": 1, "kind": "capability", "title": "Textkit",
        "requirements": [
            {"key": "split-space", "statement": "count_words MUST split on single spaces.", "modal": "MUST"},
            {"key": "import", "statement": "textkit MUST import with no dependencies.", "modal": "MUST"}],
        "acceptance_criteria": [
            {"key": "split-space-c", "requirement": "split-space", "given": "g", "when": "w", "then": "'a b' counts 2"},
            {"key": "import-c", "requirement": "import", "given": "g", "when": "w", "then": "import textkit works"}]}},
        limit=400)


def fold(change):
    path = f"spec/changes/{change}/spec.json"
    st, draft = req("GET", f"{DOCS}/{path}/fold-draft?into={CAP}")
    print("fold-draft", st, json.dumps({k: draft.get(k) for k in ("requirements", "collisions", "warnings",
                                                                 "capability_requirements")}
                                       if isinstance(draft, dict) else draft, ensure_ascii=False)[:1500])
    show("POST", f"{DOCS}/{path}/fold", {"into": CAP, "retire": ["bogus-key"], "note": "drive"}, limit=600)
    st, out = show("POST", f"{DOCS}/{path}/fold", {"into": CAP, "retire": ["split-space"],
                                                   "note": "whitespace supersedes single spaces"}, limit=1500)
    cap = on_disk(CAP)
    print("capability requirements:", [(r["key"], r.get("statement")[:60]) for r in cap.get("requirements", [])])
    print("capability criteria:", [c["key"] for c in cap.get("acceptance_criteria", [])])
    print("retired:", json.dumps(cap.get("retired") or cap.get("hub", {}).get("retired"), ensure_ascii=False)[:600])
    st, cov = req("GET", f"{B}/project/spec/coverage?document={CAP}")
    print("coverage", st, json.dumps(cov, ensure_ascii=False)[:1500])
    L = f"{DOCS}/{path}/roadmap"
    show("PUT", L, {"document": RM, "slice": "nope"}, limit=400)
    show("PUT", L, {"document": RM, "slice": "words"}, limit=400)
    print("archived change's roadmap on disk:", on_disk(path).get("roadmap"))
    st, rv = req("GET", f"{DOCS}/{RM}")
    print("roadmap view:", json.dumps({k: rv.get(k) for k in rv if "slice" in k}, ensure_ascii=False)[:800])


def delete(path):
    show("DELETE", f"{DOCS}/{path}", limit=1500)
    show("GET", f"{DOCS}/{path}", limit=300)


if __name__ == "__main__":
    {"prep": prep, "fold": lambda: fold(sys.argv[2]), "delete": lambda: delete(sys.argv[2])}[sys.argv[1]]()
