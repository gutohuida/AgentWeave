"""2026-10-23 Flows & review drive: fixture, runner, agents and the flow document (scratch Hub
:8112). A small `numkit` library with two seeded defects in two independent modules, so a flow on
one approved change document fires two build tasks in parallel (alpha, beta) and gives each review
to the named tester. The slug criterion is deliberately wrong against its own requirement, so a
tester driving the product should amend it (lands "not reviewed").

    AW_P=proj-... py -3.11 scripts/drive/s1023_lb_setup.py fixture|doc|approve
"""

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_lb_lib import B, DOCS, HAIKU, e2e, req, show  # noqa: E402

D = pathlib.Path(e2e.os.environ["AW_E2E_ROOT"]) / "lb-main"
PATH = "spec/changes/lb-flow/spec.json"


def fixture():
    (D / "numkit").mkdir(exist_ok=True)
    (D / "numkit" / "__init__.py").write_text("", encoding="utf-8")
    (D / "numkit" / "stats.py").write_text(
        "def median(values):\n"
        "    ordered = sorted(values)\n"
        "    return ordered[len(ordered) // 2]  # seeded defect: even lengths\n",
        encoding="utf-8",
    )
    (D / "numkit" / "slug.py").write_text(
        "def slugify(text):\n"
        "    out = ''.join(c.lower() if c.isalnum() else '-' for c in text)\n"
        "    return out  # seeded defect: runs and edges of '-' kept\n",
        encoding="utf-8",
    )
    (D / "tests").mkdir(exist_ok=True)
    head = "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1]))\n"
    (D / "tests" / "test_stats.py").write_text(
        head + "from numkit.stats import median\n\n\ndef test_odd():\n    assert median([3, 1, 2]) == 2\n",
        encoding="utf-8",
    )
    (D / "tests" / "test_slug.py").write_text(
        head + "from numkit.slug import slugify\n\n\ndef test_word():\n    assert slugify('Hello') == 'hello'\n",
        encoding="utf-8",
    )
    for args in (["add", "numkit", "tests"],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "numkit"]):
        subprocess.run(["git", "-C", str(D), *args])
    st, cur = req("GET", f"{B}/settings")
    cur["default_permission_mode"] = "workspace"
    cur["checks"] = [{"name": "pytest", "command": "py -3.11 -m pytest -q", "timeout_seconds": 120}]
    show("PUT", f"{B}/settings", cur, limit=600)
    st, runner = req("POST", f"{B}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
    print("runner", st, runner.get("id"))
    for name in ("alpha", "beta", "tester"):
        show("POST", f"{B}/agents", {"name": name, "runner_id": runner["id"]}, limit=300)


def crit(key, req_key, then, how):
    return {"key": key, "requirement": req_key, "given": "the numkit package", "when": "it runs",
            "then": then, "how_to_check": how}


FLOW = {
    "schema_version": 1, "kind": "change-spec", "title": "Fix median and slugify",
    "scope": {"in_scope": ["numkit.stats", "numkit.slug"], "non_goals": ["new functions"]},
    "requirements": [
        {"key": "median-even", "statement": "median MUST return the mean of the two middle values "
                                            "for an even-length list.", "modal": "MUST"},
        {"key": "slug-clean", "statement": "slugify MUST lowercase the text, turn every run of "
                                           "non-alphanumeric characters into one hyphen, and strip "
                                           "hyphens from both ends.", "modal": "MUST"},
    ],
    "acceptance_criteria": [
        crit("c-median", "median-even", "median([1, 2, 3, 4]) == 2.5",
             "py -3.11 -c \"from numkit.stats import median; print(median([1,2,3,4]))\""),
        # Deliberately wrong against its own requirement: the tester should amend it.
        crit("c-slug", "slug-clean", "slugify('  Hello,  World! ') == 'hello--world'",
             "py -3.11 -c \"from numkit.slug import slugify; print(repr(slugify('  Hello,  World! ')))\""),
    ],
    "tasks": [
        {"key": "t-median", "title": "Fix median for even-length lists",
         "description": "Fix numkit/stats.py median; add a test to tests/test_stats.py.",
         "requirements": ["median-even"], "files": ["numkit/stats.py", "tests/test_stats.py"]},
        {"key": "t-slug", "title": "Make slugify collapse and strip hyphens",
         "description": "Fix numkit/slug.py slugify; add a test to tests/test_slug.py.",
         "requirements": ["slug-clean"], "files": ["numkit/slug.py", "tests/test_slug.py"]},
    ],
    "delivery": {"mode": "flow", "agent": "alpha", "tester": "tester",
                 "stop_when_queue_empties": True, "cron": "0 0 1 1 *"},
}


def doc():
    show("POST", DOCS, {"path": PATH, "title": FLOW["title"]}, limit=300)
    show("PUT", DOCS + f"/{PATH}/content", {"document": FLOW}, limit=1500)


def approve():
    show("POST", f"{DOCS}/close-exploration?path={PATH}", limit=400)
    show("POST", f"{DOCS}/propose?path={PATH}", limit=1500)
    st, out = show("POST", f"{DOCS}/phase?path={PATH}&to=approved", {"reason": "drive"}, limit=2500)
    if st == 409:
        show("POST", f"{DOCS}/phase?path={PATH}&to=approved",
             {"reason": "drive: gaps read above", "approve_anyway": True}, limit=3000)


if __name__ == "__main__":
    {"fixture": fixture, "doc": doc, "approve": approve}[sys.argv[1]]()
