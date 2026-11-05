"""Acceptance drive: does the steady set stay steady on a busy machine?

Spec: hub-tests-pass-on-a-busy-machine-and-the-migration-tests-take-less-time (FR-1/2/3).

Runs every test in scripts/checks/steady_tests.txt --repeat times (one pytest process per
repetition), optionally with every logical CPU kept busy (--load) and optionally with a 250 ms
blocking call placed on the event loop (--inject-freeze), and prints each test's pass count.

    py -3.11 scripts/drive/d1105_steady_under_load.py --repeat 10 --load        # FR-2, under load
    py -3.11 scripts/drive/d1105_steady_under_load.py --repeat 10               # FR-2, idle
    py -3.11 scripts/drive/d1105_steady_under_load.py --repeat 10 --inject-freeze [--load]   # FR-3

Exit code 0 only when every selected test passed every repetition (normal mode), or failed every
repetition (--inject-freeze mode, restricted to the never-freezes tests that run a LagProbe).
--inject-freeze puts a 250 ms time.sleep on the loop as soon as every LagProbe window opens, which is
a real freeze in the path the test guards; it runs the never-freezes tests (`_FREEZE_GUARDS`) only.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIST = ROOT / "scripts" / "checks" / "steady_tests.txt"
HUB = ROOT / "hub"
FREEZE_SECONDS = 0.25
#: The never-freezes tests (FR-3): each guards a Hub path against holding the event loop, and judges
#: it inside a LagProbe window, so --inject-freeze puts its 250 ms hold in exactly that path. The rest
#: of the family is in the steady set but guards something a loop hold does not move, so a freeze
#: injected there proves nothing either way:
#:   test_loop_lag_probe.py (25)  tests of the probe itself; each places a real hold and asserts how
#:                                the probe reads it, which is FR-3's proof for the probe
#:   test_turn_starts_...:: test_a_turn_starts_git_is_not_queued_behind_streaming_runs  which pool
#:                                git runs on (its default executor is full, so no probe can start)
#:   test_turn_starts_...:: test_serialized_git_never_overlaps_even_when_its_caller_is_cancelled
#:                                that two gits never overlap; no Hub path, no loop
#:   test_main_watch_...:: test_a_stretch_longer_than_the_list_says_how_many_more  a pure function
#:   test_spec_lists_reuse_parsed_documents.py (3)  counts of reads and resolutions
#:   test_streamed_lines_are_recorded_in_batches.py (3)  stored lines, a statement count, a latency
_FREEZE_GUARDS = (
    "hub/tests/test_approvals_and_evidence_never_freeze_the_hub.py::test_approving_releases_and_merges_without_stalling_the_loop",
    "hub/tests/test_approvals_and_evidence_never_freeze_the_hub.py::test_recording_evidence_and_detecting_drift_never_stall_the_loop",
    "hub/tests/test_approvals_and_evidence_never_freeze_the_hub.py::test_a_run_ends_restamp_never_stalls_the_loop",
    "hub/tests/test_approvals_and_evidence_never_freeze_the_hub.py::test_staffing_a_review_never_stalls_the_loop",
    "hub/tests/test_approvals_and_evidence_never_freeze_the_hub.py::test_briefing_the_mender_never_stalls_the_loop",
    "hub/tests/test_approvals_and_evidence_never_freeze_the_hub.py::test_refreshing_reachability_answers_as_before_from_one_hop",
    "hub/tests/test_a_slow_share_does_not_freeze_the_hub.py::test_a_slow_folder_listing_does_not_block_other_requests",
    "hub/tests/test_a_slow_share_does_not_freeze_the_hub.py::test_a_slow_project_open_does_not_block_other_requests",
    "hub/tests/test_a_slow_share_does_not_freeze_the_hub.py::test_a_slow_project_create_does_not_block_other_requests",
    "hub/tests/test_a_slow_share_does_not_freeze_the_hub.py::test_a_slow_project_relocate_does_not_block_other_requests",
    "hub/tests/test_main_watch_does_not_freeze_the_hub.py::test_a_stalled_resolve_does_not_block_the_loop_during_a_watch_pass",
    "hub/tests/test_approval_holds_no_write_lock_across_git.py::test_approving_holds_no_write_lock_while_it_merges_and_releases",
    "hub/tests/test_approval_holds_no_write_lock_across_git.py::test_retrying_an_integration_holds_no_write_lock_while_it_merges",
    "hub/tests/test_approval_holds_no_write_lock_across_git.py::test_releasing_a_rejected_tasks_checkout_holds_no_write_lock",
    "hub/tests/test_approval_holds_no_write_lock_across_git.py::test_landing_a_batch_holds_no_write_lock_while_git_or_a_check_runs",
    "hub/tests/test_turn_starts_never_freeze_the_hub.py::test_a_turn_start_that_creates_its_checkout_never_stalls_the_loop",
)


# --- pytest plugin, loaded into each pytest process with -p when --inject-freeze is set -------------
def pytest_configure(config):  # noqa: ANN001, ANN201
    if not os.environ.get("D1105_INJECT_FREEZE"):
        return
    import asyncio
    import time as _time

    from tests import _loop_lag

    real_enter = _loop_lag.LagProbe.__aenter__

    async def _enter(self):  # noqa: ANN001, ANN202
        result = await real_enter(self)
        # The next thing the loop runs once the window is open, so it always lands inside it,
        # however short the guarded path is.
        asyncio.get_running_loop().call_soon(_time.sleep, FREEZE_SECONDS)
        return result

    _loop_lag.LagProbe.__aenter__ = _enter


def _load_worker(stop) -> None:  # noqa: ANN001
    while not stop.is_set():
        sum(i * i for i in range(20000))


def read_list() -> "list[tuple[str, str]]":
    rows = []
    for line in LIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            test_id, _, source = line.partition("|")
            rows.append((test_id.strip(), source.strip()))
    return rows


def _node_key(classname: str, name: str) -> str:
    """JUnit gives classname 'tests.test_x' or 'tests.test_x.TestC'; rebuild an id comparable to the list."""
    parts = classname.split(".")
    module = next(i for i, p in enumerate(parts) if p.startswith("test_") or p.startswith("_"))
    file = "hub/" + "/".join(parts[: module + 1]) + ".py"
    klass = "::".join(parts[module + 1 :])
    return file + "::" + (klass + "::" if klass else "") + name


def run_once(ids: "list[str]", inject: bool) -> "tuple[dict[str, bool], dict[str, str]]":
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "result.xml"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).parent) + os.pathsep + env.get("PYTHONPATH", "")
        env.pop("CLAUDECODE", None)
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml_path}"]
        if inject:
            env["D1105_INJECT_FREEZE"] = "1"
            cmd += ["-p", Path(__file__).stem]
        cmd += [i[len("hub/") :] for i in ids]
        subprocess.run(cmd, cwd=HUB, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        verdict: "dict[str, bool]" = {}
        why: "dict[str, str]" = {}
        if xml_path.exists():
            for case in ET.parse(xml_path).getroot().iter("testcase"):
                key = _node_key(case.get("classname", ""), case.get("name", ""))
                bad = case.find("failure") is not None or case.find("error") is not None
                skipped = case.find("skipped") is not None
                verdict[key] = not bad and not skipped
                for tag in ("failure", "error", "skipped"):
                    found = case.find(tag)
                    if found is not None:
                        why[key] = f"{tag}: {(found.get('message') or '').splitlines()[0][:300]}"
        return verdict, why


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=10)
    ap.add_argument("--load", action="store_true", help="keep every logical CPU busy for the whole run")
    ap.add_argument("--inject-freeze", action="store_true", help="put a 250 ms blocking call on the loop")
    args = ap.parse_args()

    rows = read_list()
    ids = [t for t, _ in rows]
    if args.inject_freeze:
        missing = [t for t in _FREEZE_GUARDS if t not in ids]
        if missing:
            raise SystemExit(f"never-freezes tests not in the steady set: {missing}")
        ids = [t for t in ids if t in _FREEZE_GUARDS]
    passes: Counter = Counter()
    workers, stop = [], multiprocessing.Event()
    if args.load:
        for _ in range(os.cpu_count() or 1):
            p = multiprocessing.Process(target=_load_worker, args=(stop,), daemon=True)
            p.start()
            workers.append(p)
        print(f"load: {len(workers)} busy processes (one per logical CPU)")
    started = time.monotonic()
    try:
        for n in range(args.repeat):
            verdict, why = run_once(ids, args.inject_freeze)
            for i in ids:
                if verdict.get(i) is True:
                    passes[i] += 1
            print(f"repetition {n + 1}/{args.repeat}: {sum(1 for i in ids if verdict.get(i))}/{len(ids)} passed", flush=True)
            for i in ids:
                if verdict.get(i) is not True:
                    print(f"    not passed: {i}  ({why.get(i, 'no result')})", flush=True)
    finally:
        stop.set()
        for p in workers:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()

    want = 0 if args.inject_freeze else args.repeat
    bad = [i for i in ids if passes[i] != want]
    print(f"\n{'test':<150} passes")
    for i in ids:
        print(f"{i:<150} {passes[i]}/{args.repeat}{'' if passes[i] == want else '   <-- FAIL'}")
    mode = "inject-freeze (each must FAIL every time)" if args.inject_freeze else "steady (each must PASS every time)"
    print(f"\n{mode}, load={'on' if args.load else 'off'}: {len(bad)} of {len(ids)} tests off, {time.monotonic() - started:.0f}s")
    return 1 if bad else 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
