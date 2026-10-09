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

**One storage interface** (D9). Every read and write goes through `storage`, whose only
implementation is the local filesystem. A root is an opaque string, so a later cloud backend is a
second implementation, not a rewrite.

**The private location is never inside the project** (D3, operator 2026-10-09). A folder in the
working tree can be swept into a commit, or become tracked when `.gitignore` changes. The
project's worktrees live inside it too (`.agentweave/worktrees`).
"""

from __future__ import annotations

import json
import os
import platform
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import VaultSettings
from .project_workspace import canonical_path_key

TYPES = ("transcript", "document", "rules", "example", "note")
VISIBILITIES = ("tracked", "private")
DEFAULT_VISIBILITY = "tracked"

MAX_NAME_CHARS = 200
MAX_CONTENT_BYTES = 1_048_576
PAGE_CHARS = 50_000
OPENING_CHARS = 300

TRACKED_DIRECTORY = "knowledge"
SOURCES = "sources"

_ID_RE = re.compile(r"^src-[0-9a-f]{12}$")


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


def _meta(raw: Optional[bytes], entry_id: str) -> Optional[Dict[str, Any]]:
    """A record's metadata, or None for anything that is not one of ours."""
    if raw is None:
        return None
    try:
        meta = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(meta, dict) or meta.get("id") != entry_id:
        return None
    if meta.get("visibility") not in VISIBILITIES:
        return None
    if not all(isinstance(meta.get(key), str) for key in ("name", "type", "created_at")):
        return None
    return meta


def _ids(root: str) -> List[str]:
    return [
        name[: -len(".json")]
        for name in storage.list(root, SOURCES)
        if name.endswith(".json") and _ID_RE.match(name[: -len(".json")])
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
            "name": meta["name"],
            "type": meta["type"],
            "visibility": meta["visibility"],
            "created_at": meta["created_at"],
            "holder": meta.get("holder"),
            "available": text is not None,
            "opening": None if text is None else _opening(text),
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


def build_map(project_root: Path, private_root: Path) -> List[Dict[str, Any]]:
    """Every entry, newest first."""
    listed = [
        record.listed(record.text()) for record in _records(project_root, private_root).values()
    ]
    listed.sort(key=lambda entry: (entry["created_at"], entry["id"]), reverse=True)
    return listed


def read_entry(
    project_root: Path, private_root: Path, entry_id: str, offset: int = 0
) -> Optional[Dict[str, Any]]:
    """One entry with a page of its text, or None when there is no such entry."""
    if not _ID_RE.match(entry_id):
        return None
    record = _records(project_root, private_root).get(entry_id)
    if record is None:
        return None
    text = record.text()
    entry = record.listed(text)
    if text is None:
        holder = entry["holder"] or "another machine"
        entry.update(
            content=None,
            next_offset=None,
            note=(
                f"This entry is private and its text is held on {holder}, not on this machine. "
                "Ask the operator for it if you need it."
            ),
        )
        return entry
    end = offset + PAGE_CHARS
    entry.update(content=text[offset:end], next_offset=end if end < len(text) else None, note=None)
    return entry


def add_source(
    project_root: Path,
    private_root: Path,
    *,
    name: str,
    type: str,  # noqa: A002 -- the field's own name
    content: str,
    visibility: str,
) -> Dict[str, Any]:
    """Write a new source and answer it as the map lists it. Checked before anything is written."""
    name = (name or "").strip()
    if not name:
        raise VaultError("A source needs a name.")
    if len(name) > MAX_NAME_CHARS:
        raise VaultError(f"A source's name is at most {MAX_NAME_CHARS} characters.")
    if type not in TYPES:
        raise VaultError(f"type must be one of {', '.join(TYPES)}, not {type!r}.")
    if visibility not in VISIBILITIES:
        raise VaultError(f"visibility must be tracked or private, not {visibility!r}.")
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
    }
    tracked = tracked_root(project_root)
    text_root = tracked if visibility == "tracked" else str(private_root)
    # The text before its metadata: the .json is what lists an entry, so a failure in between
    # leaves an unlisted file rather than a listed entry with no text.
    storage.write(text_root, f"{SOURCES}/{entry_id}.md", data)
    storage.write(text_root, f"{SOURCES}/{entry_id}.json", _encode(meta))
    if visibility == "private":
        stub = {key: meta[key] for key in ("id", "name", "type", "visibility", "created_at")}
        stub["holder"] = meta["holder"]
        storage.write(tracked, f"{SOURCES}/{entry_id}.json", _encode(stub))
    return _Record(meta, text_root).listed(content)


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
