# Build retrospective of A check can run only the tests for what a task changed

Document: spec/changes/a-check-can-run-only-the-tests-for-what-a-task-changed/spec.json (spdoc-4e7567892d10)
Made: 2026-11-06T22:44:30.909925+00:00

## Lessons

- An acceptance drive written before its feature exists must still be executed, with the unbuilt settings stripped out, so that every step after the expected failure reaches its assertion. Otherwise defects in the drive itself go unnoticed. (cites: ttr-75216fe0445f, run-cad6d82b8057)
- Testbed files a drive writes must not use names that shadow Python's standard library (select, socket, email and so on), because `python -m pytest` puts the project directory on sys.path. (cites: evr-6665f0cbc76e)
- When a fix lands on a new commit, every requirement whose evidence was rejected must be re-recorded at that commit, not only the one the fix touches. (cites: ttr-f0e4e26d130d)
- Specs should name new setting fields, result fields and the API transitions a drive relies on (for example, a task goes through under_review before approved), so that drives do not have to guess. (cites: ev-0b3d3a5f5ad4, ev-3608c2eac2ea)
- Acceptance drives for Hub features should run against a scratch Hub started from the checkout on its own port with a throwaway database, not against the Hub orchestrating the build. (cites: ckpt-d391252b5aed, evr-3d2e54556058)

## What to improve

- [code_and_checks] Before this spec's sizing applied, the hub-tests gate ran the full suite even on a script-only task. Once the CCROT-4 setting lands, confirm that pre-review gates actually size hub-tests, and consider path filters for checks unrelated to the change. (cites: chk-fc5ae31c9ba3, ev-d5bd3b650fdd)
- [specs] Name new settings fields, result fields and the required status path for drives (completed → under_review → approved) in the spec's design section. (cites: ev-0b3d3a5f5ad4, ev-207b84ef8c8d, ev-3608c2eac2ea)
- [specs] State in the spec which Hub acceptance drives should target: a scratch Hub on its own port, not :8010. (cites: run-f04ba0ed6efd, run-f4a55b148bda)
- [staffing_and_running] Do not approve a drive task while its later steps are unverified. Either schedule its final review after the feature task, or require the stripped-field run as evidence. (cites: ttr-b7e80d6f8396, ev-3608c2eac2ea)
- [tooling] When a task goes back for evidence, the Hub could list the requirements whose only evidence is rejected or recorded at a stale commit, so the author re-records all of them at once. (cites: ttr-f0e4e26d130d, run-228c10af75ab)
- [tooling] submit_checkpoint_notes should return a clear argument error or schema hint. Long drive commands need a background-run pattern so they do not hit the 10-minute tool limit. (cites: run-228c10af75ab, run-f4a55b148bda)
