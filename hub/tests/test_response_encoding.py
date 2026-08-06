"""JSON responses declare an explicit UTF-8 charset (task 7).

Starlette's default `JSONResponse` sends `Content-Type: application/json` with no
`charset` parameter. The body itself is always correct UTF-8 (JSON is UTF-8 by
definition, RFC 8259) — but a client that does not itself default to UTF-8 for an
unlabelled `application/json` response can decode it wrong. Reproduced live against a
real Hub: Windows PowerShell 5.1's `Invoke-WebRequest` rendered a stored runner name
containing an em dash as mojibake (`Codex CLI â€” GPT-5.4-Mini`) with no charset present,
and correctly once `hub.main.UTF8JSONResponse` added one. See design.md Decision 5 —
this superseded that decision's original "double-encoding in the write path" hypothesis,
which raw-byte inspection at the database, the HTTP wire, and construction time all ruled
out before this fix was written.
"""

import pytest


@pytest.mark.asyncio
async def test_api_responses_declare_utf8_charset(app, auth_headers):
    resp = await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json; charset=utf-8"


@pytest.mark.asyncio
async def test_health_endpoint_declares_utf8_charset(app):
    resp = await app.get("/health")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json; charset=utf-8"


@pytest.mark.asyncio
async def test_non_ascii_runner_name_round_trips_through_the_api(app, auth_headers, monkeypatch):
    """The auto-provisioning path (`hub/hub/api/v1/agents.py`) builds a runner name
    containing a literal em dash. Regression test for the actual defect: the byte
    sequence a client receives must be unambiguous UTF-8, not just correct in the
    Hub's own memory."""
    monkeypatch.setattr(
        "hub.api.v1.agents.probe_agent",
        lambda *_: {"runnable": True, "reason": None},
    )
    created = await app.post(
        "/api/v1/projects/proj-test/agents",
        json={"name": "em-dash-agent", "provider": "codex", "model": "gpt-5.4-mini"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text

    resp = await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json; charset=utf-8"
    names = [r["name"] for r in resp.json()]
    assert any("—" in name for name in names), names
