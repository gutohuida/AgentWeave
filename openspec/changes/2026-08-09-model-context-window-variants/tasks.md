# Tasks — a model may offer more than one context window

## 1. The declaration

- [ ] 1.1 A window-variant descriptor: the model id that selects it, a label, its own context
      window. Declared on the model, not as a control — a control renders to argv through an
      `ApplySpec`, and this changes the model id itself, which `build_command` applies by its own
      dedicated path
- [ ] 1.2 `ModelDescriptor` gains the variant tuple, defaulting to empty. Empty means one window
      and nothing to choose, so every existing entry is unchanged by construction
- [ ] 1.3 Declare Haiku 4.5's two windows: 200,000 at the base id, 1,000,000 at `[1m]`
- [ ] 1.4 Declare **no** variants for Opus 5, Sonnet 5, Fable 5 — live-verified as the same
      1,000,000 with and without the suffix on this subscription. Record the evidence in the
      docstring, including that this is a subscription property and not a model one

## 2. Resolution and validation

- [ ] 2.1 `context_window_for_model` resolves a variant id to the variant's own window, and does
      so **before** the longest-declared-prefix fallback — `claude-haiku-4-5-20251001[1m]` starts
      with `claude-haiku-4-5-20251001`, so the existing prefix rule would otherwise answer 200,000
      for the 1M variant. This is the defect the ordering exists to prevent; it needs its own test
- [ ] 2.2 `ProviderDescriptor.model` and `validate_overrides` accept a variant id as a model
- [ ] 2.3 `_reject_undeclared_model` accepts one too, so a runner can be bound to a variant

## 3. The catalog's own honesty

- [ ] 3.1 Correct the stale docstring paragraph: Opus 5 and Fable 5 are live-verified at
      1,000,000, which is what they already declare
- [ ] 3.2 The existing test asserting the catalog and `mcp_server.py` agree still passes, or is
      extended if variants cross that boundary

## 4. The surface

- [ ] 4.1 Variants on the catalog schema and endpoint
- [ ] 4.2 A "Context" pill beside the model pill, rendered **only** when the selected model
      declares more than one window, on the same `ControlPill` shape every other composer control
      uses — no private visual dialect
- [ ] 4.3 Selecting a variant sets the model override to the variant's id. Nothing downstream
      learns a new concept
- [ ] 4.4 `ModelPicker`'s current-model lookup recognises a variant id, or the model pill reads
      "—" whenever a variant is selected

## 5. Verification

- [ ] 5.1 `pytest hub/tests/`, `npx vitest run`, `npx tsc --noEmit`, `ruff check`
- [ ] 5.2 `npm run build` + copy to `hub/hub/static/ui`, confirmed with `diff -rq`
- [ ] 5.3 Live: select the Haiku 1M variant and confirm the Hub passes the suffixed id through to
      the spawn. On this subscription the provider refuses it for entitlement — **record that
      refusal as the observed result rather than reporting the task as passing**, since the
      selection reaching the CLI intact is what this change is responsible for
