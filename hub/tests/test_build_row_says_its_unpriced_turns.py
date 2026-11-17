"""`spec-home-shows-what-is-being-built...` (FR-3, FR-9): a build row says how many of its turns
carry no price, so the home can show 'unpriced' instead of a $0 that reads as free."""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Build, Run, TurnUsage

from .test_a_build_has_a_driver_a_level_and_its_people import (
    BASE,
    P,
    _approved,
    _build,
    _document,
    _roster_rows,
    _tasks_by_key,
    author_headers,  # noqa: F401, F811 -- a fixture, used by name
)


@pytest.mark.asyncio
async def test_a_finished_build_with_an_unpriced_turn_says_so(
    app, auth_headers, author_headers  # noqa: F811
):
    await _roster_rows("dev")
    await _approved(app, auth_headers, author_headers, _document())
    built = await _build(app, auth_headers, driver="hand", level="fast")
    build_id = built.json()["build_outcome"]["build"]["id"]
    t1 = (await _tasks_by_key())["t1"]
    async with async_session_factory() as db:
        db.add(Run(id="run-unpriced", project_id=P, agent="dev", task_id=t1.id, status="completed"))
        await db.flush()
        db.add(
            TurnUsage(
                id="usage-unpriced",
                run_id="run-unpriced",
                project_id=P,
                agent="dev",
                status="measured",
                total_tokens=10,
                api_equivalent_usd_micros=None,
            )
        )
        (await db.get(Build, build_id)).state = "finished"
        await db.commit()

    rows = (await app.get(f"{BASE}/builds", headers=auth_headers)).json()["builds"]

    (row,) = [r for r in rows if r["id"] == build_id]
    assert row["spent_usd"] == 0.0
    assert row["unpriced_turns"] >= 1
