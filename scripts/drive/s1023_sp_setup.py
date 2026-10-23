"""2026-10-23 Spec documents x Corpus & folding sweep: fixture, runner, agents and documents
(scratch Hub :8114, profile sp1023). A small `textkit` library with a seeded defect; a Haiku
runner for `builder` and `tester`; three change documents written through the operator routes:

- `spec/changes/sp-report/spec.json`  approved, no flow; one task whose two criteria cannot be met
  (the cannot-satisfy answer: reject one, accept the other, with a real reporter);
- `spec/changes/sp-flow/spec.json`    approved with a flow (builder works, tester tests): the
  tester-turn amendment path;
- `spec/changes/sp-full/spec.json`    exploring, carrying a flow `delivery`: F944's read -> edit ->
  submit round trip.

    AW_P=proj-... py -3.11 scripts/drive/s1023_sp_setup.py fixture|docs|approve-report|approve-flow
"""

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_sp_lib import B, DOCS, HAIKU, e2e, req, show  # noqa: E402

D = pathlib.Path(e2e.os.environ["AW_E2E_ROOT"]) / "sp-main"


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
    for args in (["add", "textkit", "tests"],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "textkit"]):
        subprocess.run(["git", "-C", str(D), *args])
    st, runner = req("POST", f"{B}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
    print("runner", st, runner.get("id"))
    for name in ("builder", "tester"):
        show("POST", f"{B}/agents", {"name": name, "runner_id": runner["id"]}, limit=300)


def crit(key, req_key, then, how):
    return {"key": key, "requirement": req_key, "given": "the textkit package", "when": "it runs",
            "then": then, "how_to_check": how}


REPORT = {
    "schema_version": 1, "kind": "change-spec", "title": "Instant word counts",
    "scope": {"in_scope": ["textkit.words"], "non_goals": ["other modules"]},
    "requirements": [
        {"key": "fast", "statement": "count_words MUST count a 1 GB string quickly.", "modal": "MUST"},
        {"key": "tiny", "statement": "count_words MUST use little memory.", "modal": "MUST"},
    ],
    "acceptance_criteria": [
        crit("c-fast", "fast", "count_words of a 1 GB string returns in under 1 nanosecond",
             "time it with time.perf_counter_ns"),
        crit("c-tiny", "tiny", "count_words allocates exactly zero bytes while counting a 1 GB string",
             "measure with tracemalloc"),
    ],
    "tasks": [{"key": "t-perf", "title": "Make count_words instant and allocation-free",
               "description": "Meet c-fast and c-tiny.", "requirements": ["fast", "tiny"]}],
    "delivery": {"mode": "none"},
}

FLOW = {
    "schema_version": 1, "kind": "change-spec", "title": "Count words on any whitespace",
    "scope": {"in_scope": ["textkit.words"], "non_goals": ["unicode word boundaries"]},
    "requirements": [
        {"key": "ws", "statement": "count_words MUST treat any run of whitespace (spaces, tabs, "
                                  "newlines) as one separator, and an empty or blank string MUST "
                                  "count as 0 words.", "modal": "MUST"},
    ],
    "acceptance_criteria": [
        # Deliberately wrong against its own requirement: a tester driving the product should
        # find the criterion, not the code, is wrong and amend it.
        crit("c-ws", "ws", "count_words('a  b\\tc\\n') == 3 and count_words('   ') == 1",
             "py -3.11 -c \"from textkit.words import count_words as c; print(c('a  b\\tc\\n'), c('   '))\""),
    ],
    "tasks": [{"key": "t-ws", "title": "Count words on any whitespace",
               "description": "Fix textkit/words.py count_words; add a test in tests/test_words.py.",
               "requirements": ["ws"]}],
    "delivery": {"mode": "flow", "agent": "builder", "tester": "tester",
                 "stop_when_queue_empties": True, "cron": "*/3 * * * *"},
}

FULL = {
    "schema_version": 1, "kind": "change-spec", "title": "Title case helper",
    "scope": {"in_scope": ["textkit.case"], "non_goals": ["locale rules"]},
    "requirements": [
        {"key": "title", "statement": "title_case MUST capitalise each word.", "modal": "MUST"},
    ],
    "acceptance_criteria": [
        dict(crit("c-title", "title", "title_case('a b') == 'A B'", "pytest tests/test_case.py"),
             checked_by="agent"),
    ],
    "tasks": [{"key": "t-title", "title": "Add title_case", "description": "New module textkit/case.py.",
               "requirements": ["title"]}],
    "delivery": {"mode": "flow", "agent": "builder", "reviewer": "tester",
                 "stop_when_queue_empties": True, "cron": "*/7 * * * *"},
}


def docs():
    for slug, payload in (("sp-report", REPORT), ("sp-flow", FLOW), ("sp-full", FULL)):
        path = f"spec/changes/{slug}/spec.json"
        show("POST", DOCS, {"path": path, "title": payload["title"]}, limit=300)
        show("PUT", DOCS + f"/{path}/content",
             {"document": payload}, limit=600)


def approve(slug):
    path = f"spec/changes/{slug}/spec.json"
    base = DOCS
    show("POST", f"{base}/close-exploration?path={path}", limit=400)
    show("POST", f"{base}/propose?path={path}", limit=1200)
    st, out = show("POST", f"{base}/phase?path={path}&to=approved", {"reason": "drive"}, limit=2000)
    if st == 409:
        show("POST", f"{base}/phase?path={path}&to=approved",
             {"reason": "drive: gaps read above", "approve_anyway": True}, limit=2000)


if __name__ == "__main__":
    {"fixture": fixture, "docs": docs,
     "approve-report": lambda: approve("sp-report"),
     "approve-flow": lambda: approve("sp-flow")}[sys.argv[1]]()
