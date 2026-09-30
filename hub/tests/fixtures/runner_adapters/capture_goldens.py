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

import dataclasses
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from hub.conversation_titles import build_title_command
from hub.runner_commands import build_command
from hub.runner_parsing import ParsedLine, parse_claude_line, parse_codex_line
from hub.worker import build_worker_command

FIXTURES_DIR = Path(__file__).parent
OUTPUT_PATH = FIXTURES_DIR / "argv_golden.json"
STREAM_EVENTS_OUTPUT_PATH = FIXTURES_DIR / "stream_events_golden.json"
ONE_SHOT_OUTPUT_PATH = FIXTURES_DIR / "one_shot_golden.json"
CLAUDE_STREAM_JSONL = FIXTURES_DIR / "claude_stream.jsonl"
CODEX_EXEC_JSONL = FIXTURES_DIR / "codex_exec.jsonl"

# Task 1.3: a prompt with an `@` -- `one_shot` neutralises the raw prompt itself (design D3), so
# a prompt without one would pass this golden whether or not that neutralisation runs.
ONE_SHOT_PROMPT = "please check @notes.md for context"
ONE_SHOT_MODELS: List[Optional[str]] = [None, "test-model-x"]
ONE_SHOT_SCHEMAS: List[Optional[str]] = [None, "<SCHEMA>"]

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


def _sample_to_dict(sample: Any) -> Optional[Dict[str, Any]]:
    if sample is None:
        return None
    data = dataclasses.asdict(sample)
    # `ContextUsageSample.observed_at` defaults to `time.time()` at construction -- wall-clock,
    # not part of what parsing derives from the line, so it would make the golden unreproducible.
    data.pop("observed_at", None)
    return data


def _parsed_line_to_dict(parsed: ParsedLine) -> Dict[str, Any]:
    return {
        "events": [
            {"kind": event.kind, "content": event.content, "payload": event.payload}
            for event in parsed.events
        ],
        "usage": _sample_to_dict(parsed.usage),
        "accounting": _sample_to_dict(parsed.accounting),
        "session_id": parsed.session_id,
    }


def build_stream_events_cases() -> List[Dict[str, Any]]:
    """Task 1.3: `parse_claude_line` over `claude_stream.jsonl`, `parse_codex_line(model=
    "gpt-5.5")` over `codex_exec.jsonl` -- both files copy the JSONL lines inlined in
    `test_runner_parsing.py`, in their file order."""
    cases: List[Dict[str, Any]] = []

    claude_lines = CLAUDE_STREAM_JSONL.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(claude_lines):
        parsed = parse_claude_line(line)
        cases.append(
            {
                "id": f"claude/line-{index}",
                "runner": "claude",
                "line_index": index,
                **_parsed_line_to_dict(parsed),
            }
        )

    codex_lines = CODEX_EXEC_JSONL.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(codex_lines):
        parsed = parse_codex_line(line, model="gpt-5.5")
        cases.append(
            {
                "id": f"codex/line-{index}",
                "runner": "codex",
                "line_index": index,
                **_parsed_line_to_dict(parsed),
            }
        )

    return cases


def build_one_shot_cases() -> List[Dict[str, Any]]:
    """Task 1.3: worker argv per CLI x {model, None} x {schema path, None}, and title argv per
    CLI x {model, None} (review 8.3: `build_title_command` takes no schema)."""
    cases: List[Dict[str, Any]] = []

    for runner in RUNNERS:
        cli = CLI_BY_RUNNER[runner]
        for model in ONE_SHOT_MODELS:
            for schema in ONE_SHOT_SCHEMAS:
                argv = build_worker_command(
                    cli=cli, model=model, prompt=ONE_SHOT_PROMPT, output_schema_path=schema
                )
                cases.append(
                    {
                        "id": f"{cli}/worker/model={model}/schema={schema}",
                        "kind": "worker",
                        "input": {
                            "cli": cli,
                            "model": model,
                            "prompt": ONE_SHOT_PROMPT,
                            "output_schema_path": schema,
                        },
                        "argv": argv,
                    }
                )
        for model in ONE_SHOT_MODELS:
            argv = build_title_command(cli=cli, model=model, prompt=ONE_SHOT_PROMPT)
            cases.append(
                {
                    "id": f"{cli}/title/model={model}",
                    "kind": "title",
                    "input": {"cli": cli, "model": model, "prompt": ONE_SHOT_PROMPT},
                    "argv": argv,
                }
            )

    return cases


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        context_paths = _context_paths(Path(tmp))
        cases = build_golden_cases(context_paths)

    OUTPUT_PATH.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases to {OUTPUT_PATH}")

    stream_events_cases = build_stream_events_cases()
    STREAM_EVENTS_OUTPUT_PATH.write_text(
        json.dumps(stream_events_cases, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(stream_events_cases)} cases to {STREAM_EVENTS_OUTPUT_PATH}")

    one_shot_cases = build_one_shot_cases()
    ONE_SHOT_OUTPUT_PATH.write_text(json.dumps(one_shot_cases, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(one_shot_cases)} cases to {ONE_SHOT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
