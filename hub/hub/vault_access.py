"""What agents ask the vault for: counting reads, and ordering the map by them.

`the-vault-map-is-shaped-by-what-agents-ask-for`. The agents' `vault_read` at offset 0 adds one to
that entry's count (`record_fetch`, in its own transaction, so the read never waits on or fails
with it). Both maps and both entry routes list the count and the last read (`annotate`, `shape`),
and `shape` orders the map: an area is a source with the facts citing it, the most-read area leads,
the source leads its area, and its facts follow most-read first. Nothing here runs a model; with no
reads the order is the newest-first order `vault.build_map` already produced.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import VaultFetch

#: An entry's count and when it was last read, as `counts_for` returns them.
Count = Tuple[int, str]


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


async def record_fetch(db: AsyncSession, project_id: str, entry_id: str) -> Count:
    """Add one to the entry's count and stamp it now; returns the new count.

    An UPDATE that adds in the database, so two reads at the same moment are both counted, and an
    INSERT only when there is no row yet (a lost race on it is an UPDATE again).
    """
    now = datetime.now(timezone.utc)
    table = VaultFetch.__table__
    where = (table.c.project_id == project_id) & (table.c.entry_id == entry_id)
    for _ in range(3):
        bumped = await db.execute(
            update(table).where(where).values(count=table.c.count + 1, last_fetched_at=now)
        )
        if bumped.rowcount:
            break
        db.add(VaultFetch(project_id=project_id, entry_id=entry_id, count=1, last_fetched_at=now))
        try:
            await db.commit()
            return 1, _iso(now)
        except IntegrityError:
            await db.rollback()
    else:
        raise RuntimeError(f"could not count a read of {entry_id}")
    await db.commit()
    row = (await db.execute(select(VaultFetch.count).where(where))).scalar_one()
    return int(row), _iso(now)


async def counts_for(db: AsyncSession, project_id: str) -> Dict[str, Count]:
    rows = await db.execute(select(VaultFetch).where(VaultFetch.project_id == project_id))
    return {row.entry_id: (row.count, _iso(row.last_fetched_at)) for row in rows.scalars()}


def annotate(entry: Dict[str, Any], count: Optional[Count]) -> Dict[str, Any]:
    """*entry* with `fetches` (0 when never read) and `last_fetched_at` (null when never read)."""
    fetches, last = count or (0, None)
    return {**entry, "fetches": fetches, "last_fetched_at": last}


def shape(entries: List[Dict[str, Any]], counts: Dict[str, Count]) -> List[Dict[str, Any]]:
    """The map with counts listed and areas ordered by them.

    A fact belongs to the first of its sources that is in the map; one with none is in a last area
    of its own, which stays last. Areas go by the sum of their entries' reads, then their source
    newest first; within an area the source leads and facts go by reads, then newest first. A count
    for an id that is not in *entries* is never listed.
    """
    listed = [annotate(entry, counts.get(entry["id"])) for entry in entries]
    sources = [e for e in listed if e["kind"] == "source"]
    known = {e["id"] for e in sources}
    under: Dict[str, List[Dict[str, Any]]] = {e["id"]: [] for e in sources}
    orphans: List[Dict[str, Any]] = []
    for entry in listed:
        if entry["kind"] != "fact":
            continue
        home = next((s for s in entry.get("sources", []) if s in known), None)
        (under[home] if home else orphans).append(entry)

    def newest_read(entry: Dict[str, Any]) -> Tuple[int, str, str]:
        return entry["fetches"], entry["created_at"], entry["id"]

    areas = []
    for source in sources:
        facts = sorted(under[source["id"]], key=newest_read, reverse=True)
        total = source["fetches"] + sum(f["fetches"] for f in facts)
        areas.append((total, source["created_at"], source["id"], [source, *facts]))
    areas.sort(key=lambda area: area[:3], reverse=True)
    shaped = [entry for area in areas for entry in area[3]]
    return shaped + sorted(orphans, key=newest_read, reverse=True)
