# A specification is read in results that fit

## Why

**F363 (B).** `read_spec_document` is the one route the product names for reading the specification
an agent was told to implement. Every turn context that names a document says "Read it with
`read_spec_document('<path>')`" (`hub/hub/api/v1/agents.py:1848`, `:1906`). On real documents it
cannot deliver one:

- **Size.** On `:8000`'s LoopEngine, all 57 results across four agents were too large for the
  harness. Each was spilled to a `tool-results/` file of 80–180 KB. On LoopEngine_2 (2026-09-17)
  the results were 180,097 and 143,746 characters. The spill file lies outside the workspace, so
  the workspace guard refused the agent's `Read` of it every time (F363's log, `FINDINGS.md:29611`).
  The turn that followed recorded 16.1 M input tokens. Neither mechanism is wrong alone: the
  harness spills an oversized result outside the project, and the guard exists to refuse exactly
  that path. The only fix is a result that does not spill.
  Measured on this repository's own corpus at `ce086b6`: the default `include="requirements"` view
  of `spec/capabilities/agent-conversation-workspace/spec.html` carries 47 requirements, whose
  statements serialise to 30,708 characters and whose acceptance criteria serialise to 41,875.
  R2 measured the whole default view's content at 66,559 characters (64,450 in the compact form
  fastmcp sends). Claude Code 2.1.280 spills any MCP result over **50,000 characters** to a file
  (design D1), so three of this repository's own capability documents cannot be read today. `full`
  adds the design, tasks, algorithms, evidence and lifecycle.
- **Addressing.** `read_spec_document` refuses a document id: `spdoc-97d90a3506f5` gets *"path must
  begin with 'spec/'"* from `validate_spec_path` (`hub/hub/spec_manifest.py:72`, called at
  `hub/hub/api/v1/agent_actions.py:1401-1404`). But ids are what tasks carry
  (`Task.spec_document_id`, returned by `create_task`/`list_tasks`, `mcp_server.py:754`, `:859`),
  so agents holding a task reach for the id. `run_task_binding.spec_document_for_task`
  (`run_task_binding.py:464-477`) exists only to turn that id into a path for the turn context,
  because the builder "tried and was refused on" the id.

## What Changes

- **The route never returns a result larger than a fixed budget**, 40,000 serialised characters
  (D-B12-3). When the view asked for does not fit, requirements are returned in identifier order
  until the budget is reached. The response then carries `truncated: true`,
  `remaining_identifiers: [...]` and a sentence saying how to ask for the rest. Sections that
  `full` adds and that do not fit are named in `omitted_sections`.
- **`identifiers`**: a new optional parameter, a comma-separated list such as `FR-3,FR-7`. It
  returns only those requirements. This is how the rest of a truncated read is fetched, and how a
  builder reads just the requirements its task serves.
- **`include` gains `outline`**: each requirement's identifier, modal and statement, with no
  rationale or criteria. It is the cheap map of a large document.
- **`include` also accepts one section name** (`design`, `tasks`, `algorithms`, `evidence`,
  `lifecycle`), so an omitted section can be fetched on its own. A single section still larger than
  the budget is cut at the budget and marked `section_truncated`.
- **`path` accepts a document id.** A value shaped `spdoc-<hex>` is looked up by id within the
  caller's project. Every response carries both `id` and `path`.
- The tool description, and the text restated for runners without MCP
  (`agents.py:1236-1250`), say how a truncated read continues.

## Capabilities

### Modified Capabilities

- `spec-document-authority`: adds *An agent can read a specification document in results that fit
  one tool call* and *A specification document is readable by the id tasks carry*.

## Impact

- `hub/hub/api/v1/agent_actions.py` (`read_spec_document`, `:1374-1481`): the id branch, the
  `identifiers` filter, the new `include` values and the budget.
- `hub/hub/mcp_server.py` (`read_spec_document`, `:1908-1935`): new `identifiers` argument, widened
  `include` Literal, docstring. **Subject to F354**: `:8000` spawns this file from the working tree
  on every turn (`.claude/rules/mcp-server.md`). See design D5 for why this change is safe under
  either version skew, whatever B11 recommends for F354.
- `hub/hub/api/v1/agents.py:1236-1250`: the restated operation (`fields`, `args`, `text`).
- `hub/tests/test_mcp_tool_schemas.py`: the restated `include` Literal agreement.
- No migration and no UI.
- Not in scope: `list_tasks` also spilled 24 times on LoopEngine. That is a different route with a
  different shape, and should be filed as its own finding if it is not one already.
