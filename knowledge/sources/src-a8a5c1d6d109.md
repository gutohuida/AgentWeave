# Build retrospective of The PR's CI is the full check

Document: spec/changes/the-pr-s-ci-is-the-full-check/spec.json (spdoc-45c8f455b7cc)
Made: 2026-11-07T12:18:43.234359+00:00

## Lessons

- Fix setting names and response shapes in the spec, so the failing-first drive and the builders do not have to agree on them after the fact. (cites: ckpt-b68a6bf8d325)
- When a criterion needs behaviour that another task builds, put that behaviour in the same task as the criterion, or order the tasks so it already exists. (cites: ckpt-03a69573d447, ev-533368499124)
- Check that every precondition in a criterion can actually be reached under the spec's other rules. 'Starting from a ready PR' could not be reached under FR-8. (cites: ev-c221875c411d)
- Say what happens after CI has concluded, including re-runs on the same head, so the watch stopping is a decision the spec made rather than a gap. (cites: ckpt-332c68d0748e)
- Name which task runs the end-to-end acceptance drive once the feature exists. Otherwise each approval defers it and the requirements stay partial. (cites: evr-d9f22bc46f20, evr-ee6ed70afe12)
- A drive that re-completes a sent-back task must move it from revision_needed to in_progress first, and must check each transition's result. (cites: ttr-711b36b0cbd0)
- Convert UTC timestamps with calendar.timegm, not time.mktime minus time.timezone; the latter is an hour out under daylight saving time. (cites: evr-c076806cced2)
- Tasks that touch hub/ui must expect conflicts in the committed bundle at merge time. They should merge master and rebuild the bundle right before review. (cites: ttr-5f16fae8c8f0, ttr-5695addc5e6f)
- If a spec relaxes an existing guard, such as the gh api ban or the no-timer test, name that change in the spec instead of leaving it to the builder. (cites: ckpt-806eacc24a7a, ckpt-03a69573d447)

## What to improve

- [tooling] Stop committed UI bundle assets from causing merge send-backs. Either rebuild the bundle at landing time, or regenerate it automatically when two branches conflict only in hub/hub/static/ui. (cites: ttr-5f16fae8c8f0, ttr-5695addc5e6f)
- [code_and_checks] Make the hub-tests suite robust to SQLite lock contention under parallel runs, so the gate does not need a serial re-run. (cites: chk-a7535e225b08)
- [code_and_checks] Page through check runs in commit_checks, and decide whether a concluded head should be re-read after a re-run. (cites: evr-95144919471d, ckpt-332c68d0748e)
- [specs] Write field names, response shapes and the task that runs the full acceptance drive into the spec. Assign each criterion to the task that builds the behaviour it needs. (cites: ckpt-b68a6bf8d325, ckpt-03a69573d447, evr-d9f22bc46f20)
- [staffing_and_running] Give the real-GitHub drive its own port and a time slot within the build, so reviewers can run it instead of deferring it. (cites: evr-ee6ed70afe12, run-fe26ace2c171)
- [staffing_and_running] Start tasks that depend only on settled shapes, such as the UI, in parallel with later backend tasks, to cut time spent waiting to start. (cites: ttr-c480f92373e3, task-d9145f71a6f2)
- [tooling] Let record_evidence take an FR number unambiguously within the build's own document, and align submit_checkpoint_notes's parameters with what agents expect. (cites: run-faa86dbce155)
- [tooling] Keep agents' Python file writes on Windows from introducing CRLF, for example with a .gitattributes rule or a check that fails on CRLF. (cites: ckpt-806eacc24a7a)
