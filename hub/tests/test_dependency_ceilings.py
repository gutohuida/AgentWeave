"""The third ratchet from `DECISIONS.md` R-1: a dependency ceiling may not be added to.

Two pins in this repository exist to make a major-version crossing conscious rather than silent
-- `fastmcp>=2.0,<4` and `starlette<2.0`, both taken after a crossing happened on a green board
with nobody told. A ceiling is only worth the line it is written on while every declaration of
that dependency carries it, so what is frozen here is the *number of places* it is declared.

`test_fastmcp_api_contract.py::test_the_pin_is_bounded_and_agrees_everywhere` already asserts the
three fastmcp declarations agree and are bounded -- this does not restate that. It closes the gap
that test cannot see: `_fastmcp_specifiers()` reads three *named* keys, one requirement each, so a
fourth declaration in a new optional-dependency group is invisible to it and would ship
unbounded. This file sweeps every dependency list in both `pyproject.toml` files instead.

Measured 2026-09-10: three fastmcp declarations, one starlette. Lower a ceiling when a
declaration goes away; never raise one.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_PYPROJECT = REPO_ROOT / "pyproject.toml"
HUB_PYPROJECT = REPO_ROOT / "hub" / "pyproject.toml"

FASTMCP_DECLARATION_CEILING = 3
STARLETTE_DECLARATION_CEILING = 1


def _requirement_name(requirement: str) -> str:
    """`uvicorn[standard]>=0.27` -> `uvicorn`; `pywinpty>=2.0; sys_platform == 'win32'` -> `pywinpty`."""
    head = requirement.split(";")[0].strip()
    for separator in ("[", "<", ">", "=", "!", "~", " "):
        head = head.split(separator)[0]
    return head.strip().lower().replace("_", "-")


def _declarations(name: str) -> list[tuple[str, str]]:
    """Every declaration of `name` across both pyproject files, as (where, requirement).

    Sweeps `[project] dependencies` and every group of `[project] optional-dependencies` in both
    files, so a declaration added to a new group is counted rather than missed.
    """
    found: list[tuple[str, str]] = []
    for label, path in (("pyproject.toml", CLI_PYPROJECT), ("hub/pyproject.toml", HUB_PYPROJECT)):
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        lists: dict[str, list[str]] = {"dependencies": project.get("dependencies", [])}
        for group, requirements in project.get("optional-dependencies", {}).items():
            lists[f"[{group}]"] = requirements
        for where, requirements in lists.items():
            for requirement in requirements:
                if _requirement_name(requirement) == name:
                    found.append((f"{label} {where}", requirement))
    return found


@pytest.mark.skipif(
    not CLI_PYPROJECT.exists(),
    reason="hub/ checked out without the CLI package alongside it",
)
@pytest.mark.parametrize(
    ("name", "ceiling", "bound"),
    [
        ("fastmcp", FASTMCP_DECLARATION_CEILING, "<4"),
        ("starlette", STARLETTE_DECLARATION_CEILING, "<2.0"),
    ],
)
def test_a_bounded_dependency_gains_no_unbounded_twin(name: str, ceiling: int, bound: str) -> None:
    """No new declaration of a ceilinged dependency, and every one of them carries the ceiling."""
    declarations = _declarations(name)
    assert len(declarations) <= ceiling, (
        f"{name} is now declared in {len(declarations)} places, ceiling {ceiling}: "
        f"{declarations}.\nA ceiling holds only where it is written. Add the bound to the new "
        f"declaration and raise this number in the same commit, or drop the declaration."
    )
    unbounded = [where for where, requirement in declarations if bound not in requirement]
    assert not unbounded, (
        f"{name} is declared without its {bound} ceiling in: {unbounded}. Unbounded is how this "
        f"repository crossed a major version in CI with nobody told."
    )
