## 1. Correct what the service says about itself

- [x] 1.1 Add a test asserting the refusal message for a non-operator capability write names the operator without naming a merge
- [x] 1.2 Correct `save_document`'s docstring in `hub/hub/spec_service.py` so it describes the check it actually performs — the operator writes a capability document; a merge is one way, not the only way
- [x] 1.3 Correct the `capability_write_is_the_operators` refusal message for the same reason, leaving the code unchanged
- [x] 1.4 Confirm 1.1 passes and no existing test asserted the old wording

## 2. The operator content route

- [x] 2.1 Add a test that `PUT /documents/{path}/content` writes a capability document's content and leaves it in `current`
- [x] 2.2 Add a test that the same route writes a `change-spec` document being explored
- [x] 2.3 Add a test that an agent submitting against a capability document is still refused, and the content is unchanged
- [x] 2.4 Add tests that the operator gets the same refusals as an agent — invalid payload names its field, a mismatched `kind` is refused, and an approved document is refused until reopened
- [x] 2.5 Add a test that a document at `contract`/`gate` rigor records a pending proposal for an operator write rather than writing
- [x] 2.6 Add a test that the route rejects a credential that is not the operator's
- [x] 2.7 Implement `PUT /documents/{path}/content` in `hub/hub/api/v1/spec.py`, calling `save_document` with `Actor(kind="operator", ...)` and adding no rules of its own
- [x] 2.8 Confirm 2.1–2.6 pass

## 3. Attribution

- [x] 3.1 Add a test that an operator write records an event whose actor kind is the operator and whose run id is unset
- [x] 3.2 Add a test that an agent write still records the agent and its run
- [x] 3.3 Add a test that an actor or run named in the request body is disregarded in favour of the credential
- [x] 3.4 Confirm 3.1–3.3 pass

## 4. Verification

- [ ] 4.1 Run the full `hub/tests/` suite and confirm no regression against the 2521-passed baseline
- [x] 4.2 Run `py -3.11 -m ruff check` and `py -3.11 -m black --check` on every changed file
- [ ] 4.3 Import two real openspec capabilities end to end against a throwaway project, and confirm both render, index and read back with the requirements the source declared
- [x] 4.4 Perform one mutation check: revert the operator actor to an agent actor, watch a named test fail, restore it
- [ ] 4.5 Record any friction this change surfaced in `openspec/explorations/2026-08-20-dogfooding-findings.md`
