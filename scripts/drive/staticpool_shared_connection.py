"""F285's reduction: does one session's close roll back another session's insert?

The Hub suite runs on `sqlite+aiosqlite:///:memory:` (`hub/tests/conftest.py:19`). SQLAlchemy's
aiosqlite dialect picks the pool from the URL — in-memory gets a **StaticPool**, which hands the
*same* DBAPI connection to every checkout with no in-use tracking, while a file gets an
`AsyncAdaptedQueuePool`, which does not. Returning a connection to a pool resets it, and reset
means ROLLBACK.

So under the suite's engine every `AsyncSession` shares one transaction, and an HTTP request
finishing is a ROLLBACK issued on whatever a background run task has open. This script models
exactly that interleave against both URLs and prints what each does.

    py -3.11 scripts/drive/staticpool_shared_connection.py <path-to-a-scratch-db-file>

Expected:

    sqlite+aiosqlite:///:memory:   -> InvalidRequestError: Could not refresh instance '<Row ...>'
    sqlite+aiosqlite:///<file>     -> no error; rows in db = ['r1']

The first line is the error CI reports at `hub/hub/output_recording.py:94`, on `AgentOutput`.
The second is the pooling the product actually ships (`hub/hub/config.py:16`).
"""

import asyncio
import sys

from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Row(Base):
    __tablename__ = "rows"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)


async def run(url: str) -> str:
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    print(f"  pool={type(engine.pool).__name__}")

    writer = factory()
    row = Row(id="r1")
    writer.add(row)
    # INSERT issued, transaction still open — the state `record_agent_output` is in between the
    # flush inside `commit()` and the COMMIT itself.
    await writer.flush()

    # A second session opens and closes, exactly as a FastAPI request's `get_session` does.
    async with factory() as other:
        await other.execute(select(1))

    try:
        await writer.commit()
        await writer.refresh(row)
    except Exception as exc:  # noqa: BLE001 — the exception *is* the result
        await engine.dispose()
        return f"{type(exc).__name__}: {exc}"

    async with factory() as reader:
        found = (await reader.execute(select(Row.id))).scalars().all()
    await engine.dispose()
    return f"no error; rows in db = {found}"


async def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: staticpool_shared_connection.py <path-to-a-scratch-db-file>")
    for url in ("sqlite+aiosqlite:///:memory:", "sqlite+aiosqlite:///" + sys.argv[1]):
        print(url)
        print("  ->", await run(url))


if __name__ == "__main__":
    asyncio.run(main())
