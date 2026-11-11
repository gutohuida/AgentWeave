# Build retrospective of A project says what it still needs

Document: spec/changes/a-project-says-what-it-still-needs/spec.json (spdoc-9714bb1e05be)
Made: 2026-11-11T15:56:01.289844+00:00

## Lessons

- An acceptance-drive task needs a check line for every criterion, including links that only exist once the feature renders. A check guarded by `if item:` is silently skipped on the pre-build code and leaves no baseline line. (cites: ev-271fc0ba95bb, ttr-7c67daef00cb)
- The acceptance-drive task text should state that approval requires one piece of evidence of kind drive_baseline, with one `check <key>: reached=... failed_at_assertion=...` line per check, recorded at the current commit. (cites: ttr-3f3bbd92e812, ttr-c84efb21cbe9)
- When a spec puts a UI action in one specific settings section (here, 'Show it again' only under Project), it should also say which section the 'nothing shown after resolving' assertion uses. (cites: ckpt-8350a861cb31, spreq-b9d871f6a6a8)
- In this project, every new Hub route needs a UI client in the same change because of the surface-ceiling ratchets. A Hub-only task that adds routes should own the matching hub/ui/src/api client functions. (cites: ckpt-2c448fe0c4a4)
- A new component that calls useProjects breaks every existing vitest file that renders its parent without a QueryClient. The UI task should list the tests that render those parents. (cites: chk-078b1a66c642, ttr-a8c800a91fbc)
- Acceptance criteria that need a missing folder (the folder item) or the operator's own Hub (FR-7) should say up front how they will be shown, because the drive cannot produce them. (cites: ev-4b367eeeb38f, ev-d0b3828b078f)

## What to improve

- [tooling] Tell the builder about the drive_baseline evidence rule in the acceptance-drive task brief. Also have record_evidence warn when an acceptance-drive task completes without a drive_baseline at the current commit. (cites: ttr-3f3bbd92e812, ttr-c84efb21cbe9)
- [tooling] Make submit_checkpoint_notes accept or coerce scalar fields, and raise or document record_evidence's 16-character limit on covers. (cites: run-1f5156cd84d4, ckpt-af513189cb11)
- [tooling] Before integrating, detect a dirty main checkout and send it to the operator once, instead of running repeated mender turns. (cites: stall-d7184365af08, run-188129640440)
- [code_and_checks] Make the hub-ui check retry vitest worker-start timeouts, as hub-tests already reruns flaky tests, so infrastructure timeouts do not send tasks back. (cites: chk-1a34ad540359, ttr-b893a24ffcd8)
- [code_and_checks] Wrap each section of setup_list_check.py so that one locator timeout does not end every later check. Add a way to drive the folder item. (cites: evr-ceeab57d5b3c, ev-4b367eeeb38f)
- [code_and_checks] Investigate the recurring flaky Hub tests: the frozen-merge redrain test, the submodule snapshot timeout, and the evidence restamp test. (cites: chk-6fd557e2ec44, chk-575219efe308, chk-1d07f49bd7c2)
- [specs] Name the exact settings section for each UI assertion, and give UI client functions for new routes to the Hub task. (cites: ckpt-8350a861cb31, ckpt-2c448fe0c4a4)
- [staffing_and_running] When a later task edits an approved acceptance-drive script, have someone other than that script's original reviewer review the edit. (cites: task-47224bd43f6a, run-145892bdde0b)
- [staffing_and_running] Reviewers should raise every coverage gap that blocks an acceptance drive as blocking in the first round. (cites: ttr-7c67daef00cb)
