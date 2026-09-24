## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2 (2026-09-24, recorded in design.md's round log and `spec-queue/tracks/B12.md`): re-derive the proposal against `hub/hub/api/v1/agent_actions.py:1374-1481`,
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
- [x] 0.2a Operator review (2026-09-24, Opus adversarial review): D-B12-3 answered (40,000, Hub-enforced); continuation by `identifiers` leaves out the preamble. Fixes applied to 1.1, 1.2, 1.5, 2.2, 2.3; 1.14 and 1.15 and the `agent-capability-plane` MODIFIED delta added (design, *Operator review*)
- [ ] 0.3 The operator answers D-B12-3 and approves the change in `APPROVALS.md`.

## 1. Tests first — each must fail on today's code unless marked as a control

Route cases go in `hub/tests/test_read_spec_document.py`, reusing its `builder` fixture. The large
document is generated: N requirements, each with a 600-character statement and three
400-character criteria, so its default view is over 100,000 characters. Do **not** check in a
copy of a real spec.

- [ ] 1.1 A large document read with defaults: `len(json.dumps(body)) <= READ_BUDGET_CHARS`
  **exactly**, with no envelope allowance (the budget covers the whole response, D1), and
  `len(json.dumps(body, separators=(",", ":"), ensure_ascii=False)) <= 50_000` (the compact form
  Claude Code counts, from `structuredContent`; operator review), where `body = response.json()`.
  `truncated is True`. The
  identifiers returned are a prefix of `FR-1..FR-N` in identifier order, and
  `remaining_identifiers` is exactly the rest. Record that it FAILS today: measure and paste the
  size.
- [ ] 1.2 Continuation: read again with `identifiers=",".join(remaining)`. The continuation carries
  no `summary`, `problem`, `scope` or `open_questions` key (operator decision). The union of the two
  reads is all N requirements, with no duplicates. If the second read is truncated too, repeat
  until every requirement has been returned, and assert the loop terminates in at most
  `ceil(total / budget) + 1` reads.
- [ ] 1.3 Order: identifiers are minted in declaration order on first submission, so a document
  cannot simply be *declared* out of identifier order (R2). Use at least 12 requirements, so that a
  string sort (`FR-1, FR-10, FR-11, FR-12, FR-2`) differs from `requirement_view`'s numeric order,
  and submit a second revision that lists them in reverse, so payload order differs too. The
  truncated prefix is still `FR-1..FR-k` numerically. This test fails if `fit_view` re-sorts by
  string or appends in payload order (F190: use the order the route really returns).
- [ ] 1.4 `identifiers=FR-2,FR-99`: returns `FR-2` only, with `unknown_identifiers == ["FR-99"]` and
  status 200.
- [ ] 1.5 `include=outline`: every requirement has exactly the keys
  `{identifier, key, modal, statement, state}` (operator review: `key` is how an unindexed
  requirement, whose `identifier` is `None`, is continued; `spec_reading.py:164-189`). With the
  document of 1.12, the unindexed requirement's outline entry has `identifier is None` and a
  non-empty `key`.
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
  a value an old Hub refuses by default). The route's values must first become an importable
  constant (e.g. `READ_INCLUDE_VALUES` in `agent_actions.py`, with the `pattern=` built from it);
  today they exist only inside a regex string, and no agreement test covers `include` (R2).
- [ ] 1.12 A requirement with no identifier (D3, R2): write a document file whose payload declares
  a requirement the index has not seen and whose identity block gives it none, large enough to be
  truncated before it. `remaining_identifiers` names it by `key`, and reading with that key returns
  it. Fails if continuation matches `identifier` only.
- [ ] 1.13 D6 (R2): with `read_document` patched to raise `OSError`, then `UnicodeDecodeError`,
  then `ProjectPathError`, the route answers 409 with *"the document's file could not be read"*.
  Record that each is a 500 today.

- [ ] 1.14 (operator review) Every name `omitted_sections` can carry is readable: a document whose
  `problem` alone is 60,000 characters, read with defaults, names `"problem"` in
  `omitted_sections`; `include=problem` then returns it cut, with `section_truncated`. Repeat the
  `include=<name>` read for `summary`, `scope` and `open_questions` (status 200, the field present).
  Fails today with 422 (the `pattern` accepts only `requirements|full`).
- [ ] 1.15 (operator decision, the read bound) A document with a 30,000-character preamble (split
  across `summary`, `problem`, `scope`, `open_questions`) and requirements totalling over 120,000
  characters. Follow `remaining_identifiers` until none remain. Assert every continuation read
  (those with `identifiers`) has no preamble key, and the number of reads is at most
  `ceil(len(json.dumps(default_unbounded_view)) / READ_BUDGET_CHARS) + 1`. Record that the bound
  fails if the continuation includes the preamble (mutation at IMPL: re-add it and count the reads;
  about 12 instead of 4).

## 2. The fix

- [ ] 2.1 `spec_reading.fit_view` and `READ_BUDGET_CHARS`, per D2.
- [ ] 2.2 In the route: the id branch (D4), the `identifiers` query parameter and filter (D3),
  widen `include`'s pattern to `requirements|outline|full|design|tasks|algorithms|evidence|lifecycle|summary|problem|scope|open_questions`
  (the four preamble names added by the operator review, so every name `omitted_sections` can carry
  is requestable), build the outline with `key`, leave the preamble and the `full` sections out of
  any read that names `identifiers`, and call `fit_view` last. Add `id` to the view. Handle D6: `OSError`, `UnicodeDecodeError` and `ProjectPathError` from `read_document` answer 409.
- [ ] 2.3 `mcp_server.py`: add the `identifiers: str = ""` argument (sent only when non-empty),
  widen the `include` Literal (the same values as the route's constant, task 1.11), and rewrite the
  docstring to explain truncation, `continue_with`, that a read by `identifiers` carries no preamble,
  and the id. Stdlib and fastmcp imports only.
- [ ] 2.4 `agents.py:1236-1250`: `args`, `fields` and `text` to match.
- [ ] 2.5 Run group 1 and the MCP test files, with `claude` stripped from PATH, then the lint block.

## 3. Verify

- [ ] 3.1 Trial Hub `:8010`: register a project holding a copy of
  `spec/capabilities/agent-conversation-workspace/spec.html` (in `testbed/`), start a Haiku agent
  turn that is told to read it, and record that no `tool-results/` spill happens. Also record the
  number of calls it took to read every requirement.
- [ ] 3.2 Close F363 in `FINDINGS.md` and regenerate the backlog. File `list_tasks`' spill as its
  own finding if it has none.
