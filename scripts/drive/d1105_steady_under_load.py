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
--inject-freeze starts a 250 ms time.sleep on the loop 50 ms after every LagProbe window opens, which
is a real freeze in the path the test guards; tests that measure stalls another way (their own
probe) are reported as "not injectable" until the build gives them a hook.
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
#: Files whose tests open a LagProbe window; only these can have a freeze injected through it.
_PROBE_FILES = (
    "test_approvals_and_evidence_never_freeze_the_hub.py",
    "test_turn_starts_never_freeze_the_hub.py",
    "test_spec_lists_reuse_parsed_documents.py",
    "test_streamed_lines_are_recorded_in_batches.py",
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
        asyncio.get_running_loop().call_later(0.05, _time.sleep, FREEZE_SECONDS)
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


def run_once(ids: "list[str]", inject: bool) -> "dict[str, bool]":
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
        if xml_path.exists():
            for case in ET.parse(xml_path).getroot().iter("testcase"):
                key = _node_key(case.get("classname", ""), case.get("name", ""))
                bad = case.find("failure") is not None or case.find("error") is not None
                skipped = case.find("skipped") is not None
                verdict[key] = not bad and not skipped
        return verdict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=10)
    ap.add_argument("--load", action="store_true", help="keep every logical CPU busy for the whole run")
    ap.add_argument("--inject-freeze", action="store_true", help="put a 250 ms blocking call on the loop")
    args = ap.parse_args()

    rows = read_list()
    ids = [t for t, _ in rows]
    if args.inject_freeze:
        ids = [t for t in ids if Path(t.split("::")[0]).name in _PROBE_FILES]
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
            verdict = run_once(ids, args.inject_freeze)
            for i in ids:
                if verdict.get(i) is True:
                    passes[i] += 1
            print(f"repetition {n + 1}/{args.repeat}: {sum(1 for i in ids if verdict.get(i))}/{len(ids)} passed", flush=True)
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
