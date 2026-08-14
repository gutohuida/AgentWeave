"""Copy the built UI into the Hub package and record what it was built from.

`hub/hub/static/ui` is a committed build artefact. Nothing rebuilds it in a source checkout, so it
drifts behind `hub/ui/src` whenever someone edits the UI without recopying — and the Hub's own
`/health` reports that drift.

Before the stamp, that report could not be cleared by doing what it asked. A change that leaves the
bundle byte-identical — types, comments, anything erased before the bundle is produced — gives the
rebuild nothing to commit, so the artefact's commit date never moves and the warning stands
forever. The stamp is what gives an identical rebuild something to commit.

Run it after `npm run build`:

    cd hub/ui && npm run build
    python scripts/refresh_ui_bundle.py        # or: make ui

The stamp is written **after** the copy, so a copy that replaces the directory wholesale cannot
drop it. Only this script writes it: hand-editing it would silence the check while leaving the
bundle stale, which is the failure the check exists to catch.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UI_DIST = REPO_ROOT / "hub" / "ui" / "dist"
UI_SRC = REPO_ROOT / "hub" / "ui" / "src"
STATIC_UI = REPO_ROOT / "hub" / "hub" / "static" / "ui"

sys.path.insert(0, str(REPO_ROOT / "hub"))


def differences(left: Path, right: Path) -> list[str]:
    """Every path that differs between two trees, recursively."""
    found: list[str] = []

    def walk(comparison: filecmp.dircmp, prefix: str) -> None:
        for name in comparison.left_only:
            found.append(f"{prefix}{name} (only in {left.name})")
        for name in comparison.right_only:
            found.append(f"{prefix}{name} (only in {right.name})")
        for name in comparison.diff_files:
            found.append(f"{prefix}{name} (differs)")
        for name, sub in comparison.subdirs.items():
            walk(sub, f"{prefix}{name}/")

    walk(filecmp.dircmp(left, right), "")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed bundle and stamp without writing anything",
    )
    args = parser.parse_args()

    from hub.main import UI_BUILD_STAMP, ui_source_fingerprint  # noqa: E402

    fingerprint = ui_source_fingerprint(UI_SRC)
    if fingerprint is None:
        print("Could not fingerprint hub/ui/src — is this a git checkout?", file=sys.stderr)
        return 1

    if args.check:
        stamp_path = STATIC_UI / UI_BUILD_STAMP.name
        if not stamp_path.exists():
            print(f"No build stamp at {stamp_path}. Run `make ui`.", file=sys.stderr)
            return 1
        recorded = json.loads(stamp_path.read_text(encoding="utf-8")).get("src_fingerprint")
        if recorded != fingerprint:
            print(
                "hub/hub/static/ui was built from different source than is present. "
                "Run `cd hub/ui && npm run build && make ui`.",
                file=sys.stderr,
            )
            return 1
        print("The committed bundle asserts it was built from the current source.")
        return 0

    if not UI_DIST.exists():
        print(f"No build at {UI_DIST}. Run `cd hub/ui && npm run build` first.", file=sys.stderr)
        return 1

    if STATIC_UI.exists():
        shutil.rmtree(STATIC_UI)
    shutil.copytree(UI_DIST, STATIC_UI)

    mismatched = differences(UI_DIST, STATIC_UI)
    if mismatched:
        print("The copy does not match the build:", file=sys.stderr)
        for entry in mismatched:
            print(f"  {entry}", file=sys.stderr)
        return 1

    # After the copy, so replacing the directory wholesale cannot drop it.
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    (STATIC_UI / UI_BUILD_STAMP.name).write_text(
        json.dumps(
            {
                "src_fingerprint": fingerprint,
                "src_commit": head.stdout.strip() or None,
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Refreshed {STATIC_UI.relative_to(REPO_ROOT)} and recorded the build stamp.")
    print("Commit hub/ui/src and hub/hub/static/ui together.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
