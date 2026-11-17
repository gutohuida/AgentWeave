"""Every test's outcome in every check run, and the flake rate read from them
(`landing-time-and-test-flakiness-are-measured`, FR-5, FR-6).

**What is recorded.** A check run that reads a test report records one `test_history` row per test
the report names, passed or failed (a skipped test did not run). The id is the report's own
(`classname::name`), and `file` is the report's file for it or `""`: pytest's xunit2 names none,
and nothing here depends on one (design 3). A test that failed and then passed on the confirmation
re-run of the same tree in the same check run is `flipped` (`project_checks.confirm_failure` names
those in the result's `flipped_tests`); one that failed on the re-run as well stays `failed`, so a
regression is never counted as a flake.

**How it gets here without growing the run's record.** The check run asks for every outcome by
running `recording(check)`: `project_checks._judge_by_report` then puts them on the result under
`OUTCOMES_KEY` and `FILES_KEY`. `take` removes both before anything stores the result -- a full
suite's outcomes are thousands of entries a run's `results` never kept -- and `record` writes them.

**The flake rate** (FR-6, design 4) is counted over a test's own last `WINDOW_RUNS` recorded runs,
not days, and only once it has `MINIMUM_RUNS`: below that the rate is NULL, and only its flip count
and last flip are given. `FLAKE_RATES_SQL` is the one definition, read by `flake_rates` here and by
the dashboard over the dashboard query's project-scoped `test_history` view.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import async_session_factory
from .db.models import CheckTestOutcome

logger = logging.getLogger(__name__)

#: Set on a check (`recording`) to have its run put every test outcome on the result.
RECORD_KEY = "record_test_outcomes"
#: On a result, while it is being recorded: test id -> `passed` or `failed`, in report order.
OUTCOMES_KEY = "test_outcomes"
#: On a result, while it is being recorded: test id -> the file its report names.
FILES_KEY = "test_report_files"
#: On a result: the failing tests the confirmation re-run passed (`confirm_failure`).
FLIPPED_KEY = "flipped_tests"

PASSED = "passed"
FAILED = "failed"
FLIPPED = "flipped"

PHASE_REVIEW = "review"
PHASE_LANDING = "landing"
PHASE_MAIN = "main"

#: A test's flake rate is over its most recent this many recorded runs (FR-6).
WINDOW_RUNS = 100
#: Below this many recorded runs a test has no rate, only its flips (FR-6).
MINIMUM_RUNS = 20

#: One row per test (`check_name`, `test_id`): `runs` recorded in all, `flips` in all,
#: `window_runs` and `window_flips` within its last `WINDOW_RUNS`, `flake_rate` (NULL below
#: `MINIMUM_RUNS` runs) and `last_flipped_at` (NULL until it first flips). `{source}` is the rows to
#: read: `test_history` in a dashboard query, which is already one project's.
FLAKE_RATES_SQL = f"""
with ranked as (
  select check_name, test_id, outcome, recorded_at,
         row_number() over (partition by check_name, test_id order by id desc) as recent,
         count(*) over (partition by check_name, test_id) as runs
  from {{source}}
)
select check_name, test_id,
       max(runs) as runs,
       sum(outcome = '{FLIPPED}') as flips,
       sum(recent <= {WINDOW_RUNS}) as window_runs,
       sum(recent <= {WINDOW_RUNS} and outcome = '{FLIPPED}') as window_flips,
       case when max(runs) >= {MINIMUM_RUNS}
            then round(1.0 * sum(recent <= {WINDOW_RUNS} and outcome = '{FLIPPED}')
                       / sum(recent <= {WINDOW_RUNS}), 4)
       end as flake_rate,
       max(case when outcome = '{FLIPPED}' then recorded_at end) as last_flipped_at
from ranked
group by check_name, test_id
"""

#: The ten tests with the highest flake rate among those with one, a rate of 0 being no flake
#: (FR-8's panel).
TEN_FLAKIEST_SQL = (
    "select check_name, test_id, flake_rate, last_flipped_at from ("
    + FLAKE_RATES_SQL.format(source="test_history")
    + ") where flake_rate > 0 "
    "order by flake_rate desc, last_flipped_at desc limit 10"
)


def recording(check: Dict[str, Any]) -> Dict[str, Any]:
    """*check*, run so that its result carries every test outcome its report names."""
    return {**check, RECORD_KEY: True}


Outcomes = Tuple[Dict[str, str], Dict[str, str]]


def take(result: Dict[str, Any]) -> Optional[Outcomes]:
    """Remove the test outcomes from *result* before it is stored: (outcomes, files), or `None`
    where its run read no report."""
    outcomes = result.pop(OUTCOMES_KEY, None)
    files = result.pop(FILES_KEY, None) or {}
    if not isinstance(outcomes, dict):
        return None
    return outcomes, files


def rows_for(taken: Optional[Outcomes], result: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """(test id, file, outcome) for each test of *taken*, a failure the re-run passed `flipped`."""
    if taken is None:
        return []
    outcomes, files = taken
    flipped = set(result.get(FLIPPED_KEY) or [])
    rows = []
    for test, outcome in outcomes.items():
        if outcome == FAILED and test in flipped:
            outcome = FLIPPED
        rows.append((test, str(files.get(test) or ""), outcome))
    return rows


async def record(
    *,
    project_id: str,
    check_run_id: str,
    phase: str,
    commit_sha: Optional[str],
    check_name: str,
    taken: Optional[Outcomes],
    result: Dict[str, Any],
) -> None:
    """Write one history row per test of *taken*. Never raises: a run's verdict does not depend on
    its history, so a failed write is logged and the run goes on."""
    rows = rows_for(taken, result)
    if not rows:
        return
    try:
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            session.add_all(
                CheckTestOutcome(
                    project_id=project_id,
                    check_name=check_name,
                    test_id=test,
                    file=file,
                    outcome=outcome,
                    check_run_id=check_run_id,
                    phase=phase,
                    commit_sha=commit_sha,
                    recorded_at=now,
                )
                for test, file, outcome in rows
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning(
            "could not record the test history of check %s in run %s",
            check_name,
            check_run_id,
            exc_info=True,
        )


async def flake_rates(
    session: AsyncSession,
    project_id: str,
    check_name: Optional[str] = None,
    test_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Each test's flake figures in *project_id* (`FLAKE_RATES_SQL`), optionally one check's or
    one test's."""
    source = "(select * from test_history where project_id = :project_id"
    params: Dict[str, Any] = {"project_id": project_id}
    if check_name is not None:
        source += " and check_name = :check_name"
        params["check_name"] = check_name
    if test_id is not None:
        source += " and test_id = :test_id"
        params["test_id"] = test_id
    sql = FLAKE_RATES_SQL.format(source=source + ")")
    rows = (await session.execute(text(sql), params)).mappings().all()
    return [dict(row) for row in rows]
