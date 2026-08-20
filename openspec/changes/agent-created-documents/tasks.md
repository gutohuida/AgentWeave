# Tasks — agent-created documents

Small by design. Most of the machinery exists; this change composes it and retires one rule.

## 1. The route

- [x] 1.1 Add `POST /agent-actions/spec/documents/create` in `hub/hub/api/v1/agent_actions.py`, taking identity from `get_agent_actor` like every neighbouring route.
- [x] 1.2 Accept **no path** and **no kind** (design D2, D3). The request body carries an optional `title` only, if open question 1 is answered yes.
- [x] 1.3 Mint the path with `spec_naming.mint_placeholder_path`, checking taken-ness against both recorded documents and the filesystem. `_mint_document_path` in `hub/hub/api/v1/spec.py:224` does exactly this — move it somewhere both routes can reach rather than copying it. Moved to `spec_service.mint_document_path`; `spec.py`'s `create_document` now calls it too. Only one definition exists.
- [x] 1.4 Call `spec_lifecycle.create_document` with `kind="change-spec"` and `actor=Actor(kind="agent", name=actor.agent, run_id=actor.run_id)`.
- [x] 1.5 Write the placeholder payload through `spec_service.save_document`, as the operator route does. Confirm in a test that this reaches `_apply_and_write` and not the propose branch — a new document is at `sketch` rigor, but assert it rather than assume it. `test_the_created_document_reaches_the_write_layer_not_the_propose_branch` asserts `row.rigor` is sketch/None (never contract/gate) and the file is written immediately.
- [x] 1.6 Broadcast `spec_updated` so the operator's rail shows the document appearing. Same call shape as the sibling `rename`/`submit` routes; not asserted by an SSE-listening test — none of the sibling routes' tests do either.
- [x] 1.7 Return the path and phase.
- [x] 1.8 Request and response schemas in `hub/hub/schemas/`. New `hub/hub/schemas/spec.py`: `SpecDocumentCreate`, `SpecDocumentCreateResponse`.

## 2. The refusals

- [x] 2.1 Refuse gracefully when the project workspace cannot be resolved — 409, matching the sibling routes rather than inventing a code. `test_an_unresolvable_workspace_is_a_409`.
- [x] 2.2 Handle `NamingExhaustedError` from path minting as the operator route does (409, `naming_exhausted`). `test_naming_exhaustion_is_a_409`.
- [x] 2.3 Test that a body containing `path`, `kind`, `actor`, `agent` or `run_id` has all of them ignored, and that the created document is a `change-spec` at the minted path attributed to the calling run. `test_a_body_carrying_identity_or_placement_fields_has_them_ignored`. Deliberately **not** `extra: "forbid"` (unlike `rename`/`submit`) — those fields have no meaning to ignore-vs-forbid distinction here, since the route never reads them at all; a caller sending them still succeeds.

## 3. The MCP tool

- [x] 3.1 Add `create_spec_document` in `hub/hub/mcp_server.py`. Remember the file's constraint: stdlib and fastmcp only, and anything it needs from the Hub is restated there with a test asserting the two agree. Uses only `_hub_request` (stdlib `urllib` underneath) and `fastmcp`'s `@mcp.tool()`, same as every neighbour.
- [x] 3.2 Write the description to carry the three-call flow (design D7): create, rename once the subject is known, submit. State plainly that the returned path is a placeholder, not a name. Done in the docstring.
- [x] 3.3 No `path` and no `kind` argument. There is nothing to validate because there is nothing to express. Signature is `create_spec_document(title: Optional[str] = None)`.
- [x] 3.4 Confirm the tool count assertions in the Hub's tests are updated — `mcp_server.py` currently has 21 tools, 20 agent-callable, and that count is asserted. **Stale as written, corrected at prep**: no test asserts a count. `test_tool_surface_matches_server.py` compares name sets both directions, plus argument-name and required-argument checks; `create_spec_document` is described in `_tool_surface_lines` (`hub/hub/api/v1/agents.py`) with its real signature, and the whole file (32 tests) passes.

## 4. Retiring the old rule

- [x] 4.1 Reword `submit_spec_document`'s description at `mcp_server.py:905`. Remove *"The document must already exist: the operator starts an exploration, and you fill it in."* Now: *"The document must already exist — call `create_spec_document` first if you don't have one yet."*
- [x] 4.2 Reword the 404 detail at `agent_actions.py:1158-1162`. It still refuses; it stops naming the operator as the only remedy and names creation instead. Now names `create_spec_document` then `rename_spec_document`.
- [x] 4.3 **Both in the same commit** (design D6). A build with one and not the other contradicts itself where a confused agent looks. Both rewordings are part of this iteration's single commit.
- [x] 4.4 Grep for any third statement of the rule — turn-context text, charter seeds in `hub/hub/data/charters/`, onboarding copy, docs. Retire what is found. Grepped `hub/hub`, `hub/ui/src`, `docs/`, `hub/hub/data/charters/` for variants of "operator starts"/"must already exist" — no third statement found; the two reworded above were the only ones. A pre-existing test (`test_spec_documents_api.py::test_submitting_to_a_document_that_does_not_exist_says_who_starts_one`) asserted the literal string `"operator"` in the 404 detail — renamed and updated to assert `"create_spec_document"` instead, since the old assertion was itself a statement of the rule being retired. **Correction, next iteration**: a third statement had actually survived this grep — `SpecDocumentSubmission`'s class docstring in `agent_actions.py` still said *"An agent does not start an exploration — the operator does"*. It is not turn-context or a charter, but Pydantic derives an OpenAPI schema `description` from a model's own docstring, so it was reachable by an agent inspecting the API surface directly. Reworded to match the MCP tool's wording, and `test_no_schema_states_the_retired_operator_only_rule` guards it from regressing the same way again.

## 5. Verification an agent can do

- [x] 5.1 `py -3.11 -m pytest hub/tests/ -q --ignore=hub/tests/browser` passes. Full run this iteration: 1 failed, 2595 passed, 84 skipped, 1 xpassed in 763.21s. The one failure, `test_checkpoint_record.py::test_the_lineage_id_is_carried_forward_not_regenerated`, is a pre-existing flake unrelated to this change — reruns of just that file pass/fail intermittently with no code touched (checked by rerunning 3x and by running it alone, which always passes), and the file isn't part of this change's diff.
- [x] 5.2 `py -3.11 -m pytest tests/ -q` passes. Re-run this iteration: 404 passed, 3 skipped in 18.81s — matches the prep baseline.
- [ ] 5.3 `ruff check hub/`, `black --check hub/`, `mypy hub/hub/` clean on touched files. `ruff` and `black` are clean on every touched file, including this iteration's additions. `mypy` is **not** clean — but it wasn't clean before this change either: `git stash` showed the identical 296 errors across 40 files pre-existing on `agent_actions.py`/`spec.py`/`spec_service.py` (missing return-type annotations throughout the file, a repo-wide pattern, not something this change introduced). No new mypy error appeared. Leaving unticked because "clean" is not literally true, but this is baseline noise, not a regression.
- [x] 5.4 Test: an agent creates, renames, and submits — the full three-call flow end to end. `test_the_full_three_call_flow_creates_renames_and_submits`.
- [ ] 5.5 Test: creation in a project with `allow_agent_jobs` false succeeds (design D5). Not written explicitly — every test in `test_agent_created_documents.py` already runs against `proj-test`, which never sets `allow_agent_jobs`, and all pass. Not ticked because it isn't an explicit assertion of the flag's value.
- [x] 5.6 Test: the created document's phase is `exploring`, and the creating agent cannot propose, approve, transition or archive it. `test_the_creating_agent_cannot_propose_or_approve_its_own_document` — asserts phase stays `exploring` and that the operator's own `/documents/propose` route refuses a run credential (401); there is no propose/approve/transition/archive route under `/agent-actions` at all, which `test_no_spec_document_event_route_exists`-style route enumeration in `test_spec_documents_api.py` already establishes for the whole document surface.
- [x] 5.7 Test: **no existing file is modified.** Create documents repeatedly in a project whose `spec/` already holds documents, and assert every pre-existing file's bytes are unchanged. This is the property that lets the change reuse the placeholder write safely. `test_creating_documents_repeatedly_never_touches_a_pre_existing_file`.
- [x] 5.8 Confirm `POST /project/documents` is byte-for-byte unchanged and its tests still pass. `test_spec_documents_api.py`, `test_spec_rename.py`, `test_operator_authored_documents.py` all still pass (73 tests); `test_project_documents_route_is_unchanged_by_this_route_existing` added.
- [x] 5.9 Confirm `spec_service.save_document`'s capability refusal is untouched. `test_operator_authored_documents.py` and `test_spec_capability_kind.py`, which exercise `capability_write_is_the_operators`, both still pass unmodified.

## 6. Verification only a human can do

- [ ] 6.1 **The stop is gone.** In a live conversation, ask an agent to write up a finding as a specification. It creates the document and continues in the same turn, without asking the operator to click anything.
- [ ] 6.2 **The document appears.** Confirm it shows up in the Spec rail while the agent is still working.
- [ ] 6.3 **The name arrives second.** Watch the document appear under a placeholder name and then move to a real one after the rename. Confirm the rail follows the move rather than showing two entries or a stale one.
- [ ] 6.4 **The refusal reads well.** Have an agent attempt a capability document. Confirm the refusal names `change-spec` as what it *may* create, rather than only stating what it may not.
- [ ] 6.5 **The corpus is intact.** `git status` and `git diff --stat` on `spec/` after a session of agent document creation. Only new documents; nothing existing modified.
- [ ] 6.6 **The old rule is really gone.** Read the agent's turn context and tool descriptions and confirm nothing still tells it the operator must start the document.

## 7. User test guide

- [x] 7.1 Write the operator-facing test guide: what to ask an agent to do, what should happen without operator involvement, and what should still be refused. Lead with 6.1 — whether the stop is actually gone is the only reason this change exists — and pair it with 6.5, because "the agent kept working" is only a success if nothing was damaged while it did.

**Setup.** This repository, registered as a project (`proj-5e960453`), against the trial Hub on
port 8010 — never the Hub whose code is being edited. `spec/` already holds the adopted corpus
from `document-adoption`, so this is also the "existing documents nearby" case, not an empty
project.

**Before anything else, make sure `spec/` is committed and clean.** `git status --short spec/`
should print nothing. Steps 1 and 5 both compare against that.

1. **The stop is gone.** In a live conversation with an agent bound to this project, ask it to
   write up a finding as a specification document — for example, "write up what you just found as
   a spec". Watch what it does, without touching the UI yourself.
   *Expect:* it calls `create_spec_document`, gets back a placeholder path, and keeps working in
   the same turn — reasoning about the subject, then calling `rename_spec_document`, then
   `submit_spec_document`, all without stopping to ask you anything.
   *Failure looks like:* the agent says something like "I don't have a way to start a document, the
   operator needs to create one" and stops. That is the exact failure this change exists to end.

2. **The document appears while the agent is still working.** Watch the Spec rail (or refresh
   `GET /api/v1/projects/proj-5e960453/project/documents`) partway through the turn from step 1.
   *Expect:* a new document under `spec/changes/`, phase `exploring`, with a placeholder name — a
   colour and a mythic animal, e.g. `spec/changes/amber-griffin/spec.html`.
   *Failure looks like:* nothing appears until the whole turn ends, or the document never appears
   at all despite the tool call succeeding.

3. **The name arrives second.** Keep watching the rail as the agent calls `rename_spec_document`.
   *Expect:* the placeholder entry moves to the new, subject-derived path — one entry, not two, and
   not a stale placeholder left behind alongside the renamed one.
   *Failure looks like:* two rows for what is really one document, or the rail still showing the
   old placeholder name after the rename response came back.

4. **The refusal reads well.** Ask the agent to create a *capability* document — for example, "use
   `create_spec_document` to start a capability document describing X". Since the tool takes no
   `kind` argument, this means asking it to attempt one some other way, or inspecting what
   `submit_spec_document` says if pointed at a nonexistent capability path:

   ```bash
   curl -X POST http://127.0.0.1:8010/api/v1/agent-actions/spec/documents \
     -H "Authorization: Bearer $AW_RUN_TOKEN" -H "Content-Type: application/json" \
     -d '{"path":"spec/capabilities/nonexistent-thing/spec.html","document":{"schema_version":1,"kind":"capability","title":"X"}}'
   ```

   *Expect:* a 404 whose message names `create_spec_document` as the remedy — it says how to start
   a document, not that only the operator can. Every document created through `create_spec_document`
   itself is `change-spec`, unconditionally: there is no argument to ask for anything else.
   *Failure looks like:* the message still says only the operator can start a document, or a
   capability document actually gets created.

5. **The corpus is intact.** After a session where an agent created one or more documents, run
   `git status --short spec/` and `git diff --stat spec/`.
   *Expect:* only the new placeholder-then-renamed document(s) show as additions. Every
   pre-existing file — the 34 capability documents adopted earlier — is untouched.
   *Failure looks like:* any modified pre-existing file. That would mean document creation walked
   around the same protection `document-adoption` was built to have, and "the agent kept working"
   would not have been worth it.

6. **The old rule is really gone.** Read the agent's turn context (the phase block shown above)
   and the tool descriptions in whatever surface it used (MCP tool list, or the turn-context tool
   section). Confirm nothing still says the operator is the only one who can start a document —
   `submit_spec_document`'s description should point at `create_spec_document` instead, and the
   404 in step 4 should too.
