# Build retrospective of Settings rows that hold any value

Document: spec/changes/settings-rows-that-hold-any-value/spec.json (spdoc-3feba735dc6a)
Made: 2026-11-10T15:55:31.292041+00:00

## Lessons

- A layout check that measures only widths and overflow will pass height regressions and misaligned wrapped controls, so specs for layout work should state which geometry the check asserts: alignment, spanning and vertical size. (cites: ttr-2428b54fff26, ttr-250e232324c2, spev-236fce1917c9)
- Every acceptance criterion needs seed data that actually renders the case, including runner errors and worktrees; otherwise the check passes without measuring anything. (cites: task-a6a0eb600734, ckpt-3bb68d76c641, ev-7a73caddf89b)
- A sweep-clean criterion should be owned by the task that finishes the sweep, not attached to every task that touches part of it. (cites: ev-acf954102f0e, evr-8f19c554edba)
- Every visible overflow source, such as the settings-nav header with a long project name, should be named in a specific task's scope. (cites: ckpt-3bb68d76c641, run-2a91f66a0c9d)
- CSS container-query or breakpoint fixes in this codebase must be measured in a browser before completion, because rule source order and computed thresholds both went wrong here. (cites: ckpt-1500ee468921, task-270097ca3eea)
- Any task that changes hub/ui/src also rebuilds the committed hashed bundle, which conflicts on merge, so plan on a rebuild after merging master rather than a hand merge. (cites: chk-3648e7493f14, ckpt-4fc532f9af33)
- Readiness waits in the sweep must target an element that exists only after data loads; a label that also appears on the loading row lets the measure run too early. (cites: ckpt-f74681ddb39d, evr-efd1a23c17f4)

## What to improve

- [code_and_checks] Extend long_values_check.py to assert that a wrapped settings-row control spans the row and starts at the text's edge, and that label blocks are not taller than their content. These are the regressions that slipped past it. (cites: ev-22d5bf704f8a, ttr-2428b54fff26, spev-236fce1917c9)
- [code_and_checks] Add data-loaded readiness selectors for every swept section, not only Agent:workspace, so no section can pass before its data renders. (cites: ckpt-f74681ddb39d, task-6841ab59110d)
- [code_and_checks] Stabilise or quarantine test_a_slow_project_open_does_not_block_other_requests, which failed first-run in several landing batches. (cites: chk-72ea912b0882, chk-afca5c049948, chk-f2a897b70241)
- [specs] Give each sweep-wide criterion (ac-sweep-clean / FR-1) a single owning task. Name every known overflow source, including the settings-nav header, in some task's scope. (cites: ev-acf954102f0e, ckpt-3bb68d76c641, spreq-41fb61253103)
- [specs] When a spec introduces a check, list the seed states each criterion needs (refused or missing runner CLI, worktrees, long generated-files command) as part of the check task's acceptance. (cites: task-a6a0eb600734, ev-7a73caddf89b, ev-755e6f618e92)
- [staffing_and_running] Require builders of CSS or layout tasks to measure the changed geometry in a browser, using the check's harness, before completing, rather than asking the reviewer to do it. (cites: run-8a370d38397a, run-030d61f4c97d, ckpt-1500ee468921)
- [staffing_and_running] Reviewers should finish all measurements, including re-checking every item from earlier send-backs, before approving, since approval cannot be reversed. (cites: run-8a0de071a1b6, ev-5d400316d906)
- [staffing_and_running] Add a second reviewer, or start dependent tasks like SRTHA-3 sooner, to cut the long waiting-to-start and waiting-for-review time. (cites: task-f6bcebf6815b, ttr-7733d7826a5a)
- [tooling] Let a reviewer pull back its own approval before the task lands, instead of forcing a spec amendment. (cites: run-8a0de071a1b6, spev-236fce1917c9)
- [tooling] Regenerate the UI bundle at merge or landing time, or have the Hub resolve conflicts that touch only generated assets by rebuilding, so hashed bundle files stop causing merge-needed bounces. (cites: chk-3648e7493f14, chk-3da9498455b7, evr-53a9f5844a05)
- [tooling] Make submit_checkpoint_notes accept the format agents first send, or document its schema. Stamp evidence with the post-commit sha rather than a provisional one. (cites: run-575ebbe554c9, run-e95fd557d48c, run-030d61f4c97d)
- [tooling] Allow a reviewer's own real-browser drive to upgrade partial evidence to full without a round trip through the builder. (cites: run-eefde3879007, ev-9057b1fb8262)
