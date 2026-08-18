"""Guard: every subprocess spawn in `hub/hub/` must suppress the Windows console flash.

`hub.subprocess_windows.no_console_kwargs()` is the one place `CREATE_NO_WINDOW` is decided.
Every `subprocess.run`/`Popen`/`call`/`check_call`/`check_output` and every
`asyncio.create_subprocess_exec`/`create_subprocess_shell` call in the package must reach it —
otherwise that spawn flashes a real console window on Windows the moment it runs, which is
exactly the defect this test exists to catch before it ships again.

Static (AST-based), not platform-gated: the point is to catch a *new* bare call site being
added, which is a source-level fact true on every OS this suite runs on.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional

import pytest

HUB_PACKAGE = Path(__file__).resolve().parent.parent / "hub"

# (attribute name, allowed base identifiers) -- `subprocess.run`/`Popen`/... and
# `asyncio.create_subprocess_exec`/`create_subprocess_shell` only. Matching the bare attribute
# name alone false-positives on unrelated `.run(...)` calls this codebase already has --
# `uvicorn.run(...)` (main.py), `mcp.run(...)` (mcp_server.py, a FastMCP server, not a spawn),
# `asyncio.run(...)` (migrations/env.py) -- none of which spawn a subprocess.
SPAWN_ATTRS = {
    "run": {"subprocess"},
    "Popen": {"subprocess"},
    "call": {"subprocess"},
    "check_call": {"subprocess"},
    "check_output": {"subprocess"},
    "create_subprocess_exec": {"asyncio"},
    "create_subprocess_shell": {"asyncio"},
}

# `subprocess_windows.py` itself references `subprocess.CREATE_NO_WINDOW` in its docstring/body
# but spawns nothing; nothing else is exempt.
EXEMPT_FILES = {"subprocess_windows.py"}


def _source_files() -> List[Path]:
    return sorted(
        p
        for p in HUB_PACKAGE.rglob("*.py")
        if "__pycache__" not in p.parts and p.name not in EXEMPT_FILES
    )


def _is_spawn_call(node: ast.Call) -> bool:
    """True for `subprocess.run(...)`/`asyncio.create_subprocess_exec(...)` and siblings --
    not for an unrelated same-named method on some other object.
    """
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    allowed_bases = SPAWN_ATTRS.get(func.attr)
    if allowed_bases is None:
        return False
    return isinstance(func.value, ast.Name) and func.value.id in allowed_bases


def _enclosing_function_source(tree: ast.Module, source: str, target: ast.Call) -> str:
    """The source text of the nearest enclosing function/method around *target*, or the whole
    module if *target* sits at module level.

    Console suppression is allowed to live anywhere in that scope — e.g. built into a
    conditionally-populated `popen_options` dict a few lines above the call, as
    `pty_runner.PipeSession.spawn` does — not only as a literal keyword on the call itself.
    """
    best: Optional[ast.AST] = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.lineno <= target.lineno <= (node.end_lineno or node.lineno)
            and (best is None or node.lineno > best.lineno)
        ):
            best = node
    segment = ast.get_source_segment(source, best) if best else None
    return segment if segment is not None else source


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_every_spawn_reaches_console_suppression(path: Path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_spawn_call(node):
            continue
        scope_source = _enclosing_function_source(tree, source, node)
        if "no_console_kwargs" not in scope_source and "creationflags" not in scope_source:
            violations.append(node.lineno)

    assert not violations, (
        f"{path.relative_to(HUB_PACKAGE.parent)}: subprocess spawn(s) at line(s) {violations} "
        "do not reach hub.subprocess_windows.no_console_kwargs() (or an equivalent "
        "creationflags=) anywhere in their enclosing function -- this flashes a real console "
        "window on Windows. Pass **no_console_kwargs() at the call site."
    )


def test_source_files_were_actually_found():
    """A guard on the guard: an empty parametrize list would pass vacuously."""
    assert len(_source_files()) >= 10
