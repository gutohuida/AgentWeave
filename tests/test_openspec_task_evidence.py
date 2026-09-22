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

TASK = re.compile(r"^- \[(?:x| )\] ", re.M)
# A suite run is a pytest over a test *directory* (`hub/tests/`, `tests/`), not a file or node id,
# or a task that names the full suite in words.
SUITE_RUN = re.compile(
    r"pytest\s+(?:-\S+\s+)*(?:hub/)?tests/?(?=[\s`]|$)|\bfull[- ]suite\b", re.IGNORECASE
)
COUNT = re.compile(r"\b\d[\d,]*\s+passed\b")


def _task_blocks(text: str) -> list[tuple[int, str]]:
    """`(line, text)` of each task: its checkbox line plus its indented continuation."""
    starts = [m.start() for m in TASK.finditer(text)]
    blocks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = re.split(r"\n\s*\n|\n#", text[start:end])[0]
        blocks.append((text.count("\n", 0, start) + 1, block))
    return blocks


def uncounted_suite_ticks(text: str) -> list[tuple[int, str]]:
    return [
        (line, block)
        for line, block in _task_blocks(text)
        if block.startswith("- [x]") and SUITE_RUN.search(block) and not COUNT.search(block)
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
