"""F627: another process holding the database answered every route a bare `500` after the busy
timeout ran out. A lock is a state to wait out: the Hub answers 503 saying the database is busy,
with `Retry-After`, and the request did not finish."""

import sqlite3

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_a_locked_database_answers_503_busy_with_retry_after(
    app, auth_headers, monkeypatch
) -> None:
    async def locked(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, sqlite3.OperationalError("database is locked"))

    monkeypatch.setattr(AsyncSession, "execute", locked)

    answered = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)

    assert answered.status_code == 503, answered.text
    assert answered.headers["Retry-After"] == "5"
    assert "database is busy" in answered.json()["detail"]
    assert "retry" in answered.json()["detail"]
