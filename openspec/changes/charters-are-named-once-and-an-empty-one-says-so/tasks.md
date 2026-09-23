## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: independently re-derive design's Context table; find every writer of `Charter.content` and `Charter.name` (the two routes, the starter seeding in `db/engine.py` and `project_lifecycle.py`, any migration) and check each against D1 and D3; check whether seeding a project can collide with D4's unique index. Re-run the two `mode=ro` counts on `:8000`. Record in design's round log
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate charters-are-named-once-and-an-empty-one-says-so --strict` passes
- [ ] 0.3 The operator records the F134 and F183 decisions in `spec-queue/DECISIONS.md`, and design Open Question 1

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 (F134) `hub/tests/test_charters_api.py`: `POST /charters {"name":"blank","content":""}` and `{"content":"  \n"}` each answer 422 with `content` in `loc`, and no row exists. Record that both FAIL today (201)
- [ ] 1.2 (F134) Same file: `PATCH` an existing charter to `content: ""` answers 422 and the stored content is unchanged. Record that it FAILS today
- [ ] 1.3 (F134) Control: content with leading and trailing whitespace around text is stored exactly as sent (not stripped)
- [ ] 1.4 (F134) `hub/tests/test_charter_context.py`: insert a blank-content charter directly (bypassing the route), bind it, read `agent-context`: the context contains `This charter is empty` under `## Charter: <name>`, and `missing` contains `"charter content"`. Record that it FAILS today (bare heading, `missing == []`)
- [ ] 1.5 (F183) `test_charters_api.py`: a second `POST` with an existing name answers 409 naming it; a `PATCH` renaming another charter to it answers 409 and the name is unchanged. Record that both FAIL today
- [ ] 1.6 (F183) Control: the same name in a second project is accepted; a `PATCH` that re-sends a charter's own name is accepted
- [ ] 1.7 (F183) Migration test: a database at `0105` holding three charters named `X` in one project (bound to three agents) upgrades to: `X`, `X (2)`, `X (3)` by age, the same `charter_id` on every agent, and a unique index. Downgrade restores the plain index
- [ ] 1.8 (F183) With the unique index in place, a direct duplicate insert raises `IntegrityError`, and the route turns a race into the same 409 (simulate by patching the pre-check to find nothing)

## 2. The fix

- [ ] 2.1 `schemas/common.py`: `VisibleText` (D1). `schemas/charters.py`: use it for `content` on create and update
- [ ] 2.2 `api/v1/agents.py:2108-2118`: D2
- [ ] 2.3 `api/v1/charters.py`: D3 on create and update, and the `IntegrityError` → 409
- [ ] 2.4 `db/models.py:366`: `unique=True`; the migration per D4 and `.claude/rules/db-migrations.md`
- [ ] 2.5 Group 1, then `py -3.11 -m pytest hub/tests/ -q`; record counts inline or do not tick
- [ ] 2.6 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`

## 3. Drive it

- [ ] 3.1 On a trial Hub, in the Charters screen: save a charter with empty content (the form shows the refusal), create a second charter under an existing name (refused with the name), and open the binding picker (no duplicate names)
