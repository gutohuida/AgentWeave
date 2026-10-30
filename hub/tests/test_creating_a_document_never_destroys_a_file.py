"""F1095: `POST /documents` over a file the Hub has no row for is refused and the file is kept."""

from __future__ import annotations

import pytest

BASE = "/api/v1/projects/proj-test/project"
PATH = "spec/capabilities/handmade/spec.json"
KEPT = '{"title": "KEEP ME"}'


def _put(tmp_path, text: str) -> None:
    target = tmp_path / PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _create(app, auth_headers):
    return app.post(
        f"{BASE}/documents",
        json={"path": PATH, "title": "Handmade", "kind": "capability"},
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_an_untracked_file_is_refused_and_left_untouched(app, auth_headers, tmp_path):
    _put(tmp_path, KEPT)

    response = await _create(app, auth_headers)

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "untracked_file_exists"  # not `document_exists`: nothing is tracked
    assert PATH in detail["message"]
    assert "adopt" in detail["message"]
    assert (tmp_path / PATH).read_text(encoding="utf-8") == KEPT


@pytest.mark.asyncio
async def test_a_free_path_still_creates(app, auth_headers, tmp_path):
    response = await _create(app, auth_headers)

    assert response.status_code == 201, response.text
    assert (tmp_path / PATH).is_file()


@pytest.mark.asyncio
async def test_a_tracked_path_still_answers_document_exists(app, auth_headers, tmp_path):
    assert (await _create(app, auth_headers)).status_code == 201

    again = await _create(app, auth_headers)

    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "document_exists"
