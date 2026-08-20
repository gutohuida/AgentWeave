# Tasks — agent-created documents

Small by design. Most of the machinery exists; this change composes it and retires one rule.

## 1. The route

- [ ] 1.1 Add `POST /agent-actions/spec/documents/create` in `hub/hub/api/v1/agent_actions.py`, taking identity from `get_agent_actor` like every neighbouring route.
- [ ] 1.2 Accept **no path** and **no kind** (design D2, D3). The request body carries an optional `title` only, if open question 1 is answered yes.
- [ ] 1.3 Mint the path with `spec_naming.mint_placeholder_path`, checking taken-ness against both recorded documents and the filesystem. `_mint_document_path` in `hub/hub/api/v1/spec.py:224` does exactly this — move it somewhere both routes can reach rather than copying it.
- [ ] 1.4 Call `spec_lifecycle.create_document` with `kind="change-spec"` and `actor=Actor(kind="agent", name=actor.agent, run_id=actor.run_id)`.
- [ ] 1.5 Write the placeholder payload through `spec_service.save_document`, as the operator route does. Confirm in a test that this reaches `_apply_and_write` and not the propose branch — a new document is at `sketch` rigor, but assert it rather than assume it.
- [ ] 1.6 Broadcast `spec_updated` so the operator's rail shows the document appearing.
- [ ] 1.7 Return the path and phase.
- [ ] 1.8 Request and response schemas in `hub/hub/schemas/`.

## 2. The refusals

- [ ] 2.1 Refuse gracefully when the project workspace cannot be resolved — 409, matching the sibling routes rather than inventing a code.
- [ ] 2.2 Handle `NamingExhaustedError` from path minting as the operator route does (409, `naming_exhausted`).
- [ ] 2.3 Test that a body containing `path`, `kind`, `actor`, `agent` or `run_id` has all of them ignored, and that the created document is a `change-spec` at the minted path attributed to the calling run.

## 3. The MCP tool

- [ ] 3.1 Add `create_spec_document` in `hub/hub/mcp_server.py`. Remember the file's constraint: stdlib and fastmcp only, and anything it needs from the Hub is restated there with a test asserting the two agree.
- [ ] 3.2 Write the description to carry the three-call flow (design D7): create, rename once the subject is known, submit. State plainly that the returned path is a placeholder, not a name.
- [ ] 3.3 No `path` and no `kind` argument. There is nothing to validate because there is nothing to express.
- [ ] 3.4 Confirm the tool count assertions in the Hub's tests are updated — `mcp_server.py` currently has 21 tools, 20 agent-callable, and that count is asserted.

## 4. Retiring the old rule

- [ ] 4.1 Reword `submit_spec_document`'s description at `mcp_server.py:905`. Remove *"The document must already exist: the operator starts an exploration, and you fill it in."*
- [ ] 4.2 Reword the 404 detail at `agent_actions.py:1158-1162`. It still refuses; it stops naming the operator as the only remedy and names creation instead.
- [ ] 4.3 **Both in the same commit** (design D6). A build with one and not the other contradicts itself where a confused agent looks.
- [ ] 4.4 Grep for any third statement of the rule — turn-context text, charter seeds in `hub/hub/data/charters/`, onboarding copy, docs. Retire what is found.

## 5. Verification an agent can do

- [ ] 5.1 `py -3.11 -m pytest hub/tests/ -q --ignore=hub/tests/browser` passes.
- [ ] 5.2 `py -3.11 -m pytest tests/ -q` passes.
- [ ] 5.3 `ruff check hub/`, `black --check hub/`, `mypy hub/hub/` clean on touched files.
- [ ] 5.4 Test: an agent creates, renames, and submits — the full three-call flow end to end.
- [ ] 5.5 Test: creation in a project with `allow_agent_jobs` false succeeds (design D5).
- [ ] 5.6 Test: the created document's phase is `exploring`, and the creating agent cannot propose, approve, transition or archive it.
- [ ] 5.7 Test: **no existing file is modified.** Create documents repeatedly in a project whose `spec/` already holds documents, and assert every pre-existing file's bytes are unchanged. This is the property that lets the change reuse the placeholder write safely.
- [ ] 5.8 Confirm `POST /project/documents` is byte-for-byte unchanged and its tests still pass.
- [ ] 5.9 Confirm `spec_service.save_document`'s capability refusal is untouched.

## 6. Verification only a human can do

- [ ] 6.1 **The stop is gone.** In a live conversation, ask an agent to write up a finding as a specification. It creates the document and continues in the same turn, without asking the operator to click anything.
- [ ] 6.2 **The document appears.** Confirm it shows up in the Spec rail while the agent is still working.
- [ ] 6.3 **The name arrives second.** Watch the document appear under a placeholder name and then move to a real one after the rename. Confirm the rail follows the move rather than showing two entries or a stale one.
- [ ] 6.4 **The refusal reads well.** Have an agent attempt a capability document. Confirm the refusal names `change-spec` as what it *may* create, rather than only stating what it may not.
- [ ] 6.5 **The corpus is intact.** `git status` and `git diff --stat` on `spec/` after a session of agent document creation. Only new documents; nothing existing modified.
- [ ] 6.6 **The old rule is really gone.** Read the agent's turn context and tool descriptions and confirm nothing still tells it the operator must start the document.

## 7. User test guide

- [ ] 7.1 Write the operator-facing test guide: what to ask an agent to do, what should happen without operator involvement, and what should still be refused. Lead with 6.1 — whether the stop is actually gone is the only reason this change exists — and pair it with 6.5, because "the agent kept working" is only a success if nothing was damaged while it did.
