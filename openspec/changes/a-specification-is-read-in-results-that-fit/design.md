# Design — a specification is read in results that fit

**Built on the recommended answer to D-B12-3** (a budget the Hub enforces, of 40,000 serialised
characters, with continuation by requirement identifier). If the operator picks a different
number, only `READ_BUDGET_CHARS` and the test constants move. If they want pagination by page
number instead of by identifier, D2 changes shape, and the `identifiers` parameter is still
wanted for a builder reading its own task's requirements.

**F354 assumption.** `spec-queue/tracks/B11.md` did not exist when R1 ran, so B11's
recommendation for F354 was not available. R1 assumes **nothing about F354's answer**. This change
is built to be safe under either version skew between `mcp_server.py` (spawned from the working
tree) and the running Hub (D5). So F354 constrains *when* IMPL's commit lands on the checkout that
`:8000` runs, not *what* this change is. If B11 recommends pinning the server the Hub loaded, the
skew in D5 disappears and D5 becomes belt and braces.

## Context

- The route (`agent_actions.py:1374-1481`) resolves the path, reads the file, extracts the payload,
  and builds `view` from `spec_reading.requirement_view` (`spec_reading.py:121-190`). With
  `include == "full"` it adds five sections (`:1478-1480`). Nothing bounds the size.
- The MCP tool (`mcp_server.py:1908-1935`) forwards `path` and `include`. `include` is
  `Literal["requirements", "full"]`, restated rather than imported, with an agreement test
  (`hub/tests/test_mcp_tool_schemas.py:86`).
- Runners without MCP get the same operation restated in `agents.py:1236-1250`.
- `test_read_spec_document.py` holds the route's tests (`:88-231`).
- Measured on this repository's corpus (`ce086b6`, `spec_payload.extract_payload` over the four
  largest `spec/capabilities/*/spec.html`): requirements serialised to 17–32 KB and acceptance
  criteria to 20–42 KB per document. The default view of the largest is over 72 KB before its
  envelope.

## Decisions

### D1 — The budget is enforced by the Hub, not requested by the agent

`READ_BUDGET_CHARS = 40_000`, measured as `len(json.dumps(view))`. Claude Code spills an MCP result
over its token ceiling. R1 understands that ceiling to be 25,000 tokens by default
(`MAX_MCP_OUTPUT_TOKENS`); **R2 must confirm this against current Claude Code documentation.**
40,000 characters is roughly 10–13 k tokens, well under the ceiling, and it leaves room for the
MCP envelope, which re-escapes the JSON as text.

**Rejected: a `max_chars` parameter.** The agent does not know the harness ceiling either, and the
failure is invisible to it: it sees a spill notice, not a size. A bound the agent chooses is a bound
that is chosen wrong.

**Rejected: only adding `outline`.** It shrinks the default read, but a builder still needs the
criteria, and one large requirement set still spills.

### D2 — How a read that does not fit continues

The route builds `view` as today and then fits it:

1. Fixed fields (`id`, `path`, `title`, `kind`, `phase`, `rigor`, `explore_closed`, `updated_at`,
   `diverged`, `divergence`, `diagnostics`) always go in.
2. `summary`, `problem`, `scope` and `open_questions` go in next, each only if it fits. A field
   that does not fit is named in `omitted_sections`.
3. Requirements are added in identifier order (the order `requirement_view` already returns,
   `test_requirements_come_back_in_identifier_order`) while the total stays within the budget.
   Those not added are listed in `remaining_identifiers`.
4. With `include=full`, the five sections are added only if they fit whole. Otherwise they are
   named in `omitted_sections`.
5. When anything was left out: `truncated: true` and `continue_with`. The latter is a sentence
   naming the call to make, for example *"call read_spec_document again with identifiers=FR-19,…
   (or fewer); omitted sections can be read with include=<section>"*.

The **first** requirement always goes in, even if it alone exceeds the budget. It is then cut with
`section_truncated` set on it, so a read always makes progress. The same rule applies to a single
section asked for by name.

The fitting is one function, `spec_reading.fit_view(view, *, budget) -> view`, pure and
unit-testable. The route calls it last.

### D3 — `identifiers` and `include=outline`

`identifiers` is split on commas and stripped. Unknown identifiers are not an error: they are
returned in `unknown_identifiers`, so a stale list degrades visibly instead of failing the whole
read. The filter runs before the fit, so a named subset is still bounded.

`outline` returns each requirement as `{identifier, modal, statement, state}`. For the largest
document measured, that is roughly the 30 KB statement set with its rationale removed. R2 should
measure it, because if it still exceeds 40,000 characters, the fit (D2) applies to the outline too.

### D4 — A document id is accepted in `path`

If `path` fully matches `spdoc-[0-9a-f]+`, it is looked up with
`select(SpecDocument).where(id == path, project_id == actor.project_id)`. Otherwise it goes through
`validate_spec_path` as today. An id from another project answers 404 *"no specification document
<id>"*, the same answer as an unknown one, so this does not leak which ids exist elsewhere.

**Rejected: a separate `document_id` parameter.** The turn context and the tool description both
say "path"; an agent holding an id puts it where the document goes. `spec_document_for_task`
(`run_task_binding.py:464-477`) keeps returning the path, since that is still the name that means
something to a reader.

### D5 — Version skew, because `:8000` spawns `mcp_server.py` from the working tree

There are two skews. Each must degrade to today's behaviour, never to a refusal:

| tool | Hub | what happens |
|---|---|---|
| new | old (`:8000` not restarted) | `identifiers` is a query parameter the old route does not declare. FastAPI ignores undeclared query parameters, so the old full read comes back (today's behaviour). `include=outline` or a section name fails the old route's `pattern="^(requirements|full)$"` with a 422, **so the tool's default must stay `requirements`**. The description may mention `outline`, and an agent that uses it on an old Hub gets a 422 naming the valid values, which `agent-tool-surface` *A failed tool call is reported* already surfaces. |
| old | new | The old tool sends `path` and `include`, and the new route bounds the result. The id and the bound work at once. |

R2 should confirm "FastAPI ignores undeclared query parameters" for this route, since
`RequestModel`'s `extra="forbid"` applies to bodies only (`schemas/common.py:21`).

So the Python route can ship and take effect on `:8000`'s next restart. The `mcp_server.py` half
reaches `:8000`'s agents as soon as it is committed on the checked-out branch, and it is harmless
there. No IMPL step needs `:8000` restarted before or after it.

### D6 — What the route returns when a function it calls raises

| raised | answer |
|---|---|
| `SpecPathError` (not an id, bad path) | 400 with the error text (today) |
| `ProjectWorkspaceError` | 409 (today) |
| no row, by path or by id | 404 naming what was asked for |
| `read_document` returns `None` | 404 *"registered but its file is missing"* (today) |
| `read_document` raises `OSError` | **today, an unhandled 500.** R1 did not change this; R2 should decide whether this change owns it. Recommended: 409 *"the document's file could not be read: <reason>"*. |
| `fit_view` | cannot raise on the dict shapes `requirement_view` returns. It uses `json.dumps` on values that the route already returns as JSON today. |

## Round log

- **R1 (2026-09-24):** proposed. Measured D1 and D3's sizes on this repository's corpus.
