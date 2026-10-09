"""A project orders its own spec steps (project-steps slice, task 2): the journey half.

`spec/journey.json` holds the project's steps in order: the built-ins by key, custom steps with
their Markdown and sizes, and an instruction appended to any step. Briefing, advance, the operator's
step move and the documents view read it; a broken file is a diagnostic and the built-in table is
used meanwhile. Change: spec/changes/a-project-orders-its-own-spec-steps (spdoc-3759e366caf1).
The acceptance drive is `scripts/drive/d1011_project_steps.py`.
"""

import json

import pytest

from hub import spec_journey
from hub.project_workspace import ProjectWorkspace

from .test_spec_documents_api import (
    BASE,
    PATH,
    _create,
    run_headers,  # noqa: F401  (fixture)
)
from .test_spec_journey_briefing import _briefing, _place, _row

ACTIONS = "/api/v1/agent-actions/spec/documents"
BUILTINS = list(spec_journey.STEP_ORDER)
SENTINEL = "SENTINEL-ORCHID-7731"
THREAT_MD = "List what could go wrong if someone abused the new route. Write it under Threats."
THREAT = {"key": "threat-model", "title": "Threat model", "instructions": THREAT_MD}
LARGE = ["intake", "requirements", "threat-model", "acceptance", "approach", "tasks", "delivery"]


def _steps(custom=None, after="requirements", append=None):
    """The built-ins in order, `custom` right after `after`, `append` on intake."""
    steps = []
    for key in BUILTINS:
        entry = {"key": key}
        if key == "intake" and append:
            entry["append"] = append
        steps.append(entry)
        if key == after and custom:
            steps.append(dict(custom))
    return {"steps": steps}


def _write(root, document):
    file = root / "spec" / "journey.json"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        document if isinstance(document, str) else json.dumps(document), encoding="utf-8"
    )


def _load(root):
    return spec_journey.load(ProjectWorkspace(project_id="p", root=root, path_key="p"))


# no-file-unchanged (FR-1)
def test_with_no_file_every_journey_and_duty_is_the_built_in_table(tmp_path):
    steps = _load(tmp_path)

    assert steps.diagnostics == ()
    for size, expected in spec_journey.JOURNEYS.items():
        assert spec_journey.journey(size, steps) == expected
    for step in BUILTINS:
        assert spec_journey.duty(step, steps) == spec_journey.duty(step)
        assert spec_journey.duty(step) != ""


# custom-sizes (FR-2)
def test_a_custom_step_listing_no_sizes_joins_small_and_large_and_not_fix(tmp_path):
    _write(tmp_path, _steps(THREAT, after="requirements-and-acceptance"))
    steps = _load(tmp_path)

    assert steps.diagnostics == ()
    assert spec_journey.journey("fix", steps) == spec_journey.JOURNEYS["fix"]
    assert spec_journey.journey("small", steps) == [
        "intake",
        "requirements-and-acceptance",
        "threat-model",
        "tasks",
        "delivery",
    ]
    assert "threat-model" in spec_journey.journey("large", steps)
    assert spec_journey.journey(None, steps) == spec_journey.journey("large", steps)


def test_a_custom_step_belongs_only_to_the_sizes_it_lists(tmp_path):
    _write(tmp_path, _steps({**THREAT, "sizes": ["large"]}))
    steps = _load(tmp_path)

    assert spec_journey.journey("large", steps) == LARGE
    assert spec_journey.journey(None, steps) == LARGE
    assert "threat-model" not in spec_journey.journey("small", steps)
    assert spec_journey.next_step("large", "requirements", steps) == "threat-model"
    assert spec_journey.next_step("large", "threat-model", steps) == "acceptance"
    # A size that drops the step still moves forward from it, in the file's order.
    assert spec_journey.next_step("small", "threat-model", steps) == "requirements-and-acceptance"


# hand-edit-broken (FR-7)
@pytest.mark.parametrize(
    "document, names",
    [
        ("{not json", "parse"),
        ({"steps": "intake"}, "steps"),
        ({"steps": [{"key": k} for k in BUILTINS if k != "tasks"]}, "built-in"),
        (
            {"steps": [{"key": k} for k in ["requirements", "intake", *BUILTINS[2:]]]},
            "built-in",
        ),
        (_steps({"key": "design"}), "design"),
        (_steps({**THREAT, "key": "Threat Model"}), "slug"),
        (_steps({**THREAT, "key": "t" * 49}), "48"),
        (_steps({**THREAT, "key": "requirements"}), "requirements"),
        ({"steps": _steps(THREAT)["steps"] + [dict(THREAT)]}, "duplicate"),
        (_steps({**THREAT, "instructions": "x" * 2001}), "2,000"),
        (_steps(append="y" * 2001), "2,000"),
        (_steps({**THREAT, "sizes": ["huge"]}), "huge"),
        (_steps({**THREAT, "title": ""}), "title"),
    ],
)
def test_a_broken_file_is_a_diagnostic_and_the_built_in_table_is_used(tmp_path, document, names):
    _write(tmp_path, document)
    steps = _load(tmp_path)

    assert steps.diagnostics, "a broken file must be reported"
    assert {d["code"] for d in steps.diagnostics} == {"journey_file_invalid"}
    assert names in " ".join(d["message"] for d in steps.diagnostics)
    assert [s.key for s in steps.steps] == BUILTINS
    assert spec_journey.journey("large", steps) == spec_journey.JOURNEYS["large"]


@pytest.mark.asyncio
async def test_a_broken_file_never_refuses_a_turn(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    _write(tmp_path, "{not json")
    await _place(step="requirements", size="large")

    text = await _briefing(app, auth_headers)

    assert spec_journey.duty("requirements") in text


# append-scoped (FR-4)
@pytest.mark.asyncio
async def test_an_appended_instruction_reaches_only_its_own_step(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    _write(tmp_path, _steps({**THREAT, "sizes": ["large"]}, append=f"Confirm {SENTINEL}."))

    await _place(step="intake", size="large")
    assert SENTINEL in await _briefing(app, auth_headers)
    await _place(step="requirements", size="large")
    assert SENTINEL not in await _briefing(app, auth_headers)

    await _place(step="intake", size="large")
    moved = await app.post(f"{ACTIONS}/advance", json={"path": PATH}, headers=run_headers)
    assert moved.status_code == 200, moved.text
    assert moved.json()["step"] == "requirements"
    assert SENTINEL not in moved.json()["instructions"]
    back = await app.post(
        f"{ACTIONS}/advance", json={"path": PATH, "to": "intake"}, headers=run_headers
    )
    assert SENTINEL in back.json()["instructions"]


# drive (FR-3), at the seam: briefing and advance on a custom step
@pytest.mark.asyncio
async def test_a_custom_step_is_entered_by_advance_and_briefed_with_its_markdown(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    _write(tmp_path, _steps({**THREAT, "sizes": ["large"]}, append=f"Confirm {SENTINEL}."))
    await _place(step="requirements", size="large")

    moved = await app.post(f"{ACTIONS}/advance", json={"path": PATH}, headers=run_headers)

    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert (body["previous_step"], body["step"]) == ("requirements", "threat-model")
    assert body["journey"] == LARGE
    assert spec_journey.marker("threat-model") in body["instructions"]
    assert THREAT_MD in body["instructions"]
    assert (await _row()).step == "threat-model"

    text = await _briefing(app, auth_headers)
    assert spec_journey.marker("threat-model") in text
    assert "Threat model" in text and THREAT_MD in text
    assert "tell the operator where" in text
    assert "advance_spec_step" in text, "a custom step asks to advance like a built-in one"
    assert SENTINEL not in text
    assert "**threat-model**" in text, "the journey line names the custom step"

    onward = await app.post(f"{ACTIONS}/advance", json={"path": PATH}, headers=run_headers)
    assert onward.json()["step"] == "acceptance"


@pytest.mark.asyncio
async def test_the_operator_moves_a_document_onto_a_custom_step_and_not_an_unknown_one(
    app, auth_headers, tmp_path
):
    await _create(app, auth_headers)
    _write(tmp_path, _steps(THREAT))
    route = f"{BASE}/documents/journey"

    onto = await app.post(
        route,
        params={"path": PATH},
        json={"step": "threat-model", "size": "large"},
        headers=auth_headers,
    )
    unknown = await app.post(
        route, params={"path": PATH}, json={"step": "privacy"}, headers=auth_headers
    )

    assert onto.status_code == 200, onto.text
    assert onto.json()["step"] == "threat-model"
    assert onto.json()["journey"] == LARGE
    assert unknown.status_code == 422 and "threat-model" in unknown.text


# removed-step (FR-8)
@pytest.mark.asyncio
async def test_a_removed_step_is_briefed_as_removed_and_bare_advance_is_refused(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    _write(tmp_path, _steps(THREAT))
    await _place(step="threat-model", size="large")
    _write(tmp_path, _steps())

    text = await _briefing(app, auth_headers)
    bare = await app.post(f"{ACTIONS}/advance", json={"path": PATH}, headers=run_headers)
    named = await app.post(
        f"{ACTIONS}/advance", json={"path": PATH, "to": "acceptance"}, headers=run_headers
    )

    assert "was removed" in text and "ask_user" in text
    assert bare.status_code == 422, bare.text
    assert bare.json()["detail"]["code"] == "step_not_in_journey"
    assert "approach" in bare.json()["detail"]["message"], "the refusal names the journey"
    assert named.status_code == 200 and named.json()["step"] == "acceptance"


# bar (FR-9), the documents view the bar reads
@pytest.mark.asyncio
async def test_the_documents_view_lists_the_projects_journey(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    _write(tmp_path, _steps({**THREAT, "sizes": ["large"]}))
    await _place(step="intake", size="large")

    listed = await app.get(f"{BASE}/documents", headers=auth_headers)

    (view,) = [d for d in listed.json()["documents"] if d["path"] == PATH]
    assert view["journey"] == LARGE
