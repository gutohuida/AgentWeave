"""CI's Hub test shards run every Hub test file exactly once (`scripts/checks/ci_shard.py`).

A file dropped by the split would never run on CI and nothing would say so; a file in two shards
would run twice. The job in `ci.yml` and the script must also agree on the shard count, and the
job every shard reports to must keep the name `hub-test`, the check name a project's
"the PR's CI is the full check" waits for.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"

_spec = importlib.util.spec_from_file_location(
    "ci_shard", REPO_ROOT / "scripts" / "checks" / "ci_shard.py"
)
assert _spec is not None and _spec.loader is not None
ci_shard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci_shard)


def _ci_shard_count() -> int:
    text = CI.read_text(encoding="utf-8")
    match = re.search(r"shard:\s*\[([\d,\s]+)\]", text)
    assert match, "ci.yml names no shard matrix"
    shards = [int(s) for s in match.group(1).split(",")]
    assert shards == list(range(1, len(shards) + 1)), shards
    assert f"ci_shard.py ${{{{ matrix.shard }}}} {len(shards)}" in text
    return len(shards)


def test_every_hub_test_file_is_in_exactly_one_shard():
    files = ci_shard.test_files()
    assert len(files) > 100
    split = ci_shard.shards(files, _ci_shard_count())
    flat = [path for shard in split for path in shard]
    assert sorted(flat) == files
    assert len(flat) == len(set(flat))
    assert all(split)


def test_the_split_is_the_same_on_every_call():
    files = ci_shard.test_files()
    assert ci_shard.shards(files, 4) == ci_shard.shards(list(reversed(files)), 4)


def test_the_shards_report_to_one_job_named_hub_test():
    text = CI.read_text(encoding="utf-8")
    assert re.search(r"^  hub-test:\n", text, re.M)
    assert "needs: hub-test-shard" in text


def test_a_shard_outside_the_count_is_refused():
    assert ci_shard.main(["0", "4"]) == 2
    assert ci_shard.main(["5", "4"]) == 2
    assert ci_shard.main(["x", "4"]) == 2
