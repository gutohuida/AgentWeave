"""Morning drive: seed a minimal approved-phase SpecDocument row directly, the way
`hub/tests/test_a_task_nothing_will_move_holds_nobody.py`'s `_guard_case` stages a flow's document
-- a real row through the Hub's own model, not a fixture shape unit tests only.

    py -3.11 scripts/drive/d8_0925_morning_doc_seed.py <db-path> <project-id> <doc-id>
"""

import asyncio
import os
import sys
from pathlib import Path

DB = sys.argv[1]
PROJECT = sys.argv[2]
DOC_ID = sys.argv[3]

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB}"
os.environ.setdefault("AW_LOG_LEVEL", "WARNING")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hub"))
sys.stdout.reconfigure(encoding="utf-8")

from hub.db.engine import async_session_factory  # noqa: E402
from hub.db.models import SpecDocument  # noqa: E402


async def main():
    async with async_session_factory() as db:
        db.add(
            SpecDocument(
                id=DOC_ID,
                project_id=PROJECT,
                path=f"spec/{DOC_ID}.html",
                title=f"Morning drive doc {DOC_ID}",
                phase="current",
                kind="capability",
            )
        )
        await db.commit()
        print(f"seeded SpecDocument {DOC_ID} phase=current")


asyncio.run(main())
