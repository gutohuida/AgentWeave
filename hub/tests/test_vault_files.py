"""Images and PDFs as vault sources: upload, storage, the file route, and what a read answers.

`images-and-pdfs-are-vault-sources-too` (Tier 2), requirements upload-file, file-route,
cannot-read's not-read-yet note and agents-read. The reading worker (transcribe, reader-contained)
is `test_vault_file_reading.py`. Same fixtures as `test_vault.py`: the project's directory is the
test's `tmp_path`, the vault's private root a temporary directory.
"""

import json
from pathlib import Path

import pytest

from hub import vault

BASE = "/api/v1/projects/proj-test"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24
MEBIBYTE = 1024 * 1024


async def _post(app, auth_headers, data: bytes, content_type: str, **query):
    params = {"name": "Refund policy", "type": "document", **query}
    return await app.post(
        f"{BASE}/vault/files",
        params=params,
        content=data,
        headers={**auth_headers, "Content-Type": content_type},
    )


async def _upload(app, auth_headers, data: bytes = PDF, content_type="application/pdf", **query):
    created = await _post(app, auth_headers, data, content_type, **query)
    assert created.status_code == 201, created.text
    return created.json()


def _files(root: Path) -> list:
    if not root.exists():
        return []
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _transcribe(tmp_path: Path, entry_id: str, text: str) -> None:
    (tmp_path / "knowledge" / "sources" / f"{entry_id}.md").write_bytes(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# upload-file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,content_type,ext",
    [
        (PDF, "application/pdf", "pdf"),
        (PNG, "image/png", "png"),
        (JPEG, "image/jpeg", "jpg"),
        (GIF, "image/gif", "gif"),
        (WEBP, "image/webp", "webp"),
    ],
)
async def test_a_file_is_stored_byte_for_byte_before_its_metadata(
    app, auth_headers, tmp_path, data, content_type, ext
) -> None:
    entry = await _upload(app, auth_headers, data, content_type)
    assert entry["media_type"] == content_type
    assert entry["name"] == "Refund policy"
    assert entry["type"] == "document"
    assert entry["visibility"] == "tracked"
    sources = tmp_path / "knowledge" / "sources"
    assert (sources / f"{entry['id']}.{ext}").read_bytes() == data
    meta = json.loads((sources / f"{entry['id']}.json").read_text(encoding="utf-8"))
    assert meta["media_type"] == content_type
    # Nothing is read yet: no transcription is written by the upload itself.
    assert not (sources / f"{entry['id']}.md").exists()


@pytest.mark.asyncio
async def test_a_file_over_the_global_cap_reaches_the_route(app, auth_headers, tmp_path) -> None:
    big = PDF + b"\x00" * (2 * MEBIBYTE)
    entry = await _upload(app, auth_headers, big)
    stored = tmp_path / "knowledge" / "sources" / f"{entry['id']}.pdf"
    assert stored.stat().st_size == len(big)

    # The cap is lifted for this route alone: a JSON upload of that size is still refused.
    refused = await app.post(
        f"{BASE}/vault/sources",
        json={"name": "x", "type": "note", "content": "a" * (2 * MEBIBYTE)},
        headers=auth_headers,
    )
    assert refused.status_code == 413, refused.text


@pytest.mark.asyncio
async def test_a_file_over_ten_mebibytes_is_refused_and_writes_nothing(
    app, auth_headers, tmp_path
) -> None:
    too_big = PDF + b"\x00" * (10 * MEBIBYTE)
    refused = await _post(app, auth_headers, too_big, "application/pdf")
    assert refused.status_code == 413, refused.text
    assert _files(tmp_path / "knowledge") == []

    exactly = PDF + b"\x00" * (10 * MEBIBYTE - len(PDF))
    accepted = await _post(app, auth_headers, exactly, "application/pdf")
    assert accepted.status_code == 201, accepted.text


@pytest.mark.asyncio
async def test_other_types_and_mismatched_bytes_are_refused_and_write_nothing(
    app, auth_headers, tmp_path
) -> None:
    for content_type in (
        "text/plain",
        "application/json",
        "application/octet-stream",
        "image/svg+xml",
    ):
        got = await _post(app, auth_headers, PDF, content_type)
        assert got.status_code == 415, (content_type, got.text)
    for data, content_type in ((PDF, "image/png"), (PNG, "application/pdf"), (b"", "image/gif")):
        got = await _post(app, auth_headers, data, content_type)
        assert got.status_code == 400, (content_type, got.text)
    # A webp needs its WEBP tag after the RIFF size, not only the RIFF.
    riff = await _post(app, auth_headers, b"RIFF\x00\x00\x00\x00WAVEfmt ", "image/webp")
    assert riff.status_code == 400, riff.text
    assert _files(tmp_path / "knowledge") == []


@pytest.mark.asyncio
async def test_the_query_fields_are_checked_as_a_text_uploads_are(
    app, auth_headers, tmp_path
) -> None:
    for query in (
        {"name": ""},
        {"name": "x" * 201},
        {"type": "poem"},
        {"visibility": "secret"},
        {"dated": "yesterday"},
    ):
        got = await _post(app, auth_headers, PDF, "application/pdf", **query)
        assert got.status_code == 400, (query, got.text)
    assert _files(tmp_path / "knowledge") == []

    entry = await _upload(app, auth_headers, dated="2026-09-01")
    assert entry["dated"] == "2026-09-01"


@pytest.mark.asyncio
async def test_a_private_file_leaves_only_a_stub_in_the_project(
    app, auth_headers, tmp_path, tmp_path_factory
) -> None:
    location = tmp_path_factory.mktemp("private-vault")
    put = await app.put(
        f"{BASE}/vault/settings", json={"private_location": str(location)}, headers=auth_headers
    )
    assert put.status_code == 200, put.text
    entry = await _upload(app, auth_headers, PNG, "image/png", visibility="private")
    assert entry["visibility"] == "private"
    assert entry["media_type"] == "image/png"
    assert (location / "sources" / f"{entry['id']}.png").read_bytes() == PNG
    assert _files(tmp_path / "knowledge") == [f"sources/{entry['id']}.json"]
    stub = json.loads(
        (tmp_path / "knowledge" / "sources" / f"{entry['id']}.json").read_text(encoding="utf-8")
    )
    assert stub["media_type"] == "image/png"
    assert "PNG" not in json.dumps(stub)


# ---------------------------------------------------------------------------
# file-route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_file_route_answers_the_bytes_with_their_type(app, auth_headers) -> None:
    pdf = await _upload(app, auth_headers, PDF, "application/pdf")
    png = await _upload(app, auth_headers, PNG, "image/png", name="Diagram")
    for entry, data, content_type in ((pdf, PDF, "application/pdf"), (png, PNG, "image/png")):
        got = await app.get(f"{BASE}/vault/sources/{entry['id']}/file", headers=auth_headers)
        assert got.status_code == 200, got.text
        assert got.content == data
        assert got.headers["content-type"].split(";")[0] == content_type


@pytest.mark.asyncio
async def test_the_file_route_refuses_unknown_text_and_foreign_sources(
    app, auth_headers, tmp_path
) -> None:
    text = await app.post(
        f"{BASE}/vault/sources",
        json={"name": "Notes", "type": "note", "content": "hello\n"},
        headers=auth_headers,
    )
    assert text.status_code == 201, text.text
    for unknown in (text.json()["id"], "src-ffffffffffff", "src-.."):
        got = await app.get(f"{BASE}/vault/sources/{unknown}/file", headers=auth_headers)
        assert got.status_code == 404, (unknown, got.text)

    sources = tmp_path / "knowledge" / "sources"
    (sources / "src-0123456789ab.json").write_text(
        json.dumps(
            {
                "id": "src-0123456789ab",
                "name": "Their scan",
                "type": "document",
                "visibility": "private",
                "holder": "colleague-laptop",
                "media_type": "application/pdf",
                "created_at": "2026-01-01T00:00:00.000000Z",
            }
        ),
        encoding="utf-8",
    )
    foreign = await app.get(f"{BASE}/vault/sources/src-0123456789ab/file", headers=auth_headers)
    assert foreign.status_code == 409, foreign.text
    assert "colleague-laptop" in foreign.text


# ---------------------------------------------------------------------------
# cannot-read (not-read-yet note) and agents-read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_map_and_a_read_carry_media_type_and_an_unread_file_says_so(
    app, auth_headers
) -> None:
    text = await app.post(
        f"{BASE}/vault/sources",
        json={"name": "Notes", "type": "note", "content": "hello\n"},
        headers=auth_headers,
    )
    pdf = await _upload(app, auth_headers)
    listed = await app.get(f"{BASE}/vault/map", headers=auth_headers)
    by_id = {e["id"]: e for e in listed.json()["entries"]}
    assert by_id[pdf["id"]]["media_type"] == "application/pdf"
    assert by_id[pdf["id"]]["available"] is False
    assert by_id[pdf["id"]]["opening"] is None
    assert by_id[text.json()["id"]]["media_type"] == "text/plain"

    read = await app.get(f"{BASE}/vault/entries/{pdf['id']}", headers=auth_headers)
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["media_type"] == "application/pdf"
    assert body["content"] is None
    assert body["next_offset"] is None
    assert "has not been read yet" in body["note"]
    assert "Manager page" in body["note"]


@pytest.mark.asyncio
async def test_a_transcribed_file_reads_as_its_transcription_in_pages(
    app, auth_headers, tmp_path
) -> None:
    pdf = await _upload(app, auth_headers)
    text = "Page 1\n" + ("Refunds up to 450 euros need no manager approval.\n" * 3000)
    _transcribe(tmp_path, pdf["id"], text)

    listed = await app.get(f"{BASE}/vault/map", headers=auth_headers)
    entry = next(e for e in listed.json()["entries"] if e["id"] == pdf["id"])
    assert entry["available"] is True
    assert entry["opening"].startswith("Page 1")

    first = (await app.get(f"{BASE}/vault/entries/{pdf['id']}", headers=auth_headers)).json()
    assert first["content"] == text[: vault.PAGE_CHARS]
    assert first["next_offset"] == vault.PAGE_CHARS
    assert "transcribed from the PDF" in first["note"]
    assert "Refund policy" in first["note"]
    second = (
        await app.get(
            f"{BASE}/vault/entries/{pdf['id']}",
            params={"offset": first["next_offset"]},
            headers=auth_headers,
        )
    ).json()
    assert first["content"] + second["content"] == text[: 2 * vault.PAGE_CHARS]


@pytest.mark.asyncio
async def test_an_image_is_named_an_image_in_the_note(app, auth_headers, tmp_path) -> None:
    png = await _upload(app, auth_headers, PNG, "image/png", name="Shipping sign")
    _transcribe(tmp_path, png["id"], "Free shipping threshold: 75 euros\n")
    body = (await app.get(f"{BASE}/vault/entries/{png['id']}", headers=auth_headers)).json()
    assert body["content"] == "Free shipping threshold: 75 euros\n"
    assert "transcribed from the image" in body["note"]
    assert "Shipping sign" in body["note"]


@pytest.mark.asyncio
async def test_a_foreign_file_stub_says_held_elsewhere_not_unread(
    app, auth_headers, tmp_path
) -> None:
    sources = tmp_path / "knowledge" / "sources"
    sources.mkdir(parents=True)
    (sources / "src-0123456789ab.json").write_text(
        json.dumps(
            {
                "id": "src-0123456789ab",
                "name": "Their scan",
                "type": "document",
                "visibility": "private",
                "holder": "colleague-laptop",
                "media_type": "image/png",
                "created_at": "2026-01-01T00:00:00.000000Z",
            }
        ),
        encoding="utf-8",
    )
    body = (await app.get(f"{BASE}/vault/entries/src-0123456789ab", headers=auth_headers)).json()
    assert body["media_type"] == "image/png"
    assert body["content"] is None
    assert "colleague-laptop" in body["note"]
    assert "not been read" not in body["note"]


@pytest.mark.asyncio
async def test_an_agent_reads_a_transcribed_file_through_its_run_credential(
    app, auth_headers, tmp_path
) -> None:
    from tests.test_vault import _run_headers

    pdf = await _upload(app, auth_headers)
    headers = await _run_headers("run-file-reader", "filereader")

    unread = await app.get(f"/api/v1/agent-actions/vault/entries/{pdf['id']}", headers=headers)
    assert unread.status_code == 200, unread.text
    assert unread.json()["content"] is None
    assert "has not been read yet" in unread.json()["note"]

    _transcribe(tmp_path, pdf["id"], "Refunds up to 450 euros need no manager approval.\n")
    read = await app.get(f"/api/v1/agent-actions/vault/entries/{pdf['id']}", headers=headers)
    assert read.json()["content"].startswith("Refunds up to 450 euros")
    assert read.json()["media_type"] == "application/pdf"
    listed = await app.get("/api/v1/agent-actions/vault/map", headers=headers)
    assert listed.json()["entries"][0]["media_type"] == "application/pdf"
