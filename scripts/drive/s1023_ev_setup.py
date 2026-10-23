"""2026-10-23 Requirements, evidence & coverage x Drift sweep: fixture, runner, agents and the one
change document (scratch Hub :8115, profile ev1023). A small `textkit` library with a seeded
defect; a Haiku runner for `builder` (does the work, records evidence) and `checker` (granted
`can_accept_evidence`, decides it from a real turn).

`spec/changes/ev-main/spec.json` carries five requirements, so the Spec header's requirements fact
has every unfinished state to name (F945):

- `ws`, `blank`  task t-words (builder): evidence by builder, decided by checker (accept one,
  reject the other);
- `doc`          task t-docs: the operator's own evidence on README.md, later drifted and reworded;
- `later`        task t-docs too: not started;
- `extra`        no task: "with no task".

    AW_P=proj-... py -3.11 scripts/drive/s1023_ev_setup.py fixture|doc|approve
"""

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_ev_lib import B, DOCS, HAIKU, e2e, req, show  # noqa: E402

D = pathlib.Path(e2e.os.environ["AW_E2E_ROOT"]) / "ev-main"
PATH = "spec/changes/ev-main/spec.json"


def git(*args):
    subprocess.run(["git", "-C", str(D), "-c", "user.name=t", "-c", "user.email=t@t", *args])


def fixture():
    (D / "textkit").mkdir(exist_ok=True)
    (D / "textkit" / "__init__.py").write_text("", encoding="utf-8")
    (D / "textkit" / "words.py").write_text(
        "def count_words(text):\n    return len(text.split(' '))  # seeded defect: double spaces\n",
        encoding="utf-8",
    )
    (D / "tests").mkdir(exist_ok=True)
    (D / "tests" / "test_words.py").write_text(
        "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1]))\n"
        "from textkit.words import count_words\n\n\ndef test_simple():\n"
        "    assert count_words('a b c') == 3\n",
        encoding="utf-8",
    )
    (D / "README.md").write_text(
        "# textkit\n\n`count_words(text)` returns the number of words in `text`.\n",
        encoding="utf-8",
    )
    (D / "NOTES.md").write_text("Unwatched notes.\n", encoding="utf-8")
    git("add", "textkit", "tests", "README.md", "NOTES.md")
    git("commit", "-q", "-m", "textkit")
    st, runner = req("POST", f"{B}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
    print("runner", st, runner.get("id"))
    for name in ("builder", "checker"):
        show("POST", f"{B}/agents", {"name": name, "runner_id": runner["id"]}, limit=300)
    show("PATCH", f"{B}/agents/checker", {"can_accept_evidence": True}, limit=400)


def crit(key, req_key, then, how):
    return {"key": key, "requirement": req_key, "given": "the textkit package", "when": "it runs",
            "then": then, "how_to_check": how}


DOC = {
    "schema_version": 1, "kind": "change-spec", "title": "Honest word counts",
    "scope": {"in_scope": ["textkit.words", "README.md"], "non_goals": ["unicode word boundaries"]},
    "requirements": [
        {"key": "ws", "statement": "count_words MUST treat any run of whitespace as one separator.",
         "modal": "MUST"},
        {"key": "blank", "statement": "count_words MUST return 0 for an empty or blank string.",
         "modal": "MUST"},
        {"key": "doc", "statement": "README.md MUST document count_words.", "modal": "MUST"},
        {"key": "later", "statement": "count_lines MUST count newline-separated lines.",
         "modal": "MUST"},
        {"key": "extra", "statement": "textkit SHOULD ship a py.typed marker.", "modal": "SHOULD"},
    ],
    "acceptance_criteria": [
        crit("c-ws", "ws", "count_words('a  b\\tc\\n') == 3", "pytest tests/test_words.py"),
        crit("c-blank", "blank", "count_words('   ') == 0 and count_words('') == 0",
             "pytest tests/test_words.py"),
        crit("c-doc", "doc", "README.md names count_words", "read README.md"),
        crit("c-later", "later", "count_lines('a\\nb') == 2", "pytest"),
        crit("c-extra", "extra", "textkit/py.typed exists", "ls textkit"),
    ],
    "tasks": [
        {"key": "t-words", "title": "Count words on any whitespace",
         "description": "Fix textkit/words.py count_words; add tests in tests/test_words.py.",
         "requirements": ["ws", "blank"]},
        {"key": "t-docs", "title": "Document and add count_lines",
         "description": "README for count_words; a count_lines helper.",
         "requirements": ["doc", "later"]},
    ],
    "delivery": {"mode": "none"},
}


def doc():
    show("POST", DOCS, {"path": PATH, "title": DOC["title"]}, limit=300)
    show("PUT", DOCS + f"/{PATH}/content", {"document": DOC}, limit=600)


def approve():
    show("POST", f"{DOCS}/close-exploration?path={PATH}", limit=400)
    show("POST", f"{DOCS}/propose?path={PATH}", limit=1200)
    st, _ = show("POST", f"{DOCS}/phase?path={PATH}&to=approved", {"reason": "drive"}, limit=1500)
    if st == 409:
        show("POST", f"{DOCS}/phase?path={PATH}&to=approved",
             {"reason": "drive: gaps read above", "approve_anyway": True}, limit=1500)


if __name__ == "__main__":
    {"fixture": fixture, "doc": doc, "approve": approve}[sys.argv[1]]()
