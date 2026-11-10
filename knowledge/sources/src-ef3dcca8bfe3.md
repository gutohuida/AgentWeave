# Build retrospective of An agent the operator trusts can tidy the specs

Document: spec/changes/an-agent-the-operator-trusts-can-tidy-the-specs/spec.json (spdoc-d9f38f8d3017)
Made: 2026-11-09T02:37:03.744257+00:00

## Lessons

- A spec that will be checked by a browser drive should name the page handles (test ids, data attributes, open or closed state) and the agent routes in its contract, so UI and Hub builders don't have to discover them in the drive script. (cites: ttr-b78a25d04e70, ckpt-d8c70f727f3b)
- Any 'oldest first' list in this Hub needs a tie-break that follows insertion order, such as rowid. On Windows the clock ticks only about every 15 ms, and event ids are random. (cites: ttr-48f5740c8cd7, ev-f29fe25355e6)
- Code in mcp_server that tests reach in-process must not mutate module globals. Withholding a switched tool belongs only in main(). (cites: ttr-e170331455e0, ev-f224ab388571)
- A new run environment variable must be added to both hub/tests/conftest.py and tests/conftest.py, and a switched tool changes the stdio import-vs-spawn comparison. Both are caught only by the full hub-tests suite. (cites: chk-a75724503f5f, ckpt-7262a1908618)
- A fresh scratch project has no spec/index.json, and the Hub will not guess its home. Specs and drives that expect a new capability in the spec map must reindex with a home first. (cites: ckpt-386fc264e493, ckpt-d0bf9bfd4abf)
- Specs should state what happens to superseded documents when they are archived: whether the filter keeps them, and whether a superseded document can be archived without a fold. (cites: ckpt-428ba1de4baa, ev-a10eff30e44e)

## What to improve

- [specs] In the design's contract section, name the agent routes, the refusal code for operator ops sent through the agent tool, the order of operator routes that share a path prefix, and every page test id the drive will use. (cites: ckpt-d8c70f727f3b, ttr-b78a25d04e70)
- [specs] State whether acceptance criteria assume an existing spec/index.json, and settle how archiving interacts with the superseded mark, before the build starts. (cites: ckpt-386fc264e493, ev-a10eff30e44e)
- [tooling] Run the full hub-tests check before review approval for tasks that touch mcp_server.py or conftest.py, not only at landing, so failures like the stdio surface mismatch reach the builder before approval. (cites: chk-c17eb13c032c, chk-a75724503f5f)
- [tooling] Have every drive helper start scratch Hubs with HUB_URL and AW_* stripped, and finish the drive's minted runs before it triggers real turns. d1011 start_hub now does the first; drives not built on it are unchecked. (cites: ckpt-d0bf9bfd4abf, evr-1204f6989bae)
- [code_and_checks] Confirm that the surface-ceiling ratchets raised in AOTCT-2 were lowered once the UI clients landed. The record does not show the reversal. (cites: ckpt-428ba1de4baa)
- [staffing_and_running] Don't route a run-drive task while its prerequisite is still going through landing; wait for the prerequisite to reach master before starting the drive run. (cites: ttr-b56970c4222f, ckpt-3ae266461d3a)
- [staffing_and_running] When the drive author messages builders about contract handles, the builder's run should check the drive script before completing, so this doesn't rely on the reviewer grepping for the handles. (cites: run-cdd272d32efb, run-4b9572bbefd0)
