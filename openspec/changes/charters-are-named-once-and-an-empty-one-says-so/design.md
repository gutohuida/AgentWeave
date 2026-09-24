# Design — charters are named once, and an empty one says so

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B11-2026-09-24.md` §6) answered **APPROVE
WITH FIXES (runners added)**. The operator decided, and this revision applies:

- **Runners are folded in** (was Open Question 1, now removed): an ADDED `runner-registry`
  requirement; D3 covers the two runner routes, D5 the find-or-create door, D4 the runner index.
- **Door 3 suffixes.** `POST /agents`' find-or-create picks a free suffixed name rather than
  answering 500 when an operator-named runner holds the generated one (D5).
- **Exact match**, as agent names are: `BINARY` collation, stated in both requirements (D3).
- **Suffixes are truncated** to the 256-character column, as `0063._suffixed` truncates to 32 (D4).
- **No `batch_alter_table`**: the migration only drops and creates indexes, so neither table is
  rebuilt and F177's `rowid` ordering survives (D4).
- **D4's "six sweep-charter duplicates" was wrong**: re-measured `mode=ro` on the trial database
  (`~/.agentweave/hub/profiles/trial/agentweave.db`, at `0105`) it holds no duplicate charter or
  runner name and no `sweep%` charter at all. Corrected below.

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
| The runner index is not unique | `hub/hub/db/models.py:341`; migration `0023` line 34 |
| `POST /runners` checks no name; its `IntegrityError` answers "Runner with that ID already exists" | `hub/hub/api/v1/runners.py:47-75` (catch at `:65-70`) |
| `PATCH /runners/{id}` renames with no check and catches nothing | `runners.py:134-161` (rename `:146-147`, commit `:159`) |
| `POST /agents` by provider and model creates `"{provider.label} — {model.label}"`, committed with the agent | `hub/hub/api/v1/agents.py:701-717`, commit `:743` (no `IntegrityError` handler) |
| Runner names are `VisibleName` (≤256, stripped) and `String(256)` | `hub/hub/schemas/runners.py:14`, `:28`; `models.py:328` |
| Runner seeding inserts `"{Cli} (default)"` per CLI only into a project with no runners, or a new one | `db/engine.py:246-259`; `project_lifecycle.py:298-307` |
| Agents: 409 on a duplicate name, and a unique index that renamed pre-existing duplicates | `api/v1/agents.py:682` (F183 cited `:612-617`; it has moved), migration `0063` |
| `:8000` and the trial DB today: no blank-content charter, no duplicate charter or runner name (exact or case-folded); longest names 21 (charter) and 23 (runner) | `mode=ro` queries, 2026-09-24; both at `0105` |
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

## D3 — A name is used once per project (charters and runners)

Before writing, on create and on a rename that changes the name, for charters (`charters.py`) and
identically for runners (`runners.py`: door 1 `POST /runners`, door 2 `PATCH /runners/{id}`):

```python
clash = await session.scalar(select(Charter.id).where(
    Charter.project_id == project_id, Charter.name == name, Charter.id != this_id))
if clash: raise HTTPException(409, f"A charter named '{name}' already exists in this project")
```

Exact match on the stored (already stripped) name, as agents compare: SQLite's default `BINARY`
collation, so `Coder` and `coder` are two different names, both in the pre-check and in D4's index.
This is the operator's decision (review §6), matching `ix_agents_project_name`. The `IntegrityError`
from D4's index is also caught and answered with the same 409, which closes the check-then-insert race
the way `0063`'s docstring describes for agents. For runners that replaces `create_runner`'s current
catch, whose *"Runner with that ID already exists"* could never be true (ids are fresh `short_id`s),
and adds the catch `update_runner` lacks today (`runners.py:159` commits unguarded).

**What the routes return when the new code raises:** the check is a read before any write; the
commit's `IntegrityError` becomes the 409; any other exception is unchanged (500).

## D4 — The indexes, and what happens to duplicates that exist

One new migration handles both tables, each behind **its own** missing-table guard (a database
synthesized from an early revision may lack either). For each of `charters` and `runners`: per
project, any name held by more than one row keeps it on the oldest row (by `created_at`, then
`rowid`) and each later one becomes `<name> (2)`, `(3)`, … retrying past a suffix already taken.
The candidate is checked against every row in the project, so a rename never creates a new clash:
`X`, `X` beside an existing `X (2)` gives `X`, `X (3)`, `X (2)`; two rows named `X (2)` give
`X (2)` and `X (2) (2)`. Then `op.drop_index` the plain index and `op.create_index(..., unique=True)`,
as `0063` does (`0063_*.py:104-113`).

**Truncation.** Names are `String(256)`. The suffix is kept whole and the name is cut to make room,
as `0063._suffixed` (`0063_*.py:67-70`) cuts to 32:

```python
_MAX_NAME = 256
def _suffixed(name: str, ordinal: int) -> str:
    suffix = f" ({ordinal})"
    return f"{name[: _MAX_NAME - len(suffix)]}{suffix}"
```

**No `batch_alter_table`.** SQLite's batch mode recreates the table, which would renumber the
`rowid`s F177's ordering reads; creating and dropping an index needs no rebuild, so neither table is
recreated.

Rename, never delete: an agent binds by `charter_id` and `runner_id`, so every binding survives.
`0063` made the same choice for the same three reasons. `downgrade()` restores **both** plain indexes
and leaves names as they are. On `:8000` and on the trial database, measured `mode=ro` on
2026-09-24, there is nothing to rename. (R1 claimed the trial databases held six `sweep-charter`
duplicates from F134's drive; the review's re-measurement found none, and neither did this revision.)

Follow `.claude/rules/db-migrations.md`'s checklist, including the missing-table guard and the head
assertions in `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`.

**Seeding stays safe.** Runner seeding inserts `Claude (default)` and `Codex (default)` only into a
project with no runners (`db/engine.py:246-259`) or a brand-new one (`project_lifecycle.py:298-307`);
the two names differ, so the unique index cannot make seeding raise. The charter seeds insert the
manifest's distinct names only into a project with no charters.

## D5 — A runner the Hub names itself takes a free name

`POST /agents` with a provider and model reuses a runner matching `(cli, model)` or creates one named
`f"{provider_entry.label} — {model_entry.label}"` (`agents.py:701-717`). With D4's index, if the
operator already gave some *other* runner that name, the commit at `:743` would raise
`IntegrityError` and answer 500. Instead, before creating, the route picks the first free name among
the base, `base (2)`, `base (3)`, … with D4's truncation, through a small helper in
`api/v1/runners.py` (the migration keeps its own copy, since a migration does not import app code).
The operator can rename it afterwards.

`a-model-alias-is-a-model-choice` changes the base at `agents.py:713` to `"{provider} — {alias}
(latest)"`; whichever lands second applies the helper to that base. No other rule changes.

**What the route returns when the new code raises.** A concurrent create can still take the chosen
name (or the agent's own name, `ix_agents_project_name`) between the check and `:743`; today that
race already answers 500 for the agent's name. The commit is wrapped: `IntegrityError` → rollback →
409 *"A runner or agent with that name was created at the same moment; retry."*, and neither row is
kept, as the comment at `:690-693` promises. Any other exception is unchanged.

## Open questions

None. (Open Question 1, whether to fold runners in, was answered yes by the operator on 2026-09-24.)

## Round log

- R1 2026-09-24: written.
- R2 2026-09-24: schema, both doors and the index re-read (`schemas/charters.py:11-18`,
  `charters.py:10-70`, `models.py:366`). The two seed paths (`db/engine.py:265-291`,
  `project_lifecycle.py:311-321`) insert the manifest's names only into a project with no charters,
  and the manifest's names are distinct, so the unique index cannot make seeding raise. No claim
  disagreed.
- R3 2026-09-24: recorded at bundle level (`spec-queue/tracks/B11.md`, "R3 — independent
  comparison", from line 584); it re-read F134 and F183 and agreed.
- Review fixes 2026-09-24 (`spec-queue/tracks/reviews/B11-2026-09-24.md` §6): runners folded in
  (ADDED `runner-registry` requirement; D3 for doors 1-2; D5 for door 3 with suffixing and the
  commit race); exact match stated; truncation; no batch mode; D4's sweep-charter claim corrected.
  Every citation re-checked on HEAD (`runners.py:47-75`, `:134-161`; `agents.py:674-683`,
  `:701-717`, `:743`, `:2108-2131`; `models.py:328`, `:341`, `:366`; `0063_*.py:67-113`;
  `engine.py:246-259`; `project_lifecycle.py:298-321`; head `0105`). Trial DB and `:8000` re-measured
  `mode=ro`: no exact or case-folded duplicate in either table, no blank charter.
