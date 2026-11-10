# Build retrospective of A build lands as one pull request

Document: spec/changes/a-build-lands-as-one-pull-request/spec.json (spdoc-79cf34c56bbe)
Made: 2026-11-07T00:53:29.126391+00:00

## Lessons

- An acceptance drive written before the feature must name the routes and fields it assumes. The spec should either fix those names for the implementing tasks or schedule a follow-up that re-points the drive once they ship. (cites: spev-b3d36add62d7, task-91aedddf9c2c)
- In a flow build, approval pushes only work backed by accepted evidence. Any drive that approves tasks by hand must record and accept evidence first. (cites: ttr-79d6e89e079a, ttr-db81a96a277d)
- On Windows a gh or claude stand-in must be a real .exe. It must also be probed by full path, because subprocess resolves bare names on the parent's PATH. (cites: ttr-79d6e89e079a, ttr-6fd20c70b462)
- Tasks in one PR build that edit the same file need a dependency or non-overlapping edits. Otherwise the second task conflicts on the build branch and is sent back as merge-needed. (cites: ckpt-effbedb2d7ab, run-8c9db64101ec)
- A 'never does X' check over CLI calls should match by operation, not by substring. Substring matching flags the allowed calls the feature needs, such as pr create --base and reading merge_commit_sha. (cites: ttr-6963b13d69ea, ev-76a034283582)
- New UI query call sites must bind and use their query's error, and existing App-mount mocks must gain any new hook. The surface-ceiling ratchet and the hub-ui check will refuse the work otherwise. (cites: chk-59a7a4a4ccb5, chk-0051fc325f87)
- When adding a case to the SSE event switch in useSSE.ts, check for fall-through between neighbouring cases and add a test for the invalidation that might be lost. (cites: ttr-b3e5a783795e, ev-1a0b0ff22861)
- Every requirement whose wording says where something shows (for example 'on the project') needs a task that names that surface. Otherwise it lands wherever is convenient. (cites: ttr-b3e5a783795e, spreq-8f37a32db087)

## What to improve

- [code_and_checks] Add a test that the SSE switch invalidates the expected queries for every event type. Fall-through regressions like the task_checks_finished one would then be caught by checks rather than by review. (cites: ttr-b3e5a783795e, ev-1a0b0ff22861)
- [code_and_checks] Fix or quarantine the flaky hub-tests that keep failing on first run. These are the git-timeout approval hold, the known-failing-list batch narrowing, the turn-start git queue, and the lifespan shutdown kill. (cites: chk-50c265eb9921, chk-4a8ba14b60ba, chk-2537e37ed87a)
- [code_and_checks] Handle the restart window between a successful push and recording pr_pushed_sha, for example by comparing the remote tip with the local build branch before treating a lease refusal as someone else's push. (cites: ckpt-effbedb2d7ab, run-bded42ffde0b)
- [specs] When a spec includes an acceptance drive written before the feature, also include a task that reconciles the drive with the shipped routes and runs it. That task should depend on the route-owning tasks. (cites: spev-b3d36add62d7, task-91aedddf9c2c)
- [specs] Give each requirement's criteria a single owning task. For example, sq-ac1/sq-ac2 belong to the push task, not split across settings and push. (cites: ev-5d3df410d7f3, ev-ec3eee2360bc)
- [specs] State explicitly in the spec which surfaces must show new state: the task read's pull_request field, and a project-wide 'main is behind GitHub' notice. (cites: run-e1a35e0731c8, ev-9aa38e321b06)
- [staffing_and_running] Give tasks added by amendment an explicit builder. Avoid queuing them on the same agent that owes a pending rework, so a merge-only fix does not wait behind a long drive run. (cites: task-91aedddf9c2c, ttr-2d50233eb9ad, ttr-90a8c9e808e6)
- [staffing_and_running] Provide a standard isolated drive environment, with a spare port and a copied DB, and a policy for cleaning up real GitHub PRs the drive opens. Reviewers should not have to improvise around the live :8010 Hub. (cites: run-1a6da503a477, run-8c9db64101ec)
- [tooling] Make submit_checkpoint_notes and record_evidence state their required arguments (intent, document) up front or default them. Runs repeatedly hit these rejections and sometimes left no checkpoint. (cites: run-de0c9674e0da, run-98067fe167b6, run-da7ed52381b8)
- [tooling] Brief reviewers with the current branch head rather than a stale commit, and require evidence to be recorded again at that head before review starts. (cites: run-65a9c25046c7, ttr-b3e5a783795e)
- [tooling] Regenerate the generated UI build stamp at merge time, or exclude it from conflict detection, so parallel branches do not cause merge-needed send-backs. (cites: ttr-2d50233eb9ad)
- [tooling] Record cost for failed runs and for every completed run. BLAOP-6's figures currently omit most of its spend. (cites: run-a63fa21a1256, run-8c9db64101ec)
