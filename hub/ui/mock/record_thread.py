"""Record the Thread mock's fixture from the trial Hub's database.

    py -3.11 mock/record_thread.py [--db <trial agentweave.db>] [--project proj-d85a82bf4216]

Copies the database (the Hub keeps running), builds the thread with the Hub's own code, and writes
`mock/thread-fixture.json`: every level the mock can open, as the faces `GET /thread` returns. The
file is gitignored like the other fixtures; record it again to refresh it. Run from `hub/`'s
environment (it imports `hub.project_thread`).
"""

import argparse
import asyncio
import json
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))  # hub/

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from hub import project_thread as pt  # noqa: E402

NEWEST, OLDEST, DEPTH_CAP = 12, 4, 60


async def main(db: pathlib.Path, project: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        copy = pathlib.Path(tmp) / "thread.db"
        shutil.copy(db, copy)
        engine = create_async_engine(f"sqlite+aiosqlite:///{copy.as_posix()}")
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            thread = await pt.build(session, project, [])
        await engine.dispose()

    levels: dict = {}

    def peek(under, cap=DEPTH_CAP):
        level = thread.level(None if under == pt.SURFACE else under)
        if level is None:
            return None
        shown = pt.page(level, limit=cap, first=True)
        return {"knots": [pt.face(k, thread) for k in shown["knots"]], "total": shown["total"]}

    def record(under, cap=DEPTH_CAP):
        if under not in levels and (found := peek(under, cap)) is not None:
            levels[under] = found
        return levels[under]["knots"] if under in levels else []

    surface = record(pt.SURFACE, 200)
    keep = surface[:OLDEST] + surface[-NEWEST:]
    for knot in keep:
        if knot["child_count"]:
            record(knot["key"])

    # One chain the whole way down: a document with an approved task whose run holds evidence.
    def chain_from(faces, depth=0):
        for knot in reversed(faces):
            if not knot["child_count"] or depth > 5:
                continue
            kids = peek(knot["key"])["knots"]
            if knot["kind"] == "run" and any(k["kind"] == "evidence" for k in kids):
                return [knot["key"]]
            found = chain_from(kids, depth + 1)
            if found:
                return [knot["key"]] + found
        return None

    chain = chain_from([k for k in surface if k["kind"] == "document"])
    for key in chain or []:
        record(key)
        for knot in levels[key]["knots"]:
            if knot["child_count"] and knot["kind"] in ("task", "run", "fold"):
                record(knot["key"])

    out = HERE / "thread-fixture.json"
    out.write_text(json.dumps({"project": project, "chain": chain, "levels": levels}, indent=1))
    print(f"{out}: {len(levels)} levels, chain {chain}, {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(pathlib.Path.home() / ".agentweave/hub/profiles/trial/agentweave.db"))
    ap.add_argument("--project", default="proj-d85a82bf4216")
    a = ap.parse_args()
    asyncio.run(main(pathlib.Path(a.db), a.project))
