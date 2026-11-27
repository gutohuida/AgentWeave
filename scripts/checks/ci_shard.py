"""Print the Hub test files one CI shard runs, one per line, relative to `hub/`.

    py -3.11 scripts/checks/ci_shard.py SHARD COUNT

CI's `hub-test` was one job of about 15 minutes, and with "the PR's CI is the full check" on it is
the wait before a pull request is ready. The job is split into COUNT shards (SHARD counts from 1),
each running its share of the files with `-n auto`, so the wait is roughly one shard's.

A file is never split: `--dist loadgroup` keeps each file whole and in order on one worker, because
some files rely on an earlier test in the same file (F264), and the same holds across shards. Files
are dealt out by size, largest first, each to the shard holding the fewest bytes so far: size is the
proxy for run time, and the order is fixed, so every shard computes the same split and together
they run every file exactly once (`tests/test_ci_shard.py`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

HUB = Path(__file__).resolve().parents[2] / "hub"
TESTS = HUB / "tests"


def test_files(tests: Path = TESTS) -> List[Path]:
    """Every file pytest collects under *tests* by its default `python_files`."""
    found = set(tests.rglob("test_*.py")) | set(tests.rglob("*_test.py"))
    return sorted(found)


def shards(files: List[Path], count: int) -> List[List[Path]]:
    """*files* dealt into *count* shards by size, largest first, onto the lightest shard."""
    bins: List[List[Path]] = [[] for _ in range(count)]
    loads = [0] * count
    for path in sorted(files, key=lambda p: (-p.stat().st_size, p.as_posix())):
        lightest = loads.index(min(loads))
        bins[lightest].append(path)
        loads[lightest] += path.stat().st_size
    return [sorted(b) for b in bins]


def main(argv: List[str]) -> int:
    if len(argv) != 2 or not all(a.isdigit() for a in argv):
        print("usage: ci_shard.py SHARD COUNT", file=sys.stderr)
        return 2
    shard, count = int(argv[0]), int(argv[1])
    if not 1 <= shard <= count:
        print(f"shard {shard} is not between 1 and {count}", file=sys.stderr)
        return 2
    chosen = shards(test_files(), count)[shard - 1]
    if not chosen:
        print(f"shard {shard} of {count} has no files", file=sys.stderr)
        return 1
    for path in chosen:
        print(path.relative_to(HUB).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
