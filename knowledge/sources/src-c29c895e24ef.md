# Build retrospective of A trace of a whole conversation

Document: spec/changes/a-trace-of-a-whole-conversation/spec.json (spdoc-9a013e86bc1b)
Made: 2026-11-07T21:22:38.496929+00:00

## Lessons

- Before writing the spec, check that every figure an acceptance criterion shows, such as tool errors in the totals, is already served by a Hub route. If it is not, plan the route change in the same spec. (cites: ev-4527e0075175, task-b8a22f7bb7e3)
- When a drive must fail before the UI exists, put the test-id contract and the DOM nesting in the spec, matched to the mock, so the drive and the view are written against the same structure. (cites: ttr-1ea255707d1d, ckpt-3af774496184)
- Make sure mocked components the build depends on are merged into the base branch, or name their commit in the spec. Do not rely on gitignored fixtures. (cites: run-99edf9951867)
- Write acceptance criteria at a scale a live drive can seed, or say which criteria are covered by unit tests rather than the end-to-end drive. (cites: run-1b08bcb23f41, ev-59a643e8db0c)
- Any change under hub/ui/src, even formatting only, needs scripts/refresh_ui_bundle.py and a fresh stamp committed together with the source. (cites: ttr-f83787d2ab6e, ev-d9d6f2f2fb22)
- After any send-back, record evidence again for every requirement at the new commit, not only for the pieces that were rejected. (cites: ttr-dc9779b1de21, ttr-075702f176f9)
- Build timestamp query strings with urlencode. Tz-aware ISO times contain '+', which an unencoded query string decodes as a space, and the route then answers 422. (cites: ttr-dc40b0f948cf)
- A new React Query call site must bind and use its error, or the surface-ceiling ratchet fails the sweep. (cites: chk-e38a131706b5)

## What to improve

- [code_and_checks] Run the bundle-matches-source stamp test in the gate whenever hub/ui/src changes, instead of skipping it unless AW_CHECK_UI_BUNDLE=1 is set. (cites: ttr-f83787d2ab6e, chk-017d2e8053e7)
- [code_and_checks] Look into the flaky hub-tests run (MemoryError copying the schema template, xdist workers crashing) and the projectSettingsPanel vitest timeout. Each forced a full re-run of its check. (cites: chk-264f2596bcc8, chk-75258ee7b561)
- [specs] State in the spec which Hub routes supply each displayed figure, plus the shared test-id contract and DOM nesting for drive-tested views, and the commit where any mock lives. (cites: task-b8a22f7bb7e3, ttr-1ea255707d1d, run-99edf9951867)
- [specs] Give requirements ids that are unique across documents, or scope them to the document, so evidence calls don't need the path. (cites: run-2838afbb0b54, run-c0444f8c8981)
- [staffing_and_running] Once the view exists, re-run a failing-first drive's unreached steps as part of the drive task's own acceptance, rather than approving it on a script read alone. (cites: ttr-bd52b1458332, run-99edf9951867)
- [tooling] When work comes back, carry held evidence forward automatically, or prompt the builder with the full list of requirements to re-record, to avoid evidence-only rounds. (cites: ttr-dc9779b1de21, ttr-075702f176f9)
- [tooling] Tag evidence recorded during a turn with the commit the turn produces, not the previous one. (cites: run-c23adf9eff05)
