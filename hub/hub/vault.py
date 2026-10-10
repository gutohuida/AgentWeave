"""The knowledge vault: business sources the operator gives a project, and the map agents read.

`a-vault-the-operator-fills-with-text-and-agents-can-read`, the first vault slice of the roadmap
`the-knowledge-vault-and-its-manager-roadmap`.

**Files are the record** (roadmap D2). A source is two files: `sources/<id>.md`, the text exactly
as given and never rewritten, and `sources/<id>.json`, its metadata. A tracked source lives under
the project's `knowledge/` directory, so a colleague who pulls the repository has it. A private
source lives at the project's private location, outside the repository. Only a stub (its
metadata, never its text) is written under `knowledge/`, so colleagues can see that the entry
exists and whose machine holds it (D3, D6). Nothing here keeps an index: the map is built from the
files on every read (D5), which is why a colleague's pulled entries need no import.

**Facts** (`the-manager-distils-vault-sources-into-cited-facts`) are one file each,
`facts/<id>.json`, written by the manager's distillation job (`distillation.py`), never by an
agent. A fact holds its claim and citations (source, quote, line span) and lives where its source
does: a private source's facts are private, with a stub under `knowledge/facts` that names its
sources and holder but never its claim.

**Contradictions** (`sources-that-disagree-are-pointed-out`) are one file each,
`contradictions/<id>.json`, written by the distillation job's check and resolved by the operator.
A contradiction cites two facts and presumes the one whose source was said later (a source's
`dated`, else the day it was uploaded). It is private when either fact is, with a claimless stub
under `knowledge/contradictions`. Whether a fact is disputed, presumed or superseded is derived
from these files on every read; a fact's own file is never rewritten. Resolving writes a source of
type `decision` naming both facts, the one that stands and the operator's note.

**One storage interface** (D9). Every read and write goes through `storage`, whose only
implementation is the local filesystem. A root is an opaque string, so a later cloud backend is a
second implementation, not a rewrite.

**The private location is never inside the project** (D3, operator 2026-10-09). A folder in the
working tree can be swept into a commit, or become tracked when `.gitignore` changes. The
project's worktrees live inside it too (`.agentweave/worktrees`).
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import secrets
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import VaultSettings
from .project_workspace import canonical_path_key

TYPES = ("transcript", "document", "rules", "example", "note", "decision")
DECISION = "decision"
VISIBILITIES = ("tracked", "private")
DEFAULT_VISIBILITY = "tracked"

MAX_NAME_CHARS = 200
MAX_CONTENT_BYTES = 1_048_576
PAGE_CHARS = 50_000
OPENING_CHARS = 300

TRACKED_DIRECTORY = "knowledge"
SOURCES = "sources"
FACTS = "facts"
CONTRADICTIONS = "contradictions"

_ID_RE = re.compile(r"^src-[0-9a-f]{12}$")
_FACT_ID_RE = re.compile(r"^fct-[0-9a-f]{12}$")
_CTR_ID_RE = re.compile(r"^ctr-[0-9a-f]{12}$")
_DATED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# What a private fact's stub under knowledge/facts holds: never the claim, which is the knowledge.
_FACT_STUB_KEYS = ("id", "kind", "visibility", "holder", "created_at", "sources")
# A private contradiction's stub: which two facts, never what either claims or why they disagree.
_CTR_STUB_KEYS = ("id", "kind", "visibility", "holder", "created_at", "facts")


class VaultError(ValueError):
    """A request the vault refuses. `status` is the HTTP status the route answers with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


class VaultStorage(Protocol):
    """Where vault records are kept. *root* is opaque to callers; *relative* uses `/`."""

    def write(self, root: str, relative: str, data: bytes) -> None: ...

    def read(self, root: str, relative: str) -> Optional[bytes]: ...

    def list(self, root: str, directory: str) -> List[str]:
        """The names of the files directly inside *directory*, sorted."""
        ...

    def delete(self, root: str, relative: str) -> None:
        """Remove one file; a file that is not there is not an error."""
        ...


class LocalVaultStorage:
    """The local filesystem. A write goes to a temporary file first and is renamed into place, so
    a reader never sees half a record."""

    @staticmethod
    def _path(root: str, relative: str) -> Path:
        parts = Path(relative).parts
        if not parts or Path(relative).is_absolute() or ".." in parts:
            raise VaultError(f"not a vault path: {relative!r}")
        return Path(root).joinpath(*parts)

    def write(self, root: str, relative: str, data: bytes) -> None:
        path = self._path(root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    def read(self, root: str, relative: str) -> Optional[bytes]:
        try:
            return self._path(root, relative).read_bytes()
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
            return None

    def list(self, root: str, directory: str) -> List[str]:
        try:
            return sorted(p.name for p in self._path(root, directory).iterdir() if p.is_file())
        except (FileNotFoundError, NotADirectoryError):
            return []

    def delete(self, root: str, relative: str) -> None:
        with contextlib.suppress(FileNotFoundError, NotADirectoryError):
            self._path(root, relative).unlink()


storage: VaultStorage = LocalVaultStorage()


# ---------------------------------------------------------------------------
# Locations and settings
# ---------------------------------------------------------------------------


def vaults_root() -> Path:
    """The Hub's own folder for private vaults, one subfolder per project."""
    return Path.home() / ".agentweave" / "hub" / "vaults"


def default_private_location(project_id: str) -> Path:
    return vaults_root() / project_id


def holder_name() -> str:
    """Whose machine holds a private entry: its network name (D7)."""
    return platform.node() or "an unnamed machine"


def _inside(path: Path, parent: Path) -> bool:
    child, ancestor = canonical_path_key(path), canonical_path_key(parent)
    separator = "\\" if child.startswith("windows:") else "/"
    return child == ancestor or child.startswith(ancestor.rstrip(separator) + separator)


def check_private_location(raw: str, project_root: Path) -> Path:
    """The private location *raw* names, resolved and created, or `VaultError`.

    Refused: a relative path, control characters, anything inside the project (its worktrees
    included), a location whose `sources` folder would fall inside it, and a folder that cannot
    be created. Checked on resolved paths, so neither `..` nor a symlink gets past it."""
    if not raw or not raw.strip():
        raise VaultError("The private location is empty.")
    if any(ord(character) < 32 or ord(character) == 127 for character in raw):
        raise VaultError("The private location contains control characters.")
    candidate = Path(raw.strip()).expanduser()
    if not candidate.is_absolute():
        raise VaultError(f"The private location must be an absolute path, not {raw!r}.")
    resolved = candidate.resolve(strict=False)
    root = project_root.resolve(strict=False)
    if _inside(resolved, root) or _inside(resolved / SOURCES, root):
        raise VaultError(
            f"{resolved} is inside the project's directory ({root}). A private entry kept there "
            "could be committed with the repository; choose a folder outside it."
        )
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise VaultError(f"The private location {resolved} cannot be created: {exc}") from exc
    if not resolved.is_dir():
        raise VaultError(f"The private location {resolved} is not a folder.")
    return resolved


def _listed_settings(project_id: str, row: Optional[VaultSettings]) -> Dict[str, Any]:
    chosen = row.private_location if row is not None else None
    return {
        "private_location": chosen,
        "effective_private_location": chosen or str(default_private_location(project_id)),
        "default_visibility": row.default_visibility if row is not None else DEFAULT_VISIBILITY,
    }


async def get_settings(db: AsyncSession, project_id: str) -> Dict[str, Any]:
    return _listed_settings(project_id, await db.get(VaultSettings, project_id))


async def set_settings(
    db: AsyncSession, project_id: str, project_root: Path, fields: Dict[str, Any]
) -> Dict[str, Any]:
    """Store what *fields* names (omitted means unchanged, a null location means the default).
    Everything is checked before anything is stored, so a refusal changes nothing."""
    values: Dict[str, Any] = {}
    if "default_visibility" in fields:
        visibility = fields["default_visibility"]
        if visibility not in VISIBILITIES:
            raise VaultError(f"default_visibility must be tracked or private, not {visibility!r}.")
        values["default_visibility"] = visibility
    if "private_location" in fields:
        raw = fields["private_location"]
        values["private_location"] = (
            None if raw is None else str(check_private_location(raw, project_root))
        )
    row = await db.get(VaultSettings, project_id)
    if row is None:
        row = VaultSettings(project_id=project_id, default_visibility=DEFAULT_VISIBILITY)
        db.add(row)
    for key, value in values.items():
        setattr(row, key, value)
    await db.flush()
    return _listed_settings(project_id, row)


# ---------------------------------------------------------------------------
# Records and the map
# ---------------------------------------------------------------------------


def tracked_root(project_root: Path) -> str:
    return str(project_root / TRACKED_DIRECTORY)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _load(raw: Optional[bytes], entry_id: str) -> Optional[Dict[str, Any]]:
    """A JSON record naming *entry_id* with a known visibility, or None."""
    if raw is None:
        return None
    try:
        meta = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(meta, dict) or meta.get("id") != entry_id:
        return None
    if meta.get("visibility") not in VISIBILITIES or not isinstance(meta.get("created_at"), str):
        return None
    return meta


def _meta(raw: Optional[bytes], entry_id: str) -> Optional[Dict[str, Any]]:
    """A source's metadata, or None for anything that is not one of ours."""
    meta = _load(raw, entry_id)
    if meta is None or not all(isinstance(meta.get(key), str) for key in ("name", "type")):
        return None
    return meta


def _citation_ok(citation: Any) -> bool:
    return (
        isinstance(citation, dict)
        and isinstance(citation.get("source"), str)
        and isinstance(citation.get("quote"), str)
        and isinstance(citation.get("line_start"), int)
        and isinstance(citation.get("line_end"), int)
    )


def _fact_meta(raw: Optional[bytes], entry_id: str) -> Optional[Dict[str, Any]]:
    """A fact's record or stub, or None. A record holds a claim; a stub holds only `sources`."""
    meta = _load(raw, entry_id)
    if meta is None:
        return None
    sources = meta.get("sources")
    if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
        return None
    if "claim" in meta:
        citations = meta.get("citations")
        if not isinstance(meta["claim"], str) or not isinstance(citations, list):
            return None
        if not citations or not all(_citation_ok(c) for c in citations):
            return None
    return meta


def _ids(root: str, directory: str = SOURCES, pattern: "re.Pattern[str]" = _ID_RE) -> List[str]:
    return [
        name[: -len(".json")]
        for name in storage.list(root, directory)
        if name.endswith(".json") and pattern.match(name[: -len(".json")])
    ]


def _opening(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines)[:OPENING_CHARS]


class _Record:
    def __init__(self, meta: Dict[str, Any], text_root: Optional[str]) -> None:
        self.meta = meta
        self.text_root = text_root  # None: the text is not on this machine

    def text(self) -> Optional[str]:
        if self.text_root is None:
            return None
        raw = storage.read(self.text_root, f"{SOURCES}/{self.meta['id']}.md")
        return None if raw is None else raw.decode("utf-8", errors="replace")

    def listed(self, text: Optional[str]) -> Dict[str, Any]:
        meta = self.meta
        return {
            "id": meta["id"],
            "kind": "source",
            "name": meta["name"],
            "type": meta["type"],
            "visibility": meta["visibility"],
            "created_at": meta["created_at"],
            "dated": meta.get("dated"),
            "holder": meta.get("holder"),
            "available": text is not None,
            "opening": None if text is None else _opening(text),
        }


class _Fact:
    def __init__(self, meta: Dict[str, Any], root: str) -> None:
        self.meta = meta
        self.root = root  # where its record (or, for a stub, the stub) lives

    @property
    def claim(self) -> Optional[str]:
        return self.meta.get("claim")

    def listed(self, flags: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """As the map lists it, with *flags* (disputed, presumed, superseded_by) derived from the
        contradictions that cite it."""
        meta, claim = self.meta, self.claim
        return {
            **(flags or _UNDISPUTED),
            "id": meta["id"],
            "kind": "fact",
            "name": claim[:MAX_NAME_CHARS] if claim else "A private fact",
            "type": "fact",
            "visibility": meta["visibility"],
            "created_at": meta["created_at"],
            "holder": meta.get("holder"),
            "available": claim is not None,
            "opening": claim,
            "sources": list(meta["sources"]),
        }


def _records(project_root: Path, private_root: Path) -> Dict[str, _Record]:
    tracked, private = tracked_root(project_root), str(private_root)
    records: Dict[str, _Record] = {}
    # Private entries held here first: their full record wins over this repository's stub of them.
    for entry_id in _ids(private):
        meta = _meta(storage.read(private, f"{SOURCES}/{entry_id}.json"), entry_id)
        if meta is not None and meta["visibility"] == "private":
            records[entry_id] = _Record(meta, private)
    for entry_id in _ids(tracked):
        if entry_id in records:
            continue
        meta = _meta(storage.read(tracked, f"{SOURCES}/{entry_id}.json"), entry_id)
        if meta is not None:
            records[entry_id] = _Record(meta, tracked if meta["visibility"] == "tracked" else None)
    return records


def _facts(project_root: Path, private_root: Path) -> Dict[str, _Fact]:
    """Every fact, private records held here winning over their stubs, as for sources."""
    tracked, private = tracked_root(project_root), str(private_root)
    facts: Dict[str, _Fact] = {}
    for fact_id in _ids(private, FACTS, _FACT_ID_RE):
        meta = _fact_meta(storage.read(private, f"{FACTS}/{fact_id}.json"), fact_id)
        if meta is not None and meta["visibility"] == "private" and "claim" in meta:
            facts[fact_id] = _Fact(meta, private)
    for fact_id in _ids(tracked, FACTS, _FACT_ID_RE):
        if fact_id in facts:
            continue
        meta = _fact_meta(storage.read(tracked, f"{FACTS}/{fact_id}.json"), fact_id)
        if meta is None:
            continue
        if meta["visibility"] == "private":
            # Only ever a stub here: a claim found in the repository for a private fact is
            # not shown as though it were tracked.
            meta = {key: meta[key] for key in _FACT_STUB_KEYS if key in meta}
        facts[fact_id] = _Fact(meta, tracked)
    return facts


def _source_date(meta: Dict[str, Any]) -> str:
    """When a source was said: its `dated`, else the day it was uploaded."""
    dated = meta.get("dated")
    return dated if isinstance(dated, str) and dated else meta["created_at"][:10]


def _fact_order(fact: _Fact, records: Dict[str, _Record]) -> Tuple[str, str, str]:
    """What makes one fact newer than another: its source's date, then its source's upload, then
    its own. A fact whose sources are absent counts by its own creation."""
    source = next((records[s] for s in fact.meta["sources"] if s in records), None)
    created = fact.meta["created_at"]
    if source is None:
        return created[:10], created, created
    return _source_date(source.meta), source.meta["created_at"], created


def dated_facts(project_root: Path, private_root: Path) -> List[Dict[str, Any]]:
    """Every fact whose claim is on this machine, latest-dated first: its id, claim, sources,
    visibility, date, and `order`, the key that decides which side of a contradiction is
    presumed."""
    records = _records(project_root, private_root)
    listed = []
    for fact in _facts(project_root, private_root).values():
        if fact.claim is None:
            continue
        order = _fact_order(fact, records)
        listed.append(
            {
                "id": fact.meta["id"],
                "claim": fact.claim,
                "sources": list(fact.meta["sources"]),
                "visibility": fact.meta["visibility"],
                "date": order[0],
                "order": order,
            }
        )
    return sorted(listed, key=lambda fact: (fact["order"], fact["id"]), reverse=True)


def _newest_first(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(entries, key=lambda entry: (entry["created_at"], entry["id"]), reverse=True)


def build_map(project_root: Path, private_root: Path) -> List[Dict[str, Any]]:
    """Every source, newest first, each followed by the facts that cite it, newest first. A fact
    whose sources are all absent is listed at the end. Facts carry their derived flags."""
    sources = _newest_first(
        [record.listed(record.text()) for record in _records(project_root, private_root).values()]
    )
    flags = _flags(_contradictions(project_root, private_root))
    facts = _newest_first(
        [
            fact.listed(flags.get(fact_id))
            for fact_id, fact in _facts(project_root, private_root).items()
        ]
    )
    known = {source["id"] for source in sources}
    under: Dict[str, List[Dict[str, Any]]] = {}
    orphans: List[Dict[str, Any]] = []
    for fact in facts:
        home = next((s for s in fact["sources"] if s in known), None)
        (under.setdefault(home, []) if home else orphans).append(fact)
    listed: List[Dict[str, Any]] = []
    for source in sources:
        listed.append(source)
        listed.extend(under.get(source["id"], []))
    return listed + orphans


def _held_elsewhere(holder: Optional[str]) -> str:
    return (
        f"This entry is private and its text is held on {holder or 'another machine'}, not on "
        "this machine. Ask the operator for it if you need it."
    )


def _lines(citation: Dict[str, Any]) -> str:
    start, end = citation["line_start"], citation["line_end"]
    return f"line {start}" if start == end else f"lines {start}-{end}"


def _card(meta: Dict[str, Any]) -> str:
    """A fact as an agent reads it: the claim, then where each quote is in its source."""
    cited = "\n".join(f'- {c["source"]}, {_lines(c)}: "{c["quote"]}"' for c in meta["citations"])
    return f"Fact: {meta['claim']}\n\nCited from:\n{cited}\n"


def _said(fact_id: Optional[str], facts: Dict[str, _Fact]) -> str:
    fact = facts.get(fact_id) if fact_id else None
    claim = fact.claim if fact is not None else None
    return f'{fact_id}: "{claim}"' if claim else f"{fact_id} (its claim is not on this machine)"


def _dispute_lines(
    fact_id: str, contradictions: Dict[str, Dict[str, Any]], facts: Dict[str, _Fact]
) -> List[str]:
    """What a fact's card says about the contradictions citing it, open ones first."""
    lines: List[str] = []
    for record in _open_first(list(contradictions.values())):
        if fact_id not in record["facts"] or "status" not in record:
            continue
        other = next(f for f in record["facts"] if f != fact_id)
        if record["status"] == "open":
            presumed = "this fact" if record["presumed"] == fact_id else other
            lines.append(
                f"DISPUTED: this fact contradicts {_said(other, facts)}. Until the operator "
                f"decides, {presumed} is presumed, its source being the later said. "
                f"(Contradiction {record['id']}.)"
            )
            continue
        resolution = record["resolution"]
        if resolution.get("stands") != fact_id:
            lines.append(
                f"SUPERSEDED by decision {resolution.get('decision')}: the operator resolved its "
                f"contradiction with {_said(other, facts)}. Note: {resolution.get('note')}"
            )
    return lines


def _read_fact(project_root: Path, private_root: Path, fact_id: str) -> Optional[Dict[str, Any]]:
    facts = _facts(project_root, private_root)
    fact = facts.get(fact_id)
    if fact is None:
        return None
    contradictions = _contradictions(project_root, private_root)
    entry = fact.listed(_flags(contradictions).get(fact_id))
    if fact.claim is None:
        entry.update(content=None, next_offset=None, note=_held_elsewhere(entry["holder"]))
        return entry
    content = _card(fact.meta)
    disputes = _dispute_lines(fact_id, contradictions, facts)
    if disputes:
        content += "\n" + "\n".join(disputes) + "\n"
    entry.update(
        claim=fact.claim,
        citations=fact.meta["citations"],
        content=content,
        next_offset=None,
        note=None,
    )
    return entry


def read_entry(
    project_root: Path, private_root: Path, entry_id: str, offset: int = 0
) -> Optional[Dict[str, Any]]:
    """One entry with a page of its text (a fact: its card), or None when there is no such entry."""
    if _FACT_ID_RE.match(entry_id):
        return _read_fact(project_root, private_root, entry_id)
    if not _ID_RE.match(entry_id):
        return None
    record = _records(project_root, private_root).get(entry_id)
    if record is None:
        return None
    text = record.text()
    entry = record.listed(text)
    if text is None:
        entry.update(content=None, next_offset=None, note=_held_elsewhere(entry["holder"]))
        return entry
    end = offset + PAGE_CHARS
    entry.update(content=text[offset:end], next_offset=end if end < len(text) else None, note=None)
    return entry


def source_text(
    project_root: Path, private_root: Path, source_id: str
) -> Optional[Tuple[Dict[str, Any], Optional[str]]]:
    """A source's metadata and its whole text (None when held elsewhere); None if unknown."""
    if not _ID_RE.match(source_id):
        return None
    record = _records(project_root, private_root).get(source_id)
    if record is None:
        return None
    return dict(record.meta), record.text()


def check_dated(dated: str) -> None:
    """`VaultError` unless *dated* is a real day written YYYY-MM-DD."""
    try:
        if not _DATED_RE.match(dated):
            raise ValueError(dated)
        date.fromisoformat(dated)
    except ValueError:
        raise VaultError(
            f"dated must be a day written YYYY-MM-DD, such as 2026-09-01, not {dated!r}."
        ) from None


def add_source(
    project_root: Path,
    private_root: Path,
    *,
    name: str,
    type: str,  # noqa: A002 -- the field's own name
    content: str,
    visibility: str,
    dated: Optional[str] = None,
) -> Dict[str, Any]:
    """Write a new source and answer it as the map lists it. Checked before anything is written.
    *dated* is the day it was said (YYYY-MM-DD), which decides the newer side of a
    contradiction."""
    name = (name or "").strip()
    if not name:
        raise VaultError("A source needs a name.")
    if len(name) > MAX_NAME_CHARS:
        raise VaultError(f"A source's name is at most {MAX_NAME_CHARS} characters.")
    if type not in TYPES:
        raise VaultError(f"type must be one of {', '.join(TYPES)}, not {type!r}.")
    if visibility not in VISIBILITIES:
        raise VaultError(f"visibility must be tracked or private, not {visibility!r}.")
    if dated is not None:
        check_dated(dated)
    if not content:
        raise VaultError("A source needs some text.")
    data = content.encode("utf-8")
    if len(data) > MAX_CONTENT_BYTES:
        raise VaultError(
            f"The text is {len(data)} bytes; a source is at most {MAX_CONTENT_BYTES}.", status=413
        )
    if visibility == "private":
        # The stored location was checked when it was set; the project may have moved since.
        check_private_location(str(private_root), project_root)

    entry_id = f"src-{secrets.token_hex(6)}"
    meta = {
        "id": entry_id,
        "name": name,
        "type": type,
        "visibility": visibility,
        "created_at": _now(),
        "holder": holder_name() if visibility == "private" else None,
        "media_type": "text/plain",
        "dated": dated,
    }
    tracked = tracked_root(project_root)
    text_root = tracked if visibility == "tracked" else str(private_root)
    # The text before its metadata: the .json is what lists an entry, so a failure in between
    # leaves an unlisted file rather than a listed entry with no text.
    storage.write(text_root, f"{SOURCES}/{entry_id}.md", data)
    storage.write(text_root, f"{SOURCES}/{entry_id}.json", _encode(meta))
    if visibility == "private":
        stub = {
            key: meta[key] for key in ("id", "name", "type", "visibility", "created_at", "dated")
        }
        stub["holder"] = meta["holder"]
        storage.write(tracked, f"{SOURCES}/{entry_id}.json", _encode(stub))
    return _Record(meta, text_root).listed(content)


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


def add_fact(
    project_root: Path,
    private_root: Path,
    *,
    claim: str,
    citations: List[Dict[str, Any]],
    visibility: str,
    made_by: Dict[str, Any],
) -> Dict[str, Any]:
    """Write one fact and answer its record. A tracked fact citing a private source is refused
    (roadmap D3); a private fact also leaves a stub, with no claim, under knowledge/facts."""
    claim = (claim or "").strip()
    if not claim:
        raise VaultError("A fact needs a claim.")
    if visibility not in VISIBILITIES:
        raise VaultError(f"visibility must be tracked or private, not {visibility!r}.")
    if not citations or not all(_citation_ok(c) for c in citations):
        raise VaultError("A fact needs at least one citation.")
    records = _records(project_root, private_root)
    for citation in citations:
        cited = records.get(citation["source"])
        if cited is None:
            raise VaultError(f"A fact cites an unknown source {citation['source']!r}.")
        if visibility == "tracked" and cited.meta["visibility"] == "private":
            raise VaultError("A tracked fact may not cite a private source.")

    sources: List[str] = []
    for citation in citations:
        if citation["source"] not in sources:
            sources.append(citation["source"])
    fact_id = f"fct-{secrets.token_hex(6)}"
    meta = {
        "id": fact_id,
        "kind": "fact",
        "claim": claim,
        "citations": [
            {key: c[key] for key in ("source", "quote", "line_start", "line_end")}
            for c in citations
        ],
        "sources": sources,
        "visibility": visibility,
        "created_at": _now(),
        "holder": holder_name() if visibility == "private" else None,
        "made_by": made_by,
    }
    tracked = tracked_root(project_root)
    root = tracked if visibility == "tracked" else str(private_root)
    storage.write(root, f"{FACTS}/{fact_id}.json", _encode(meta))
    if visibility == "private":
        stub = {key: meta[key] for key in _FACT_STUB_KEYS}
        storage.write(tracked, f"{FACTS}/{fact_id}.json", _encode(stub))
    return meta


def facts_citing(project_root: Path, private_root: Path, source_id: str) -> List[str]:
    """The ids of the facts, records or stubs, that cite *source_id*."""
    return [
        fact_id
        for fact_id, fact in _facts(project_root, private_root).items()
        if source_id in fact.meta["sources"]
    ]


def delete_fact(project_root: Path, private_root: Path, fact_id: str) -> None:
    """Remove a fact's record and its stub, wherever each is."""
    if not _FACT_ID_RE.match(fact_id):
        raise VaultError(f"not a fact id: {fact_id!r}")
    for root in (str(private_root), tracked_root(project_root)):
        storage.delete(root, f"{FACTS}/{fact_id}.json")


# ---------------------------------------------------------------------------
# Contradictions
# ---------------------------------------------------------------------------

_UNDISPUTED: Dict[str, Any] = {"disputed": False, "presumed": None, "superseded_by": None}


def _contradiction_meta(raw: Optional[bytes], ctr_id: str) -> Optional[Dict[str, Any]]:
    """A contradiction's record or stub, or None. A record holds a status; a stub only `facts`."""
    meta = _load(raw, ctr_id)
    if meta is None:
        return None
    facts = meta.get("facts")
    if not isinstance(facts, list) or len(facts) != 2 or facts[0] == facts[1]:
        return None
    if not all(isinstance(f, str) and _FACT_ID_RE.match(f) for f in facts):
        return None
    if "status" in meta:
        if meta["status"] not in ("open", "resolved") or meta.get("presumed") not in facts:
            return None
        if meta["status"] == "resolved" and not isinstance(meta.get("resolution"), dict):
            return None
    return meta


def _contradictions(project_root: Path, private_root: Path) -> Dict[str, Dict[str, Any]]:
    """Every contradiction, private records held here winning over their stubs, as for facts."""
    tracked, private = tracked_root(project_root), str(private_root)
    found: Dict[str, Dict[str, Any]] = {}
    for ctr_id in _ids(private, CONTRADICTIONS, _CTR_ID_RE):
        meta = _contradiction_meta(storage.read(private, f"{CONTRADICTIONS}/{ctr_id}.json"), ctr_id)
        if meta is not None and meta["visibility"] == "private" and "status" in meta:
            found[ctr_id] = meta
    for ctr_id in _ids(tracked, CONTRADICTIONS, _CTR_ID_RE):
        if ctr_id in found:
            continue
        meta = _contradiction_meta(storage.read(tracked, f"{CONTRADICTIONS}/{ctr_id}.json"), ctr_id)
        if meta is None:
            continue
        if meta["visibility"] == "private":
            meta = {key: meta[key] for key in _CTR_STUB_KEYS if key in meta}
        found[ctr_id] = meta
    return found


def _open_first(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Open contradictions, then resolved ones, then stubs; newest first within each."""
    rank = {"open": 0, "resolved": 1}
    newest = sorted(records, key=lambda r: (r["created_at"], r["id"]), reverse=True)
    return sorted(newest, key=lambda r: rank.get(r.get("status"), 2))


def _flags(contradictions: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Each cited fact's derived marks: disputed while an open contradiction cites it, presumed
    only when it is the presumed side of every open one, superseded_by the decision of a
    resolved one it did not stand in. A stub, whose status is elsewhere, marks nothing."""
    flags: Dict[str, Dict[str, Any]] = {}
    for record in sorted(contradictions.values(), key=lambda r: (r["created_at"], r["id"])):
        status = record.get("status")
        for fact_id in record["facts"]:
            if status == "open":
                mark = flags.setdefault(fact_id, dict(_UNDISPUTED))
                presumed = record["presumed"] == fact_id
                mark["presumed"] = presumed and (mark["presumed"] is not False)
                mark["disputed"] = True
            elif status == "resolved" and record["resolution"].get("stands") != fact_id:
                mark = flags.setdefault(fact_id, dict(_UNDISPUTED))
                mark["superseded_by"] = record["resolution"].get("decision")
    return flags


def contradiction_between(project_root: Path, private_root: Path, a: str, b: str) -> bool:
    """Whether a contradiction between facts *a* and *b*, either way round, is recorded."""
    wanted = {a, b}
    return any(
        set(record["facts"]) == wanted
        for record in _contradictions(project_root, private_root).values()
    )


def add_contradiction(
    project_root: Path,
    private_root: Path,
    *,
    facts: List[str],
    presumed: str,
    explanation: str,
    visibility: str,
    found_by: Dict[str, Any],
) -> Dict[str, Any]:
    """Write one open contradiction and answer its record; a private one also leaves a stub."""
    if len(facts) != 2 or presumed not in facts or visibility not in VISIBILITIES:
        raise VaultError("A contradiction cites two facts and presumes one of them.")
    ctr_id = f"ctr-{secrets.token_hex(6)}"
    meta = {
        "id": ctr_id,
        "kind": "contradiction",
        "facts": list(facts),
        "presumed": presumed,
        "explanation": (explanation or "").strip(),
        "status": "open",
        "visibility": visibility,
        "holder": holder_name() if visibility == "private" else None,
        "created_at": _now(),
        "found_by": found_by,
        "resolution": None,
    }
    tracked = tracked_root(project_root)
    root = tracked if visibility == "tracked" else str(private_root)
    storage.write(root, f"{CONTRADICTIONS}/{ctr_id}.json", _encode(meta))
    if visibility == "private":
        stub = {key: meta[key] for key in _CTR_STUB_KEYS}
        storage.write(tracked, f"{CONTRADICTIONS}/{ctr_id}.json", _encode(stub))
    return meta


def delete_open_contradictions_citing(
    project_root: Path, private_root: Path, fact_ids: List[str]
) -> List[str]:
    """Remove every open contradiction citing one of *fact_ids*, record and stub. A resolved one
    is kept: it is the history of a decision. Answers the ids removed."""
    gone = set(fact_ids)
    removed = []
    for ctr_id, record in _contradictions(project_root, private_root).items():
        if record.get("status") == "open" and gone & set(record["facts"]):
            for root in (str(private_root), tracked_root(project_root)):
                storage.delete(root, f"{CONTRADICTIONS}/{ctr_id}.json")
            removed.append(ctr_id)
    return removed


def _listed_contradiction(
    record: Dict[str, Any], facts: Dict[str, _Fact], records: Dict[str, _Record]
) -> Dict[str, Any]:
    """A contradiction as the list answers it: the record, with each side's claim and date."""
    listed = {"status": None, "presumed": None, "resolution": None, **record}
    sides = []
    for fact_id in record["facts"]:
        fact = facts.get(fact_id)
        source = None
        if fact is not None:
            source = next((s for s in fact.meta["sources"] if s in records), None)
        sides.append(
            {
                "id": fact_id,
                "claim": fact.claim if fact is not None else None,
                "source": source,
                "date": _fact_order(fact, records)[0] if fact is not None else None,
                "presumed": record.get("presumed") == fact_id,
            }
        )
    listed["sides"] = sides
    return listed


def list_contradictions(project_root: Path, private_root: Path) -> List[Dict[str, Any]]:
    """Every contradiction, open first, each with its two sides' claims and dates."""
    facts, records = _facts(project_root, private_root), _records(project_root, private_root)
    return [
        _listed_contradiction(record, facts, records)
        for record in _open_first(list(_contradictions(project_root, private_root).values()))
    ]


def _decision_text(
    record: Dict[str, Any], facts: Dict[str, _Fact], stands: Optional[str], note: str
) -> str:
    first, second = record["facts"]
    chosen = (
        f"The fact that stands is {_said(stands, facts)}." if stands else "Neither fact stands."
    )
    return (
        f"Decision on contradiction {record['id']}, between two facts of the vault:\n"
        f"- {_said(first, facts)}\n- {_said(second, facts)}\n\n{chosen}\n\nNote: {note}\n"
    )


def resolve_contradiction(
    project_root: Path,
    private_root: Path,
    ctr_id: str,
    *,
    stands: Optional[str],
    note: str,
) -> Dict[str, Any]:
    """Record the operator's decision: a `decision` source, then the contradiction resolved,
    answered as the list answers it.

    `VaultError` 404 for an unknown contradiction, 409 for one already resolved or held on
    another machine, 400 for a *stands* that is not one of its facts or an empty note."""
    found = _contradictions(project_root, private_root)
    record = found.get(ctr_id) if _CTR_ID_RE.match(ctr_id) else None
    if record is None:
        raise VaultError(f"No contradiction '{ctr_id}'", status=404)
    if "status" not in record:
        holder = record.get("holder") or "another machine"
        raise VaultError(
            f"This contradiction is private and held on {holder}; it can be resolved there.",
            status=409,
        )
    if record["status"] == "resolved":
        raise VaultError(f"Contradiction {ctr_id} is already resolved.", status=409)
    if stands is not None and stands not in record["facts"]:
        first, second = record["facts"]
        raise VaultError(f"stands must be {first}, {second} or null for neither, not {stands!r}.")
    note = (note or "").strip()
    if not note:
        raise VaultError("A resolution needs a note saying why.")

    facts = _facts(project_root, private_root)
    decision = add_source(
        project_root,
        private_root,
        name=f"Decision on {ctr_id}",
        type=DECISION,
        content=_decision_text(record, facts, stands, note),
        visibility=record["visibility"],
    )
    resolved = dict(record)
    resolved["status"] = "resolved"
    resolved["resolution"] = {
        "stands": stands,
        "note": note,
        "decision": decision["id"],
        "resolved_at": _now(),
    }
    root = tracked_root(project_root) if record["visibility"] == "tracked" else str(private_root)
    storage.write(root, f"{CONTRADICTIONS}/{ctr_id}.json", _encode(resolved))
    return _listed_contradiction(resolved, facts, _records(project_root, private_root))


def _encode(meta: Dict[str, Any]) -> bytes:
    return (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# The index in every turn
# ---------------------------------------------------------------------------


def render_turn_index(entries: List[Dict[str, Any]]) -> List[str]:
    """The Knowledge vault section of a turn's context, or nothing for an empty vault.

    One line that says the vault exists, how many entries it holds and which tools read it. It
    deliberately names no entry, so its cost does not grow with the vault (the operator's choice,
    2026-10-09, over an index of entries capped at 2,000 characters)."""
    if not entries:
        return []
    count = len(entries)
    noun = "entry" if count == 1 else "entries"
    return [
        "### Knowledge vault",
        f"- This project has a knowledge vault with {count} {noun} (meeting transcripts, rules, "
        "documents): `vault_map()` lists them and `vault_read(entry_id)` reads one. Check it "
        "before guessing at what the business decided.",
    ]
