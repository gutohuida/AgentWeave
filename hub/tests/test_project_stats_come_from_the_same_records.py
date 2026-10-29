"""`project-stats-come-from-the-same-records`: one tally feeds the spec page, the project view and the
Activity tab's ledger (slice G of the roadmap "Flows that do not stall").

The acceptance drive. Every test seeds the records the Hub keeps (runs and their usage, transitions,
check runs, evidence, stalls, builds) with a hand-written timeline, then reads them through the real
routes, so the expected figures are arithmetic rather than a measurement. On master each fails for
the reason the slice exists: `GET /projects/{id}/stats` answers 404, the ledger adds an unpriced run
as $0, three sums with three rules exist, and nothing knows a mender run's spec or a run's role.

Named by acceptance criterion: `-k same_function`, `-k no_second_sum`, `-k totals_agree`, `-k roles`,
`-k mender`, `-k partition`, `-k checks`, `-k send_back`, `-k per_piece`, `-k beside_failing`,
`-k groupings`, `-k unpriced`.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hub import work_tally
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    Build,
    InboundQueueEntry,
    Loop,
    RequirementEvidence,
    Run,
    SpecDocument,
    Stall,
    Task,
    TaskCheckRun,
    TaskTransition,
    TurnUsage,
    WorkerInvocation,
)

P = "proj-test"
BASE = f"/api/v1/projects/{P}"
STATS = f"{BASE}/stats"
LEDGER = f"{BASE}/ledger"
ACCOUNTING = f"{BASE}/accounting"
T0 = datetime(2026, 10, 26, 22, 0, tzinfo=timezone.utc)
HUB = Path(work_tally.__file__).parent

_n = 0


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def _id(prefix: str) -> str:
    global _n
    _n += 1
    return f"{prefix}-{_n}"


# --- the records, one factory each ------------------------------------------------------------


def doc(doc_id: str, title: str = "") -> SpecDocument:
    return SpecDocument(
        id=doc_id,
        project_id=P,
        path=f"spec/changes/{doc_id}/spec.json",
        title=title or doc_id,
        phase="approved",
    )


def build(build_id: str, document: str, *, level="reviewed", start=0, stop=None, **extra) -> Build:
    return Build(
        id=build_id,
        project_id=P,
        document_id=document,
        state="running" if stop is None else "finished",
        driver="hand",
        level=level,
        builders=[],
        reviewers=[],
        created_at=at(start),
        stopped_at=at(stop) if stop is not None else None,
        **extra,
    )


def task(task_id: str, document, build_id=None, status="in_progress", level="reviewed") -> Task:
    return Task(
        id=task_id,
        project_id=P,
        title=task_id,
        status=status,
        spec_document_id=document,
        build_id=build_id,
        level=level if build_id else None,
    )


def run(run_id, agent, start, end, task_id=None, conv=None) -> Run:
    return Run(
        id=run_id,
        project_id=P,
        agent=agent,
        status="completed",
        turn_depth=0,
        task_id=task_id,
        conversation_id=conv,
        started_at=at(start),
        ended_at=at(end),
    )


def usage(run_id, agent, micros, model="sonnet", tokens=100, **extra) -> TurnUsage:
    return TurnUsage(
        id=f"u-{run_id}",
        run_id=run_id,
        project_id=P,
        agent=agent,
        status="measured" if tokens is not None else "unavailable",
        model=model,
        total_tokens=tokens,
        api_equivalent_usd_micros=micros,
        observed_at=T0,
        **extra,
    )


def move(task_id, frm, to, minute, agent, run_id, level="reviewed") -> TaskTransition:
    return TaskTransition(
        id=_id("ttr"),
        project_id=P,
        task_id=task_id,
        from_status=frm,
        to_status=to,
        actor_kind="run",
        run_id=run_id,
        actor_agent=agent,
        created_at=at(minute),
        level=level,
    )


def check(task_id, state, start, end) -> TaskCheckRun:
    return TaskCheckRun(
        id=_id("tcr"),
        project_id=P,
        task_id=task_id,
        main_sha="a",
        target_shas=[],
        state=state,
        results=[],
        error="",
        started_at=at(start),
        ended_at=at(end) if end is not None else None,
    )


def piece(task_id, state, run_id, requirement="req-1") -> RequirementEvidence:
    return RequirementEvidence(
        id=_id("ev"),
        project_id=P,
        requirement_id=requirement,
        task_id=task_id,
        digest="d" * 64,
        kind="commit",
        actor_kind="agent",
        actor="dev",
        run_id=run_id,
        review_state=state,
        produced_at=at(1),
    )


async def seed(*rows) -> None:
    async with async_session_factory() as db:
        db.add_all(rows)
        await db.commit()


async def read(app, auth_headers, since=None) -> dict:
    response = await app.get(
        STATS, params={"since": since.isoformat()} if since else None, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def entry(groups: list, key) -> dict:
    (found,) = [e for e in groups if e["key"] == key]
    return found


def pick(row: dict, path: str):
    for part in path.split("."):
        row = row[part]
    return row


def total_of(entries: list, path: str):
    values = [pick(e["row"], path) for e in entries]
    known = [v for v in values if v is not None]
    return sum(known) if known else None


# ---------------------------------------------------------------------------------------------
# one-tally
# ---------------------------------------------------------------------------------------------


async def _one_build() -> None:
    await seed(
        doc("doc-a", "Spec A"),
        build("b-a", "doc-a"),
        task("t-a", "doc-a", "b-a"),
        run("r-a", "dev", 1, 5, "t-a"),
        usage("r-a", "dev", 1_500_000),
    )


@pytest.mark.asyncio
async def test_the_spec_page_the_project_view_and_the_ledger_call_the_same_function(
    app, auth_headers, monkeypatch
):
    """Patch `work_tally.tally` to return the real tally with one recorded sentinel written into it:
    the sentinel reaches the build card, the stats route and the ledger, unchanged. On master the
    stats route answers 404 and the other two sum their own figures."""
    await _one_build()
    sentinel = 7_000_000
    real = work_tally.tally

    async def patched(*args, **kwargs):
        whole = await real(*args, **kwargs)
        whole["builds"]["b-a"]["cost_micros"]["building"] = sentinel
        whole["project"]["cost_micros"]["total"] = sentinel
        for group in whole["groups"]["agent"]:
            if group["key"] == "dev":
                group["row"]["cost_micros"]["total"] = sentinel
        return whole

    monkeypatch.setattr(work_tally, "tally", patched)

    stats = await app.get(STATS, headers=auth_headers)
    ledger = await app.get(LEDGER, headers=auth_headers)
    figures = await app.get(f"{BASE}/project/builds/b-a/figures", headers=auth_headers)

    assert stats.status_code == 200, stats.text
    assert stats.json()["project"]["cost_micros"]["total"] == sentinel
    assert ledger.json()["spend"]["total_usd"] == 7.0
    assert [(a["agent"], a["usd"]) for a in ledger.json()["spend"]["by_agent"]] == [("dev", 7.0)]
    assert figures.json()["cost"]["build"] == 7.0


def test_no_second_sum_over_usage_check_runs_or_durations_outside_the_tally():
    """The stats route, the ledger and the builds route read the tally; none of them reads the rows
    it sums. A name check, since a sum can be spelled many ways."""
    sources = {
        "api/v1/stats.py": (HUB / "api" / "v1" / "stats.py").read_text(encoding="utf-8"),
        "project_ledger.py": (HUB / "project_ledger.py").read_text(encoding="utf-8"),
        "api/v1/spec.py": (HUB / "api" / "v1" / "spec.py").read_text(encoding="utf-8"),
    }
    for name, text in sources.items():
        for forbidden in ("TurnUsage", "TaskCheckRun", "WorkerInvocation"):
            assert forbidden not in text, f"{name} reads {forbidden}: only work_tally.py may"
        assert not re.search(r"func\.sum\(", text), f"{name} sums rows itself"
        if name != "api/v1/spec.py":  # the spec router has unrelated date arithmetic
            assert ".total_seconds()" not in text, f"{name} computes a duration itself"
    assert not (HUB / "build_figures.py").exists(), "the stand-in tally was to be replaced"


# ---------------------------------------------------------------------------------------------
# totals-agree
# ---------------------------------------------------------------------------------------------


async def _a_project():
    """Two spec documents: A with two builds (a builder, a reviewer, a mender stall), B with work
    before any build; plus an unbound conversation run, an unpriced run, a Copilot run and two
    worker invocations."""
    await seed(
        doc("doc-a", "Spec A"),
        doc("doc-b", "Spec B"),
        build("b-a1", "doc-a", start=0, stop=30),
        build("b-a2", "doc-a", start=40, stop=60),
        task("t-a1", "doc-a", "b-a1", "approved"),
        task("t-a2", "doc-a", "b-a2", "in_progress"),
        task("t-b", "doc-b", None, "in_progress"),
        Agent(
            id="agt-mender",
            project_id=P,
            name="mender",
            lifecycle="open",
            config={"hub_role": "mender"},
        ),
        Stall(
            id="stall-a",
            project_id=P,
            key="stuck_task:t-a1",
            cause="stuck_task",
            task_id="t-a1",
            conversation_id="conv-mender-a",
            first_seen_at=at(10),
        ),
        # build A1: built, reviewed, approved
        run("r-a1-dev", "dev", 1, 8, "t-a1"),
        usage("r-a1-dev", "dev", 3_000_000, tokens=300),
        move("t-a1", "pending", "in_progress", 1, "dev", "r-a1-dev"),
        move("t-a1", "in_progress", "completed", 8, "dev", "r-a1-dev"),
        move("t-a1", "completed", "under_review", 9, "qa", "r-a1-qa"),
        run("r-a1-qa", "qa", 9, 12, "t-a1"),
        usage("r-a1-qa", "qa", 1_000_000, model="opus", tokens=100),
        move("t-a1", "under_review", "approved", 12, "qa", "r-a1-qa"),
        run("r-mend-a", "mender", 10, 14, conv="conv-mender-a"),
        usage("r-mend-a", "mender", 500_000, model="opus", tokens=50),
        check("t-a1", "passed", 8, 9),
        # build A2: one builder run
        run("r-a2-dev", "dev", 41, 45, "t-a2"),
        usage("r-a2-dev", "dev", 2_000_000, tokens=200),
        move("t-a2", "pending", "in_progress", 41, "dev", "r-a2-dev"),
        # spec B: work before any build, one unpriced run
        run("r-b-dev", "dev", 2, 4, "t-b"),
        usage("r-b-dev", "dev", None, tokens=20),
        # not from a spec: a conversation run, a Copilot run reporting credits only
        run("r-chat", "dev", 3, 4, conv="conv-chat"),
        usage("r-chat", "dev", 250_000, tokens=25),
        run("r-copilot", "copilot-agent", 5, 6),
        usage(
            "r-copilot",
            "copilot-agent",
            None,
            model="gpt",
            tokens=None,
            ai_nano_aiu=4_000_000_000,
            premium_requests=1.0,
        ),
        WorkerInvocation(
            id="wi-1",
            project_id=P,
            kind="title",
            prompt_version="v1",
            cli="claude",
            outcome="ok",
            cost_usd_micros=100_000,
            total_tokens=50,
            output_tokens=10,
            created_at=at(1),
        ),
        WorkerInvocation(
            id="wi-2",
            project_id=P,
            kind="summary",
            prompt_version="v1",
            cli="copilot",
            outcome="ok",
            ai_nano_aiu=1_000_000_000,
            premium_requests=0.5,
            created_at=at(2),
        ),
    )


@pytest.mark.asyncio
async def test_totals_agree_spec_rows_equal_the_pages_and_the_accounting_total(app, auth_headers):
    await _a_project()
    stats = await read(app, auth_headers)
    spec = stats["groups"]["spec"]

    # Each spec row is the sum of its builds (and its work before builds), figure by figure, and the
    # build rows are what the spec page's cards show.
    a = entry(spec, "doc-a")
    assert [b["id"] for b in a["builds"]] == ["b-a1", "b-a2"]
    cards = []
    for built in a["builds"]:
        cards.append(
            (
                await app.get(f"{BASE}/project/builds/{built['id']}/figures", headers=auth_headers)
            ).json()
        )
    assert sum(c["runs"] for c in cards) == a["row"]["runs"]["total"] == 4
    assert round(sum(sum(c["cost"].values()) for c in cards) * 1_000_000) == (
        a["row"]["cost_micros"]["total"]
    )
    for part in work_tally.WALL_PARTS:
        assert sum(c["time"][part] for c in cards) == a["row"]["wall"][part]
    for path in ("runs.total", "cost_micros.total", "tokens", "checks.runs", "wall.total"):
        assert pick(a["row"], path) == sum(pick(b["row"], path) for b in a["builds"]), path
    b = entry(spec, "doc-b")
    assert b["builds"] == [] and b["row"] == b["before_builds"]

    # The spec rows, the work outside any spec and the Hub's worker calls are the accounting total.
    accounting = (await app.get(ACCOUNTING, headers=auth_headers)).json()["project"]
    project = stats["project"]
    assert project["cost_micros"]["total"] == accounting["api_equivalent_usd_micros"] == 6_850_000
    assert project["tokens"] == accounting["total_tokens"]
    assert project["ai_nano_aiu"] == accounting["ai_nano_aiu"] == 5_000_000_000
    assert project["premium_requests"] == accounting["premium_requests"] == 1.5
    for path in ("cost_micros.total", "tokens", "ai_nano_aiu", "premium_requests"):
        parts = [pick(e["row"], path) for e in spec] + [pick(stats["workers"], path)]
        assert sum(p for p in parts if p is not None) == pick(project, path), path


# ---------------------------------------------------------------------------------------------
# cost-by-role, mender-attributed-to-its-spec
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roles_every_run_has_one_role_and_the_role_costs_sum_to_the_spec_cost(
    app, auth_headers
):
    """Developer builds t1; QA reviews it through a review turn and, later, through an ordinary
    message bound to the task while it is under_review; the mender runs on its stall."""
    await seed(
        doc("doc-a"),
        build("b-a", "doc-a"),
        task("t1", "doc-a", "b-a", "under_review"),
        Agent(
            id="agt-m", project_id=P, name="mender", lifecycle="open", config={"hub_role": "mender"}
        ),
        Stall(
            id="stall-1",
            project_id=P,
            key="stuck_task:t1",
            cause="stuck_task",
            task_id="t1",
            conversation_id="conv-m",
            first_seen_at=at(30),
        ),
        run("r-dev", "dev", 1, 10, "t1"),
        usage("r-dev", "dev", 4_000_000),
        move("t1", "pending", "in_progress", 1, "dev", "r-dev"),
        move("t1", "in_progress", "completed", 10, "dev", "r-dev"),
        move("t1", "completed", "under_review", 11, "qa", "r-qa1"),
        run("r-qa1", "qa", 11, 15, "t1"),
        usage("r-qa1", "qa", 2_000_000, model="opus"),
        InboundQueueEntry(
            id="iq-review",
            project_id=P,
            agent="qa",
            origin_type="job",
            content="review t1",
            hop_depth=0,
            state="delivered",
            review_task_id="t1",
            delivered_in_run_id="r-qa1",
        ),
        run("r-qa2", "qa", 20, 22, "t1"),  # an ordinary message, bound to the task it is about
        usage("r-qa2", "qa", 1_000_000, model="opus"),
        run("r-mend", "mender", 30, 36, conv="conv-m"),
        usage("r-mend", "mender", 500_000),
    )

    stats = await read(app, auth_headers)

    row = entry(stats["groups"]["spec"], "doc-a")["row"]
    assert row["runs"] == {
        "building": 1,
        "reviewing": 2,
        "leading": 0,
        "mending": 1,
        "other": 0,
        "total": 4,
    }
    assert row["cost_micros"]["building"] == 4_000_000
    assert row["cost_micros"]["reviewing"] == 3_000_000
    assert row["cost_micros"]["mending"] == 500_000
    roles = ("building", "reviewing", "leading", "mending", "other")
    assert sum(row["cost_micros"][r] or 0 for r in roles) == row["cost_micros"]["total"]
    assert row["run_seconds"]["mending"] == 6 * 60
    assert row["run_seconds"]["total"] == sum(row["run_seconds"][r] for r in roles)


@pytest.mark.asyncio
async def test_a_mender_run_counts_toward_the_spec_its_stall_names(app, auth_headers):
    """Three mender conversations: a stall naming a task of document A, a loop_stalled stall naming
    document B's flow, and a stall naming neither."""
    await seed(
        doc("doc-a"),
        doc("doc-b"),
        build("b-a", "doc-a"),
        task("t-a", "doc-a", "b-a"),
        Loop(id="loop-b", project_id=P, job_id="job-b", purpose="b", spec_document_id="doc-b"),
        Agent(
            id="agt-m", project_id=P, name="mender", lifecycle="open", config={"hub_role": "mender"}
        ),
        Stall(
            id="s-1",
            project_id=P,
            key="k1",
            cause="stuck_task",
            task_id="t-a",
            conversation_id="c-1",
            first_seen_at=at(1),
        ),
        Stall(
            id="s-2",
            project_id=P,
            key="k2",
            cause="loop_stalled",
            loop_id="loop-b",
            conversation_id="c-2",
            first_seen_at=at(2),
        ),
        Stall(
            id="s-3",
            project_id=P,
            key="k3",
            cause="no_progress",
            conversation_id="c-3",
            first_seen_at=at(3),
        ),
        run("m-1", "mender", 1, 2, conv="c-1"),
        usage("m-1", "mender", 100_000),
        run("m-2", "mender", 2, 3, conv="c-2"),
        usage("m-2", "mender", 200_000),
        run("m-3", "mender", 3, 4, conv="c-3"),
        usage("m-3", "mender", 400_000),
    )

    stats = await read(app, auth_headers)

    spec = stats["groups"]["spec"]
    assert entry(spec, "doc-a")["row"]["runs"]["mending"] == 1
    assert entry(spec, "doc-a")["builds"][0]["row"]["cost_micros"]["mending"] == 100_000
    assert entry(spec, "doc-b")["row"]["cost_micros"]["mending"] == 200_000
    assert entry(spec, "doc-b")["before_builds"]["runs"]["mending"] == 1
    assert entry(spec, None)["row"]["cost_micros"]["mending"] == 400_000


# ---------------------------------------------------------------------------------------------
# wall-time-partition, checks-on-their-own-line
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_wall_time_partition_sums_to_the_builds_wall_time(app, auth_headers):
    """Built 10 min, waits 2 min, a check fails after 8 min, 30 min held by that failure, reviewed
    for 5 min while a second check runs, approved."""
    await seed(
        doc("doc-a"),
        build("b-a", "doc-a", start=0, stop=60),
        task("t1", "doc-a", "b-a", "approved"),
        run("r-dev", "dev", 0, 10, "t1"),
        usage("r-dev", "dev", 1_000_000),
        move("t1", "pending", "in_progress", 0, "dev", "r-dev"),
        move("t1", "in_progress", "completed", 10, "dev", "r-dev"),
        check("t1", "failed", 12, 20),
        move("t1", "completed", "under_review", 50, "qa", "r-qa"),
        run("r-qa", "qa", 50, 55, "t1"),
        usage("r-qa", "qa", 1_000_000, model="opus"),
        check("t1", "passed", 52, 56),
        move("t1", "under_review", "approved", 55, "qa", "r-qa"),
    )

    stats = await read(app, auth_headers)

    wall = stats["builds"]["b-a"]["wall"]
    assert wall == {
        "building": 600,
        "reviewing": 300,
        "checks": 480,
        "held": 1800,
        "review": 120,
        "waiting": 0,
        "total": 3300,
    }
    figures = (await app.get(f"{BASE}/project/builds/b-a/figures", headers=auth_headers)).json()
    assert figures["time"] == {k: v for k, v in wall.items() if k != "total"}
    assert sum(figures["time"].values()) == 55 * 60


@pytest.mark.asyncio
async def test_checks_have_their_own_line_apart_from_any_agents_time(app, auth_headers):
    await seed(
        doc("doc-a"),
        build("b-a", "doc-a"),
        task("t1", "doc-a", "b-a"),
        run("r-dev", "dev", 0, 3, "t1"),
        usage("r-dev", "dev", 1_000_000),
        check("t1", "passed", 0, 4),
        check("t1", "failed", 5, 8),
        check("t1", "passed", 10, 12),
    )

    stats = await read(app, auth_headers)

    line = {"runs": 3, "passed": 2, "failed": 1, "seconds": (4 + 3 + 2) * 60}
    page = (await app.get(f"{BASE}/project/builds/b-a/figures", headers=auth_headers)).json()
    assert page["checks"] == line
    row = entry(stats["groups"]["spec"], "doc-a")["row"]
    assert row["checks"] == line
    assert row["run_seconds"]["total"] == 3 * 60, "no agent's run time includes the checks"
    assert stats["groups"]["level"][0]["row"]["checks"] == line


# ---------------------------------------------------------------------------------------------
# send-backs-counted-once, verdicts-per-piece, reviews-beside-a-failing-check
# ---------------------------------------------------------------------------------------------


async def _sent_back_twice() -> None:
    await seed(
        doc("doc-a"),
        build("b-a", "doc-a"),
        task("t1", "doc-a", "b-a", "revision_needed"),
        run("r-d1", "dev", 0, 5, "t1"),
        usage("r-d1", "dev", 1_000_000, model="sonnet"),
        run("r-d2", "dev", 8, 12, "t1"),
        usage("r-d2", "dev", 1_000_000, model="sonnet"),
        run("r-q1", "qa", 6, 7, "t1"),
        usage("r-q1", "qa", 1_000_000, model="opus"),
        run("r-q2", "qa", 13, 14, "t1"),
        usage("r-q2", "qa", 1_000_000, model="opus"),
        move("t1", "pending", "in_progress", 0, "dev", "r-d1"),
        move("t1", "in_progress", "completed", 5, "dev", "r-d1"),
        move("t1", "completed", "under_review", 6, "qa", "r-q1"),
        move("t1", "under_review", "revision_needed", 7, "qa", "r-q1"),
        move("t1", "revision_needed", "in_progress", 8, "dev", "r-d2"),
        move("t1", "in_progress", "completed", 12, "dev", "r-d2"),
        move("t1", "completed", "under_review", 13, "qa", "r-q2"),
        move("t1", "under_review", "revision_needed", 14, "qa", "r-q2"),
    )


@pytest.mark.asyncio
async def test_a_send_back_is_counted_once_not_once_per_rejected_piece(app, auth_headers):
    """Sonnet built the task and was sent back twice by Opus, each time with four pieces rejected
    as recorded before slice K: two send-backs received and two made, not eight."""
    await _sent_back_twice()
    await seed(*[piece("t1", "rejected", "r-d1") for _ in range(4)])

    stats = await read(app, auth_headers)

    models = stats["groups"]["model"]
    assert entry(models, "sonnet")["row"]["send_backs"] == {"made": 0, "received": 2}
    assert entry(models, "opus")["row"]["send_backs"] == {"made": 2, "received": 0}
    assert stats["total"]["send_backs"] == {"made": 2, "received": 2}
    agents = stats["groups"]["agent"]
    assert entry(agents, "dev")["row"]["send_backs"]["received"] == 2
    assert entry(agents, "qa")["row"]["send_backs"]["made"] == 2


@pytest.mark.asyncio
async def test_per_piece_one_failing_piece_of_four_counts_one_rejected_three_held(
    app, auth_headers
):
    await seed(
        doc("doc-a"),
        build("b-a", "doc-a"),
        task("t1", "doc-a", "b-a", "revision_needed"),
        run("r-d1", "dev", 0, 5, "t1"),
        usage("r-d1", "dev", 1_000_000, model="sonnet"),
        piece("t1", "rejected", "r-d1"),
        piece("t1", "held", "r-d1"),
        piece("t1", "held", "r-d1"),
        piece("t1", "held", "r-d1"),
    )

    stats = await read(app, auth_headers)

    row = entry(stats["groups"]["model"], "sonnet")["row"]
    assert row["pieces"] == {"accepted": 0, "rejected": 1, "held": 3, "awaiting": 0}
    assert entry(stats["groups"]["spec"], "doc-a")["row"]["pieces"]["held"] == 3


@pytest.mark.asyncio
async def test_beside_failing_check_review_is_counted_with_its_cost_and_time(app, auth_headers):
    """Two send-backs: one made while the task's newest check had failed, one after a passing
    check. Exactly the first is a review beside a failing check."""
    await seed(
        doc("doc-a"),
        build("b-a", "doc-a"),
        task("t1", "doc-a", "b-a", "revision_needed"),
        task("t2", "doc-a", "b-a", "revision_needed"),
        run("r-q1", "qa", 10, 14, "t1"),
        usage("r-q1", "qa", 1_300_000, model="opus"),
        run("r-q2", "qa", 20, 22, "t2"),
        usage("r-q2", "qa", 600_000, model="opus"),
        check("t1", "failed", 5, 9),
        check("t2", "failed", 1, 3),
        check("t2", "passed", 15, 18),
        move("t1", "completed", "under_review", 10, "qa", "r-q1"),
        move("t1", "under_review", "revision_needed", 14, "qa", "r-q1"),
        move("t2", "completed", "under_review", 20, "qa", "r-q2"),
        move("t2", "under_review", "revision_needed", 22, "qa", "r-q2"),
    )

    stats = await read(app, auth_headers)

    assert stats["total"]["beside_failing"] == {
        "count": 1,
        "cost_micros": 1_300_000,
        "run_seconds": 4 * 60,
    }
    assert entry(stats["groups"]["spec"], "doc-a")["row"]["beside_failing"]["count"] == 1
    assert entry(stats["groups"]["agent"], "qa")["row"]["beside_failing"]["count"] == 1
    assert entry(stats["groups"]["model"], "opus")["row"]["beside_failing"]["count"] == 1


# ---------------------------------------------------------------------------------------------
# groupings, unknown-is-not-zero
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_groupings_agree_on_their_totals_for_every_since(app, auth_headers):
    await _a_project()
    await seed(
        # work on a document's task before any build was recorded, earlier than both builds
        run("r-old", "dev", -120, -110, "t-b"),
        usage("r-old", "dev", 900_000),
    )

    for since in (None, at(35)):
        stats = await read(app, auth_headers, since)
        for path in (
            "runs.total",
            "cost_micros.total",
            "run_seconds.total",
            "tokens",
            "unpriced",
            "checks.runs",
            "send_backs.made",
            "wall.total",
        ):
            for name, entries in stats["groups"].items():
                assert total_of(entries, path) == pick(stats["total"], path), (name, path, since)

    full = await read(app, auth_headers)
    later = await read(app, auth_headers, at(35))
    assert later["total"]["runs"]["total"] < full["total"]["runs"]["total"]
    spec_b = entry(full["groups"]["spec"], "doc-b")
    assert spec_b["before_builds"]["runs"]["total"] == 2, "work before builds shows as such"
    assert any(e["key"] is None for e in full["groups"]["level"]), "no level recorded"
    assert entry(full["groups"]["level"], None)["label"] == "no level recorded"


@pytest.mark.asyncio
async def test_an_unpriced_run_is_counted_beside_the_cost_never_added_as_zero(app, auth_headers):
    """One priced run, one unpriced run, one Copilot run reporting credits only."""
    await seed(
        doc("doc-a"),
        build("b-a", "doc-a"),
        task("t1", "doc-a", "b-a"),
        run("r-1", "dev", 0, 1, "t1"),
        usage("r-1", "dev", 2_000_000),
        run("r-2", "unpriced-agent", 1, 2, "t1"),
        usage("r-2", "unpriced-agent", None),
        run("r-3", "copilot-agent", 2, 3, "t1"),
        usage(
            "r-3",
            "copilot-agent",
            None,
            tokens=None,
            ai_nano_aiu=3_000_000_000,
            premium_requests=1.0,
        ),
    )

    stats = await read(app, auth_headers)

    for row in (
        entry(stats["groups"]["spec"], "doc-a")["row"],
        stats["builds"]["b-a"],
    ):
        assert row["cost_micros"]["total"] == 2_000_000
        assert row["unpriced"] == 1
        assert row["ai_nano_aiu"] == 3_000_000_000 and row["premium_requests"] == 1.0
    ledger = (await app.get(LEDGER, headers=auth_headers)).json()["spend"]
    assert ledger["total_usd"] == 2.0
    by_agent = {a["agent"]: a for a in ledger["by_agent"]}
    assert by_agent["unpriced-agent"]["usd"] is None, "unknown, not $0"
    assert by_agent["unpriced-agent"]["unpriced"] == 1
    assert by_agent["dev"]["usd"] == 2.0 and by_agent["dev"]["unpriced"] == 0
    assert stats["groups"]["agent"][0]["key"] == "dev", "known spend first"


# ---------------------------------------------------------------------------------------------
# scope: a build's figures read only that build
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scope_a_builds_figures_equal_the_whole_tallys_and_load_only_its_runs(app):
    """The page polls one build's figures every few seconds: the same code path, scoped to the
    build, answers its row identically and books no run that is not the build's."""
    await _a_project()
    now = at(500)
    async with async_session_factory() as db:
        full = await work_tally.tally(db, P, now=now)
    for build_id in ("b-a1", "b-a2"):
        async with async_session_factory() as db:
            scoped = await work_tally.tally(db, P, now=now, build_id=build_id)
        assert scoped["builds"][build_id] == full["builds"][build_id], build_id
        assert scoped["total"]["runs"]["total"] == full["builds"][build_id]["runs"]["total"]
        assert scoped["total"]["runs"]["total"] < full["total"]["runs"]["total"]
    async with async_session_factory() as db:
        with pytest.raises(LookupError):
            await work_tally.tally(db, P, build_id="no-such-build")


@pytest.mark.asyncio
async def test_scope_one_builds_figures_stay_fast_beside_thousands_of_other_runs(app, auth_headers):
    """The scoped read loads that build's runs, not the project's: counted in rows, not timed.

    A 200 ms wall-clock bound passed here and failed on CI's loaded runner at 201-209 ms (runs
    40600112011, 40606840326); the rows read are what the scoping changes, and they do not vary
    with the machine. Unscoped, the read loads all 3001 runs and their usage.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    rows = [doc("doc-big"), build("b-one", "doc-big"), task("t-one", "doc-big", "b-one")]
    rows += [run("r-one", "dev", 1, 5, "t-one"), usage("r-one", "dev", 1_000_000)]
    rows += [
        doc("doc-other"),
        build("b-big", "doc-other", start=10),
        task("t-big", "doc-other", "b-big"),
    ]
    for i in range(3000):
        rows.append(run(f"r-big-{i}", "dev", 11, 12, "t-big"))
        rows.append(usage(f"r-big-{i}", "dev", 1_000))
    await seed(*rows)

    read = {"runs": 0, "turn_usage": 0}

    def count_rows(state):  # noqa: ANN001, ANN202
        tables = {getattr(f, "name", None) for f in state.statement.get_final_froms()}
        counted = tables & read.keys()
        if not state.is_select or not counted:
            return None
        frozen = state.invoke_statement().freeze()
        for table in counted:
            read[table] += len(frozen().all())
        return frozen()

    event.listen(Session, "do_orm_execute", count_rows)
    try:
        response = await app.get(f"{BASE}/project/builds/b-one/figures", headers=auth_headers)
    finally:
        event.remove(Session, "do_orm_execute", count_rows)

    assert response.status_code == 200, response.text
    assert response.json()["runs"] == 1 and response.json()["cost"]["build"] == 1.0
    assert read["runs"] and read["runs"] < 10, f"read {read['runs']} run rows for a one-run build"
    assert read["turn_usage"] < 10, f"read {read['turn_usage']} usage rows for a one-run build"
