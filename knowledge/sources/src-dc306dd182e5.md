# Build retrospective of Every checkpoint, findable and readable

Document: spec/changes/every-checkpoint-findable-and-readable/spec.json (spdoc-1fe353346b56)
Made: 2026-11-05T00:07:52.854192+00:00

## Lessons

- Any new /api/v1 route must have a client in hub/ui/src in the same task, because a ratchet caps clientless routes. Keep a route and its UI hook together, or have the routes task add the hook. (cites: chk-4aa03e8a3b09, run-5f769f17d999)
- Every new UI query call site must bind its error and use it, for example with QueryErrorNotice. A ratchet caps the number of query sites that ignore their errors. (cites: chk-03bdfd3cae31, run-411589da7bad)
- An acceptance drive written before the UI exists should be written against selectors and URLs the spec names. Otherwise the view task ends up rewriting the drive it is judged by. (cites: ev-a146a6bdfb1d, run-8f607dc2fb65)
- A spec that adds unattended model calls, such as a startup backfill, should state which runner and model pay for them and what to do when no runner is configured. (cites: run-70c227d9e4e4, ckpt-10c6064f1ad8)
- After a check-gate send-back, every requirement's evidence is held. The fix must re-record all of it at the new commit, not just the fixed part. (cites: ttr-955c5421245c, ttr-9234b98e6416)

## What to improve

- [code_and_checks] Fix test_checks_give_way, which fails on main, and stabilise the flaky scheduler, pty_runner and mcp_announce tests. Between them they failed most check runs in this build. (cites: chk-ea3fc5226146, chk-e24d2398fe46, chk-c5d4603e953b, chk-0e44d3828f94)
- [code_and_checks] Fix the d1104 drive's misleading PASS message on the tab step. Change its row selector so it counts rows rather than child elements. (cites: run-92da9b9055fb, evr-d60ea92a70f2)
- [specs] Put a route and its UI client in one task, or require the routes task to add hooks. Name the selectors and URLs the acceptance drive will use. (cites: ttr-61c6743f454f, ev-a146a6bdfb1d)
- [specs] For backfills, state the cost model, which runner pays, and the retry bound for unreachable workers. (cites: run-70c227d9e4e4, ckpt-10c6064f1ad8)
- [staffing_and_running] Builders should run test_surface_ceilings.py, which is quick, before marking UI or route work completed. Both check-gate send-backs came from that file. (cites: chk-4aa03e8a3b09, chk-03bdfd3cae31)
- [tooling] When a check-gate fix leaves a requirement's code unchanged, carry its held evidence forward or prompt the author to re-record all of it. This would avoid the evidence-only round trips. (cites: ttr-9234b98e6416, ttr-955c5421245c)
- [tooling] Avoid re-running the full hub suite on a tree already checked, and after a task is approved. Default record_evidence to the task's spec document. (cites: chk-0e44d3828f94, chk-c5d4603e953b, run-b0caa39f7eec)
