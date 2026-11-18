"""`one-profile-runs-many-turns-at-once-on-different-tasks` FR-16 (task OPMR-7, D7).

Two threads working one draft is routine once a profile runs many turns at once. An agent's save
based on a copy somebody else has saved over since is refused, naming the document, and changes
nothing; an amendment or a tidy act never writes over a save stored between its read and its
write; and a document's file is never left partly written.
"""

import json
import os

import pytest

from hub import spec_amendments, spec_documents, spec_service
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocumentEvent

from .test_spec_documents_api import PATH, _create, _document, _submit
from .test_spec_tidy import (
    CAP,
    TIDIER,
    _capability_two,
    _create_capability,
    _tidy,
    tidier,  # noqa: F401 - a fixture, used by name
)
from .test_spec_tidy import _stored as _stored_at
from .test_tester_amendments import (
    NEW_CRITERION,
    _approved,
    _run,
    author_headers,  # noqa: F401 - a fixture, used by name
)

AGENT = "/api/v1/agent-actions/spec/documents"
AMEND = "/api/v1/agent-actions/spec/documents/amend"


def _stored(tmp_path, path=PATH):
    return spec_documents.parse_stored((tmp_path / path).read_text(encoding="utf-8"))


def _workspace(tmp_path):
    from hub.project_workspace import ProjectWorkspace

    return ProjectWorkspace(project_id="proj-test", root=tmp_path, path_key="test:proj-test")


async def _read(app, headers, path=PATH):
    read = await app.get(AGENT, params={"path": path, "include": "full"}, headers=headers)
    assert read.status_code == 200, read.text
    return read.json()


def _save_in_between(tmp_path, path, summary):
    """Another write landing on the file: what a concurrent save stores."""
    file = tmp_path / path
    stored = json.loads(file.read_text(encoding="utf-8"))
    stored["summary"] = summary
    file.write_text(json.dumps(stored, sort_keys=True, indent=2) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ ac-stale-save-refused


@pytest.mark.asyncio
async def test_a_save_based_on_a_copy_saved_over_since_is_refused_until_read_again(
    app, auth_headers, tmp_path
):
    await _create(app, auth_headers)
    first = await _run("run-thread-a", "writer")
    second = await _run("run-thread-b", "writer")
    seeded = await _submit(app, first, _document(summary="seed"))
    assert seeded.status_code == 200, seeded.text

    await _read(app, first)
    await _read(app, second)
    saved = await _submit(app, first, _document(summary="the first thread's change"))
    assert saved.status_code == 200, saved.text

    refused = await _submit(app, second, _document(summary="the second thread's change"))

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "document_changed"
    assert PATH in detail["message"] and "changed since it was read" in detail["message"]
    assert _stored(tmp_path)["summary"] == "the first thread's change"

    # Refused again without a fresh read: the refusal does not forget the stale copy.
    again = await _submit(app, second, _document(summary="the second thread's change"))
    assert again.status_code == 409, again.text

    view = await _read(app, second)
    assert view["summary"] == "the first thread's change"
    retried = await _submit(app, second, _document(summary="the second thread, on top"))
    assert retried.status_code == 200, retried.text
    assert _stored(tmp_path)["summary"] == "the second thread, on top"


@pytest.mark.asyncio
async def test_an_author_saving_again_and_again_is_not_refused_by_its_own_saves(
    app, auth_headers, tmp_path
):
    await _create(app, auth_headers)
    author = await _run("run-author-only", "writer")
    for summary in ("one", "two", "three"):
        saved = await _submit(app, author, _document(summary=summary))
        assert saved.status_code == 200, saved.text
    assert _stored(tmp_path)["summary"] == "three"


@pytest.mark.asyncio
async def test_an_operator_save_after_the_agents_read_refuses_the_agents_save(
    app, auth_headers, tmp_path
):
    await _create(app, auth_headers)
    agent = await _run("run-after-operator", "writer")
    assert (await _submit(app, agent, _document(summary="agent"))).status_code == 200
    operator = await app.put(
        f"/api/v1/projects/proj-test/project/documents/{PATH}/content",
        json={"document": _document(summary="the operator's edit")},
        headers=auth_headers,
    )
    assert operator.status_code == 200, operator.text

    refused = await _submit(app, agent, _document(summary="agent again"))

    assert refused.status_code == 409, refused.text
    assert _stored(tmp_path)["summary"] == "the operator's edit"


@pytest.mark.asyncio
async def test_a_document_read_back_as_it_is_is_submittable(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    agent = await _run("run-read-back", "writer")
    assert (await _submit(app, agent, _document(summary="kept"))).status_code == 200
    view = await _read(app, agent)

    resubmitted = await _submit(app, agent, _document(summary=view["summary"]))

    assert resubmitted.status_code == 200, resubmitted.text


@pytest.mark.asyncio
async def test_an_agents_rename_does_not_make_its_own_copy_stale(app, auth_headers, tmp_path):
    created = await app.post(
        AGENT + "/create", json={"title": "Placeholder"}, headers=await _run("run-rn", "writer")
    )
    assert created.status_code == 201, created.text
    headers = {"Authorization": "Bearer aw_run_run-rn-secret"}
    path = created.json()["path"]
    assert (
        await _submit(app, headers, _document(title="Placeholder", summary="s"), path=path)
    ).status_code == 200
    renamed = await app.post(
        AGENT + "/rename", json={"path": path, "subject": "glowing widgets"}, headers=headers
    )
    assert renamed.status_code == 200, renamed.text
    new_path = renamed.json()["path"]

    saved = await _submit(app, headers, _document(title="Glowing widgets"), path=new_path)

    assert saved.status_code == 200, saved.text


# ------------------------------------------------------------------ ac-delta-not-lost


@pytest.mark.asyncio
async def test_an_amendment_paused_while_a_save_lands_is_refused_and_keeps_the_save(
    app, auth_headers, author_headers, tmp_path, monkeypatch  # noqa: F811
):
    task_id = await _approved(app, auth_headers, author_headers)
    tester = await _run("run-tester-delayed", "tess", reviews=task_id)
    real = spec_amendments.tested_task

    async def paused(*args, **kwargs):
        # Between the amendment's read of the document and its write.
        _save_in_between(tmp_path, PATH, "saved while the amendment was paused")
        return await real(*args, **kwargs)

    monkeypatch.setattr(spec_amendments, "tested_task", paused)

    refused = await app.post(AMEND, json=NEW_CRITERION, headers=tester)

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "document_changed"
    assert PATH in json.dumps(detail)
    stored = _stored(tmp_path)
    assert stored["summary"] == "saved while the amendment was paused"
    assert [c["key"] for c in stored["acceptance_criteria"]] == ["c1"]
    async with async_session_factory() as session:
        from sqlalchemy import select

        kinds = (await session.execute(select(SpecDocumentEvent.kind))).scalars().all()
    assert spec_amendments.EVENT not in kinds

    # Made again against what the document holds now, it applies over the save.
    monkeypatch.setattr(spec_amendments, "tested_task", real)
    applied = await app.post(AMEND, json=NEW_CRITERION, headers=tester)
    assert applied.status_code == 201, applied.text
    stored = _stored(tmp_path)
    assert stored["summary"] == "saved while the amendment was paused"
    assert [c["key"] for c in stored["acceptance_criteria"]] == ["c1", "c-slow"]


@pytest.mark.asyncio
async def test_a_tidy_edit_paused_while_a_save_lands_is_refused_and_keeps_the_save(
    app, auth_headers, tidier, tmp_path, monkeypatch  # noqa: F811
):
    await _create_capability(app, auth_headers, path=CAP, payload=_capability_two())
    real = spec_service.may_write_capability

    async def paused(*args, **kwargs):
        # Between the tidy act's read of the capability and the merge's write.
        _save_in_between(tmp_path, CAP, "saved while the tidy act was paused")
        return await real(*args, **kwargs)

    monkeypatch.setattr(spec_service, "may_write_capability", paused)

    refused = await _tidy(
        app,
        tidier,
        CAP,
        "edit_capability",
        reason="widget.py paints them blue",
        requirement="widgets-old",
        statement="A widget MUST be blue.",
    )

    assert refused.status_code >= 400, refused.text
    assert refused.json()["detail"]["code"] == "document_changed", refused.text
    assert CAP in refused.text
    stored = _stored_at(tmp_path, CAP)
    assert stored["summary"] == "saved while the tidy act was paused"
    assert "A widget MUST be grey." in [r["statement"] for r in stored["requirements"]]
    assert TIDIER  # the act's author, refused


@pytest.mark.asyncio
async def test_a_write_whose_read_is_stale_is_refused_at_the_write(tmp_path):
    """The seam every amendment, tidy act and fold writes through (`write_document`)."""
    workspace = _workspace(tmp_path)
    path = "spec/changes/seam/spec.json"
    spec_documents.write_payload(workspace, path, {"title": "read"}, {})
    read = spec_documents.read_document(workspace, path)
    spec_documents.write_payload(workspace, path, {"title": "stored since"}, {})

    with pytest.raises(spec_documents.DocumentChangedError) as refused:
        spec_documents.write_payload(
            workspace,
            path,
            {"title": "over the stale read"},
            {},
            expected_version=spec_documents.content_version(read),
        )

    assert path in str(refused.value)
    assert spec_documents.read_payload(workspace, path) == {"title": "stored since"}


# ------------------------------------------------------------------ ac-atomic-write


def test_a_write_failing_partway_leaves_the_previous_content_whole(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    path = "spec/changes/atomic/spec.json"
    previous = spec_documents.write_payload(workspace, path, {"title": "previous"}, {})
    real_fdopen = os.fdopen

    class HalfWritten:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.handle.close()
            return False

        def write(self, text):
            self.handle.write(text[: len(text) // 2])
            self.handle.flush()
            raise OSError(28, "No space left on device")

    monkeypatch.setattr(
        spec_documents.os, "fdopen", lambda *a, **k: HalfWritten(real_fdopen(*a, **k))
    )

    with pytest.raises(OSError):
        spec_documents.write_payload(workspace, path, {"title": "new " * 500}, {})

    assert (tmp_path / path).read_text(encoding="utf-8") == previous
    assert sorted(p.name for p in (tmp_path / path).parent.iterdir()) == ["spec.json"]


def test_a_write_failing_at_the_move_leaves_the_previous_content_whole(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    path = "spec/changes/atomic/spec.json"
    previous = spec_documents.write_payload(workspace, path, {"title": "previous"}, {})

    def refuse(*args, **kwargs):
        raise OSError(13, "Access is denied")

    monkeypatch.setattr(spec_documents.os, "replace", refuse)

    with pytest.raises(OSError):
        spec_documents.write_payload(workspace, path, {"title": "new"}, {})

    assert (tmp_path / path).read_text(encoding="utf-8") == previous
    assert sorted(p.name for p in (tmp_path / path).parent.iterdir()) == ["spec.json"]


def test_a_successful_write_holds_the_new_content_in_full(tmp_path):
    workspace = _workspace(tmp_path)
    path = "spec/changes/atomic/spec.json"
    spec_documents.write_payload(workspace, path, {"title": "previous"}, {})

    written = spec_documents.write_payload(workspace, path, {"title": "new " * 500}, {})

    assert (tmp_path / path).read_bytes() == written.encode("utf-8")
    assert "\r\n" not in (tmp_path / path).read_bytes().decode("utf-8")
