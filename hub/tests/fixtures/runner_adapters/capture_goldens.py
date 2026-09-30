"""Capture today's `build_command` argv into `argv_golden.json` (task 1.1).

Run from the repo root: `py -3.11 hub/tests/fixtures/runner_adapters/capture_goldens.py`.
This script must be run, and its output committed, *before* group 2 of
`openspec/changes/each-runner-cli-is-one-adapter/tasks.md` edits any of the code it imports —
the golden is only meaningful as a snapshot of pre-change behaviour. Never `git stash` /
`git checkout --` the working tree while capturing (DEAD-ENDS 2026-09-27); this script only
reads the code, so it is safe to run against a dirty tree.

Every case's `context_file` path (when the "present" case is exercised) is a real temp file, so
`_build_claude_command`'s / `_build_codex_command`'s own `.exists()` check takes the branch the
case means to probe; the resulting argv is then normalised so that path reads literally `<CTX>`,
since a machine-specific temp path in the committed JSON would make the golden non-portable
(the same reason a fixed fake `mcp_command` — literally `["<PY>", "<SERVER>"]` — is used as
*input*, rather than a real interpreter/server path normalised after the fact: the real
`--mcp-config` JSON embeds it, so only a fake input value keeps the file CI-portable, per
tasks.md 1.1).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from hub.runner_commands import build_command

FIXTURES_DIR = Path(__file__).parent
OUTPUT_PATH = FIXTURES_DIR / "argv_golden.json"

FAKE_MCP_COMMAND = ["<PY>", "<SERVER>"]
RUNNERS = ("claude", "codex")
CLI_BY_RUNNER = {"claude": "claude", "codex": "codex"}

# `permission_mode` axis for the main cross product. `None` means "no override" (today's code
# falls back to `posture_at_rest`); the other four are every value the catalog declares for
# either provider (model_catalog.py PERMISSION_MODE_CONTROL).
PERMISSION_MODES: List[Optional[str]] = [
    None,
    "acceptEdits",
    "workspace",
    "manual",
    "bypassPermissions",
]

BOOL_AXIS = (False, True)


def _context_paths(tmp_dir: Path) -> Dict[str, Path]:
    present = tmp_dir / "present-context.md"
    present.write_text("context", encoding="utf-8")
    missing = tmp_dir / "missing-context.md"  # never created
    return {"present": present, "missing": missing}


def _control_overrides(
    permission_mode: Optional[str], *, effort: Optional[str] = None
) -> Optional[Dict[str, str]]:
    overrides: Dict[str, str] = {}
    if permission_mode is not None:
        overrides["permission_mode"] = permission_mode
    if effort is not None:
        overrides["effort"] = effort
    return overrides or None


def _case(
    case_id: str,
    *,
    runner: str,
    context_path: Path,
    prompt: str = "hello world",
    model: Optional[str] = None,
    session_id: Optional[str] = None,
    yolo: bool = False,
    mcp_command: Optional[List[str]] = None,
    extra_flags: Optional[List[str]] = None,
    control_overrides: Optional[Dict[str, str]] = None,
    restrict_spec_writes: bool = False,
) -> Dict[str, Any]:
    cli = CLI_BY_RUNNER[runner]
    argv = build_command(
        runner=runner,
        cli=cli,
        prompt=prompt,
        model=model,
        context_file=context_path,
        session_id=session_id,
        yolo=yolo,
        mcp_command=mcp_command,
        extra_flags=extra_flags,
        control_overrides=control_overrides,
        restrict_spec_writes=restrict_spec_writes,
    )
    normalised = [arg.replace(str(context_path), "<CTX>") for arg in argv]
    return {
        "id": case_id,
        "input": {
            "runner": runner,
            "cli": cli,
            "prompt": prompt,
            "model": model,
            "context_file": "present" if context_path.exists() else "missing",
            "session_id": session_id,
            "yolo": yolo,
            "mcp_command": mcp_command,
            "extra_flags": extra_flags,
            "control_overrides": control_overrides,
            "restrict_spec_writes": restrict_spec_writes,
        },
        "argv": normalised,
    }


def build_golden_cases(context_paths: Dict[str, Path]) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    missing = context_paths["missing"]
    present = context_paths["present"]

    for runner in RUNNERS:
        # Main cross product: permission_mode x mcp_command x yolo x restrict_spec_writes,
        # against a missing context file (the common case for a fresh turn).
        for pm in PERMISSION_MODES:
            for mcp in (None, FAKE_MCP_COMMAND):
                for yolo in BOOL_AXIS:
                    for restrict in BOOL_AXIS:
                        case_id = (
                            f"{runner}/cross/pm={pm}/mcp={'set' if mcp else 'none'}/"
                            f"yolo={yolo}/restrict={restrict}"
                        )
                        cases.append(
                            _case(
                                case_id,
                                runner=runner,
                                context_path=missing,
                                yolo=yolo,
                                mcp_command=mcp,
                                control_overrides=_control_overrides(pm),
                                restrict_spec_writes=restrict,
                            )
                        )

        # One-axis variations off the all-default case (pm=None, mcp=None, yolo=False,
        # restrict=False, context missing).
        cases.append(
            _case(
                f"{runner}/axis/model",
                runner=runner,
                context_path=missing,
                model="test-model-x",
            )
        )
        cases.append(
            _case(
                f"{runner}/axis/session_id",
                runner=runner,
                context_path=missing,
                session_id="session-abc-123",
            )
        )
        cases.append(
            _case(
                f"{runner}/axis/context_present",
                runner=runner,
                context_path=present,
            )
        )
        cases.append(
            _case(
                f"{runner}/axis/extra_flags",
                runner=runner,
                context_path=missing,
                extra_flags=["--some-extra-flag", "value"],
            )
        )
        cases.append(
            _case(
                f"{runner}/axis/effort",
                runner=runner,
                context_path=missing,
                control_overrides=_control_overrides(None, effort="high"),
            )
        )

        # Review 8: extra_flags=["--no-app-server"] specifically (the trigger strips it before
        # calling build_command today; this records what build_command itself does if given it).
        cases.append(
            _case(
                f"{runner}/no-app-server",
                runner=runner,
                context_path=missing,
                extra_flags=["--no-app-server"],
            )
        )

        # D6: mcp_command=[] is falsy, same as None (no tool server, no approver flag).
        cases.append(
            _case(
                f"{runner}/mcp-empty-list",
                runner=runner,
                context_path=missing,
                mcp_command=[],
            )
        )

        # Review 8: effort crossed with each permission_mode (pins the order control_args are
        # spliced relative to the permission-mode flag).
        for pm in PERMISSION_MODES:
            case_id = f"{runner}/effort-x-pm/pm={pm}"
            cases.append(
                _case(
                    case_id,
                    runner=runner,
                    context_path=missing,
                    control_overrides=_control_overrides(pm, effort="high"),
                )
            )

    return cases


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        context_paths = _context_paths(Path(tmp))
        cases = build_golden_cases(context_paths)

    OUTPUT_PATH.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
