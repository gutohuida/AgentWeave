# Build retrospective of The spec header, redesigned

Document: spec/changes/the-spec-header-redesigned/spec.json (spdoc-407caf5abcdb)
Made: 2026-11-03T03:24:57.875853+00:00

## Lessons

- Name the data-testid or selector for every new UI element the acceptance drive must find, such as the message count and the condensed header line, so the drive and the build agree on it. (cites: run-ef6073384cec)
- Labels styled with text-transform: uppercase come back uppercased from innerText. Drive checks should read textContent or compare case-insensitively. (cites: ttr-7f24f6f344f3, ev-683d82bceb97)
- When a spec gives a user-facing sentence with a count, give its exact singular and plural forms. The unit tests and the drive should both check those forms. (cites: ttr-39b24c5c932c, task-c24ef7bbfec5)
- A list's 'ready to approve' must use the same refusals-plus-gaps check approval uses (spec_service.phase_findings). The warm GET /documents path must also stay within its file-read budget, so plan caching from the start. (cites: ttr-795cff937007, ttr-5e164521d8d3, ev-0c9b18f1242e)
- Seeded drive documents must genuinely be in the state they claim. For example, a 'ready' change needs every requirement covered by a task and its journey advanced. (cites: run-6ce9b2a83d3c, run-d7f1e4ce21e7)
- New UI query hooks must bind and use their error. Otherwise the n11 ratchet in test_surface_ceilings.py fails, and its ceiling must not be raised. (cites: chk-573b30a2500e, run-b58e1266a1c7)
- Layout behaviour such as scroll condensing and pixel budgets cannot be proven in jsdom. Plan a real-browser drive run inside the task that builds the layout, not only in a final ship task. (cites: ttr-57a5e942487b, ev-70863f74c68e)
- The Hub's test suite flags literal 'proposed' strings in spec.py and other readiness sources. Use spec_lifecycle.PROPOSED instead. (cites: chk-fd0c9aa8f878, run-5495f0acd43e)

## What to improve

- [code_and_checks] Make the d1102 drive read labels via textContent and target stable data-testid selectors for the condensed line. Its seeds should be validated against the approve route, so a seed that is not in its claimed state fails as SETUP, not as a behaviour check. (cites: ttr-7f24f6f344f3, run-6ce9b2a83d3c, ttr-57a5e942487b)
- [code_and_checks] Keep main free of lint warnings under --max-warnings 0, so the hub-ui gate result reflects the task being checked. (cites: chk-ccafa946696f, chk-65a489c30aa9)
- [specs] In UI specs, list the test ids the drive relies on and the exact singular and plural wording of count sentences. State any existing performance ratchets the change must respect, such as the warm-list file-read budget and the n11 query-error ceiling. (cites: run-ef6073384cec, task-c24ef7bbfec5, chk-fd0c9aa8f878, chk-573b30a2500e)
- [specs] Let each UI task build the bundle and run the relevant drive checks itself, instead of deferring every real-browser measurement and the bundle refresh to a final task. (cites: ev-bcfec3cdd5d9, run-5dac30541a54)
- [staffing_and_running] Base each task's branch on all approved upstream work, so authors do not have to merge sibling task branches by hand. (cites: run-1d66b702bb2c, run-6ce9b2a83d3c)
- [staffing_and_running] Have builders run the full hub-tests suite, or at least the ratchet and reuse test files, before marking a task complete. Each gate failure cost a long hub-tests run. (cites: ttr-6768937917b1, ttr-52707db03ee0, run-5495f0acd43e)
- [tooling] Let record_evidence infer the document from the task's spec when a requirement id is declared in several documents. (cites: run-ef6073384cec, run-1d66b702bb2c)
- [tooling] Avoid discarding long gate runs when main moves, for example by reusing results for unaffected trees. Give reviewers an easy way to get a credential for a drive's scratch Hub. (cites: chk-62662419dae0, chk-f11b1d109c36, run-44404ff7c0ad)
- [tooling] Give the mender visibility of a flow loop's tasks and queue, so it can do more for a no-progress stall than withdraw one input. (cites: run-62baf0f91a12, stall-5951ce811f86)
