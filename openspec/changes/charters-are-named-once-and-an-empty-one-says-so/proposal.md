# Proposal — charters are named once, and an empty one says so

**Round 1, 2026-09-24** (bundle B11, `spec-queue/tracks/B11.md`). Findings: **F134 (B)** and
**F183 (C)**. Both are about what a charter is allowed to be, both are write-door rules on
`hub/hub/api/v1/charters.py`, and both land in `agent-charter`. Re-verified on `ce086b6`.
**Nothing here is implemented yet.**

## Why

**F134: a charter with no content is delivered as a bare heading.** `CharterCreate.content` and
`CharterUpdate.content` are unconstrained `str` (`hub/hub/schemas/charters.py:13`, `:18`), while the
name is a `VisibleName` (`:12`, `:17`; `schemas/common.py:18`). So `POST /charters {"content": ""}`
and a `PATCH` that blanks a charter both succeed. The context renderer tests the row, not its text:

```python
# hub/hub/api/v1/agents.py:2108-2118
if charter:
    lines.append(f"## Charter: {charter.name}")
    lines.append("")
    lines.append(charter.content)          # ""
    ...
else:
    ... "No charter is assigned to this agent." ...
    missing.append("charter")
```

An agent bound to it reads a heading that promises a behaviour contract and then nothing, on every
turn, and the context response's `missing` stays empty. Measured on `:8000` (read-only): **0**
charters with blank content today, so nothing real is affected yet.

**F183: two charters can share a name, and the picker shows only names.** Neither
`create_charter` (`charters.py:18-34`) nor `update_charter` (`:62-80`) checks names, and
`ix_charters_project_name` is a plain index (`db/models.py:366`, migration `0023`). The binding
picker renders `{charter.name}` as each option (`AgentSettingsControls.tsx`, F183's entry), so two
charters called `Code Reviewer` cannot be told apart where the choice is made; a drive measured four.
Agents already refuse a duplicate name with a 409 and a unique index (migration `0063`). Measured on
`:8000` (read-only): **no** duplicate charter names today.

## What Changes

- **A charter's content must say something** (design D1): `content` becomes a `VisibleText` (the
  same strip-and-refuse rule `VisibleName` applies, without the 256-character cap) on create and on
  update. A blank create or blanking update answers 422 naming the field. The charter form already
  renders its own 422 (F187, UI-1).
- **A charter that is empty anyway says so** (design D2). A row written before this, or by a path
  that bypasses the schema, renders as *"This charter is empty, so it sets out no behaviour for
  you."*, and `missing` gains `"charter content"`.
- **A name is used once per project** (design D3). Create and rename refuse a name another charter
  in the project already has, with a 409 naming it, as agents do.
- **The database enforces it** (design D4). A new migration (the next free revision at IMPL time; `0105` is the head on `ce086b6`) makes `ix_charters_project_name`
  unique, renaming any pre-existing duplicate to `<name> (2)`, `(3)`, oldest keeping the name. On
  `:8000`, measured, it renames nothing.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-charter`: two new requirements, *A charter's content states something* and *A charter's
  name is unique within its project*.

## Impact

- `hub/hub/schemas/common.py` (a `VisibleText`), `hub/hub/schemas/charters.py`,
  `hub/hub/api/v1/charters.py`, `hub/hub/api/v1/agents.py:2108-2118`, `hub/hub/db/models.py:366`,
  a new migration.
- **A migration**: it runs on `:8000` at its next restart (the operator's call). It renames nothing
  there, measured today.
- `hub/tests/test_charters_api.py`, `hub/tests/test_charter_context.py`, and a migration test.
- **Not in scope, same shape:** runner names have no uniqueness rule either
  (`ix_runners_project_name` is plain; `runners.py` checks none), and `VisibleName`'s own comment
  groups runners with charters. Design Open Question 1.
