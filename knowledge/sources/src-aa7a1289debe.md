# Build retrospective of Hub tests pass on a busy machine, and the migration tests take less time

Document: spec/changes/hub-tests-pass-on-a-busy-machine-and-the-migration-tests-take-less-time/spec.json (spdoc-916d8283ab19)
Made: 2026-11-05T16:18:18.610578+00:00

## Lessons

- Before building on an acceptance drive's load, show that it makes master fail. On this machine, CPU spinners alone did not reproduce the Hub suite's flakes; competing pytest processes appear to be needed. (cites: q-c371f19b3127, ev-0c6809048863)
- A requirement for zero failures under load cannot sit beside a requirement to leave real-stall tests failing while Hub fixes are out of scope. Either exclude tests that have an open filed finding, or bring the fixes into scope. (cites: spev-1e758109bc27)
- Any claim that tests are steady under load must come from a loaded run on the changed tree, not from an idle run or from a baseline run before the change. (cites: ttr-7b5fefdd5e39, ev-76fc96cb0ff8)
- Never raise load generators above normal priority on the shared machine: HIGH-priority spinners starved every agent and the operator for about 15 minutes. (cites: ckpt-d748ffc8d80d)
- Adding a lag probe to an existing test can surface real Hub stalls on the request path, so plan for a filed finding whenever the probe's coverage widens. (cites: ev-76fc96cb0ff8, ev-b39d6b673df7)
- Timing requirements on this shared machine should be judged by running base and change at the same time and comparing the ratio, not by comparing absolute times. (cites: ev-c0e0d863cf34, evr-e4c9050473fb)
- Time dependencies hide in cache TTLs as well as in explicit elapsed-time asserts. A list of wall-clock sites should also cover TTLs that a slow first request can outlast. (cites: ev-3aabf16d10e5)

## What to improve

- [specs] Reconcile drive-passes-after with FR-6. Either exclude tests that have an open filed finding from the zero-failure count, or bring the off-loop wraps for F1131 and F1132 into scope. (cites: spev-1e758109bc27, spreq-236b1ca0d031)
- [specs] Define the drive's load to include competing pytest processes, and require drive-fails-today to be shown before any later task depends on the drive. (cites: q-c371f19b3127, ev-0c6809048863)
- [code_and_checks] Register the real_alembic_run marker in the pytest config. (cites: evr-e4c9050473fb)
- [code_and_checks] Keep the drive's longer failure messages, so a stall's stack is always captured and findings do not rest on elimination. (cites: ev-390a8648a8ae, ev-b39d6b673df7)
- [staffing_and_running] Do not run load experiments and timing-measurement tasks at the same time on one machine. Alternatively, give load drives a slot of their own. (cites: run-ea667f4cc14b, run-e474672d7fa9, ckpt-d748ffc8d80d)
- [tooling] On a loaded machine, check timeouts end without judging the work and block tasks. The 120 s limits should scale with machine load, or retry once the machine has settled. (cites: stall-51b7439729c0, chk-291c6e38cf9e, chk-710722746120)
- [tooling] Allocate FINDINGS.md numbers centrally so concurrent branches do not collide. (cites: ev-b39d6b673df7, ev-76fc96cb0ff8)
- [tooling] Add a way to run long drives in the background with polling, so agents do not hit the shell's 10-minute limit. (cites: ckpt-08b2d0a3270d)
