# Build retrospective of The Build dialog, redesigned

Document: spec/changes/the-build-dialog-redesigned/spec.json (spdoc-65c2edc8896a)
Made: 2026-11-04T01:25:40.993537+00:00

## Lessons

- When a spec builds from an approved mock, it should name the commit and branch that hold the mock, list every file the mock needs including CSS, and say that the builder's branch must contain them. (cites: run-a5a3b84359cc, ev-589aeaf5ed20)
- Before approving a mock as the source of truth, check it against the spec's criteria. In this build the mock still emitted checkers at Fast, against FR-7. (cites: ev-8576fdde3f59, spreq-d405fd8e013e)
- On this machine the full hub-tests suite can take more than an hour when another task's checks run at the same time. Plan for the check gate, not the building, to be the long pole. (cites: chk-e00281f3f705, run-4882da39867c)
- Evidence calls must name the document, or record_evidence is refused. (cites: run-a5a3b84359cc)

## What to improve

- [tooling] Make the no_progress stall detector aware of in-flight check runs, so that it neither fires nor sends menders while the gate is running. (cites: stall-1c1281267c8f, stall-f2ff27828b0f, chk-e00281f3f705)
- [tooling] Make the mender's task lookup by loop reliable, so that list_tasks returns the loop's task. Two menders reported this task as missing. (cites: run-a8df0418eedb, run-ed32fa5a8aaf, run-f58cb8919747)
- [staffing_and_running] Serialize full hub-tests runs, or cap their xdist workers, when several tasks reach the check gate together. The first attempt here crashed with workers going down under contention. (cites: chk-e00281f3f705, run-4882da39867c)
- [specs] In mock-based specs, cite the mock commit together with its full file list, so that builders do not have to hunt across branches. (cites: run-a5a3b84359cc)
- [tooling] Close QA runs with their status, model and cost once the approval transition is recorded. (cites: run-df2d93e14e9a)
- [staffing_and_running] Enable symlink creation (Developer Mode) for the Hub account, so that worker checkouts get the shared dependency directories. (cites: run-a8df0418eedb)
