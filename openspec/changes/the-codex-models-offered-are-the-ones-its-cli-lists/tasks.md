## 0. Rounds and decision

- [x] 0.1 R2: re-derive the proposal independently. Grep every read of `CATALOG` and every caller of `get_provider`, `providers` and `context_window_for_model`, including `scripts/` and `tests/`. Re-measure `scripts/check_model_catalog.py` and the real cache's shape (`priority`, `visibility`, encoding). Check whether anything in Docker mode (`AW_WORKSPACE_ROOT`) spawns Codex from a different home than the Hub process's. Record the result in `design.md`'s round log
- [x] 0.2 R3: a second independent re-derivation. `openspec validate the-codex-models-offered-are-the-ones-its-cli-lists --strict` passes
- [ ] 0.3 The operator answers D2's source question (runtime read / regenerate at release), recorded in `spec-queue/DECISIONS.md`

## 1. Tests first

- [ ] 1.1 Add the conftest guard (design D4) and design test 8. Confirm it passes with the guard and fails on this machine without it (remove the guard, run it, restore the guard)
- [ ] 1.2 Design tests 1–7 in `hub/tests/test_codex_models_from_the_cli_cache.py`. Record which fail today (1, 6 and 7 must; 2 must pass as a control once `source` exists)
- [ ] 1.3 Design test 9 (UI)

## 2. The fix

- [ ] 2.1 `model_catalog.py`: `_codex_cache_path`, `_codex_models_from_cache` and `_effective_catalog`, and route the four readers through them (design D1). Rewrite the docstring's Codex paragraph so it describes the runtime read and the fallback
- [ ] 2.2 `schemas/model_catalog.py`: add `source`, filled by `api/v1/model_catalog.py`
- [ ] 2.3 `scripts/check_model_catalog.py`: add a docstring paragraph (design D3)
- [ ] 2.4 UI: the source line in the runner form. Refresh the bundle and commit `hub/ui/src` and `hub/hub/static/ui` together
- [ ] 2.5 Run `py -3.11 -m pytest hub/tests/ -q` with `claude` stripped from PATH, then the CLAUDE.md lint block

## 3. Drive (no Codex spawn: Codex is undrivable, 2026-08-29)

- [ ] 3.1 On the trial Hub `:8010`: `GET /api/v1/model-catalog` should list this machine's cached Codex models (`gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5` at 0.146.0) with `source.kind == "cli_cache"`. Record it verbatim
- [ ] 3.2 `POST /runners {"cli":"codex","model":"gpt-6-sol"}` answers 400 on this machine, and an existing runner on it (seed one through SQL on the trial database only) reads `model_unrecognised: true`
- [ ] 3.3 Open New runner, choose Codex, and read the source line. Record it verbatim
