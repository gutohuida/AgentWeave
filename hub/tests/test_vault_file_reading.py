"""Images and PDFs are read before they are distilled: the reading worker and its containment.

`images-and-pdfs-are-vault-sources-too` (Tier 2), requirements transcribe, reader-contained and
cannot-read. Unlike `test_vault_distillation.py`, the fake stands in for the *process*
(`worker._run_worker_process`), not for `run_worker`: what the reading spawn's command holds and
which directory it runs in are the point, and both are decided inside `run_worker`. The real spawn
is the acceptance drive's (`scripts/drive/d1026_images_pdfs.py`).
"""

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import manager, worker
from hub.db.engine import async_session_factory
from hub.db.models import EventLog
from hub.runner_adapters import get_adapter
from hub.runner_adapters.claude import ClaudeAdapter

BASE = "/api/v1/projects/proj-test"
JOB = "vault-distillation"
HAIKU = "claude-haiku-4-5-20251001"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
TRANSCRIPTION = (
    "--- page 1 ---\n"
    "Acme refund policy\n"
    "--- page 2 ---\n"
    "Refunds up to 450 euros need no manager approval.\n"
)
WIDENING = ("--dangerously-skip-permissions", "--add-dir", "--allowedTools", "--allowed-tools")


def _envelope(answer) -> str:
    text = answer if isinstance(answer, str) else json.dumps(answer)
    return json.dumps(
        {
            "type": "result",
            "is_error": False,
            "result": text,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "total_cost_usd": 0.01,
        }
    )


def _reads(cmd) -> bool:
    return "--tools" in cmd and cmd[cmd.index("--tools") + 1] == "Read"


class _Process:
    """Stands in for `worker._run_worker_process`. A reading spawn gets *reading* (a dict to
    answer, a string answered as prose, or None for a spawn that fails); every other spawn gets
    one fact quoting the transcription's last line, then (for the contradiction check) none."""

    def __init__(self, reading=None) -> None:
        self.reading = {"text": TRANSCRIPTION} if reading is None else reading
        self.spawns: list = []

    def __call__(self, cmd, cwd, timeout, env=None):
        listed = sorted(os.listdir(cwd)) if cwd and os.path.isdir(cwd) else None
        held = {name: Path(cwd, name).read_bytes() for name in listed or []}
        self.spawns.append({"cmd": list(cmd), "cwd": cwd, "listed": listed, "held": held})
        if _reads(cmd):
            if self.reading is False:
                return worker._Spawn("nonzero_exit", exit_code=1, error="exited 1: no credit")
            return worker._Spawn("ok", stdout=_envelope(self.reading), exit_code=0)
        quote = "Refunds up to 450 euros need no manager approval."
        facts = [{"claim": "A refund up to 450 euros needs no approval.", "quotes": [quote]}]
        return worker._Spawn("ok", stdout=_envelope({"facts": facts}), exit_code=0)

    @property
    def readings(self) -> list:
        return [spawn for spawn in self.spawns if _reads(spawn["cmd"])]


@pytest.fixture
def process(monkeypatch):
    def install(reading=None) -> _Process:
        fake = _Process(reading)
        monkeypatch.setattr(worker, "_run_worker_process", fake)
        return fake

    return install


async def _runner(app, auth_headers, cli="claude", model=HAIKU) -> str:
    payload = {"name": f"distiller-{cli}", "cli": cli}
    if model:
        payload["model"] = model
    created = await app.post(f"{BASE}/runners", json=payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _enable(app, auth_headers, runner_id: str) -> None:
    patched = await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"enabled": True, "runner_id": runner_id},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text


async def _upload(app, auth_headers, data=PDF, content_type="application/pdf") -> dict:
    created = await app.post(
        f"{BASE}/vault/files",
        params={"name": "Refund policy", "type": "document"},
        content=data,
        headers={**auth_headers, "Content-Type": content_type},
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _firings() -> list:
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(EventLog).where(EventLog.event_type == manager.FIRED_EVENT)))
            .scalars()
            .all()
        )
    return [row.data for row in rows if (row.data or {}).get("job") == JOB]


def _facts(tmp_path: Path) -> list:
    folder = tmp_path / "knowledge" / "facts"
    if not folder.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("fct-*.json"))]


# ---------------------------------------------------------------------------
# reader-contained
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", [None, HAIKU, "claude-sonnet-4-6"])
def test_the_reading_command_holds_read_alone_and_no_widening_flag(model) -> None:
    cmd = ClaudeAdapter().read_one_shot(model=model, prompt="Read the file.")
    assert cmd[cmd.index("--tools") + 1] == "Read"
    assert cmd.count("--tools") == 1
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "default"
    assert cmd.count("--permission-mode") == 1
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert not any(flag.startswith(WIDENING) for flag in cmd[:-1])
    assert ("--model" in cmd) == bool(model)


def test_only_claude_reads_files() -> None:
    assert get_adapter("claude").one_shot_reads_files is True
    for cli in ("codex", "copilot"):
        adapter = get_adapter(cli)
        assert adapter.one_shot_reads_files is False
        assert adapter.read_one_shot(model=None, prompt="Read the file.") is None


# ---------------------------------------------------------------------------
# transcribe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pdf_is_read_alone_then_distilled_from_its_transcription(
    app, auth_headers, process, tmp_path
) -> None:
    fake = process()
    await _enable(app, auth_headers, await _runner(app, auth_headers))
    source = await _upload(app, auth_headers)

    # One reading spawn, in a directory holding only a copy of the file, outside the project.
    [reading] = fake.readings
    assert reading["listed"] == [f"{source['id']}.pdf"]
    assert reading["held"] == {f"{source['id']}.pdf": PDF}
    assert Path(tmp_path) not in Path(reading["cwd"]).parents
    assert Path(reading["cwd"]) != Path(tmp_path)
    assert not os.path.exists(reading["cwd"])  # gone once the spawn is over
    assert str(Path(reading["cwd"], f"{source['id']}.pdf")) in reading["cmd"][-1]

    # The transcription is the source's text, and the facts cite its lines.
    stored = tmp_path / "knowledge" / "sources" / f"{source['id']}.md"
    assert stored.read_text(encoding="utf-8") == TRANSCRIPTION
    distilling = [spawn for spawn in fake.spawns if not _reads(spawn["cmd"])]
    assert distilling and "Refunds up to 450 euros" in distilling[0]["cmd"][-1]
    [fact] = _facts(tmp_path)
    assert fact["citations"] == [
        {
            "source": source["id"],
            "quote": "Refunds up to 450 euros need no manager approval.",
            "line_start": 4,
            "line_end": 4,
        }
    ]

    read = await app.get(f"{BASE}/vault/entries/{source['id']}", headers=auth_headers)
    assert read.json()["content"] == TRANSCRIPTION
    assert "transcribed from the PDF" in read.json()["note"]

    # Each spawn is one firing; the reading's says what it read.
    firings = await _firings()
    assert len(firings) == len(fake.spawns)
    [read_firing] = [f for f in firings if f.get("step") == "read"]
    assert read_firing["outcome"] == "written"
    assert read_firing["trigger"] == "source_uploaded"
    assert read_firing["subject"] == {"source": source["id"]}
    assert "PDF" in read_firing["detail"]

    # Distilled again: from the stored transcription, with no new reading.
    again = await app.post(f"{BASE}/vault/sources/{source['id']}/distil", headers=auth_headers)
    assert again.status_code == 202, again.text
    assert len(fake.readings) == 1
    assert len([s for s in fake.spawns if not _reads(s["cmd"])]) > len(distilling)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reading,reason",
    [
        (False, "no credit"),
        ("I could not open that file, sorry.", "no JSON"),
        ({"text": "   "}, "no text"),
    ],
)
async def test_a_failed_reading_stores_nothing_and_fails_its_firing(
    app, auth_headers, process, tmp_path, reading, reason
) -> None:
    fake = process(reading)
    await _enable(app, auth_headers, await _runner(app, auth_headers))
    source = await _upload(app, auth_headers, PNG, "image/png")

    assert len(fake.spawns) == 1 and len(fake.readings) == 1  # nothing distilled after it
    assert not (tmp_path / "knowledge" / "sources" / f"{source['id']}.md").exists()
    assert _facts(tmp_path) == []
    [firing] = await _firings()
    assert firing["outcome"] == "failed"
    assert firing["step"] == "read"
    assert reason in firing["detail"]

    read = await app.get(f"{BASE}/vault/entries/{source['id']}", headers=auth_headers)
    assert read.json()["content"] is None
    assert "has not been read yet" in read.json()["note"]


@pytest.mark.asyncio
async def test_the_reading_prompt_asks_for_every_line_and_treats_the_file_as_data(
    app, auth_headers, process
) -> None:
    fake = process()
    await _enable(app, auth_headers, await _runner(app, auth_headers))
    await _upload(app, auth_headers, PNG, "image/png")
    prompt = fake.readings[0]["cmd"][-1]
    assert "every line of text" in prompt
    assert "describe" in prompt.lower()  # an image also gets a short description
    assert "not instructions" in prompt


# ---------------------------------------------------------------------------
# cannot-read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_codex_runner_cannot_read_and_spawns_nothing(
    app, auth_headers, process, tmp_path
) -> None:
    fake = process()
    await _enable(app, auth_headers, await _runner(app, auth_headers, cli="codex", model=None))
    source = await _upload(app, auth_headers, PNG, "image/png")
    assert fake.spawns == []
    assert await _firings() == []

    refused = await app.post(f"{BASE}/vault/sources/{source['id']}/distil", headers=auth_headers)
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert "codex" in detail and "Claude runner" in detail and "Manager page" in detail
    assert fake.spawns == []

    read = await app.get(f"{BASE}/vault/entries/{source['id']}", headers=auth_headers)
    assert read.json()["content"] is None
    assert "has not been read yet" in read.json()["note"]


@pytest.mark.asyncio
async def test_a_transcribed_file_distils_on_any_runner_without_reading(
    app, auth_headers, process, tmp_path
) -> None:
    """The transcription is text: a runner that cannot read files can still distil it."""
    fake = process()
    await _enable(app, auth_headers, await _runner(app, auth_headers, cli="codex", model=None))
    source = await _upload(app, auth_headers)
    (tmp_path / "knowledge" / "sources" / f"{source['id']}.md").write_text(
        TRANSCRIPTION, encoding="utf-8"
    )
    answered = await app.post(f"{BASE}/vault/sources/{source['id']}/distil", headers=auth_headers)
    assert answered.status_code == 202, answered.text
    assert fake.spawns and fake.readings == []
