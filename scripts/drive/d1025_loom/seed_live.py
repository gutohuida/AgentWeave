import asyncio, os, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "hub"))
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument
P = sys.argv[1]
T0 = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)
async def main():
    async with async_session_factory() as s:
        s.add_all([SpecDocument(id=f"spdoc-live{i}", project_id=P, path=f"spec/changes/live{i}/spec.json", title=f"Live document {i + 1}", created_at=T0 + timedelta(days=2 * i), updated_at=T0 + timedelta(days=2 * i)) for i in range(8)])
        await s.commit()
asyncio.run(main())
