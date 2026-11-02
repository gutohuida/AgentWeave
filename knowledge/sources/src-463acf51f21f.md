# Build retrospective of Every task comes with a recommended builder and checker

Document: spec/changes/every-task-comes-with-a-recommended-builder-and-checker/spec.json (spdoc-1a72da59c1d4)
Made: 2026-11-02T17:29:08.520910+00:00

## Lessons

- When an acceptance drive uses a real LLM author, the spec should say how the drive walks the journey: one conversation, explicit 'continue' answers, re-reading the document path by id, and choosing the delivery itself. (cites: ttr-d4674cae4b20, ttr-56df3b78a411, ttr-6e08c11444b7)
- Name the cross-task contracts in the spec itself: UI test ids, reason field names, and MCP tool names. A drive task should not have to guess them for implementation tasks. (cites: ttr-aee57cbad984, run-a65427a6e221)
- When a requirement depends on run attribution, define build turns and review turns in terms of the stored data, for example the run behind a task's move to completed. (cites: ttr-7e18aedf98d7, ev-1c3c1fba0da0)
- When a requirement lists what a reopened build keeps, also say what happens to every other build setting, including the time window. (cites: ttr-fb2082931165)
- If an author must record structured findings, the spec and the prompt should state the exact evidence shape. (cites: ev-5532bd1321bc)
- Several tasks editing the same drive script and prompt function will conflict at merge. Plan their order, or expect merge-only send-backs. (cites: ttr-89c6622fd96d, ttr-9878828d4560)

## What to improve

- [specs] Put the acceptance drive's harness requirements in the spec: journey walk, conversation reuse, delivery choice, and approval fields such as how_to_check and depends_on. (cites: ttr-56df3b78a411, ttr-6e08c11444b7, spreq-2e90db2d597c)
- [specs] Define build turns versus review turns in terms of stored fields, and state window behaviour on reopen. (cites: ttr-7e18aedf98d7, ttr-fb2082931165)
- [tooling] Let record_evidence default to the task's own spec document when an FR-n is declared in several documents. Builders would then stop hitting repeated refusals. (cites: run-66abc3aa7591, run-ce5862b290cd)
- [tooling] Make the 422 for malformed spec evidence name the expected {checked, limits} shape. (cites: ev-5532bd1321bc)
- [tooling] Provide ruff on PATH and a supported way to run long suites and drives in the background beyond the 10-minute tool limit. (cites: run-e9074a8f0dd1, run-b69f87824df4)
- [tooling] Have side-finding filing warn before it joins a running build and assigns a builder. (cites: run-b176626c0c98)
- [code_and_checks] Add a fast pre-completion check that every served MCP tool is described. The builder would then catch it before the gate. (cites: chk-536f6e3e2b06)
- [code_and_checks] Stabilise or quarantine the flaky test test_a_turn_start_that_creates_its_checkout_never_stalls_the_loop. (cites: chk-7c08b3c0621e)
- [staffing_and_running] Order or serialise tasks that edit the same drive script and prompt function, such as ETCRB-4, 6 and 7. This avoids merge-only send-backs and repeated drive re-runs. (cites: ttr-89c6622fd96d, ttr-9878828d4560)
- [staffing_and_running] Name a builder when filing side findings, rather than letting them fall to the build default. (cites: task-36b0360dabd5, task-f7824de9c8c1, task-670a4e6eef2e)
