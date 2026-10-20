"""Adding files to the knowledge vault by path, in bulk.

`agents-add-files-to-the-vault-by-path` (vault-1019). A caller names files and folders; the Hub
reads each file itself, so an agent never reads or pastes what it adds (vault-D1), and every file
goes through the same checks a single upload does (`vault.add_source`, `vault.add_file`). The
answer is one result per file reached -- added, skipped as a duplicate, or refused with its reason
-- never all-or-nothing (vault-D2).

**Where a caller may point** is a `Reach`. An agent's reach is its run's workspace and the
project's directory: a relative path is looked up in the workspace, then the project directory,
and anything that resolves outside both is refused naming them. That is a guardrail against an
agent's mistake, not containment. `agent_reach` takes the operator-granted extra roots that
`reach-1019` adds as *granted*; nothing passes any yet. The operator's API and CLI may name any
absolute path the Hub can read, except in Docker mode, where only paths beneath
`AW_WORKSPACE_ROOT` are visible to the Hub at all.

Everything here is synchronous file work; the routes run it in a thread.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import vault
from .project_workspace import configured_workspace_root

#: Text a path may name, by extension: the Vault tab's own text-file list, plus a few more plain
#: text formats. Read as UTF-8 and stored exactly as a pasted source is (at most 1 MiB).
TEXT_EXTENSIONS = (
    ".md",
    ".markdown",
    ".txt",
    ".text",
    ".rst",
    ".vtt",
    ".srt",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".log",
)

#: PDF and images, by extension, to the media type `vault.add_file` checks the bytes against.
FILE_EXTENSIONS: Dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

#: The most files one call reaches; a folder that holds more is refused before anything is
#: written, so a mistaken path (a home directory) cannot fill the vault.
MAX_BATCH_FILES = 200

ACCEPTED = ", ".join([*TEXT_EXTENSIONS, *FILE_EXTENSIONS])


class IntakeError(ValueError):
    """A whole call refused before anything is written. `status` is the HTTP answer."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Reach:
    """Where a caller's paths may resolve. *bases* are where a relative path is looked up, in
    order (none: relative paths are refused); *roots* are what a resolved path must lie in (None:
    anywhere the Hub can read)."""

    bases: Tuple[Path, ...] = ()
    roots: Optional[Tuple[Path, ...]] = None
    described: str = ""


def agent_reach(
    workspace: Optional[Path], project_root: Path, granted: Sequence[Path] = ()
) -> Reach:
    """An agent run's reach: its workspace (when the run recorded one) and the project directory,
    plus *granted*, the seam for the extra roots an operator grants (reach-1019)."""
    bases: List[Path] = []
    for root in (workspace, project_root):
        if root is not None and root.resolve() not in bases:
            bases.append(root.resolve())
    roots = (*bases, *(Path(g).resolve() for g in granted))
    named = [f"your workspace ({bases[0]})"] if workspace is not None else []
    named.append(f"the project directory ({project_root.resolve()})")
    named += [f"{g}" for g in granted]
    return Reach(bases=tuple(bases), roots=roots, described=" or ".join(named))


def operator_reach() -> Reach:
    """The operator's reach: any absolute path in native mode; beneath AW_WORKSPACE_ROOT in
    Docker mode, the only place a container-run Hub can see the operator's files."""
    mounted = configured_workspace_root()
    if mounted is None:
        return Reach()
    return Reach(roots=(mounted,), described=f"the workspace root ({mounted}, AW_WORKSPACE_ROOT)")


@dataclass
class Item:
    """One file reached, or one path refused before any file was reached."""

    given: str
    path: Optional[Path] = None
    name: str = ""
    refused: Optional[str] = None
    media_type: Optional[str] = None  # None for text


@dataclass
class Batch:
    items: List[Item] = field(default_factory=list)

    @property
    def reads_files(self) -> bool:
        return any(item.media_type is not None and item.refused is None for item in self.items)


def _inside(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return True
    return False


def _locate(given: str, reach: Reach) -> Tuple[Optional[Path], Optional[str]]:
    """The path *given* names, resolved, or why it is refused."""
    if not given or not given.strip():
        return None, "An empty path names nothing."
    if any(ord(ch) < 32 for ch in given):
        return None, "A path cannot hold control characters."
    candidate = Path(given.strip()).expanduser()
    if candidate.is_absolute():
        found: Optional[Path] = candidate if candidate.exists() else None
        if found is None:
            return None, f"No file or folder at {given!r}."
    else:
        if not reach.bases:
            return None, (
                f"{given!r} is relative; name an absolute path (the CLI resolves relative paths "
                "against its own directory)."
            )
        found = next(
            (base / candidate for base in reach.bases if (base / candidate).exists()), None
        )
        if found is None:
            return None, f"No file or folder at {given!r} in {reach.described}."
    resolved = found.resolve()
    if reach.roots is not None and not _inside(resolved, reach.roots):
        return None, f"{given!r} resolves to {resolved}, outside {reach.described}."
    return resolved, None


def _kind(path: Path) -> Tuple[Optional[str], Optional[str]]:
    """(media type or None for text, refusal or None)."""
    suffix = path.suffix.lower()
    if suffix in FILE_EXTENSIONS:
        return FILE_EXTENSIONS[suffix], None
    if suffix in TEXT_EXTENSIONS:
        return None, None
    shown = suffix or "no extension"
    return None, f"A {shown} file is not a vault source; the vault takes {ACCEPTED}."


def _short(name: str) -> str:
    return name if len(name) <= vault.MAX_NAME_CHARS else name[-vault.MAX_NAME_CHARS :]


def _walk(folder: Path, unlistable: List[Tuple[Path, str]]) -> List[Path]:
    """The files under *folder*, sorted, leaving out hidden names (`.git`, `.agentweave`, ...).
    A folder the Hub cannot list is recorded in *unlistable* with the reason and walked no
    further; it never fails the walk."""
    try:
        children = sorted(folder.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        unlistable.append((folder, exc.strerror or str(exc)))
        return []
    found: List[Path] = []
    for child in children:
        if child.name.startswith("."):
            continue
        if child.is_dir():
            found += _walk(child, unlistable)
        elif child.is_file():
            found.append(child)
    return found


def expand(paths: Sequence[str], reach: Reach) -> Batch:
    """Every file *paths* reach, in their order (a folder's files sorted, recursively), each one
    checked against *reach* and its extension. `IntakeError` past MAX_BATCH_FILES."""
    if not paths:
        raise IntakeError("Name at least one file or folder.")
    batch = Batch()
    for given in paths:
        located, refusal = _locate(given, reach)
        if located is None:
            batch.items.append(Item(given=given, refused=refusal))
            continue
        if located.is_dir():
            unlistable: List[Tuple[Path, str]] = []
            files = _walk(located, unlistable)
            for blocked, why in unlistable:
                batch.items.append(
                    Item(
                        given=given,
                        path=None,
                        refused=f"The Hub could not list the folder {blocked}: {why}.",
                    )
                )
            if not files and not unlistable:
                batch.items.append(
                    Item(given=given, path=located, refused=f"The folder {given!r} holds no files.")
                )
            for file in files:
                real = file.resolve()
                item = Item(
                    given=given,
                    path=real,
                    name=_short(f"{located.name}/{file.relative_to(located).as_posix()}"),
                )
                if reach.roots is not None and not _inside(real, reach.roots):
                    item.refused = f"{file} resolves to {real}, outside {reach.described}."
                else:
                    item.media_type, item.refused = _kind(file)
                batch.items.append(item)
        else:
            item = Item(given=given, path=located, name=_short(located.name))
            item.media_type, item.refused = _kind(located)
            batch.items.append(item)
        reached = sum(1 for item in batch.items if item.path is not None)
        if reached > MAX_BATCH_FILES:
            raise IntakeError(
                f"These paths reach more than {MAX_BATCH_FILES} files; one call adds at most "
                f"{MAX_BATCH_FILES}. Name smaller folders or fewer files. Nothing was added."
            )
    return batch


def _mib(limit: int) -> str:
    return f"{limit // 1_048_576} MiB"


def _read(item: Item) -> Tuple[Optional[bytes], Optional[str]]:
    assert item.path is not None
    limit = vault.MAX_FILE_BYTES if item.media_type else vault.MAX_CONTENT_BYTES
    try:
        size = item.path.stat().st_size
        if size > limit:
            what = "a PDF or image source" if item.media_type else "a text source"
            return None, f"The file is {size} bytes; {what} is at most {_mib(limit)}."
        return item.path.read_bytes(), None
    except OSError as exc:
        return None, f"The Hub could not read it: {exc.strerror or exc}."


def add_all(
    project_root: Path,
    private_root: Path,
    batch: Batch,
    *,
    type: str,  # noqa: A002 -- the field's own name
    visibility: str,
    dated: Optional[str],
    added_by: Optional[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Add every file of *batch* that is not refused or a duplicate. Answers the results, one per
    item in order, and the text of each text source added (by id), for the cost estimate."""
    digests = vault.source_digests(project_root, private_root)
    results: List[Dict[str, Any]] = []
    texts: Dict[str, str] = {}
    for item in batch.items:
        shown = str(item.path) if item.path is not None else item.given
        if item.refused is not None:
            results.append({"path": shown, "status": "refused", "reason": item.refused})
            continue
        data, refusal = _read(item)
        if data is None:
            results.append({"path": shown, "status": "refused", "reason": refusal})
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in digests:
            results.append(
                {
                    "path": shown,
                    "status": "skipped",
                    "duplicate_of": digests[digest],
                    "reason": f"The same bytes are already the vault source {digests[digest]}.",
                }
            )
            continue
        try:
            if item.media_type is None:
                try:
                    content = data.decode("utf-8")
                except UnicodeDecodeError:
                    raise vault.VaultError("The file is not UTF-8 text.") from None
                entry = vault.add_source(
                    project_root,
                    private_root,
                    name=item.name,
                    type=type,
                    content=content,
                    visibility=visibility,
                    dated=dated,
                    added_by=added_by,
                )
                texts[entry["id"]] = content
            else:
                entry = vault.add_file(
                    project_root,
                    private_root,
                    name=item.name,
                    type=type,
                    media_type=item.media_type,
                    data=data,
                    visibility=visibility,
                    dated=dated,
                    added_by=added_by,
                )
        except vault.VaultError as exc:
            results.append({"path": shown, "status": "refused", "reason": str(exc)})
            continue
        digests[digest] = entry["id"]
        results.append({"path": shown, "status": "added", "source": entry})
    return results, texts


def counts(results: List[Dict[str, Any]]) -> Dict[str, int]:
    tally = {"added": 0, "skipped": 0, "refused": 0}
    for result in results:
        tally[result["status"]] += 1
    return tally


def check_fields(type: str, visibility: str, dated: Optional[str]) -> None:  # noqa: A002
    """`IntakeError` for a field that would refuse every file alike, before anything is read."""
    if type not in vault.TYPES or type == vault.DECISION:
        allowed = ", ".join(t for t in vault.TYPES if t != vault.DECISION)
        raise IntakeError(f"type must be one of {allowed}, not {type!r}.")
    if visibility not in vault.VISIBILITIES:
        raise IntakeError(f"visibility must be tracked or private, not {visibility!r}.")
    if dated is not None:
        try:
            vault.check_dated(dated)
        except vault.VaultError as exc:
            raise IntakeError(str(exc)) from exc
