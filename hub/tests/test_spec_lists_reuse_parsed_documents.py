"""The spec and document listings reuse what they read until a file changes.

`turn-starts-approvals-and-evidence-never-freeze-the-hub`, FR-7 (spec-list-cost). Measured before
this change on this repository: `GET /project/specs` 454 ms with 504 path resolutions, 850 stats
and 162 parses per request, all on the event loop; `GET /project/documents` read and hashed every
document file per request.

The cost half counts what a warm request does to the files -- resolutions and reads -- rather than
milliseconds, so it does not depend on the machine running the suite; the drive
(`scripts/drive/perf_loop_lag.py`) measures the milliseconds on this repository's own tree.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from hub import project_workspace
from hub.spec_documents import write_document

from ._spec_files import stored_text

BASE = "/api/v1/projects/proj-test/project"
DOCUMENTS = 30


def _payload(index: int) -> dict:
    return {
        "schema_version": 1,
        "kind": "change-spec",
        "title": f"Listed document {index}",
        "requirements": [],
    }


async def _documents(app, auth_headers) -> list:
    paths = []
    for index in range(DOCUMENTS):
        path = f"spec/changes/listed-{index}/spec.json"
        created = await app.post(
            f"{BASE}/documents",
            json={"path": path, "title": f"Listed document {index}"},
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        paths.append(path)
    return paths


class _Counting:
    def __init__(self) -> None:
        self.resolutions = 0
        self.reads = 0


@pytest.fixture
def counting(monkeypatch):
    counts = _Counting()
    real_resolve = project_workspace.ProjectWorkspace.resolve_relative
    real_read = Path.read_text

    def _resolve(self, relative):  # noqa: ANN001, ANN202
        counts.resolutions += 1
        return real_resolve(self, relative)

    def _read(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        if "spec" in Path(self).parts:
            counts.reads += 1
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(project_workspace.ProjectWorkspace, "resolve_relative", _resolve)
    monkeypatch.setattr(Path, "read_text", _read)
    return counts


@pytest.mark.asyncio
async def test_a_warm_spec_list_reads_and_resolves_nothing_it_already_knows(
    app, auth_headers, tmp_path, counting
):
    await _documents(app, auth_headers)
    first = await app.get(f"{BASE}/specs", headers=auth_headers)
    assert first.status_code == 200, first.text
    assert len(first.json()["specs"]) >= DOCUMENTS

    counting.resolutions = counting.reads = 0
    second = await app.get(f"{BASE}/specs", headers=auth_headers)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    # Before: three resolutions and a read for every document. Now the spec root is resolved and
    # the tree compared; nothing in it is resolved or read again.
    assert counting.reads == 0, counting.reads
    assert counting.resolutions <= 3, counting.resolutions


@pytest.mark.asyncio
async def test_a_warm_document_list_reads_no_file_again(app, auth_headers, tmp_path, counting):
    await _documents(app, auth_headers)
    first = await app.get(f"{BASE}/documents", headers=auth_headers)
    assert first.status_code == 200, first.text
    counting.reads = 0
    second = await app.get(f"{BASE}/documents", headers=auth_headers)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert counting.reads <= 1, counting.reads  # the journey file, as before


@pytest.mark.asyncio
async def test_a_changed_file_is_seen_by_the_next_listing(app, auth_headers, tmp_path):
    paths = await _documents(app, auth_headers)
    before_specs = {
        s["path"]: s for s in (await app.get(f"{BASE}/specs", headers=auth_headers)).json()["specs"]
    }
    before_docs = {
        d["path"]: d
        for d in (await app.get(f"{BASE}/documents", headers=auth_headers)).json()["documents"]
    }
    target = paths[3]
    assert before_docs[target].get("diverged") is False

    # Changed behind the Hub's back, with a modification time a coarse clock could not hide.
    file = tmp_path / target
    file.write_text(stored_text(_payload(99)), encoding="utf-8")
    later = time.time() + 5
    os.utime(file, (later, later))

    after_specs = {
        s["path"]: s for s in (await app.get(f"{BASE}/specs", headers=auth_headers)).json()["specs"]
    }
    after_docs = {
        d["path"]: d
        for d in (await app.get(f"{BASE}/documents", headers=auth_headers)).json()["documents"]
    }
    assert after_specs[target]["updated_at"] != before_specs[target]["updated_at"]
    assert after_docs[target]["diverged"] is True

    # And a new document appears, and a removed one goes.
    project = project_workspace.ProjectWorkspace("proj-test", tmp_path, "k")
    write_document(project, "spec/changes/listed-new/spec.json", stored_text(_payload(100)))
    (tmp_path / paths[0]).unlink()
    listed = {
        s["path"] for s in (await app.get(f"{BASE}/specs", headers=auth_headers)).json()["specs"]
    }
    assert "spec/changes/listed-new/spec.json" in listed
    assert paths[0] not in listed
