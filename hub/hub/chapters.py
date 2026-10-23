"""A project's chapters: the thread as the manager tells it, kept as append-only versions.

A chapter groups surface knots of the structural thread (`project_thread.py`) under a title and a
summary, over a span; chapters may overlap in time. Every change is a new `ChapterVersion` row,
never an update, recording who made it, who asked, when and why. `save` is the one way in -- the
manager's firing and the agents' tools both go through it -- and implements the spec's "Saving a
chapters version": citations must resolve, every surface knot sits in exactly one chapter, and a
save nobody asked for only adds chapters.

A chapter is `{id, title, summary, start, end, members, cites}`. `members` are surface knot keys
(`project_thread.Thread.top`); `cites` are Hub record ids (`task-...`), `commit:<sha>` or
`tag:<name>`, checked against the Hub's tables and the project's git repository.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import (
    ChapterVersion,
    Conversation,
    Message,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecRequirement,
    Task,
)
from .project_thread import Knot, Thread, _parse, aware
from .subprocess_windows import no_console_kwargs

# Hub record ids a chapter may cite, by id prefix.
_RECORD_MODELS = {
    "task": Task,
    "run": Run,
    "spdoc": SpecDocument,
    "spreq": SpecRequirement,
    "conv": Conversation,
    "msg": Message,
    "ev": RequirementEvidence,
}
_FIELDS = ("title", "summary", "start", "end", "members", "cites")


class ChapterRefusedError(ValueError):
    """The whole version is refused. `problems` name every knot or citation at fault."""

    def __init__(self, problems: Sequence[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


@dataclass
class SaveResult:
    #: The version written, None when an unasked save had nothing new to keep.
    version: Optional[Dict[str, Any]]
    #: Existing chapters an unasked save tried to change, named, whose changes were dropped.
    dropped: List[str] = field(default_factory=list)


def surface_keys(thread: Thread) -> List[str]:
    """The surface knots of slice 1: each document, and each record outside any document."""
    return [knot.key for knot in thread.top]


def _normal(raw: Dict[str, Any], problems: List[str]) -> Optional[Dict[str, Any]]:
    cid = str(raw.get("id") or "").strip()
    title = str(raw.get("title") or "").strip()
    if not cid or not title:
        problems.append("a chapter has no id or no title")
        return None
    start, end = _parse(str(raw.get("start") or "")), _parse(str(raw.get("end") or ""))
    if start is None or end is None or end < start:
        problems.append(f"chapter {cid} has no valid span (start and end, start not after end)")
        return None
    return {
        "id": cid,
        "title": title,
        "summary": str(raw.get("summary") or ""),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "members": [str(m) for m in raw.get("members") or []],
        "cites": [str(c) for c in raw.get("cites") or []],
    }


def _git_has(repo: Path, args: List[str]) -> bool:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            timeout=30,
            **no_console_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


async def _unresolved(
    db: AsyncSession, project_id: str, cites: Iterable[str], repo: Optional[Path]
) -> List[str]:
    missing: List[str] = []
    for cite in dict.fromkeys(cites):
        kind, _, rest = cite.partition(":")
        if kind in ("commit", "tag"):
            args = (
                ["cat-file", "-e", f"{rest}^{{commit}}"]
                if kind == "commit"
                else ["rev-parse", "-q", "--verify", f"refs/tags/{rest}"]
            )
            found = bool(rest) and not rest.startswith("-") and repo is not None
            if found:
                found = await asyncio.to_thread(_git_has, repo, args)  # type: ignore[arg-type]
            if not found:
                missing.append(cite)
            continue
        model = _RECORD_MODELS.get(cite.split("-", 1)[0])
        row = None
        if model is not None:
            row = (
                await db.execute(
                    select(model.id).where(model.id == cite, model.project_id == project_id)
                )
            ).first()
        if row is None:
            missing.append(cite)
    return missing


async def versions(db: AsyncSession, project_id: str) -> List[ChapterVersion]:
    """Every version, oldest first."""
    return list(
        (
            await db.execute(
                select(ChapterVersion)
                .where(ChapterVersion.project_id == project_id)
                .order_by(ChapterVersion.version)
            )
        )
        .scalars()
        .all()
    )


def version_record(row: ChapterVersion) -> Dict[str, Any]:
    return {
        "id": row.id,
        "version": row.version,
        "author": row.author,
        "asked_by": row.asked_by,
        "asked_for": row.asked_for,
        "reason": row.reason,
        "at": aware(row.created_at).isoformat() if row.created_at else None,
        "chapters": row.chapters,
    }


def ordered(chapters: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Chapters by start; chapters whose spans overlap sit side by side in the order they began."""
    # By the moment, not the string: starts written with different UTC offsets must still order.
    far = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(chapters, key=lambda c: (_parse(c["start"]) or far, c["id"]))


async def save(
    db: AsyncSession,
    project_id: str,
    *,
    chapters: Sequence[Dict[str, Any]],
    surface: Sequence[str],
    author: str,
    reason: str,
    asked_for: bool,
    asked_by: Optional[str] = None,
    repo: Optional[Path] = None,
    commit: bool = True,
) -> SaveResult:
    """Save *chapters* as the next version, or raise `ChapterRefusedError` naming what is wrong.

    *surface* is the surface knot keys of the thread now. *asked_for* is whether the operator (or an
    agent a user asked to) wanted this save; if not, only chapters for knots no chapter holds are
    kept and each change proposed to an existing chapter is dropped and named in the result.
    """
    problems: List[str] = []
    proposed = [c for c in (_normal(raw, problems) for raw in chapters) if c is not None]
    ids = [c["id"] for c in proposed]
    for cid in dict.fromkeys(i for i in ids if ids.count(i) > 1):
        problems.append(f"chapter id {cid} is used twice")
    if not (reason or "").strip():
        problems.append("a version needs a reason")

    # Citations first: any that does not resolve refuses the whole version.
    for cite in await _unresolved(
        db, project_id, [c for chapter in proposed for c in chapter["cites"]], repo
    ):
        problems.append(f"citation {cite} does not resolve")
    if problems:
        raise ChapterRefusedError(problems)

    history = await versions(db, project_id)
    previous = history[-1] if history else None
    dropped: List[str] = []
    if not asked_for and previous is not None:
        stored = {c["id"]: c for c in previous.chapters}
        added = [c for c in proposed if c["id"] not in stored]
        for chapter in proposed:
            old = stored.get(chapter["id"])
            if old is not None and any(old.get(name) != chapter[name] for name in _FIELDS):
                dropped.append(f"{old['title']} ({old['id']})")
        if not added:
            return SaveResult(None, dropped)
        proposed = list(previous.chapters) + added

    # Every knot that existed at the previous save sits in exactly one chapter, and every member
    # is a knot; knots recorded since may be placed or left ungrouped.
    held: Dict[str, List[str]] = {}
    for chapter in proposed:
        for member in chapter["members"]:
            held.setdefault(member, []).append(chapter["id"])
    known = set(surface) | (set(previous.known_knots) if previous else set())
    required = set(previous.known_knots) if previous else set(surface)
    for key in sorted(required - set(held)):
        problems.append(f"knot {key} is in no chapter")
    for key, owners in sorted(held.items()):
        if key not in known:
            problems.append(f"knot {key} does not exist")
        elif len(owners) > 1:
            problems.append(f"knot {key} is in more than one chapter ({', '.join(owners)})")
    if problems:
        raise ChapterRefusedError(problems)

    row = ChapterVersion(
        id=f"chv-{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        version=(previous.version if previous else 0) + 1,
        author=author,
        asked_by=asked_by,
        asked_for=asked_for,
        reason=reason.strip(),
        chapters=ordered(proposed),
        known_knots=sorted(known),
    )
    db.add(row)
    if commit:
        await db.commit()
    else:
        await db.flush()
    return SaveResult(version_record(row), dropped)


def _git_lines(repo: Path, args: List[str]) -> List[str]:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            timeout=60,
            **no_console_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    return done.stdout.decode("utf-8", "replace").splitlines()


_TAG_SUFFIX = re.compile(r"[~^].*$")
UNRELEASED = "Not yet released"


def _commit_facts(repo: Path, shas: List[str]) -> Dict[str, Dict[str, Any]]:
    """For each commit sha: its full sha, date, author, subject and the release tag it shipped in
    (the nearest tag reaching it, `Not yet released` for none). Commits git cannot show are absent.
    """
    facts: Dict[str, Dict[str, Any]] = {}
    rows = _git_lines(
        repo,
        ["show", "-s", "--no-patch", "--format=%H%x1f%aI%x1f%an%x1f%s", *shas],
    )
    for row in rows:
        parts = row.split("\x1f")
        if len(parts) != 4:
            continue
        full, date, author, subject = parts
        facts[full] = {"sha": full, "date": date, "author": author, "subject": subject}
    full_shas = list(facts)
    if full_shas:
        # One output line per input, in order; `undefined` for a commit no tag reaches.
        named = _git_lines(repo, ["name-rev", "--tags", "--name-only", *full_shas])
        for sha, name in zip(full_shas, named, strict=False):
            name = _TAG_SUFFIX.sub("", name.strip())
            facts[sha]["tag"] = name if name and name != "undefined" else UNRELEASED
    for fact in facts.values():
        fact.setdefault("tag", UNRELEASED)
    return facts


def _resolve_shas(repo: Path, shas: List[str]) -> Dict[str, str]:
    """Each cited sha (maybe abbreviated) as the full sha git knows it by."""
    out: Dict[str, str] = {}
    for sha in shas:
        lines = _git_lines(repo, ["rev-parse", "-q", "--verify", f"{sha}^{{commit}}"])
        if lines:
            out[sha] = lines[0].strip()
    return out


def _derived(chapter_id: str, kind: str, name: str) -> str:
    return f"{kind}:{chapter_id}|{name}"


async def overlay(
    db: AsyncSession, project_id: str, thread: Thread, repo: Optional[Path] = None
) -> Thread:
    """Make *thread*'s surface its current chapters, ordered by start, followed by every surface
    knot no chapter holds yet. A chapter's children are the knots it groups; a chapter from before
    the Hub, which cites commits, opens into release tags and those into commits. A project with no
    chapters is left exactly as slice 1 built it."""
    history = await versions(db, project_id)
    if not history:
        return thread
    current = ordered(history[-1].chapters)
    author = history[-1].author
    by_key = {knot.key: knot for knot in thread.top}

    cited: List[str] = []
    for chapter in current:
        cited.extend(c.partition(":")[2] for c in chapter["cites"] if c.startswith("commit:"))

    resolved: Dict[str, str] = {}
    facts: Dict[str, Dict[str, Any]] = {}
    if cited and repo is not None:
        resolved = await asyncio.to_thread(_resolve_shas, repo, list(dict.fromkeys(cited)))
        facts = await asyncio.to_thread(_commit_facts, repo, list(dict.fromkeys(resolved.values())))

    def count(knot: Knot) -> int:
        knot.descendants = sum(count(c) + 1 for c in knot.children)
        return knot.descendants

    placed: set = set()
    chapter_knots: List[Knot] = []
    for chapter in current:
        start, end = _parse(chapter["start"]), _parse(chapter["end"])
        knot = Knot(
            key=f"chapter:{chapter['id']}",
            kind="chapter",
            title=chapter["title"],
            start=start,  # type: ignore[arg-type]
            end=end,  # type: ignore[arg-type]
            actors=[author],
            records=[chapter["id"]],
            record_count=1,
            summary=chapter["summary"],
        )
        members = [by_key[m] for m in chapter["members"] if m in by_key]
        placed.update(m.key for m in members)
        for member in members:
            member.parent = knot.key
        knot.children = sorted(members, key=lambda k: k.sort_key)
        tags: Dict[str, List[Knot]] = {}
        for cite in chapter["cites"]:
            if not cite.startswith("commit:"):
                continue
            fact = facts.get(resolved.get(cite.partition(":")[2], ""))
            if fact is None:
                continue
            when = _parse(fact["date"])
            commit = Knot(
                key=_derived(chapter["id"], "commit", fact["sha"]),
                kind="commit",
                title=fact["subject"],
                start=when,  # type: ignore[arg-type]
                end=when,  # type: ignore[arg-type]
                actors=[fact["author"]],
                records=[fact["sha"][:12]],
                record_count=1,
            )
            if any(c.key == commit.key for group in tags.values() for c in group):
                continue
            tags.setdefault(fact["tag"], []).append(commit)
        for name, commits in tags.items():
            commits.sort(key=lambda k: k.sort_key)
            release = Knot(
                key=_derived(chapter["id"], "tag", name),
                kind="release",
                title=name,
                start=commits[0].start,
                end=commits[-1].end,
                actors=list(dict.fromkeys(a for c in commits for a in c.actors)),
                records=[name],
                record_count=1,
                children=commits,
            )
            for commit in commits:
                commit.parent = release.key
                thread.add(commit)
            release.parent = knot.key
            thread.add(release)
            knot.children.append(release)
        knot.children.sort(key=lambda k: k.sort_key)
        thread.add(knot)
        count(knot)
        chapter_knots.append(knot)
    ungrouped = [k for k in thread.top if k.key not in placed]
    thread.chaptered = chapter_knots + ungrouped
    return thread


async def read(
    db: AsyncSession, project_id: str, thread: Optional[Thread] = None
) -> Dict[str, Any]:
    """The current chapters (ordered by start), every version newest first, and the surface knots
    no chapter holds yet, ungrouped, to be shown after the chapters."""
    history = await versions(db, project_id)
    current = ordered(history[-1].chapters) if history else []
    placed = {m for chapter in current for m in chapter["members"]}
    ungrouped: List[Dict[str, Any]] = []
    if thread is not None:
        ungrouped = [
            {"key": k.key, "title": k.title, "start": k.start.isoformat()}
            for k in thread.top
            if k.key not in placed
        ]
    return {
        "chapters": current,
        "ungrouped": ungrouped,
        "versions": [version_record(v) for v in reversed(history)],
    }
