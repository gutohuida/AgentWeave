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

**R2 (2026-09-24):** `spec-queue/tracks/B11.md` still does not exist, but B11's change for F354 does
(`openspec/changes/an-agents-tool-server-is-the-one-its-hub-loaded/`). It recommends pinning the
tool server when the Hub starts, and its design orders the work as: that change's IMPL, then the
operator's `:8000` restart, then this change's `mcp_server.py` half, while noting this change can
also ship without it because of D5. That agrees with the assumption above: nothing in this design
changes. Under the pin, the tool and the route change together on a restart, so neither skew row
in D5 occurs, and D5 remains correct for a Hub that predates the pin.

## Context

- The route (`agent_actions.py:1374-1481`) resolves the path, reads the file, extracts the payload,
  and builds `view` from `spec_reading.requirement_view` (`spec_reading.py:121-190`). With
  `include == "full"` it adds five sections (`:1478-1480`). Nothing bounds the size.
- The MCP tool (`mcp_server.py:1908-1935`) forwards `path` and `include`. `include` is
  `Literal["requirements", "full"]`, restated rather than imported. **No agreement test covers it
  today** (R2): `test_mcp_tool_schemas.py`'s two parametrised agreement tests list `send_message`,
  `create_task`, `update_task`, `create_job` and `decide_evidence` only, and the route's accepted
  values live in a `pattern=` string, not a constant a test can import. Task 1.11 adds both.
- Runners without MCP get the same operation restated in `agents.py:1236-1250`.
- `test_read_spec_document.py` holds the route's tests (`:88-231`).
- Measured on this repository's corpus (`ce086b6`, `spec_payload.extract_payload` over the four
  largest `spec/capabilities/*/spec.html`): requirements serialised to 17–32 KB and acceptance
  criteria to 20–42 KB per document. R2 re-measured the default view's content (`summary`,
  `problem`, `scope`, `open_questions` and `requirement_view`'s list) with `json.dumps`: 66,559
  characters for `agent-conversation-workspace`, 58,641 for `spec-document-authority` and 52,052
  for `task-lifecycle-governance`. All three exceed the 50,000-character spill threshold (D1).
  R1's 72 KB summed separately serialised parts; the conclusion is the same.

## Decisions

### D1 — The budget is enforced by the Hub, not requested by the agent

`READ_BUDGET_CHARS = 40_000`, measured as `len(json.dumps(view))` over the **whole** response,
including `remaining_identifiers`, `continue_with`, `omitted_sections` and `diagnostics`.

**The ceiling that spills, read from the installed CLI (R2, Claude Code 2.1.280).** There are two
limits, and the one R1 named is not the one that spills:

- **Spill to a `tool-results/` file** happens when the result's text exceeds the tool's persistence
  threshold: `min(maxResultSizeChars, 50_000)` characters, where the MCP tool declares
  `maxResultSizeChars: 1e5` and the global cap is `C$ = 50000`. The count is the summed length of
  the result's text blocks (`N(e)` in the bundle). A remote flag (`tengu_velvet_ibis[<tool>]`) can
  override the threshold per tool, so it is not guaranteed to stay 50,000. **This is F363's
  mechanism**: the LoopEngine results were 80–180 KB, all above 50,000.
- **Truncation** at `MAX_MCP_OUTPUT_TOKENS` (default `d = 25000` tokens, estimated at 4 characters
  a token, so about 100,000 characters) cuts the text and appends `[OUTPUT TRUNCATED …]`. This is
  the limit R1 cited; it is larger than the spill threshold, so it never binds first by default.

What the harness measures is the text fastmcp sends: `pydantic_core.to_json(result)`, compact, not
indented (fastmcp 3.1.0 `tools/tool.py:64-65`, the version installed). `json.dumps` with its default
`", "` separators and ASCII escaping is never shorter for this data, so measuring with it is
conservative. On the largest document measured, `json.dumps` gave 66,559 characters where
fastmcp's form gave 64,450.

So 40,000 leaves 10,000 characters under the 50,000 spill threshold. The binary also has an
aggregate per-message tool-result budget (`skipAggregateToolResultBudget`); its size was not
measured, and an agent reading several documents in parallel in one message could still meet it.
That residual is accepted: the fix is for one read, which is what spilled.

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

`outline` returns each requirement as `{identifier, modal, statement, state}`. **Measured by R2**
over this repository's 34 `spec/**/spec.html` documents: the largest outline
(`agent-conversation-workspace`, 47 requirements) is 13,199 characters, the next 12,656. Every
outline in the corpus fits. The fit (D2) still applies to it.

**A requirement with no identifier (R2).** `requirement_view` appends requirements the document
declares and the index has not seen with `identifier` taken from the document's own identity block,
which can be `None` (`spec_reading.py:164-189`). Continuation by identifier cannot name those. So
`identifiers` matches a requirement's `identifier` **or** its `key`, and `remaining_identifiers`
lists the key wherever the identifier is null. Without this, a truncated read of a document whose
index lags its file could never return its unindexed requirements.

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

Confirmed by R2: the route declares each query parameter individually with `Query(...)`
(`agent_actions.py:1374-1379`); FastAPI validates only the parameters it declares and ignores the
rest. `extra="forbid"` belongs to `RequestModel`, a body model, and a query-parameter model with
`extra="forbid"` is not used here.

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
| `read_document` raises `OSError` (permission, a directory where the file was) | **today an unhandled 500. This change owns it:** 409 *"the document's file could not be read: <reason>"*. |
| `read_document` raises `UnicodeDecodeError` (a file that is not UTF-8) | today an unhandled 500, since it is a `ValueError`, not an `OSError`. Same 409. |
| `read_document` raises `ProjectPathError` (`workspace.resolve_relative`, e.g. a `spec/` symlink resolving outside the project, `project_workspace.py:78-80`) | today an unhandled 500. Same 409: the path is the stored row's, not the agent's input, so it is a state conflict, not a bad request. |

Decided by R2. The precedent is the operator's `GET /project/spec` (`spec.py:197-205`), which
already answers `OSError` with 409 *"could not read document: …"*. That route answers
`ProjectPathError` with 400 because there the path is the caller's; here it is not.
| `fit_view` | cannot raise on the dict shapes `requirement_view` returns. It uses `json.dumps` on values that the route already returns as JSON today. |

## Round log

- **R1 (2026-09-24):** proposed. Measured D1 and D3's sizes on this repository's corpus.
- **R2 (2026-09-24):** D1's ceiling read from the installed Claude Code 2.1.280: the spill is a
  50,000-character persistence threshold, not the 25k-token truncation. D3 gains key-based
  continuation for requirements with no identifier; the outline was measured (13.2 KB at most).
  D6's unhandled raises decided (409). B11's F354 change agrees with the assumption. Tasks 1.3,
  1.11 and 1.12–1.13 corrected or added.
