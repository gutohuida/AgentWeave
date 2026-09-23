## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: re-derive the proposal against `hub/hub/api/v1/agent_actions.py:1374-1481`,
  `hub/hub/spec_reading.py:121-190`, `hub/hub/mcp_server.py:1908-1935`,
  `hub/hub/api/v1/agents.py:1236-1250`, `hub/hub/run_task_binding.py:464-477` and
  `hub/tests/test_read_spec_document.py`. In particular:
  - confirm Claude Code's MCP output ceiling (D1) from its current documentation;
  - re-measure the sizes in D1 and D3, including `outline` on the largest document;
  - confirm that FastAPI ignores undeclared query parameters on this route (D5);
  - decide D6's `OSError` row;
  - read `spec-queue/tracks/B11.md`'s F354 recommendation, if it exists by then, and check it
    against the design's F354 assumption.
- [ ] 0.2 R3: a second independent re-derivation. `openspec validate
  a-specification-is-read-in-results-that-fit --strict` passes.
- [ ] 0.3 The operator answers D-B12-3 and approves the change in `APPROVALS.md`.

## 1. Tests first — each must fail on today's code unless marked as a control

Route cases go in `hub/tests/test_read_spec_document.py`, reusing its `builder` fixture. The large
document is generated: N requirements, each with a 600-character statement and three
400-character criteria, so its default view is over 100,000 characters. Do **not** check in a
copy of a real spec.

- [ ] 1.1 A large document read with defaults: `len(response.text) <= READ_BUDGET_CHARS + 2_000`
  (the envelope allowance is named as a constant in the test), and `truncated is True`. The
  identifiers returned are a prefix of `FR-1..FR-N` in identifier order, and
  `remaining_identifiers` is exactly the rest. Record that it FAILS today: measure and paste the
  size.
- [ ] 1.2 Continuation: read again with `identifiers=",".join(remaining)`. The union of the two
  reads is all N requirements, with no duplicates. If the second read is truncated too, repeat
  until every requirement has been returned, and assert the loop terminates in at most
  `ceil(total / budget) + 1` reads.
- [ ] 1.3 Order: build the document with requirements declared out of identifier order. The
  truncated prefix is still `FR-1..FR-k`. This test fails if `fit_view` appends in payload order
  rather than in `requirement_view`'s order (F190: use the order the route really returns).
- [ ] 1.4 `identifiers=FR-2,FR-99`: returns `FR-2` only, with `unknown_identifiers == ["FR-99"]` and
  status 200.
- [ ] 1.5 `include=outline`: every requirement has exactly the keys
  `{identifier, modal, statement, state}`.
- [ ] 1.6 `include=full` on a document with a 60,000-character `design`: `"design"` is in
  `omitted_sections`. `include=design` then returns it, cut, with `section_truncated`.
- [ ] 1.7 By id: reading `spdoc-…` returns the same `requirements` as reading by path, and carries
  `id` and `path`. Record that it FAILS today (400 *"path must begin with 'spec/'"*).
- [ ] 1.8 An id from another project answers 404, with the same detail shape as an unknown id.
- [ ] 1.9 Controls: every existing test in `test_read_spec_document.py`,
  `test_divergence_on_read.py` and `test_task_spec_document_context.py` passes unchanged. Record the
  counts before group 2.
- [ ] 1.10 `fit_view` unit tests in a new `hub/tests/test_spec_read_budget.py`: a view that fits is
  returned unchanged (identity on content); a single requirement larger than the budget is returned
  cut and marked; the fixed fields are never dropped.
- [ ] 1.11 In `hub/tests/test_mcp_tool_schemas.py`: the tool's `include` Literal equals the route's
  accepted values, and the tool's default is still `"requirements"` (D5: a new tool must not send
  a value an old Hub refuses by default).

## 2. The fix

- [ ] 2.1 `spec_reading.fit_view` and `READ_BUDGET_CHARS`, per D2.
- [ ] 2.2 In the route: the id branch (D4), the `identifiers` query parameter and filter (D3),
  widen `include`'s pattern to `requirements|outline|full|design|tasks|algorithms|evidence|lifecycle`,
  build the outline, and call `fit_view` last. Add `id` to the view. Handle D6 as R2 decides.
- [ ] 2.3 `mcp_server.py`: add the `identifiers: str = ""` argument (sent only when non-empty),
  widen the `include` Literal, and rewrite the docstring to explain truncation, `continue_with` and
  the id. Stdlib and fastmcp imports only.
- [ ] 2.4 `agents.py:1236-1250`: `args`, `fields` and `text` to match.
- [ ] 2.5 Run group 1 and the MCP test files, with `claude` stripped from PATH, then the lint block.

## 3. Verify

- [ ] 3.1 Trial Hub `:8010`: register a project holding a copy of
  `spec/capabilities/agent-conversation-workspace/spec.html` (in `testbed/`), start a Haiku agent
  turn that is told to read it, and record that no `tool-results/` spill happens. Also record the
  number of calls it took to read every requirement.
- [ ] 3.2 Close F363 in `FINDINGS.md` and regenerate the backlog. File `list_tasks`' spill as its
  own finding if it has none.
