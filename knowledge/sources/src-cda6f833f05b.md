# Build retrospective of Evidence review sends work back only for what is wrong with it

Document: spec/changes/evidence-review-sends-work-back-only-for-what-is-wrong-with-it/spec.json (spdoc-90c4b16a5d3e)
Made: 2026-11-11T03:00:00.678575+00:00

## Lessons

- An acceptance-drive check must not read a task's current status or notes after further flow firings, because a firing hands a sent-back task straight to its builder. Assert from task_transitions and from durable evidence-review reasons instead. (cites: ttr-f07b9ced4364, ev-4350252f6fe6)
- A drive's staged evidence must be something the scratch project actually reproduces. Otherwise a careful reviewer rejects it for its own reason, and the Hub path the drive targets never fires. (cites: ev-ae6076b9b184, ckpt-2ba924bcb1eb)
- The Hub hands out a completed task's review immediately. A drive that has to change the branch between completion and review must hold the reviewer first. (cites: run-4ffe32a1cfd1, ckpt-462b734d18c7)
- A reviewer's checkout sits at the evidence's commit, not at the branch tip. Any requirement that depends on the reviewer reproducing at the tip has to say how the reviewer learns where the tip is. (cites: run-787e8aeae6e2, ckpt-ddebc12c37d2)
- Starting a Hub from a branch that adds a migration, against the shared trial DB, would stamp that migration and stop master-code Hubs from starting. Drives for such branches need a fresh database on their own port. (cites: run-787e8aeae6e2, ev-37442b457e95)
- A requirement about a UI view should name the evidence that will count, for example a component render test or a screenshot. Otherwise the piece stays partial through several rounds. (cites: ev-5eaff26e800b, evr-cd9189b27326)
- A drive predicate that passes on master code has to be tightened until it fails at its own assertion. K2 passed vacuously at first because approving notes happened to mention both check names. (cites: ev-97f06996d72d, run-4ffe32a1cfd1)

## What to improve

- [tooling] A check verdict whose only failures are timeouts should not be reused for an identical tree on re-completion. The Hub should either re-run the check or let the operator request a re-run, so that agents do not need nudge commits. (cites: chk-6d4a0da3fe92, q-7be39c9d3c46, run-8877aecc5589)
- [code_and_checks] Reduce how sensitive hub-ui is to load. Options are raising the timeouts or limiting vitest workers. Also look at the recurring flaky git-timeout tests in hub-tests, which keep forcing serial retries. (cites: chk-6d4a0da3fe92, chk-1cca257fd058, chk-77e1d3d14b44)
- [code_and_checks] Stop committed hashed UI bundle assets from conflicting on every master move. For example, regenerate the bundle at land time or treat it as a build artefact. (cites: chk-f4bd3a770364, ckpt-a9803b553996)
- [code_and_checks] Change the d1110 drive so that the scratch project's drive_check.py really prints the staged baseline. The Hub's drive_baseline_checks_not_failing refusal can then fire in the live drive. (cites: ev-ae6076b9b184, ckpt-2ba924bcb1eb)
- [specs] In a drive-gated spec, say where the reviewer's checkout sits and what counts as a passing reproduction (the requirement, not the author's recorded output). For UI requirements, name the evidence that will count. (cites: run-787e8aeae6e2, ev-5eaff26e800b)
- [specs] State the gate boundaries in the spec itself: whether the operator is gated, whether already-built closes are exempt, and what happens when the document cannot be read. That way the builder does not have to decide them. (cites: ckpt-2ba924bcb1eb, evr-e25a04d264c3)
- [staffing_and_running] Give review turns enough budget, or a background mechanism, to re-run a 15–30 minute real-Haiku drive, so that drive claims are not verified only from the author's runs. (cites: run-6d5742712425, evr-dcbda4fdb27b)
- [tooling] Give drives a documented default of their own port plus a fresh DB, and record which Hub orchestrates the build. That way agents do not have to probe ports or risk migrating the shared trial DB. (cites: run-787e8aeae6e2, run-c3211e1684af)
