# Build retrospective of The build card shows where check time went

Document: spec/changes/the-build-card-shows-where-check-time-went/spec.json (spdoc-2e8fa32cbf80)
Made: 2026-11-05T23:10:25.663281+00:00

## Lessons

- When an acceptance drive must detect a UI element that does not exist yet, the spec should name that element's accessible label or role. Otherwise the drive may match existing text and pass vacuously. (cites: ttr-7585938f01bf, run-a654b8f54107)
- A drive check meant to fail on master should be run on master and seen to fail before its evidence is recorded. (cites: ev-ce194bf14903, ev-1a2df6c386f6)
- On this project's Windows hosts, scratch-directory cleanup must handle read-only git object files and verify the directory is gone. rmtree with ignore_errors fails silently. (cites: ttr-80adc162e950, run-189d8d0342be)
- After any send-back, every requirement on the task must be re-recorded at the new commit, including those whose evidence was only held. Re-recording only one leads to another round. (cites: ttr-83b1268360fe, ttr-c6eeb64fcf3f)
- Live drives that use real Haiku turns can take anywhere from about 4 minutes to over 9 minutes, and can stall. The spec should state the expected duration so reviewers can budget a turn for it. (cites: run-efe66dc44d56, ev-3ee95febc00c, run-14baacf2b0fe)
- A nullable timestamp introduced by a migration can be NULL for two reasons: an old row, or a new row that never reached that point. The spec should say how each case is reported. (cites: ckpt-c8a10b83bca6, ev-da3dd1b985a3)
- Line-number pointers in task text go stale. Name functions instead, for example landing_queue._narrow and run_batch_checks. (cites: run-3a763fd29cc8)

## What to improve

- [tooling] When a send-back holds evidence, tell the builder in one place which requirements must be re-recorded. Alternatively, let held-but-accurate evidence carry forward when the reviewer confirms the diff does not touch it. This avoids evidence-only rounds. (cites: ttr-83b1268360fe, ttr-c6eeb64fcf3f)
- [tooling] Make record_evidence infer the spec document from the task, or say in its error what is missing, so the first call does not fail. (cites: run-fc82149c15c9, run-a654b8f54107, run-b59898636b64)
- [specs] For UI criteria checked by a drive written before the UI exists, specify the element's accessible name or role, such as an aria-label prefix of 'Checks', and the exact figure keys the route will emit. (cites: ttr-7585938f01bf, run-fc82149c15c9)
- [specs] Say how NULL values are reported for each case, such as pre-migration rows versus new rows that skip the step, and for historical data that predates a table, such as builds before task_landings. (cites: ckpt-c8a10b83bca6, task-37d4559887b7)
- [code_and_checks] Give drive scripts a shared Windows-safe cleanup helper that clears read-only bits, retries, and asserts the directory is gone. Register the scratch root for cleanup immediately after creating it. (cites: ttr-80adc162e950, ev-1bc435b283b4)
- [code_and_checks] Keep live drives within a reviewer turn. Bound the polling LIMIT well under the turn length and make cleanup run even when the drive is interrupted. (cites: ttr-2fe16435e4de, run-efe66dc44d56)
- [staffing_and_running] Start the product tasks alongside the acceptance-drive task rather than queuing them behind it, so drive review rounds do not hold up the code that the drive tests. (cites: task-232623a4f224, task-99ce893f5f59)
- [staffing_and_running] Ask builders to run any changed live drive before recording evidence. Evidence recorded without a re-run was rejected and cost a full review round. (cites: ev-1a2df6c386f6, evr-f6681162197b)
