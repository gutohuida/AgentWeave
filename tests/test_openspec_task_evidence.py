"""A ticked full-suite task carries its own count (F392).

`a-loop-staffs-the-agent-it-names` ticked its "full suite green" task with the count deferred to
the window log: *"result recorded there rather than here to avoid a stale placeholder"*. The
process died before writing that log, so the tick rested on a number nobody recorded, and
the suite it claimed was green had three red tests in a sibling change's guard file. A measurement
recorded nowhere reads the same as one that passed. So the count goes on the task line itself.

The run has to be the full suite, not a list of files the change names, and that is the other half
of F392. A change cannot enumerate its sibling changes' guard files, or the tests parametrised over
source files it adds (`test_no_console_flash.py` gained a case from a new migration that no
artifact of its change mentions). Only the full suite reaches them. `openspec/config.yaml`
`rules.tasks` states both halves to whoever writes the tasks; this file is what enforces the first.

In-flight changes only. The archive holds dozens of ticks without counts, written before this
rule existed, and rewriting history would not make any of them more true.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGES = REPO_ROOT / "openspec" / "changes"

# Indented subtasks are tasks, `*` is a list marker, and `[X]` is ticked.
TASK = re.compile(r"^[ \t]*[-*] \[[xX ]\] ", re.M)
TICKED = re.compile(r"^[ \t]*[-*] \[[xX]\] ")
PYTEST = re.compile(r"\bpytest\b")
# The argument that makes a pytest run a whole suite: a test *directory*, however it is spelled.
SUITE_PATH = re.compile(r"(?<![\w./\\-])(?:\./)?(?:hub[/\\])?tests[/\\]?(?=[\s`]|$)")
# A run narrowed to some tests is not the suite, whatever directory it names.
NARROWED = re.compile(r"(?:^|\s)-k(?:\s|=)|::")
SUITE_IN_WORDS = re.compile(
    r"(?<!no )(?<!not )\b(?:full|whole|entire)[- ](?:test[- ])?suite\b", re.I
)
COUNT = re.compile(r"\b\d[\d,]*\s+passed\b")
# A count of failures that is not zero, so "0 failed" still reads as evidence.
FAILURES = re.compile(r"\b[1-9][\d,]*\s+(?:failed|error|errors)\b")
# A number carried over from before the change is not this run's result.
BASELINE = re.compile(r"\b(?:baseline|before this change|at this change's start)\b", re.I)


def _task_blocks(text: str) -> list[tuple[int, str]]:
    """`(line, text)` of each task: its checkbox line plus its own continuation lines."""
    starts = [m.start() for m in TASK.finditer(text)]
    blocks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = re.split(r"\n\s*\n|\n#", text[start:end])[0]
        blocks.append((text.count("\n", 0, start) + 1, block))
    return blocks


def _runs_a_whole_suite(block: str) -> bool:
    """Does this task run the suite? Read each `pytest` command, not the block as one string.

    A flag with a value (`pytest -n 8 hub/tests/`) defeats a single regex that tries to skip
    flags, and a `-k` selection defeats one that only looks for the directory.
    """
    for match in PYTEST.finditer(block):
        command = re.split(r"[`\n]", block[match.start() :])[0]
        if NARROWED.search(command):
            continue
        if SUITE_PATH.search(command):
            return True
    return bool(SUITE_IN_WORDS.search(block))


def _carries_its_result(block: str) -> bool:
    """A count of the suite run itself, not a number quoted from somewhere else.

    A count belongs to the last `pytest` command written before it, so the 12 passed of a
    one-file run does not stand in for the suite's own count. A count with no command before it
    belongs to the task ("Full suite green -- 4474 passed").
    """
    for match in COUNT.finditer(block):
        before = block[: match.start()]
        if BASELINE.search(before[-60:]):
            continue
        commands = list(PYTEST.finditer(before))
        if commands:
            nearest = re.split(r"[`\n]", block[commands[-1].start() :])[0]
            if NARROWED.search(nearest) or not SUITE_PATH.search(nearest):
                continue
        return not FAILURES.search(block)
    return False


def uncounted_suite_ticks(text: str) -> list[tuple[int, str]]:
    return [
        (line, block)
        for line, block in _task_blocks(text)
        if TICKED.match(block) and _runs_a_whole_suite(block) and not _carries_its_result(block)
    ]


def test_every_ticked_full_suite_task_in_flight_carries_its_count() -> None:
    if not CHANGES.is_dir():
        pytest.skip("openspec/changes is absent; nothing in flight to check")
    offenders = []
    for tasks in sorted(CHANGES.glob("*/tasks.md")):
        for line, block in uncounted_suite_ticks(tasks.read_text(encoding="utf-8")):
            first = block.splitlines()[0]
            offenders.append(f"{tasks.relative_to(REPO_ROOT).as_posix()}:{line}  {first}")
    assert not offenders, (
        "A ticked full-suite task must carry its result on the task itself, e.g. "
        "'4474 passed, 86 skipped at 8508377'. 'See the log' is how F392 ticked a run "
        "nobody recorded. Write the count, or untick the task:\n  " + "\n  ".join(offenders)
    )


def test_the_check_reads_what_f392_ticked() -> None:
    """The detector itself, on the tick that F392 was found through and on its repair."""
    f392 = (
        "- [x] 6.2 `pytest hub/tests/ -q` -- full suite green -- see log entry for the exact count\n"
        "      and duration (result recorded there rather than here).\n"
    )
    counted = "- [x] 6.2-REDO `py -3.11 -m pytest hub/tests/ -q` -- **4474 passed, 86 skipped**.\n"
    one_file = "- [x] 3.4 `pytest hub/tests/test_loop_busy_guard.py -q` passes.\n"
    open_task = "- [ ] 6.2 `pytest hub/tests/ -q` -- full suite green.\n"
    assert [line for line, _ in uncounted_suite_ticks(f392)] == [1]
    assert uncounted_suite_ticks(counted) == []
    assert uncounted_suite_ticks(one_file) == []
    assert uncounted_suite_ticks(open_task) == []


# Each of these is a full-suite tick carrying no result of its own, written the way this
# corpus writes them. Every one was missed by the first version of this check.
UNCOUNTED = [
    "- [x] 7.1 `pytest -n 8 hub/tests/` green.\n",
    "- [x] 7.1 `pytest -p no:cacheprovider --timeout 60 tests/` green.\n",
    "- [x] 7.1 `py -3.11 -m pytest hub/tests -q` passes.\n",
    "- [x] 7.1 `pytest ./hub/tests/ -q` passes.\n",
    "- [X] 7.1 `pytest hub/tests/ -q` passes.\n",
    "* [x] 7.1 `pytest hub/tests/ -q` passes.\n",
    "  - [x] 7.1.2 `pytest hub/tests/ -q` passes.\n",
    "- [x] 7.1 Full test suite green.\n",
    "- [x] 7.1 The whole suite passes.\n",
    "- [x] 7.1 `pytest hub/tests/ -q` -- green (baseline before this change: 4400 passed).\n",
    "- [x] 7.1 `pytest hub/tests/ -q` -- 4470 passed, 3 failed (pre-existing).\n",
    "- [x] 7.1 `pytest hub/tests/ -q` green.\n  `pytest hub/tests/test_x.py` -- 12 passed.\n",
]

# And these must not be flagged.
CLEAN = [
    "- [x] 7.1 `pytest hub/tests/test_x.py` (no full suite needed).\n",
    "- [x] 7.1 `pytest hub/tests/ -k busy` -- 4 passed.\n",
    "- [x] 7.1 `pytest hub/tests/ -q` -- **4474 passed, 86 skipped, 0 failed** at 8508377.\n",
    "- [x] 7.1 `pytest hub/tests/ -q`\n      -- **4474 passed, 86 skipped** at 8508377.\n",
    "- [x] 7.1 `cd hub && pytest tests/ -q` -- 4474 passed, 86 skipped.\n",
    "- [ ] 7.1 `pytest hub/tests/ -q` -- full suite green.\n",
]

# Deliberately flagged, though no run happened: a ticked task that writes the suite command
# reads as a claim that it ran it. The check cannot tell that apart from a run, and a loud
# false positive is cheap -- reword the prose, or write the count.
PROSE_MENTION = "- [x] 7.1 See `pytest tests/` conventions in CONTRIBUTING before ticking 7.2.\n"


def test_the_check_reads_the_phrasings_this_corpus_uses() -> None:
    for text in UNCOUNTED:
        assert uncounted_suite_ticks(text), f"not flagged: {text!r}"
    for text in CLEAN:
        assert not uncounted_suite_ticks(text), f"wrongly flagged: {text!r}"
    assert uncounted_suite_ticks(PROSE_MENTION)


def test_a_ticked_subtask_under_an_unticked_parent_is_still_checked() -> None:
    """The parent's own `- [ ]` must not shelter a ticked child (the first version folded them)."""
    text = (
        "- [ ] 7. Regression\n"
        "  - [x] 7.1 `pytest hub/tests/ -q` -- full suite green, count in the log.\n"
    )
    assert [line for line, _ in uncounted_suite_ticks(text)] == [2]
