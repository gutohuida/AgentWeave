# Build retrospective of Settings in the app's style, where you expect them

Document: spec/changes/settings-in-the-app-s-style-where-you-expect-them/spec.json (spdoc-587b2763c787)
Made: 2026-11-11T04:53:06.378263+00:00

## Lessons

- State counts and lists consistently in the spec. The "fifteen sections" text with fourteen names was flagged by every task and never resolved. (cites: ev-b1fdd9cd7526, run-1a7dc5654af4)
- Mark acceptance criteria that only the operator can satisfy, such as sign-off against a mock, as operator-owned. Agents cannot produce that evidence, and treating it as agent work causes send-backs. (cites: ttr-e93b19d20df0, ev-6f4fed0b53e4)
- Any task that deletes or adds UI query call sites must update scripts/drive/n11_query_error_surface.py and the ceilings in hub/tests/test_surface_ceilings.py in the same change, or the sweep fails. (cites: chk-f703c72d7818, chk-69835ecc36e8, run-fd8704c86824)
- Check scripts such as long_values_check.py hardcode section ids. A spec that renames sections should say to update those lists, or the checks silently measure the old layout. (cites: run-c016a750d453, run-ce7a2f4c2f6c)
- On this machine the full long_values_check sweep takes about 40 minutes. Specs should name the specific --section runs that demonstrate each criterion rather than a full sweep. (cites: run-6227b2f67a82, run-99f2a381d664)
- The hub-ui hubTime test forbids raw new Date(value) outside two sites. New UI code that builds dates must avoid that pattern. (cites: chk-a305f9ca392e, run-dbdb8791733e)
- When a requirement is shared across tasks, each task's evidence should say which part it covers. Evidence left partial on the last task blocks landing even after review passes. (cites: run-90973afecb29, ev-01738a54d474)

## What to improve

- [code_and_checks] Derive long_values_check.py's section lists from the settings screen definitions instead of hardcoding ids, so renames cannot leave the check measuring retired sections. (cites: run-c016a750d453, run-ce7a2f4c2f6c)
- [code_and_checks] Extend the long-values check to detect text overlapping sibling elements, which it still misses beyond the new own-box rule. (cites: run-1a7dc5654af4, task-5a94afabcfa3)
- [code_and_checks] Address the flaky Hub and UI tests that repeatedly fail under load, such as vaultTab, pty_runner and the retrospective tests, so check gates stop reporting load as failures. (cites: chk-7ace270f19db, chk-90beb551ce85, chk-80c96a07eafc)
- [specs] Keep counts and named lists in agreement. Tag operator-only criteria such as mock sign-off so they are not assigned to agents as evidence. (cites: ev-b1fdd9cd7526, ttr-e93b19d20df0)
- [specs] When a spec removes or adds UI components, require updates to the n11 ledger and surface ceilings, and to any check script that enumerates sections. (cites: chk-f703c72d7818, chk-69835ecc36e8)
- [staffing_and_running] Split long Playwright checks into per-section runs and avoid running parallel Hubs on an already contended machine. Full sweeps repeatedly timed out or crashed. (cites: run-1a7dc5654af4, run-a67598a70a2d, run-f8a81c64595f)
- [staffing_and_running] Keep the main checkout clean before builds start, so integration does not stall on unrelated uncommitted spec/ files. (cites: stall-2de0e9aeebf8)
- [tooling] Regenerate the hashed UI bundle automatically at landing, or stop committing it per task. Bundle-only conflicts caused most of the merge-needed send-backs. (cites: ttr-793602ed8a88, ttr-bd1fce78df72, chk-4c9dc16525cf, ttr-b30417a5801a)
- [tooling] Re-run the check gate on a new completion instead of re-applying a prior failed check run to an unchanged resubmission. (cites: ttr-a8cbbf9435f8, ttr-2d5eeebbe99c, chk-90beb551ce85)
- [tooling] Make submit_checkpoint_notes accept a string for list fields, or name the expected shape in its error. The rejection recurred across many runs. (cites: run-bc0c98fef272, run-8ca107d0668d, run-dff44bac517a)
- [tooling] Let a reviewer's verified drive upgrade partial evidence coverage, or surface the cross-task coverage gap before approval, so approved work is not left unable to land. (cites: run-90973afecb29)
