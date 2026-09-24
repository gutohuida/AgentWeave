## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: independently re-derive design's Context table; find every writer of `Charter.content` and `Charter.name` (the two routes, the starter seeding in `db/engine.py` and `project_lifecycle.py`, any migration) and check each against D1 and D3; check whether seeding a project can collide with D4's unique index. Re-run the two `mode=ro` counts on `:8000`. Record in design's round log
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate charters-are-named-once-and-an-empty-one-says-so --strict` passes
- [x] 0.3 The operator records the F134 and F183 decisions (review `spec-queue/tracks/reviews/B11-2026-09-24.md` §6, 2026-09-24: runners folded in, exact match, door 3 suffixes); design Open Question 1 is closed

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 (F134) `hub/tests/test_charters_api.py`: `POST /charters {"name":"blank","content":""}` and `{"content":"  \n"}` each answer 422 with `content` in `loc`, and no row exists. Record that both FAIL today (201)
- [ ] 1.2 (F134) Same file: `PATCH` an existing charter to `content: ""` answers 422 and the stored content is unchanged. Record that it FAILS today
- [ ] 1.3 (F134) Control: content with leading and trailing whitespace around text is stored exactly as sent (not stripped)
- [ ] 1.4 (F134) `hub/tests/test_charter_context.py`: insert a blank-content charter directly (bypassing the route), bind it, read `agent-context`: the context contains `This charter is empty` under `## Charter: <name>`, and `missing` contains `"charter content"`. Record that it FAILS today (bare heading, `missing == []`)
- [ ] 1.5 (F183) `test_charters_api.py`: a second `POST` with an existing name answers 409 naming it; a `PATCH` renaming another charter to it answers 409 and the name is unchanged. Record that both FAIL today
- [ ] 1.6 (F183) Control: the same name in a second project is accepted; a `PATCH` that re-sends a charter's own name is accepted
- [ ] 1.7 (F183) Migration test: a database at `0105` holding three charters named `X` in one project (bound to three agents) upgrades to: `X`, `X (2)`, `X (3)` by age, the same `charter_id` on every agent, and a unique index. Downgrade restores the plain index
- [ ] 1.8 (F183) With the unique index in place, a direct duplicate insert raises `IntegrityError`, and the route turns a race into the same 409 (simulate by patching the pre-check to find nothing)
- [ ] 1.9 (F183, runners) `hub/tests/test_runners_api.py`: a second `POST /runners` with an existing name answers 409 whose detail names the name (not "Runner with that ID already exists"); a `PATCH` renaming another runner to it answers 409 and the name is unchanged. Record that both FAIL today (201 / 200)
- [ ] 1.10 (F183, runners) Controls: the same runner name in a second project is accepted; a `PATCH` re-sending a runner's own name is accepted; `Coder` beside `coder` is accepted in both tables (exact match)
- [ ] 1.11 (F183, runners) Race: with the pre-check patched to find nothing, a duplicate `POST /runners` and a duplicate-name `PATCH /runners/{id}` each answer 409 naming the name, not 500. Record that the `PATCH` answers 500 today once the index exists (it has no catch)
- [ ] 1.12 (door 3) `hub/tests/test_operator_agent_creation.py`: create a `claude` runner on model A named exactly what find-or-create would name model B (`"{provider label} — {model B label}"`), then `POST /agents` by provider `claude` and model B: 201, a new runner named `"… (2)"`, the operator's runner untouched. With the index in place and no fix this answers 500; record it. Also: when `"… (2)"` is taken too, the new runner is `"… (3)"`
- [ ] 1.13 (door 3) Race: with the free-name pick patched to return a taken name, `POST /agents` answers 409 (retry), and neither the runner nor the agent exists afterwards
- [ ] 1.14 (D4) Migration test, runners: a database at `0105` holding three runners named `R` in one project (each bound to an agent) upgrades to `R`, `R (2)`, `R (3)` by age with every `runner_id` unchanged, and a unique `ix_runners_project_name`; downgrade restores **both** plain indexes. Record that the runner half fails before the fix
- [ ] 1.15 (D4) Migration edge cases, charters and runners alike: two `X` beside an existing `X (2)` become `X` and `X (3)` (`X (2)` untouched); two rows named `X (2)` become `X (2)` and `X (2) (2)`; two 256-character names become the name and its first 252 characters plus ` (2)` (256 total). Both tables keep their `rowid`s across the upgrade (no table rebuild)
- [ ] 1.16 (D4) Each missing-table guard alone: a database with `charters` but no `runners` (and the reverse) upgrades without error

## 2. The fix

- [ ] 2.1 `schemas/common.py`: `VisibleText` (D1). `schemas/charters.py`: use it for `content` on create and update
- [ ] 2.2 `api/v1/agents.py:2108-2118`: D2
- [ ] 2.3 `api/v1/charters.py`: D3 on create and update, and the `IntegrityError` → 409
- [ ] 2.4 `db/models.py:341` and `:366`: `unique=True`; one migration per D4 (both tables, own guards, `op.drop_index`/`op.create_index` only, never `batch_alter_table`, 256-character `_suffixed`) and `.claude/rules/db-migrations.md` (head assertions in `test_migrations.py` and `test_project_persistence.py`)
- [ ] 2.4a `api/v1/runners.py`: D3 on create and update; replace the "Runner with that ID already exists" catch; add the catch `update_runner` lacks; the free-name helper for D5
- [ ] 2.4b `api/v1/agents.py:701-717`, `:743`: D5 (free suffixed name; `IntegrityError` at the commit → rollback → 409)
- [ ] 2.5 Group 1, then `py -3.11 -m pytest hub/tests/ -q`; record counts inline or do not tick
- [ ] 2.6 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`

## 3. Drive it

- [ ] 3.1 On a trial Hub, in the Charters screen: save a charter with empty content (the form shows the refusal), create a second charter under an existing name (refused with the name), and open the binding picker (no duplicate names)
- [ ] 3.2 On a trial Hub, in the Runners screen: create a runner under an existing name and rename another to it (both refused with the name, shown in the form); name a runner `Claude Code — <model B label>`, then create an agent by provider and model B and see a runner `… (2)` appear
