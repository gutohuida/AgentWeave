"""A materialised task carries the criteria its requirements state.

`materialise()` wrote nine fields and not `acceptance_criteria`, so every task the document's own
decomposition created arrived with no standard on it — measured against the live database: of 32
spec-materialised tasks, **32 carried NULL** and none carried `[]`. The field was never written
rather than written empty. Meanwhile the briefing that reaches both the implementer and the reviewer
renders `acceptance_criteria` and nothing else of the document's statement of done
(`scheduler.py`), so what the document required reached neither of them.

Each test below pins a scenario from `specs/spec-document-authority/spec.md`. Most call
`materialise()` directly: the payloads that discriminate the correct implementation from a naive one
are, for the most part, payloads `validate_payload` refuses on submission — and that is the
realistic case rather than a contrived one, because the approval route parses the file with
`extract_payload` and `spec_adoption` never validates at all. The first test goes the whole way
through the HTTP approval route, so nothing here rests on the unit alone.
"""

import pytest
from sqlalchemy import select

from hub import spec_reading, spec_tasks
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    Loop,
    Run,
    SpecDocument,
    SpecRequirement,
    Task,
    TaskRequirementLink,
)
from hub.scheduler import _compose_loop_briefing
from hub.spec_lifecycle import Actor
from hub.spec_payload import SCHEMA_VERSION

PROJECT = "proj-test"
ACTOR = Actor(kind="operator", name="operator")
DIGEST = "d" * 64

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/criteria-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It records a completed watering", "modal": "SHOULD"}

AC_ALPHA = {
    "key": "ac-alpha",
    "requirement": "alpha",
    "given": "two plants are due",
    "when": "the list is shown",
    "then": "both appear",
}
AC_BETA = {
    "key": "ac-beta",
    "requirement": "beta",
    "given": "one has been watered",
    "when": "it is recorded",
    "then": "the log shows it",
}

RENDERED_ALPHA = "ac-alpha: Given two plants are due, when the list is shown, then both appear"
RENDERED_BETA = "ac-beta: Given one has been watered, when it is recorded, then the log shows it"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
async def author():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-crit", project_id=PROJECT, name="author"))
        session.add(
            Run(
                id="run-crit",
                project_id=PROJECT,
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_crit-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_crit-secret"}


async def _document(db, suffix, *, keys=("alpha", "beta")):
    """A document row and the requirement index a real approval would already have built."""
    document = SpecDocument(
        id=f"doc-crit-{suffix}",
        project_id=PROJECT,
        path=f"spec/changes/criteria-{suffix}/spec.html",
        title=f"Criteria {suffix}",
        phase="approved",
        kind="change-spec",
    )
    db.add(document)
    for index, key in enumerate(keys, start=1):
        db.add(
            SpecRequirement(
                id=f"req-crit-{suffix}-{index}",
                project_id=PROJECT,
                document_id=document.id,
                identifier=f"FR-{index}",
                key=key,
                digest=DIGEST,
            )
        )
    await db.commit()
    return document


async def _materialise(suffix, payload, *, keys=("alpha", "beta"), quietly=False):
    """Create *payload*'s tasks against a fresh document. Returns `{spec_task_key: Task}`.

    The session factory sets `expire_on_commit=False`, so the returned rows stay readable after the
    session closes.
    """
    async with async_session_factory() as db:
        document = await _document(db, suffix, keys=keys)
        create = spec_tasks.materialise_quietly if quietly else spec_tasks.materialise
        created = await create(db, document, payload, actor=ACTOR)
        await db.commit()
    return {task.spec_task_key: task for task in created}


def _entry(key, *, requirements=None, description=None):
    entry = {"key": key, "description": description or f"Build {key}."}
    if requirements is not None:
        entry["requirements"] = list(requirements)
    return entry


async def _identifiers_for(task_id):
    """The requirement identifiers a created task actually resolved to."""
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(SpecRequirement.identifier)
                    .join(
                        TaskRequirementLink,
                        TaskRequirementLink.requirement_id == SpecRequirement.id,
                    )
                    .where(TaskRequirementLink.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )
    return sorted(rows)


class _Row:
    """A requirement row for the pure-function view, duck-typed as `test_spec_reading.py` does."""

    def __init__(self, identifier, key):
        self.identifier = identifier
        self.key = key
        self.state = "active"
        self.anchor = ""


# ---------------------------------------------------------------------------
# 3.1-3.3, 3.8, 3.13 — what the document says reaches the task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_3_1_a_tasks_criteria_follow_its_requirements(app, auth_headers, author):
    """The whole way through: submit, approve, read the board.

    Every other test here calls `materialise()` directly. This one does not, so that the claim
    "approving a document gives its tasks their criteria" rests on the route an operator uses
    rather than on the unit beneath it.
    """
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Criteria demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Criteria demo",
                "requirements": [ALPHA, BETA],
                "acceptance_criteria": [AC_ALPHA, AC_BETA],
                "tasks": [_entry("build-listing", requirements=["alpha"])],
            },
        },
        headers=author,
    )
    assert saved.status_code == 200, saved.text

    closed = await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )
    assert closed.status_code in (200, 409), closed.text
    for phase in ("proposed", "approved"):
        moved = await app.post(
            f"{BASE}/documents/phase",
            params={"path": PATH, "to": phase},
            json={"reason": "looks right"},
            headers=auth_headers,
        )
        assert moved.status_code == 200, moved.text

    listed = await app.get(TASKS, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    board = listed.json()["tasks"]
    assert len(board) == 1
    assert board[0]["acceptance_criteria"] == [RENDERED_ALPHA]


@pytest.mark.asyncio
async def test_3_2_criteria_belonging_to_other_requirements_are_not_attached(app):
    payload = {
        "requirements": [ALPHA, BETA],
        "acceptance_criteria": [AC_ALPHA, AC_BETA],
        "tasks": [_entry("listing", requirements=["alpha"])],
    }
    tasks = await _materialise("others", payload)
    assert tasks["listing"].acceptance_criteria == [RENDERED_ALPHA]


@pytest.mark.asyncio
async def test_3_3_a_task_naming_several_requirements_carries_all_their_criteria(app):
    payload = {
        "requirements": [ALPHA, BETA],
        "acceptance_criteria": [AC_ALPHA, AC_BETA],
        "tasks": [_entry("both", requirements=["alpha", "beta"])],
    }
    tasks = await _materialise("several", payload)
    assert tasks["both"].acceptance_criteria == [RENDERED_ALPHA, RENDERED_BETA]


@pytest.mark.asyncio
async def test_3_8_every_attached_criterion_carries_its_given_its_when_and_its_then(app):
    payload = {
        "requirements": [ALPHA],
        "acceptance_criteria": [AC_ALPHA],
        "tasks": [_entry("listing", requirements=["alpha"])],
    }
    tasks = await _materialise("parts", payload)
    (line,) = tasks["listing"].acceptance_criteria
    assert f"Given {AC_ALPHA['given']}" in line
    assert f"when {AC_ALPHA['when']}" in line
    assert f"then {AC_ALPHA['then']}" in line


@pytest.mark.asyncio
async def test_3_13_criteria_carry_their_key_and_are_distinguishable(app):
    """Design D2. The rendered string is the only carrier and D5 forbids backfill, so a criterion
    that arrives without its handle can never be matched back to the document."""
    second = dict(AC_ALPHA, key="ac-alpha-late", then="the overdue one is marked")
    payload = {
        "requirements": [ALPHA],
        "acceptance_criteria": [AC_ALPHA, second],
        "tasks": [_entry("listing", requirements=["alpha"])],
    }
    tasks = await _materialise("handles", payload)
    lines = tasks["listing"].acceptance_criteria
    assert len(lines) == 2
    assert lines[0].startswith("ac-alpha: ")
    assert lines[1].startswith("ac-alpha-late: ")
    assert lines[0] != lines[1]


# ---------------------------------------------------------------------------
# 3.4, 3.5, 3.21 — the cases that attach nothing, and must not refuse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_3_4_a_task_naming_no_requirement_carries_no_criteria(app):
    """Unset, not `[]` — which is what all 32 existing tasks carry, so a reader cannot tell a task
    that predates this change from one whose requirements state nothing."""
    payload = {
        "requirements": [ALPHA],
        "acceptance_criteria": [AC_ALPHA],
        "tasks": [_entry("chores")],
    }
    tasks = await _materialise("nameless", payload)
    assert list(tasks) == ["chores"]
    assert tasks["chores"].acceptance_criteria is None


@pytest.mark.asyncio
async def test_3_5_a_requirement_with_no_criteria_contributes_nothing(app):
    payload = {
        "requirements": [ALPHA, BETA],
        "acceptance_criteria": [AC_ALPHA],
        "tasks": [_entry("both", requirements=["alpha", "beta"])],
    }
    tasks = await _materialise("silent", payload)
    assert tasks["both"].acceptance_criteria == [RENDERED_ALPHA]


@pytest.mark.asyncio
async def test_3_21_an_entry_already_served_by_hand_made_work_creates_no_task(app):
    """The `already_served` skip. Scenario 1's premise is satisfiable while its conclusion fails:
    a declared entry whose requirements a hand-made task already covers creates nothing at all, so
    there is no task for criteria to reach — and the approval still must not be refused."""
    async with async_session_factory() as db:
        document = await _document(db, "served")
        hand_made = Task(
            id="task-hand-made",
            project_id=PROJECT,
            title="Somebody already started the listing",
            status="in_progress",
        )
        db.add(hand_made)
        await db.flush()
        db.add(
            TaskRequirementLink(
                id="trl-hand-made",
                project_id=PROJECT,
                task_id=hand_made.id,
                requirement_id="req-crit-served-1",
            )
        )
        await db.commit()

        created = await spec_tasks.materialise(
            db,
            document,
            {
                "requirements": [ALPHA, BETA],
                "acceptance_criteria": [AC_ALPHA, AC_BETA],
                "tasks": [
                    _entry("listing", requirements=["alpha"]),
                    _entry("recording", requirements=["beta"]),
                ],
            },
            actor=ACTOR,
        )
        await db.commit()

    by_key = {task.spec_task_key: task for task in created}
    assert list(by_key) == ["recording"]
    assert by_key["recording"].acceptance_criteria == [RENDERED_BETA]


# ---------------------------------------------------------------------------
# 3.6, 3.15, 3.23 — ordering (design D4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_3_6_criteria_for_one_requirement_keep_the_order_the_document_wrote(app):
    """The stable half of D4. The keys are deliberately **not** alphabetical: sorted by key they
    would come out `apple, mango, zebra`, so a key-sort produces a different list than written
    order and this discriminates between them."""
    written = [
        dict(AC_ALPHA, key="zebra"),
        dict(AC_ALPHA, key="apple"),
        dict(AC_ALPHA, key="mango"),
    ]
    payload = {
        "requirements": [ALPHA],
        "acceptance_criteria": written,
        "tasks": [_entry("listing", requirements=["alpha"])],
    }
    tasks = await _materialise("written-order", payload)
    assert [line.split(":")[0] for line in tasks["listing"].acceptance_criteria] == [
        "zebra",
        "apple",
        "mango",
    ]


@pytest.mark.asyncio
async def test_3_15_interleaved_criteria_follow_the_documents_requirement_order(app):
    """The cross-requirement half of D4, in the form that discriminates.

    The entry lists its requirements in the **reverse** of `payload.requirements` order, so an
    implementation that concatenates in the entry's own order yields `beta` first, and one that
    keeps raw `acceptance_criteria` position yields them interleaved. All three orders differ.
    """
    payload = {
        "requirements": [ALPHA, BETA],
        "acceptance_criteria": [
            dict(AC_ALPHA, key="alpha-1"),
            dict(AC_BETA, key="beta-1"),
            dict(AC_ALPHA, key="alpha-2"),
            dict(AC_BETA, key="beta-2"),
        ],
        "tasks": [_entry("both", requirements=["beta", "alpha"])],
    }
    tasks = await _materialise("interleaved", payload)
    assert [line.split(":")[0] for line in tasks["both"].acceptance_criteria] == [
        "alpha-1",
        "alpha-2",
        "beta-1",
        "beta-2",
    ]


@pytest.mark.asyncio
async def test_3_23_a_criterion_whose_requirement_is_no_longer_listed_is_attached_last(app):
    """The `len(position)` fallback, which `spec_render._acceptance` already uses.

    The absent-requirement criterion is written **before** the present one in the document, so a
    raw-document-order implementation would put it first and this would discriminate nothing.
    """
    payload = {
        "requirements": [ALPHA],
        "acceptance_criteria": [
            dict(AC_ALPHA, key="ghost-1", requirement="ghost"),
            dict(AC_ALPHA, key="alpha-1"),
        ],
        "tasks": [_entry("listing", requirements=["alpha", "ghost"])],
    }
    tasks = await _materialise("fallback", payload, keys=("alpha",))
    assert [line.split(":")[0] for line in tasks["listing"].acceptance_criteria] == [
        "alpha-1",
        "ghost-1",
    ]


# ---------------------------------------------------------------------------
# 3.7, 3.12, 3.14 — which name the match is made on (design D3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_3_7_a_requirement_whose_row_key_has_drifted_still_gets_its_criteria(app):
    """`spec_index` explicitly allows a row's `key` to move while its identifier does not. Matching
    on the resolved row's `.key` rather than on the name the entry gave loses the criteria exactly
    when a requirement has been renamed — the case that costs most."""
    payload = {
        "aw_identity": {"requirements": {"alpha": "FR-1"}, "high_water": 1},
        "requirements": [ALPHA],
        "acceptance_criteria": [AC_ALPHA],
        "tasks": [_entry("listing", requirements=["alpha"])],
    }
    tasks = await _materialise("drift", payload, keys=("alpha-renamed",))
    # The requirement really did resolve — through the identity map, not through the key.
    assert await _identifiers_for(tasks["listing"].id) == ["FR-1"]
    assert tasks["listing"].acceptance_criteria == [RENDERED_ALPHA]


@pytest.mark.asyncio
async def test_3_12_a_file_whose_tasks_and_criteria_use_different_namespaces(app):
    """D3's accepted consequence. Both fields come from the same file and are self-consistent
    within it — but nothing validates that at this point, because the approval route parses with
    `extract_payload` and `spec_adoption` never validates at all. So it degrades, and does not
    raise."""
    payload = {
        "requirements": [ALPHA, BETA],
        "acceptance_criteria": [
            dict(AC_ALPHA, requirement="REQ-A"),
            dict(AC_BETA, requirement="REQ-B"),
        ],
        "tasks": [_entry("both", requirements=["alpha", "beta"])],
    }
    tasks = await _materialise("namespaces", payload)
    assert list(tasks) == ["both"]
    assert tasks["both"].acceptance_criteria is None


@pytest.mark.asyncio
async def test_3_14_an_entry_naming_a_requirement_twice_attaches_its_criteria_once(app):
    payload = {
        "requirements": [ALPHA],
        "acceptance_criteria": [AC_ALPHA],
        "tasks": [_entry("listing", requirements=["alpha", "alpha"])],
    }
    tasks = await _materialise("repeated", payload)
    assert tasks["listing"].acceptance_criteria == [RENDERED_ALPHA]


# ---------------------------------------------------------------------------
# 3.16, 3.17 — what a partial criterion renders as (design D8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_3_16_a_criterion_with_no_handle_renders_without_the_literal_none(app):
    """`criteria_by_requirement_key` preserves a missing handle as `None`, so a prefix written
    unconditionally emits `"None: Given ..."` into the implementer's briefing. Asserted on the
    string, because the string is what a reader sees."""
    payload = {
        "requirements": [ALPHA],
        "acceptance_criteria": [{k: v for k, v in AC_ALPHA.items() if k != "key"}],
        "tasks": [_entry("listing", requirements=["alpha"])],
    }
    tasks = await _materialise("no-handle", payload)
    (line,) = tasks["listing"].acceptance_criteria
    assert "None" not in line
    assert line == "Given two plants are due, when the list is shown, then both appear"


@pytest.mark.asyncio
async def test_3_17_a_criterion_that_states_nothing_is_not_attached(app):
    """`spec_payload` sets no `min_length` on given, when or then, so `""` passes validation. A
    check written against `is None` alone emits `"Given , when , then "`."""
    payload = {
        "requirements": [ALPHA],
        "acceptance_criteria": [
            {"key": "empty", "requirement": "alpha", "given": "", "when": "", "then": ""},
            AC_ALPHA,
        ],
        "tasks": [_entry("listing", requirements=["alpha"])],
    }
    tasks = await _materialise("states-nothing", payload)
    assert list(tasks) == ["listing"]
    assert tasks["listing"].acceptance_criteria == [RENDERED_ALPHA]


# ---------------------------------------------------------------------------
# 3.11, 3.18, 3.24, 3.26 — totality (design D6/D7)
# ---------------------------------------------------------------------------


MALFORMED_CRITERIA = {
    "absent": None,
    "scalar": 5,
    "string": "abc",
    "list-of-non-dicts": ["ac-alpha", 7],
    "dicts-missing-every-field": [{"requirement": "alpha"}, {}],
}


@pytest.mark.asyncio
async def test_3_11_a_malformed_criteria_block_still_creates_every_declared_task(app):
    """`materialise_quietly` catches every exception and returns `[]`, so a raise anywhere in here
    creates **no tasks at all** while the approval reports success. Asserted through that path,
    because it is the one approval uses and the one that would hide the raise.

    Two tasks are declared and both are asserted: that is what proves totality, rather than a
    committed prefix. `"abc"` and `["ac-alpha", 7]` are the shapes that matter — `spec_reading`
    reads every field with `.get()`, so a dict merely missing `key`, `given`, `when` or `then`
    raises nothing even with the skip removed.
    """
    for suffix, shape in MALFORMED_CRITERIA.items():
        payload = {
            "requirements": [ALPHA, BETA],
            "tasks": [
                _entry("listing", requirements=["alpha"]),
                _entry("recording", requirements=["beta"]),
            ],
        }
        if shape is not None:
            payload["acceptance_criteria"] = shape

        tasks = await _materialise(f"malformed-{suffix}", payload, quietly=True)
        assert sorted(tasks) == ["listing", "recording"], f"{suffix}: {sorted(tasks)}"
        for key, task in tasks.items():
            assert task.acceptance_criteria is None, f"{suffix}/{key}"


@pytest.mark.asyncio
async def test_3_18_a_scalar_criteria_block_creates_every_task_with_no_criteria(app):
    """The exact `TypeError: 'int' object is not iterable` measured against the helper in R4."""
    payload = {
        "requirements": [ALPHA, BETA],
        "acceptance_criteria": 5,
        "tasks": [
            _entry("listing", requirements=["alpha"]),
            _entry("recording", requirements=["beta"]),
        ],
    }
    tasks = await _materialise("scalar-criteria", payload, quietly=True)
    assert sorted(tasks) == ["listing", "recording"]
    assert [task.acceptance_criteria for task in tasks.values()] == [None, None]


@pytest.mark.asyncio
async def test_3_24_a_scalar_requirements_block_costs_the_ordering_not_the_criteria(app):
    """New exposure: `materialise()` has never read `payload["requirements"]` before this change.

    The fixture **declares criteria the entry names**, or the guard is never reached: matching is on
    the name the entry gave and is independent of `payload["requirements"]`, so an implementation
    that short-circuits on an empty criteria set never builds the position map at all. Called
    through `materialise()` rather than `materialise_quietly`, so a raise surfaces here as a
    failure rather than as an empty board.
    """
    payload = {
        "requirements": 5,
        "acceptance_criteria": [AC_ALPHA, AC_BETA],
        "tasks": [_entry("both", requirements=["alpha", "beta"])],
    }
    tasks = await _materialise("scalar-requirements", payload)
    assert list(tasks) == ["both"]
    assert sorted(tasks["both"].acceptance_criteria) == sorted([RENDERED_ALPHA, RENDERED_BETA])


@pytest.mark.asyncio
async def test_3_26_a_requirements_list_holding_a_non_dict_element_still_materialises(app):
    """Distinct from 3.24: this shape passes an `isinstance(raw, list)` guard, and only a
    per-element check survives it. A bare `{r["key"]: i for i, r in enumerate(raw)}` raises
    `TypeError: string indices must be integers` here; `statements_by_key`'s per-element skip does
    not. This is the one behavioural difference between the two readings of task 2.7."""
    payload = {
        "requirements": ["not a requirement", ALPHA],
        "acceptance_criteria": [AC_ALPHA],
        "tasks": [_entry("listing", requirements=["alpha"])],
    }
    tasks = await _materialise("ragged-requirements", payload, keys=("alpha",))
    assert list(tasks) == ["listing"]
    assert tasks["listing"].acceptance_criteria == [RENDERED_ALPHA]


# ---------------------------------------------------------------------------
# 3.22, 3.25 — the helper's other caller (design D7)
# ---------------------------------------------------------------------------


def test_3_22_requirement_view_survives_a_scalar_criteria_block():
    """`read_spec_document` reaches `requirement_view` with no `try`/`except`, so the same
    `TypeError` returns a 500 to an agent asking to read the document it was told to implement.
    This is what distinguishes a guard inside the helper from a guard at `materialise()`'s call
    site — the latter leaves this route broken."""
    requirements, diagnostics = spec_reading.requirement_view(
        {"requirements": [ALPHA], "acceptance_criteria": 5}, [_Row("FR-1", "alpha")]
    )
    assert [row["identifier"] for row in requirements] == ["FR-1"]
    assert requirements[0]["statement"] == ALPHA["statement"]
    assert requirements[0]["acceptance_criteria"] == []
    assert diagnostics == []


def test_3_25_requirement_view_survives_a_scalar_requirements_block():
    """The `statements_by_key` half of the same argument. 3.22 covers only the criteria half;
    without this the 500 on `requirements` stands."""
    requirements, diagnostics = spec_reading.requirement_view(
        {"requirements": 5, "acceptance_criteria": [AC_ALPHA]}, [_Row("FR-1", "alpha")]
    )
    assert [row["identifier"] for row in requirements] == ["FR-1"]
    # No wording to be had — but an answer, not an exception.
    assert requirements[0]["statement"] is None
    assert [row["key"] for row in requirements[0]["acceptance_criteria"]] == ["ac-alpha"]
    assert [row["problem"] for row in diagnostics] == [
        "the document no longer states this requirement"
    ]


# ---------------------------------------------------------------------------
# 3.9, 3.19 — what attaching criteria does not change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_3_9_re_approval_does_not_revisit_or_duplicate_criteria(app):
    """Design D5: write-once. A task that already exists is never touched, so a revision that
    reworded its criteria does not reach it — and does not create a second task either."""
    first_payload = {
        "requirements": [ALPHA],
        "acceptance_criteria": [AC_ALPHA],
        "tasks": [_entry("listing", requirements=["alpha"])],
    }
    revised = {
        "requirements": [ALPHA],
        "acceptance_criteria": [dict(AC_ALPHA, key="ac-alpha-v2", then="only the overdue appear")],
        "tasks": [_entry("listing", requirements=["alpha"])],
    }

    async with async_session_factory() as db:
        document = await _document(db, "reapproved", keys=("alpha",))
        created = await spec_tasks.materialise(db, document, first_payload, actor=ACTOR)
        await db.commit()
        assert len(created) == 1
        again = await spec_tasks.materialise(db, document, revised, actor=ACTOR)
        await db.commit()
        assert again == []

    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(Task).where(Task.spec_document_id == "doc-crit-reapproved")))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].acceptance_criteria == [RENDERED_ALPHA]


@pytest.mark.asyncio
async def test_3_19_attaching_criteria_changes_nothing_about_which_tasks_exist(app):
    """Two documents declaring the same decomposition, one stating criteria and one not. Same
    count, same titles, same keys — the criteria are the only difference."""
    declared = [
        _entry("listing", requirements=["alpha"], description="Build the listing command."),
        _entry("recording", requirements=["beta"], description="Build the recording command."),
    ]
    with_criteria = await _materialise(
        "with-criteria",
        {
            "requirements": [ALPHA, BETA],
            "acceptance_criteria": [AC_ALPHA, AC_BETA],
            "tasks": declared,
        },
    )
    without = await _materialise(
        "without-criteria", {"requirements": [ALPHA, BETA], "tasks": declared}
    )

    assert sorted(with_criteria) == sorted(without) == ["listing", "recording"]
    assert {key: task.title for key, task in with_criteria.items()} == {
        key: task.title for key, task in without.items()
    }
    assert with_criteria["listing"].acceptance_criteria == [RENDERED_ALPHA]
    assert with_criteria["recording"].acceptance_criteria == [RENDERED_BETA]
    assert without["listing"].acceptance_criteria is None
    assert without["recording"].acceptance_criteria is None


# ---------------------------------------------------------------------------
# 3.10 — and into the turn the agent actually gets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_3_10_criteria_render_into_a_loop_briefing_one_line_each(app):
    """The model field is not the point; the briefing is. `scheduler.py` renders
    `acceptance_criteria` and nothing else of the document's statement of done, for the implementer
    and the reviewer alike.

    The `isinstance(line, str)` assertion is what pins *"a form the existing readers of that field
    already accept"*: the briefing's f-string stringifies any object, so a list of dicts would
    render without error and read as noise.
    """
    payload = {
        "requirements": [ALPHA, BETA],
        "acceptance_criteria": [AC_ALPHA, AC_BETA],
        "tasks": [_entry("both", requirements=["alpha", "beta"])],
    }
    tasks = await _materialise("briefing", payload)
    task_id = tasks["both"].id

    async with async_session_factory() as db:
        db.add(
            AIJob(
                id="job-crit-briefing",
                project_id=PROJECT,
                name="Criteria briefing",
                agent="author",
                message="work the queue",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=False,
            )
        )
        await db.flush()
        db.add(
            Loop(
                id="loop-crit-briefing",
                project_id=PROJECT,
                job_id="job-crit-briefing",
                purpose="build what the document declared",
                spec_document_id="doc-crit-briefing",
            )
        )
        task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()
        task.loop_id = "loop-crit-briefing"
        task.status = "assigned"
        await db.commit()

    async with async_session_factory() as db:
        loop = (await db.execute(select(Loop).where(Loop.id == "loop-crit-briefing"))).scalar_one()
        task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()
        assert all(isinstance(line, str) for line in task.acceptance_criteria)
        briefing = await _compose_loop_briefing(db, loop, task, None, is_review=False, agent="dev")
        review = await _compose_loop_briefing(db, loop, task, None, is_review=True, agent="dev")

    for rendered in (briefing, review):
        assert "Acceptance criteria:" in rendered
        assert f"- {RENDERED_ALPHA}" in rendered
        assert f"- {RENDERED_BETA}" in rendered
    # One line per criterion, not one line holding the list.
    assert briefing.count("- ac-") == 2
