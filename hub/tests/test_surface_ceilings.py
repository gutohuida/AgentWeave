"""Ratchets for the two measured surfaces in `DECISIONS.md` R-1.

R-1, quoted: *"the repo writes a check, and the check freezes today's count as a ceiling that may
shrink and may never grow."* And, load-bearing: *"Existing instances are not repaired before the
check may pass."* So these tests assert `<=`, never `==`, and nothing here fixes a single one of
the routes or call sites it counts.

The measurements themselves already exist as reports under `scripts/drive/`. Each is loaded by
path and its own functions are called, in the manner of `tests/test_skill_sync.py`, so the gate
counts what the report prints instead of restating the classification and drifting from it.

**Skip-when-absent, on purpose.** `n10` reaches the route table by importing `hub.main` in a
subprocess; on a checkout where that import cannot resolve, the honest result is "not measured",
not "red". A permanently red gate is one nobody reads.

The ceilings below were measured on 2026-09-10 by running both scripts. They are **not** copied
from any earlier note: the route total had already moved 187 -> 188 and the MISREPORT count
51 -> 52 since those numbers were first written down.
"""

from __future__ import annotations

import importlib.util
import warnings
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVE = REPO_ROOT / "scripts" / "drive"

# Measured 2026-09-10. Lower these when the count drops; never raise one.
CLIENTLESS_ROUTE_CEILING = 35
MISREPORT_CEILING = 52
UNHANDLED_SITE_CEILING = 100


def _load(name: str) -> ModuleType:
    """Import a `scripts/drive/` report by path -- `scripts/` is not a package."""
    path = DRIVE / f"{name}.py"
    if not path.exists():
        pytest.skip(f"{path.relative_to(REPO_ROOT).as_posix()} is absent; nothing to measure")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ratchet(count: int, ceiling: int, subject: str) -> None:
    """Fail when the count grew; say so when it shrank, so the ceiling can be tightened."""
    assert count <= ceiling, (
        f"{subject}: {count}, ceiling {ceiling}.\n"
        f"This is a ratchet -- R-1 froze today's count as a number that may shrink and may "
        f"never grow. Something new was added to this surface. Reach it from a client (or "
        f"handle its error) rather than raising the ceiling."
    )
    if count < ceiling:
        warnings.warn(
            f"{subject} dropped to {count} from a ceiling of {ceiling}. Lower the constant in "
            f"{Path(__file__).name} so the ratchet holds the new floor.",
            stacklevel=2,
        )


def test_no_new_route_without_a_client() -> None:
    """No route may join the set that no client anywhere in the repo calls."""
    n10 = _load("n10_route_reachability")
    try:
        rows = n10.route_rows()
    except SystemExit as exc:  # declared_routes() could not import the Hub app
        pytest.skip(f"the Hub route table is not readable here: {exc}")
    orphans = n10.clientless_routes(rows)
    _ratchet(len(orphans), CLIENTLESS_ROUTE_CEILING, "routes with no client anywhere")


def test_no_new_query_call_site_ignores_its_error() -> None:
    """No call site may join the set that never binds and uses its query's error.

    This is the assertion that catches a *new* offender. The MISREPORT ceiling below cannot:
    `n11` classifies by hand, keyed by file and line, so a site added today lands in
    UNCLASSIFIED and leaves MISREPORT untouched. This count reads no classification at all,
    which also makes it immune to the line shifts that silently re-key that table.
    """
    n11 = _load("n11_query_error_surface")
    if not (REPO_ROOT / "hub" / "ui" / "src").is_dir():
        pytest.skip("hub/ui/src is absent; nothing to measure")
    unhandled = n11.unhandled_sites()
    _ratchet(len(unhandled), UNHANDLED_SITE_CEILING, "query call sites that ignore their error")


def test_no_new_misreporting_surface() -> None:
    """No surface may join the set that shows an operator something false on a failed query.

    Growth here means a hand classification was added or worsened -- which is exactly how this
    number moves, since `n11.RENDERS` is where a site becomes MISREPORT rather than UNCLASSIFIED.
    """
    n11 = _load("n11_query_error_surface")
    if not (REPO_ROOT / "hub" / "ui" / "src").is_dir():
        pytest.skip("hub/ui/src is absent; nothing to measure")
    live = n11.operator_reachable_misreports(n11.unhandled_sites())
    _ratchet(len(live), MISREPORT_CEILING, "operator-reachable MISREPORT surfaces")
