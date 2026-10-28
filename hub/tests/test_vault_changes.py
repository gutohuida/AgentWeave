"""The operator changes a vault source: edits a text, replaces a file, and the facts follow.

`vault-sources-can-be-edited-replaced-and-archived` (Tier 2), the operator's half: ac-operator-edit,
ac-outdated-edit, ac-file-not-text (operator side), ac-operator-replace, ac-record (the list kept
with the source), ac-redistil and ac-stale. The distillation worker is faked, as in
`test_vault_distillation.py`: what is checked is what the Hub does around it.
"""

import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import distillation, manager, vault
from hub.db.engine import async_session_factory
from hub.db.models import EventLog
from hub.worker import WorkerResult

BASE = "/api/v1/projects/proj-test"
JOB = "vault-distillation"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
PDF2 = b"%PDF-1.7\n2 0 obj\n<< /Type /Catalog /Signed true >>\nendobj\n%%EOF\n"
NOTE = "Problems\nF-1 the map is slow: open\nF-2 the tab flickers: open\n"
EDITED = "Problems\nF-1 the map is slow: cleared\nF-2 the tab flickers: open\n"


class _Worker:
    """Stands in for `run_worker`. A reading call answers *transcription*; every other call
    answers *facts* as (claim, [quotes]) pairs. With a *gate* set, a call waits for it."""

    def __init__(self) -> None:
        self.facts = [("F-2 is open", ["F-2 the tab flickers: open"])]
        self.transcription = "Signed policy\nRefunds need approval.\n"
        self.gate: asyncio.Event = asyncio.Event()
        self.gate.set()
        self.calls: list = []

    async def __call__(self, **kwargs) -> WorkerResult:
        self.calls.append(kwargs)
        await self.gate.wait()
        if kwargs.get("reading"):
            return WorkerResult("ok", parsed=distillation.Transcribed(text=self.transcription))
        return WorkerResult(
            "ok",
            parsed=distillation.Distilled(
                facts=[distillation.FactDraft(claim=c, quotes=q) for c, q in self.facts]
            ),
        )


@pytest.fixture
def worker(monkeypatch):
    fake = _Worker()
    monkeypatch.setattr(distillation, "run_worker", fake)
    return fake


async def _enable(app, auth_headers, enabled=True) -> None:
    if enabled:
        runner = await app.post(
            f"{BASE}/runners",
            json={"name": "distiller", "cli": "claude", "model": "claude-haiku-4-5-20251001"},
            headers=auth_headers,
        )
        assert runner.status_code in (201, 409), runner.text
        runners = (await app.get(f"{BASE}/runners", headers=auth_headers)).json()
        runners = runners if isinstance(runners, list) else runners.get("runners", [])
        fields = {"enabled": True, "runner_id": runners[0]["id"]}
    else:
        fields = {"enabled": False}
    patched = await app.patch(f"{BASE}/manager/jobs/{JOB}", json=fields, headers=auth_headers)
    assert patched.status_code == 200, patched.text


async def _text(app, auth_headers, content=NOTE, **fields) -> dict:
    body = {"name": "Problems", "type": "note", "content": content, **fields}
    created = await app.post(f"{BASE}/vault/sources", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()


async def _pdf(app, auth_headers, data=PDF, **query) -> dict:
    created = await app.post(
        f"{BASE}/vault/files",
        params={"name": "Policy", "type": "document", **query},
        content=data,
        headers={**auth_headers, "Content-Type": "application/pdf"},
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _run_headers(run_id: str, agent: str) -> dict:
    from hub.agent_auth import hash_run_token
    from hub.db.models import Agent, Run

    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as db:
        db.add(Agent(id=f"agent-{agent}", project_id="proj-test", name=agent))
        db.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _read(app, headers, entry_id) -> dict:
    got = await app.get(f"{BASE}/vault/entries/{entry_id}", headers=headers)
    assert got.status_code == 200, got.text
    return got.json()


async def _edit(app, auth_headers, entry_id, content, version):
    return await app.put(
        f"{BASE}/vault/sources/{entry_id}/text",
        json={"content": content, "version": version},
        headers=auth_headers,
    )


async def _replace(app, auth_headers, entry_id, data, content_type="application/pdf"):
    return await app.put(
        f"{BASE}/vault/sources/{entry_id}/file",
        content=data,
        headers={**auth_headers, "Content-Type": content_type},
    )


async def _firings(source_id: str) -> list:
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(EventLog).where(EventLog.event_type == manager.FIRED_EVENT)))
            .scalars()
            .all()
        )
    return [
        row.data
        for row in rows
        if (row.data or {}).get("job") == JOB
        and ((row.data or {}).get("subject") or {}).get("source") == source_id
    ]


async def _idle() -> None:
    """Wait for the background re-distillations to end."""
    for _ in range(200):
        if not distillation._changed:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("a re-distillation never ended")


def _facts(tmp_path: Path) -> list:
    folder = tmp_path / "knowledge" / "facts"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("fct-*.json"))]


# ---------------------------------------------------------------------------
# operator-edits-text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["tracked", "private"])
async def test_ac_operator_edit(app, auth_headers, tmp_path, visibility) -> None:
    source = await _text(app, auth_headers, visibility=visibility, dated="2026-10-01")
    read = await _read(app, auth_headers, source["id"])
    assert read["version"] and read["changes"] == []

    done = await _edit(app, auth_headers, source["id"], EDITED, read["version"])
    assert done.status_code == 200, done.text
    answer = done.json()
    for key in ("id", "name", "type", "visibility", "dated", "created_at"):
        assert answer[key] == source[key], key

    entries = (await app.get(f"{BASE}/vault/map", headers=auth_headers)).json()["entries"]
    assert (
        "F-1 the map is slow: cleared"
        in next(e for e in entries if e["id"] == source["id"])["opening"]
    )
    agent = await _run_headers("run-edit-reader", "reader")
    for url, headers in (
        (f"{BASE}/vault/entries/{source['id']}", auth_headers),
        (f"/api/v1/agent-actions/vault/entries/{source['id']}", agent),
    ):
        got = await app.get(url, headers=headers)
        assert got.status_code == 200, got.text
        assert got.json()["content"] == EDITED
    assert answer["version"] != read["version"]

    after = await _read(app, auth_headers, source["id"])
    assert [(c["action"], c["by"]) for c in after["changes"]] == [("edit", {"kind": "operator"})]
    assert (tmp_path / "knowledge" / "sources" / f"{source['id']}.changes.json").is_file()


@pytest.mark.asyncio
async def test_ac_outdated_edit(app, auth_headers) -> None:
    source = await _text(app, auth_headers)
    v1 = (await _read(app, auth_headers, source["id"]))["version"]
    assert (await _edit(app, auth_headers, source["id"], EDITED, v1)).status_code == 200

    stale = await _edit(app, auth_headers, source["id"], "Overwritten\n", v1)
    assert stale.status_code == 409
    assert "changed since it was opened" in stale.json()["detail"]
    assert (await _read(app, auth_headers, source["id"]))["content"] == EDITED


# ---------------------------------------------------------------------------
# file-source-not-edited-as-text and operator-replaces-file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_file_not_text_operator(app, auth_headers, tmp_path) -> None:
    source = await _pdf(app, auth_headers)
    sources = tmp_path / "knowledge" / "sources"
    (sources / f"{source['id']}.md").write_text("Transcribed.\n", encoding="utf-8")
    version = (await _read(app, auth_headers, source["id"]))["version"]

    refused = await _edit(app, auth_headers, source["id"], "Typed over.\n", version)
    assert refused.status_code == 409
    assert "replacing" in refused.json()["detail"]
    assert (sources / f"{source['id']}.pdf").read_bytes() == PDF
    assert (sources / f"{source['id']}.md").read_text(encoding="utf-8") == "Transcribed.\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["tracked", "private"])
async def test_ac_operator_replace(app, auth_headers, tmp_path, visibility) -> None:
    source = await _pdf(app, auth_headers, visibility=visibility, dated="2026-10-02")
    held = tmp_path / "knowledge" if visibility == "tracked" else None
    if held is None:
        found = await app.get(f"{BASE}/vault/sources/{source['id']}/file", headers=auth_headers)
        assert found.content == PDF
    else:
        (held / "sources" / f"{source['id']}.md").write_text("Old reading.\n", encoding="utf-8")

    done = await _replace(app, auth_headers, source["id"], PDF2)
    assert done.status_code == 200, done.text
    for key in ("id", "name", "type", "visibility", "dated", "created_at"):
        assert done.json()[key] == source[key], key
    served = await app.get(f"{BASE}/vault/sources/{source['id']}/file", headers=auth_headers)
    assert served.content == PDF2
    if held is not None:
        assert not (held / "sources" / f"{source['id']}.md").exists()
    read = await _read(app, auth_headers, source["id"])
    assert read["content"] is None
    assert [c["action"] for c in read["changes"]] == ["replace"]

    mismatched = await _replace(app, auth_headers, source["id"], PDF, "image/png")
    assert mismatched.status_code == 400
    wrong_type = await _replace(app, auth_headers, source["id"], PDF, "text/plain")
    assert wrong_type.status_code == 415
    served = await app.get(f"{BASE}/vault/sources/{source['id']}/file", headers=auth_headers)
    assert served.content == PDF2


@pytest.mark.asyncio
async def test_a_text_source_is_not_replaced_by_a_file_and_unknown_ones_are_404(
    app, auth_headers
) -> None:
    source = await _text(app, auth_headers)
    refused = await _replace(app, auth_headers, source["id"], PDF)
    assert refused.status_code == 409
    assert (await _replace(app, auth_headers, "src-ffffffffffff", PDF)).status_code == 404
    assert (await _edit(app, auth_headers, "src-ffffffffffff", "x", "v")).status_code == 404


# ---------------------------------------------------------------------------
# record-each-change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_private_sources_changes_are_kept_beside_its_stub_without_text(
    app, auth_headers, tmp_path
) -> None:
    source = await _text(app, auth_headers, visibility="private")
    version = (await _read(app, auth_headers, source["id"]))["version"]
    assert (await _edit(app, auth_headers, source["id"], EDITED, version)).status_code == 200

    stub = tmp_path / "knowledge" / "sources" / f"{source['id']}.changes.json"
    recorded = json.loads(stub.read_text(encoding="utf-8"))
    assert [c["action"] for c in recorded] == ["edit"]
    assert "cleared" not in stub.read_text(encoding="utf-8")
    assert "sha256" not in (stub.parent / f"{source['id']}.json").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# redistil-after-change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_redistil(app, auth_headers, worker) -> None:
    await _enable(app, auth_headers)
    text = await _text(app, auth_headers)
    pdf = await _pdf(app, auth_headers)
    await _idle()
    before = {s["id"]: len(await _firings(s["id"])) for s in (text, pdf)}
    worker.gate.clear()

    version = (await _read(app, auth_headers, text["id"]))["version"]
    edited = await asyncio.wait_for(_edit(app, auth_headers, text["id"], EDITED, version), 5)
    replaced = await asyncio.wait_for(_replace(app, auth_headers, pdf["id"], PDF2), 5)
    assert edited.status_code == 200 and replaced.status_code == 200
    assert "background" in edited.json()["note"]

    for _ in range(100):  # both distillations have started and wait on the held worker
        if len(worker.calls) >= 2:
            break
        await asyncio.sleep(0.02)
    worker.gate.set()
    await _idle()
    for source in (text, pdf):
        fired = await _firings(source["id"])
        assert len(fired) > before[source["id"]], source["id"]
    # The new file was read afresh, not served from the old transcription.
    assert any(call.get("reading") for call in worker.calls[-6:])


@pytest.mark.asyncio
async def test_changes_during_a_distillation_coalesce_into_one_more(
    app, auth_headers, worker
) -> None:
    await _enable(app, auth_headers)
    source = await _text(app, auth_headers)
    await _idle()
    worker.gate.clear()
    version = (await _read(app, auth_headers, source["id"]))["version"]
    texts = [NOTE + "a\n", NOTE + "a\nb\n", NOTE + "a\nb\nc\n"]
    for text in texts:
        done = await _edit(app, auth_headers, source["id"], text, version)
        assert done.status_code == 200, done.text
        version = done.json()["version"]
    worker.calls.clear()
    worker.gate.set()
    await _idle()
    # The first run saw the first or later text; at most one more follows, never one per edit.
    assert 1 <= len(worker.calls) <= 2
    read = await _read(app, auth_headers, source["id"])
    assert read["stale"] is False


# ---------------------------------------------------------------------------
# stale-when-not-distilled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_stale(app, auth_headers, worker, tmp_path) -> None:
    worker.facts = [
        ("F-1 is open", ["F-1 the map is slow: open"]),
        ("F-2 is open", ["F-2 the tab flickers: open"]),
    ]
    await _enable(app, auth_headers)
    source = await _text(app, auth_headers)
    await _idle()
    [one, two] = _facts(tmp_path)
    await _enable(app, auth_headers, enabled=False)

    version = (await _read(app, auth_headers, source["id"]))["version"]
    done = await _edit(app, auth_headers, source["id"], EDITED + "More.\n", version)
    assert done.status_code == 200, done.text
    assert done.json()["stale"] is True
    assert "stale" in done.json()["note"] and "Enable" in done.json()["note"]

    entries = (await app.get(f"{BASE}/vault/map", headers=auth_headers)).json()["entries"]
    facts = {e["id"]: e for e in entries if e["kind"] == "fact"}
    assert facts[one["id"]]["stale"] is True and facts[two["id"]]["stale"] is True
    for fact in (one, two):
        read = await _read(app, auth_headers, fact["id"])
        assert "source changed after this fact was drawn" in read["content"]

    # Distilling again, as the job comes back on, clears it.
    worker.facts = [("F-2 is open", ["F-2 the tab flickers: open"])]
    await _enable(app, auth_headers)
    queued = await app.post(f"{BASE}/vault/sources/{source['id']}/distil", headers=auth_headers)
    assert queued.status_code == 202
    await _idle()
    entries = (await app.get(f"{BASE}/vault/map", headers=auth_headers)).json()["entries"]
    assert not any(e["stale"] for e in entries if e["kind"] == "fact")
    assert (await _read(app, auth_headers, source["id"]))["stale"] is False


def test_a_source_changed_on_disk_is_stale_by_its_version(tmp_path) -> None:
    """The version is the text's hash, so a pull that changes the file is seen as a change."""
    source = vault.add_source(
        tmp_path, tmp_path / "private", name="n", type="note", content="one\n", visibility="tracked"
    )
    vault.set_distilled_version(
        tmp_path,
        tmp_path / "private",
        source["id"],
        vault.source_version(tmp_path, tmp_path / "private", source["id"]),
    )
    path = tmp_path / "knowledge" / "sources" / f"{source['id']}.md"
    path.write_text("two\n", encoding="utf-8")
    entry = vault.read_entry(tmp_path, tmp_path / "private", source["id"])
    assert entry is not None and entry["stale"] is True
