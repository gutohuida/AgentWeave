"""The chapters store: versions are validated on the way in and never rewritten.

Store level only (`hub/hub/chapters.py`); the routes, the manager firing and the agents' tools are
other tasks of `the-thread-reads-as-chapters-the-manager-writes`. The fixture repository is a real
git repository with one commit and one tag.
"""

import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from hub import chapters, project_thread
from hub.db.engine import async_session_factory
from hub.db.models import ChapterVersion, SpecDocument, Task

P = "proj-test"
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def span(a, b):
    return {"start": at(a).isoformat(), "end": at(b).isoformat()}


async def seed(*rows):
    async with async_session_factory() as session:
        for row in rows:
            session.add(row)
            await session.flush()
        await session.commit()


def doc(i, minutes):
    return SpecDocument(
        id=f"spdoc-{i}",
        project_id=P,
        path=f"spec/changes/d{i}/spec.json",
        title=f"Document {i}",
        created_at=at(minutes),
        updated_at=at(minutes),
    )


def task(i, minutes):
    return Task(id=f"task-{i}", project_id=P, title=f"Task {i}", created_at=at(minutes))


async def surface():
    async with async_session_factory() as session:
        return chapters.surface_keys(await project_thread.build(session, P))


async def save(proposed, *, author="manager", asked_for=False, repo=None, reason="because", **kw):
    async with async_session_factory() as session:
        return await chapters.save(
            session,
            P,
            chapters=proposed,
            surface=chapters.surface_keys(await project_thread.build(session, P)),
            author=author,
            reason=reason,
            asked_for=asked_for,
            repo=repo,
            **kw,
        )


def chapter(cid, members, a=0, b=5, title=None, **extra):
    return {
        "id": cid,
        "title": title or f"Chapter {cid}",
        "summary": "s",
        "members": members,
        **span(a, b),
        **extra,
    }


async def read():
    async with async_session_factory() as session:
        return await chapters.read(session, P, await project_thread.build(session, P))


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        subprocess.run(
            ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
            check=True,
            capture_output=True,
        )

    git("init")
    (root / "a.txt").write_text("a")
    git("add", "a.txt")
    git("commit", "-m", "first")
    git("tag", "v1")
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return root, sha


async def test_overlapping_chapters_are_both_kept_ordered_by_start(app):
    await seed(doc(1, 0), doc(2, 10))
    await save(
        [
            chapter("late", ["document:spdoc-2"], 8, 30),
            chapter("early", ["document:spdoc-1"], 0, 12),
        ]
    )
    body = await read()
    assert [c["id"] for c in body["chapters"]] == ["early", "late"]
    assert body["chapters"][0]["end"] > body["chapters"][1]["start"]


async def test_every_chapter_opened_reaches_the_surface_once_and_new_tasks_trail(app):
    await seed(doc(1, 0), doc(2, 10))
    await save([chapter("a", ["document:spdoc-1"]), chapter("b", ["document:spdoc-2"], 10, 20)])
    await seed(task("late", 60))
    body = await read()
    reached = [m for c in body["chapters"] for m in c["members"]]
    assert sorted(reached) == ["document:spdoc-1", "document:spdoc-2"]
    assert [k["key"] for k in body["ungrouped"]] == ["task:task-late"]
    assert sorted(reached + [k["key"] for k in body["ungrouped"]]) == sorted(await surface())


async def test_a_version_missing_or_doubling_a_knot_is_refused_and_the_old_one_stands(app):
    await seed(doc(1, 0), doc(2, 10))
    await save([chapter("a", ["document:spdoc-1"]), chapter("b", ["document:spdoc-2"], 10, 20)])
    with pytest.raises(chapters.ChapterRefusedError, match="document:spdoc-2 is in no chapter"):
        await save([chapter("a", ["document:spdoc-1"])], asked_for=True)
    with pytest.raises(chapters.ChapterRefusedError, match="document:spdoc-1 is in more than one"):
        await save(
            [
                chapter("a", ["document:spdoc-1"]),
                chapter("b", ["document:spdoc-2", "document:spdoc-1"], 10, 20),
            ],
            asked_for=True,
        )
    body = await read()
    assert len(body["versions"]) == 1
    assert [c["id"] for c in body["chapters"]] == ["a", "b"]


async def test_a_citation_that_does_not_resolve_refuses_the_version(app, repo):
    root, sha = repo
    await seed(doc(1, 0), task("real", 1))
    members = ["document:spdoc-1", "task:task-real"]
    await save([chapter("a", members)], repo=root)
    with pytest.raises(chapters.ChapterRefusedError, match="task-ghost"):
        await save([chapter("a", members, cites=["task-ghost"])], asked_for=True, repo=root)
    with pytest.raises(chapters.ChapterRefusedError, match="commit:" + "0" * 40):
        await save([chapter("a", members, cites=["commit:" + "0" * 40])], asked_for=True, repo=root)
    with pytest.raises(chapters.ChapterRefusedError, match="tag:nope"):
        await save([chapter("a", members, cites=["tag:nope"])], asked_for=True, repo=root)
    assert len((await read())["versions"]) == 1
    # The same chapter citing things that exist is saved.
    await save(
        [chapter("a", members, cites=["task-real", f"commit:{sha}", "tag:v1"])],
        asked_for=True,
        repo=root,
    )
    assert len((await read())["versions"]) == 2


async def test_an_unasked_save_keeps_only_new_chapters(app):
    await seed(doc(1, 0))
    await save([chapter("a", ["document:spdoc-1"], title="Original")])
    await seed(doc(2, 10))
    result = await save(
        [
            chapter("a", ["document:spdoc-1"], title="Retitled"),
            chapter("b", ["document:spdoc-2"], 10, 20),
        ]
    )
    assert result.dropped and "Original" in result.dropped[0]
    body = await read()
    assert {c["id"]: c["title"] for c in body["chapters"]} == {"a": "Original", "b": "Chapter b"}
    # Nothing new left: no version is written.
    again = await save([chapter("a", ["document:spdoc-1"], title="Again")])
    assert again.version is None and len((await read())["versions"]) == 2


async def test_an_asked_save_rewrites_an_existing_chapter_as_a_new_version(app):
    await seed(doc(1, 0))
    await save([chapter("a", ["document:spdoc-1"], title="Original")])
    await save(
        [chapter("a", ["document:spdoc-1"], title="Retitled")],
        asked_for=True,
        asked_by="operator",
        reason="Weave the thread",
    )
    body = await read()
    assert body["chapters"][0]["title"] == "Retitled"
    assert [v["chapters"][0]["title"] for v in body["versions"]] == ["Retitled", "Original"]


async def test_versions_keep_author_asker_time_and_reason_and_are_never_rewritten(app):
    await seed(doc(1, 0))
    await save([chapter("a", ["document:spdoc-1"])], reason="first firing")
    await save(
        [chapter("a", ["document:spdoc-1"], title="B")],
        asked_for=True,
        asked_by="operator",
        reason="requested",
    )
    await save(
        [chapter("a", ["document:spdoc-1"], title="C")],
        asked_for=True,
        author="Architect",
        asked_by="operator",
        reason="agent edit",
    )
    versions = (await read())["versions"]
    assert [(v["author"], v["asked_by"], v["reason"]) for v in versions] == [
        ("Architect", "operator", "agent edit"),
        ("manager", "operator", "requested"),
        ("manager", None, "first firing"),
    ]
    assert all(v["at"] for v in versions)
    async with async_session_factory() as session:
        rows = (await session.execute(select(ChapterVersion))).scalars().all()
        assert [r.version for r in rows] == [1, 2, 3]
