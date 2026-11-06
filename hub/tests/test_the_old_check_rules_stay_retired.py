"""The rules the known-failing list replaced stay retired (`failures-already-known-are-on-a-list-not-
re-argued`, FR-12, ac-retired).

Before the list, the completion and landing gates re-ran every failure on a checkout of main
(`_MainBaseline`) to decide whose it was; a batch whose failures main shared was held for the
operator (`_main_shares_the_failure`) and released when main moved (`_release_shared_failure_holds`);
a batch that timed out twice was held too; the Hub landed over a shared failure on its own, as the
project's `checks_auto_override` allowed; flaky tests were rebuilt from thirty days of check runs
and event-log rows; and the Overview's flaky list was dealt with by marking it "handled". The
setting itself is gone too (FR-15), so its name appears nowhere in the Hub but its migrations. Each of those is a shape in the source, so this test reads the Hub's source for
each one and fails, naming the file and line, if it is back. Each pattern is proven against the code
it was written to catch, so a pattern that silently stopped matching fails too.

A sweep test: it reads hub/hub rather than importing what it guards
(`scripts/checks/sweep_tests.txt`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

HUB = Path(__file__).resolve().parents[1] / "hub"

#: name -> (pattern, files it applies to (empty: every Hub module), what it caught before).
RETIRED: Dict[str, Tuple[str, Tuple[str, ...], str]] = {
    "the main-baseline re-run": (
        r"class\s+_MainBaseline\b|_MainBaseline\s*\(|\b_record_main_(tests|result)\b"
        r"|\[\s*[\"']on_main[\"']\s*\]\s*=",
        (),
        'baseline = project_checks._MainBaseline(root, owner, base)\nresult["on_main"] = {}',
    ),
    "the shared-failure hold": (
        r"\b_main_shares_the_failure\b|fail on main too, so the failure is not this work",
        (),
        "return await _main_shares_the_failure(root, main_branch, project_id, batch_id)",
    ),
    "the hold's release when main moves": (
        r"\b_release_shared_failure_holds\b",
        (),
        "await _release_shared_failure_holds(project_id)",
    ),
    "a batch held for the operator (the timeout hold among them)": (
        r"_end_batch\(\s*batch_id\s*,\s*[\"']held[\"']",
        (),
        'await _end_batch(batch_id, "held", error=why)',
    ),
    "the shared-failure automatic override": (
        r"\bautomatic_override(_allowed)?\b|\bnot_the_tasks\b|\bfile_fix_task\b"
        r"|\boverride_reason_for\b",
        (),
        "refusal.automatic_override = await automatic_override(session, task, view)",
    ),
    "the checks_auto_override setting, anywhere outside the migrations (FR-15)": (
        r"\bchecks_auto_override\b",
        (),
        'return bool(getattr(project, "checks_auto_override", True))',
    ),
    "the flaky list and its 'handled' action, which the known-failing list replaced (FR-11)": (
        r"checks/flaky|[\"']/flaky(/handled)?[\"']|\bmark_handled\b|\bHANDLED_EVENT\b"
        r"|\bchecks_flaky_handled\b",
        (),
        '@checks_router.post("/flaky/handled")\nawait flaky_tests.mark_handled(session, project_id)',
    ),
    "the event-log flaky reconstruction": (
        r"\bWINDOW_DAYS\b|select\(\s*TaskCheckRun\.id,\s*TaskCheckRun\.task_id"
        r"|for check, tests, _how in flakes_in\(",
        ("flaky_tests.py",),
        "    for check, tests, _how in flakes_in(results):",
    ),
}


def _modules(only: Tuple[str, ...]) -> List[Path]:
    paths = [p for p in HUB.rglob("*.py") if "migrations" not in p.parts]
    return [p for p in paths if not only or p.name in only]


def _found(pattern: str, only: Tuple[str, ...]) -> List[str]:
    hits = []
    compiled = re.compile(pattern)
    for path in _modules(only):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if compiled.search(line):
                hits.append(f"{path.relative_to(HUB.parent).as_posix()}:{number}: {line.strip()}")
    return hits


@pytest.mark.parametrize("name", sorted(RETIRED))
def test_the_retired_rule_is_not_back(name):
    pattern, only, _ = RETIRED[name]
    assert _modules(only), f"no Hub module to read for {name}"
    hits = _found(pattern, only)
    assert hits == [], f"{name} is back:\n" + "\n".join(hits)


@pytest.mark.parametrize("name", sorted(RETIRED))
def test_each_pattern_catches_the_code_it_retired(name):
    pattern, _, before = RETIRED[name]
    assert any(
        re.search(pattern, line) for line in before.splitlines()
    ), f"the pattern for {name} no longer matches the code it was written to catch"


def test_the_gates_still_ask_the_list():
    """The other half: the completion and landing gates call the list's judgement, so the rules
    above cannot be dropped with nothing in their place."""
    checks = (HUB / "project_checks.py").read_text(encoding="utf-8")
    landing = (HUB / "landing_queue.py").read_text(encoding="utf-8")
    assert "known_failing.judge(" in checks
    assert "known_failing.judge(" in landing
