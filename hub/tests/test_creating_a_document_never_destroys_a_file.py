"""F1095: `POST /documents` over a file the Hub has no row for is refused and the file is kept."""

from __future__ import annotations

import pytest

BASE = "/api/v1/projects/proj-test/project"
PATH = "spec/capabilities/handmade/spec.json"
KEPT = '{"title": "KEEP ME"}'


def _put(tmp_path, content) -> None:
    target = tmp_path / PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        target.write_bytes(content)
    else:
        target.write_text(content, encoding="utf-8")


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


#: Whatever the file holds, it is someone's: nothing about its content exempts it, and it is not read.
UNTRACKED = {
    "valid_payload": KEPT,
    "broken_json": '{"title": "KEEP ME"',
    "json_array": '["KEEP ME"]',
    "html": "<html><body>KEEP ME</body></html>",
    "plain_text": "KEEP ME",
    "empty": "",
    "not_utf8": bytes([0xFF, 0xFE, 0x00]) + b"KEEP ME" + bytes([0x80]),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("content", UNTRACKED.values(), ids=UNTRACKED.keys())
async def test_any_file_at_the_path_is_kept(app, auth_headers, tmp_path, content):
    _put(tmp_path, content)
    before = (tmp_path / PATH).read_bytes()

    response = await _create(app, auth_headers)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "untracked_file_exists"
    assert (tmp_path / PATH).read_bytes() == before


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
