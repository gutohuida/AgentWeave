"""The thread feed with chapters (`GET /projects/{id}/thread`): ac-surface and ac-once of
`the-thread-reads-as-chapters-the-manager-writes`, plus a chapter from before the Hub opening into
its release tags and commits.

Tests walk the feed in the order the route returns it, as the page does.
"""

import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from hub import chapters, project_thread
from hub.api.v1 import thread as thread_routes
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, Task

P = "proj-test"
THREAD = f"/api/v1/projects/{P}/thread"
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def doc(i, minutes):
    return SpecDocument(
        id=f"spdoc-{i}",
        project_id=P,
        path=f"spec/changes/d{i}/spec.json",
        title=f"Document {i}",
        created_at=at(minutes),
        updated_at=at(minutes),
    )


def task(i, minutes, document=None):
    return Task(
        id=f"task-{i}",
        project_id=P,
        title=f"Task {i}",
        spec_document_id=document,
        created_at=at(minutes),
    )


async def seed(*rows):
    async with async_session_factory() as session:
        for row in rows:
            session.add(row)
            await session.flush()
        await session.commit()


def chapter(cid, members, a, b, **extra):
    return {
        "id": cid,
        "title": f"Chapter {cid}",
        "summary": f"What {cid} was about",
        "members": members,
        "start": at(a).isoformat(),
        "end": at(b).isoformat(),
        **extra,
    }


async def write(proposed, author="manager", **kw):
    async with async_session_factory() as session:
        surface = chapters.surface_keys(await project_thread.build(session, P))
        return await chapters.save(
            session,
            P,
            chapters=proposed,
            surface=surface,
            author=author,
            reason="because",
            asked_for=kw.pop("asked_for", True),
            **kw,
        )


async def level(app, headers, under=None, **params):
    if under:
        params["under"] = under
    response = await app.get(THREAD, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def walk(app, headers, under=None):
    seen = []
    body = await level(app, headers, under, limit=200, first=True)
    while True:
        for knot in body["knots"]:
            seen.append(knot)
            if knot["child_count"]:
                seen.extend(await walk(app, headers, knot["key"]))
        if not body["has_after"]:
            return seen
        body = await level(app, headers, under, limit=200, after=body["after_cursor"])


def reached(knots):
    """The stored records a walk reaches: what a chapter groups, not the chapters themselves."""
    return sorted(
        r
        for k in knots
        if k["kind"] not in ("fold", "chapter", "release", "commit")
        for r in k["records"]
    )


async def test_the_surface_is_the_chapters_ordered_by_start_and_one_opens(app, auth_headers):
    await seed(doc(1, 0), doc(2, 10), task("a", 1, "spdoc-1"))
    plain_surface = await level(app, auth_headers, limit=200, first=True)
    assert all(k["kind"] != "chapter" for k in plain_surface["knots"]), "no chapters: slice 1's"

    await write(
        [
            chapter("late", ["document:spdoc-2"], 10, 20),
            chapter("early", ["document:spdoc-1"], 0, 5),
        ]
    )
    body = await level(app, auth_headers, limit=200, first=True)
    shown = body["knots"]
    assert [k["key"] for k in shown] == ["chapter:early", "chapter:late"]
    first = shown[0]
    assert first["title"] == "Chapter early" and first["summary"] == "What early was about"
    assert first["start"] == at(0).isoformat() and first["end"] == at(5).isoformat()
    assert first["actors"] == ["manager"] and first["word"] == "Chapter"

    opened = await level(app, auth_headers, "chapter:early", limit=200, first=True)
    assert [k["key"] for k in opened["knots"]] == ["document:spdoc-1"]


async def test_every_chapter_opened_equals_the_structural_walk(app, auth_headers):
    await seed(doc(1, 0), doc(2, 10), task("a", 1, "spdoc-1"), task("loose", 12))
    structural = reached(await walk(app, auth_headers))

    async with async_session_factory() as session:
        keys = chapters.surface_keys(await project_thread.build(session, P))
    docs = [k for k in keys if k.startswith("document:")]
    rest = [k for k in keys if k not in docs]
    await write([chapter("one", docs, 0, 5), chapter("two", rest, 10, 20)])

    await seed(task("new", 60))
    body = await level(app, auth_headers, limit=200, first=True)
    kinds = [k["kind"] for k in body["knots"]]
    assert kinds[:2] == ["chapter", "chapter"] and "chapter" not in kinds[2:]
    assert body["knots"][-1]["records"] == ["tasks:task-new"], "the new task trails, ungrouped"

    chaptered = reached(await walk(app, auth_headers))
    assert chaptered == sorted(structural + ["tasks:task-new"])
    assert len(chaptered) == len(set(chaptered)), "no knot twice"


async def test_a_refused_version_leaves_the_feed_as_it_was(app, auth_headers):
    await seed(doc(1, 0), doc(2, 10))
    await write([chapter("one", ["document:spdoc-1", "document:spdoc-2"], 0, 20)])
    with pytest.raises(chapters.ChapterRefusedError) as dropped:
        await write([chapter("one", ["document:spdoc-1"], 0, 20)])
    assert "document:spdoc-2" in str(dropped.value)
    with pytest.raises(chapters.ChapterRefusedError) as doubled:
        await write(
            [
                chapter("one", ["document:spdoc-1", "document:spdoc-2"], 0, 10),
                chapter("two", ["document:spdoc-2"], 10, 20),
            ]
        )
    assert "document:spdoc-2" in str(doubled.value)
    body = await level(app, auth_headers, limit=200, first=True)
    assert [k["key"] for k in body["knots"]] == ["chapter:one"]
    opened = await level(app, auth_headers, "chapter:one", limit=200, first=True)
    assert len(opened["knots"]) == 2


async def small_pages(app, headers):
    """The surface the way the page loads: newest page, then each page before its cursor."""
    body = await level(app, headers, limit=1)
    keys = [k["key"] for k in body["knots"]]
    while body["has_before"]:
        body = await level(app, headers, limit=1, before=body["before_cursor"])
        keys = [k["key"] for k in body["knots"]] + keys
    return keys


async def test_chapters_with_mixed_utc_offsets_order_by_the_moment(app, auth_headers):
    await seed(doc(1, 0), doc(2, 10))
    plus_one = timezone(timedelta(hours=1))
    a_start = T0.astimezone(plus_one)  # 09:00Z written as 10:00+01:00
    b_start = T0 + timedelta(minutes=30)  # 09:30Z
    await write(
        [
            {**chapter("a", ["document:spdoc-1"], 0, 60), "start": a_start.isoformat()},
            {**chapter("b", ["document:spdoc-2"], 0, 60), "start": b_start.isoformat()},
        ]
    )
    body = await level(app, auth_headers, limit=200, first=True)
    assert [k["key"] for k in body["knots"]] == ["chapter:a", "chapter:b"]
    assert await small_pages(app, auth_headers) == ["chapter:a", "chapter:b"]


async def test_small_pages_lose_nothing_when_an_ungrouped_knot_predates_a_chapter(
    app, auth_headers
):
    await seed(doc(1, 0), doc(2, 10))
    await write(
        [chapter("a", ["document:spdoc-1"], 0, 5), chapter("b", ["document:spdoc-2"], 10, 20)]
    )
    await seed(task("early", 3))
    body = await level(app, auth_headers, limit=200, first=True)
    expected = [k["key"] for k in body["knots"]]
    assert expected == ["chapter:a", "chapter:b", "task:task-early"] or len(expected) == 3
    assert expected[:2] == ["chapter:a", "chapter:b"]
    assert await small_pages(app, auth_headers) == expected
    after = await level(app, auth_headers, limit=1, first=True)
    seen = [k["key"] for k in after["knots"]]
    while after["has_after"]:
        after = await level(app, auth_headers, limit=1, after=after["after_cursor"])
        seen += [k["key"] for k in after["knots"]]
    assert seen == expected


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args, **env):
        return subprocess.run(
            ["git", "-C", str(root), "-c", "user.name=Ada", "-c", "user.email=a@a", *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init")
    shas = []
    for n, subject in enumerate(["first", "second", "third"]):
        (root / "f.txt").write_text(str(n))
        git("add", "f.txt")
        git("commit", "-m", subject, "--date", f"2026-01-0{n + 1}T10:00:00+00:00")
        shas.append(git("rev-parse", "HEAD"))
        if n == 1:
            git("tag", "v1")
    return root, shas


async def test_a_chapter_from_before_the_hub_opens_into_release_tags_then_commits(
    app, auth_headers, repo, monkeypatch
):
    root, shas = repo

    async def workspace(session, project_id):
        return root

    monkeypatch.setattr(thread_routes, "project_root", workspace)
    await seed(doc(1, 0))
    await write(
        [
            chapter(
                "origins",
                [],
                -100,
                -50,
                cites=[f"commit:{sha}" for sha in shas],
            ),
            chapter("hub", ["document:spdoc-1"], 0, 5),
        ],
        repo=root,
    )
    body = await level(app, auth_headers, limit=200, first=True)
    assert [k["key"] for k in body["knots"]] == ["chapter:origins", "chapter:hub"]

    tags = (await level(app, auth_headers, "chapter:origins", limit=200, first=True))["knots"]
    assert [(k["kind"], k["title"]) for k in tags] == [
        ("release", "v1"),
        ("release", "Not yet released"),
    ]
    commits = (await level(app, auth_headers, tags[0]["key"], limit=200, first=True))["knots"]
    assert [c["title"] for c in commits] == ["first", "second"]
    assert all(c["actors"] == ["Ada"] and c["start"] for c in commits)
    assert commits[0]["records"] == [shas[0][:12]]
    unreleased = (await level(app, auth_headers, tags[1]["key"], limit=200, first=True))["knots"]
    assert [c["title"] for c in unreleased] == ["third"]


async def test_a_paged_level_counts_and_places_its_knots_over_all_of_it(app, auth_headers):
    """The panel's figures come from the whole level, never the page a reader has loaded: a chapter
    read one knot at a time still says what it is made of, who was in it, and 'n of N'."""
    loose = task("loose", 1)
    loose.assignee = "mender"
    await seed(doc(1, 0), doc(2, 10), doc(3, 20), loose)
    await write(
        [
            chapter("a", ["document:spdoc-1", "document:spdoc-2", "document:spdoc-3"], 0, 30),
            chapter("b", ["task:task-loose"], 1, 2),
        ]
    )
    await seed(task("late", 90))
    body = await level(app, auth_headers, limit=1)
    assert body["counts"] == {"chapter": 2, "task": 1}
    assert body["span"] == {"start": at(0).isoformat(), "end": at(30).isoformat()}, "the chapters'"

    surface = await level(app, auth_headers, limit=1, first=True)
    first = surface["knots"][0]
    assert first["key"] == "chapter:a" and first["place"] == {"n": 1, "of": 2}
    assert first["made_of"] == [{"kind": "document", "word": "Document", "count": 3}]
    second = await level(app, auth_headers, limit=1, after=surface["after_cursor"])
    assert second["knots"][0]["place"] == {"n": 2, "of": 2}
    assert "mender" in second["knots"][0]["people"], "the actors of what it holds"
    assert second["knots"][0]["actors"] == ["manager"]

    inner = await level(app, auth_headers, "chapter:a", limit=1, first=True)
    assert inner["knots"][0]["place"] == {"n": 1, "of": 3}
    knot = await app.get(f"{THREAD}/knot", params={"key": "document:spdoc-3"}, headers=auth_headers)
    assert knot.json()["knot"]["place"] == {"n": 3, "of": 3}
