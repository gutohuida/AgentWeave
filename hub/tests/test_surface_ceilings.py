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
UNHANDLED_SITE_CEILING = 100
# Re-measured 2026-09-22, the one exception to "never raise". The 52 of 2026-09-10 was counted
# through a table keyed by line number, and by then 5 of its MISREPORT rows already named lines
# with no call site. Those 5 surfaces had dropped out of the count while still misreporting, and 3
# more followed by 2026-09-21, which read as "dropped to 49" (F396). Keyed by hook and occurrence,
# the same classifications give 55: 49 plus the 6 lost rows whose sites are still live. The other 2
# were real repairs, and their rows were removed.
MISREPORT_CEILING = 55


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
    `n11` classifies by hand, so a site added today lands in UNCLASSIFIED and leaves MISREPORT
    untouched. This count reads no classification at all.
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
    unhandled = n11.unhandled_sites()
    stale = n11.stale_classifications(unhandled)
    assert not stale, (
        f"{len(stale)} row(s) in n11's CLASSIFIED name no unhandled call site: {stale}. A row "
        f"whose site was repaired must be deleted. Otherwise the count below falls with nothing "
        f"reviewed (F396). A row whose hook was renamed must be re-keyed."
    )
    live = n11.operator_reachable_misreports(unhandled)
    _ratchet(len(live), MISREPORT_CEILING, "operator-reachable MISREPORT surfaces")


def test_the_misreport_count_does_not_move_when_lines_do() -> None:
    """F396: an edit above a classified site must not change what the ratchet counts.

    Keyed by line, every row named a number that any edit higher in the file shifted. The row
    then matched nothing, and the site dropped out of the count while still misreporting. This
    shifts every site's line and requires the same count.
    """
    n11 = _load("n11_query_error_surface")
    if not (REPO_ROOT / "hub" / "ui" / "src").is_dir():
        pytest.skip("hub/ui/src is absent; nothing to measure")
    unhandled = n11.unhandled_sites()
    shifted = [{**site, "line": site["line"] + 40} for site in unhandled]
    assert len(n11.operator_reachable_misreports(shifted)) == len(
        n11.operator_reachable_misreports(unhandled)
    )
    assert n11.stale_classifications(shifted) == n11.stale_classifications(unhandled)


def test_a_repaired_site_leaves_its_row_stale_rather_than_uncounted() -> None:
    """The other half of F396: a site that stops being unhandled must be reported, not dropped."""
    n11 = _load("n11_query_error_surface")
    if not (REPO_ROOT / "hub" / "ui" / "src").is_dir():
        pytest.skip("hub/ui/src is absent; nothing to measure")
    unhandled = n11.unhandled_sites()
    repaired = n11.operator_reachable_misreports(unhandled)[0]
    remaining = [site for site in unhandled if site is not repaired]
    assert n11.stale_classifications(remaining) == [n11.site_key(repaired)]
