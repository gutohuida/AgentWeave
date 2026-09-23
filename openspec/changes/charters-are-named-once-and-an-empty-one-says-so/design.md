# Design — charters are named once, and an empty one says so

**Built on the recommended answers to B11's F134 and F183 questions** (ROUNDS.md D13, *"an empty
charter"* and *"charter name uniqueness"*): **refuse empty content at both write doors and render any
empty row honestly (F134); refuse a duplicate name at both doors and enforce it with a unique index
(F183).** Independent halves: if the operator answers one otherwise, drop its D-sections, tasks and
requirement.

## Context — measured on `ce086b6`

| Fact | Where |
|---|---|
| `content: str` unconstrained on create and update | `hub/hub/schemas/charters.py:13`, `:18` |
| `name: VisibleName` (stripped; blank refused) on both | `charters.py:12`, `:17`; `hub/hub/schemas/common.py:8-18` |
| Create and update write the body straight to the row | `hub/hub/api/v1/charters.py:18-34`, `:62-80` |
| Render tests the row, so an empty charter takes the "has a charter" branch | `hub/hub/api/v1/agents.py:2108-2118` |
| `missing` is returned by the context route; no UI reads it | `agents.py:2131`; `grep -rn "\.missing" hub/ui/src` finds only spec and checkpoint types |
| The charter index is not unique | `hub/hub/db/models.py:366`; migration `0023` line 46 |
| Agents: 409 on a duplicate name, and a unique index that renamed pre-existing duplicates | `api/v1/agents.py:682` (F183 cited `:612-617`; it has moved), migration `0063` |
| `:8000` today: no blank-content charter, no duplicate charter name | `mode=ro` query, 2026-09-24 |
| The migration head | `0105_clear_archived_agent_charter_bindings.py` |

## D1 — Content must contain a visible character

```python
def _has_visible(value: str) -> str:
    if not value.strip():
        raise ValueError("must contain a visible character")
    return value                     # stored as written, not stripped

VisibleText = Annotated[str, AfterValidator(_has_visible)]
```

Not `VisibleName`: that strips what it stores and caps at 256 characters, both wrong for a markdown
body. `CharterCreate.content: VisibleText`; `CharterUpdate.content: Optional[VisibleText] = None`
(absent still means "unchanged"). A blank body answers 422 with `loc: ["body", "content"]`.

**Why refuse rather than accept and render a notice** (F134's option 1 against 2 and 3): an empty
charter is not a draft the Hub can hold for later, since binding and rendering it both happen
immediately. An operator mid-edit loses nothing: the form keeps their text and shows the 422.

## D2 — An empty row still renders honestly

Rows written before D1, or seeded by a path that bypasses the schema, can still be blank. So:

```python
if charter and charter.content.strip():
    ...  # as today
elif charter:
    lines += [f"## Charter: {charter.name}", "",
              "This charter is empty, so it sets out no behaviour for you.", ""]
    missing.append("charter content")
else:
    ...  # as today
```

The heading still names the bound charter (the agent is bound to it), and the sentence says what is
true of it. `"charter content"`, not `"charter"`, because a charter is assigned.

## D3 — A name is used once per project

Before writing, on create and on a rename that changes the name:

```python
clash = await session.scalar(select(Charter.id).where(
    Charter.project_id == project_id, Charter.name == name, Charter.id != this_id))
if clash: raise HTTPException(409, f"A charter named '{name}' already exists in this project")
```

Exact match on the stored (already stripped) name, as agents compare. The `IntegrityError` from D4's
index is also caught and answered with the same 409, which closes the check-then-insert race the way
`0063`'s docstring describes for agents.

**What the routes return when the new code raises:** the check is a read before any write; the
commit's `IntegrityError` becomes the 409; any other exception is unchanged (500).

## D4 — The index, and what happens to duplicates that exist

A new migration drops `ix_charters_project_name` and recreates it `unique=True`. Before that, per
project, any name held by more than one charter keeps it on the oldest row (by `created_at`, then
`rowid`) and each later one becomes `<name> (2)`, `(3)`, … retrying past a suffix already taken.
Rename, never delete: an agent binds by `charter_id`, so every binding survives. `0063` made the same
choice for the same three reasons. `downgrade()` restores the plain index and leaves names as they
are. On `:8000`, measured, there is nothing to rename. On the trial databases that the sweeps
filled, there is (F134's drive left six `sweep-charter` rows).

Follow `.claude/rules/db-migrations.md`'s checklist, including the missing-table guard `0090`
needed for tests that synthesize a database from an earlier revision.

## Open questions

1. Runner names have the same gap (`ix_runners_project_name` is plain; `runners.py` checks nothing),
   and they are also chosen from a picker by name. Fold runners into D3/D4, or file them as their own
   finding? Recommended: file separately; this change stays with the findings it was built for.

## Round log

- R1 2026-09-24: written.
