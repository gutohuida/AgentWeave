"""Seed 10,000 items into the scale project: 165 documents (surface knots), 1000 tasks, 3000 runs, 5835 messages."""
import asyncio, os, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "hub"))
from hub.db.engine import async_session_factory
from hub.db.models import Message, Run, SpecDocument, Task

P = sys.argv[1]
T0 = datetime(2025, 11, 20, 9, 0, tzinfo=timezone.utc)
# documents a day apart, with a 3-week silence every 20 documents
day = []
d = 0
for i in range(165):
    day.append(d)
    d += 22 if i % 20 == 19 else 1
at = lambda days, minutes=0: T0 + timedelta(days=days, minutes=minutes)

async def main():
    async with async_session_factory() as s:
        s.add_all([SpecDocument(id=f"spdoc-s{i}", project_id=P, path=f"spec/changes/d{i}/spec.json", title=f"Scale document {i + 1}", created_at=at(day[i]), updated_at=at(day[i])) for i in range(165)])
        await s.flush()
        s.add_all([Task(id=f"task-s{i}", project_id=P, title=f"Scale task {i + 1}", spec_document_id=f"spdoc-s{i % 165}", created_at=at(day[i % 165], 10 + i // 165)) for i in range(1000)])
        await s.flush()
        s.add_all([Run(id=f"run-s{i}", project_id=P, agent="builder", status="completed", turn_depth=0, task_id=f"task-s{i % 1000}", started_at=at(day[(i % 1000) % 165], 30 + i // 1000), ended_at=at(day[(i % 1000) % 165], 31 + i // 1000)) for i in range(3000)])
        await s.flush()
        s.add_all([Message(id=f"msg-s{i}", project_id=P, sender="builder", recipient="qa", content="x", created_by_run_id=f"run-s{i % 3000}", timestamp=at(day[((i % 3000) % 1000) % 165], 40 + i // 3000)) for i in range(5835)])
        await s.commit()
    print("seeded 10000")

asyncio.run(main())
