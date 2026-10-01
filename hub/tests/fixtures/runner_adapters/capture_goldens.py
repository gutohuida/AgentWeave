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

import asyncio
import dataclasses
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

from hub.conversation_titles import build_title_command
from hub.runner_commands import build_command
from hub.runner_parsing import ParsedLine, parse_claude_line, parse_codex_line
from hub.worker import build_worker_command

FIXTURES_DIR = Path(__file__).parent
OUTPUT_PATH = FIXTURES_DIR / "argv_golden.json"
STREAM_EVENTS_OUTPUT_PATH = FIXTURES_DIR / "stream_events_golden.json"
ONE_SHOT_OUTPUT_PATH = FIXTURES_DIR / "one_shot_golden.json"
RPC_KWARGS_OUTPUT_PATH = FIXTURES_DIR / "rpc_kwargs_golden.json"
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


#: Task 1.4's main cross product, against the default one-axis values below.
RPC_PERMISSION_MODES: List[Optional[str]] = [
    None,
    "acceptEdits",
    "workspace",
    "manual",
    "bypassPermissions",
]


def _rpc_project_id() -> str:
    return "proj-rpc-capture"


def _rpc_env(*, decision_timeout: Optional[str] = None) -> Dict[str, str]:
    env = {"HUB_URL": "http://fake-hub.invalid", "AW_RUN_TOKEN": "tok-distinctive"}
    if decision_timeout is not None:
        env["AW_DECISION_TIMEOUT"] = decision_timeout
    return env


def _rpc_cases() -> List[Dict[str, Any]]:
    """Task 1.4's inputs: the main cross product plus its one-axis variations, each a full set
    of keyword arguments for `_execute_rpc_run(get_adapter("codex"), CodexAppServerTransport(),
    **inputs)` (design D9, task 3.4). `refusal_method` is not one of the
    executor's own parameters -- it tells the capture driver which of `codex_appserver
    ._REFUSAL_LABELS` this case's recorder should additionally invoke `on_refusal` for (task
    1.4's behaviour 2); `None` means the case only exercises behaviours 1/3/4.
    """
    cases: List[Dict[str, Any]] = []

    def _add(case_id: str, *, refusal_method: Optional[str] = None, **overrides: Any) -> None:
        inputs: Dict[str, Any] = {
            "cli": "codex",
            "prompt": f"prompt for {case_id}",
            "model": None,
            "work_dir": f"/fake/workspace/{case_id}",
            "known_session_id": None,
            "yolo": False,
            "mcp_command": None,
            "env": _rpc_env(),
            "worktree": None,
            "repo_root": None,
            "permission_mode": None,
            "config_overrides": None,
        }
        inputs.update(overrides)
        cases.append({"id": case_id, "inputs": inputs, "refusal_method": refusal_method})

    # Main cross product: permission_mode x mcp_command x yolo.
    for pm in RPC_PERMISSION_MODES:
        for mcp in (None, FAKE_MCP_COMMAND):
            for yolo in BOOL_AXIS:
                case_id = f"cross/pm={pm}/mcp={'set' if mcp else 'none'}/yolo={yolo}"
                _add(case_id, permission_mode=pm, mcp_command=mcp, yolo=yolo)

    # One-axis variations off the default case (pm=None, mcp=None, yolo=False).
    _add("axis/known_session_id", known_session_id="thread-x")
    _add("axis/config_overrides", config_overrides={"model_reasoning_effort": "high"})
    _add("axis/model", model="gpt-5.5")
    # The timeout behaviour's "once with, once without" pair: the default case above is the
    # "without" side (no `AW_DECISION_TIMEOUT` in `env`); this is the "with" side.
    _add("axis/decision_timeout", env=_rpc_env(decision_timeout="90"))

    # One case per `codex_appserver._REFUSAL_LABELS` method, off the default inputs, so the
    # refusal-label mapping is checked independent of the main cross product's axes.
    from hub.codex_appserver import _REFUSAL_LABELS

    for method in _REFUSAL_LABELS:
        safe_method = method.replace("/", "-")
        _add(f"refusal/{safe_method}", refusal_method=method)

    return cases


async def _drive_rpc_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Drive one case of task 1.4's RPC golden: seed a Conversation/Run, patch
    `hub.codex_appserver.run_turn`/`_await_operator_permission` with recorders, call
    `_execute_rpc_run(get_adapter("codex"), CodexAppServerTransport(), **inputs)` (design D9's
    adapter/transport shape, task 3.4), and read back what it recorded.
    """
    import hub.api.v1.agent_trigger as agent_trigger
    from hub import codex_appserver
    from hub.codex_appserver import FILE_CHANGE_APPROVAL_METHOD, TurnOutcome
    from hub.db.engine import async_session_factory
    from hub.db.models import Conversation, EventLog, Run
    from hub.runner_adapters import get_adapter
    from hub.runner_adapters.codex import CodexAppServerTransport

    case_id = case["id"]
    slug = case_id.replace("/", "_").replace("=", "-")
    inputs = dict(case["inputs"])
    refusal_method = case["refusal_method"]

    project_id = _rpc_project_id()
    agent = f"rpc-{slug}"
    run_id = f"run-{slug}"
    conversation_id = f"conv-{slug}"

    async with async_session_factory() as db:
        db.add(
            Conversation(id=conversation_id, project_id=project_id, agent=agent, lifecycle="open")
        )
        db.add(Run(id=run_id, project_id=project_id, agent=agent, conversation_id=conversation_id))
        await db.commit()

    permission_calls: List[Dict[str, Any]] = []

    async def _fake_await_operator_permission(**kwargs: Any) -> bool:
        permission_calls.append(
            {
                "method": kwargs["method"],
                "subject": kwargs["subject"],
                "project_id": kwargs["project_id"],
                "agent": kwargs["agent"],
                "run_id": kwargs["run_id"],
                "timeout_seconds": kwargs["timeout_seconds"],
            }
        )
        return True

    broadcasts: List[Dict[str, Any]] = []

    async def _fake_broadcast(project_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        broadcasts.append({"event_type": event_type, "payload": payload})

    captured: Dict[str, Any] = {}

    async def _recorder(**kwargs: Any) -> TurnOutcome:
        captured["data_kwargs"] = {
            "cli": kwargs["cli"],
            "posture": kwargs["posture"],
            "workspace": kwargs["workspace"],
            "cwd": kwargs["cwd"],
            "env": kwargs["env"],
            "prompt": kwargs["prompt"],
            "model": kwargs["model"],
            "resume_thread_id": kwargs["resume_thread_id"],
            "yolo": kwargs["yolo"],
            "mcp_command": kwargs["mcp_command"],
            "config_overrides": kwargs["config_overrides"],
        }

        should_interrupt = kwargs["should_interrupt"]
        before = should_interrupt()
        agent_trigger._stop_requested.add(run_id)
        after = should_interrupt()
        agent_trigger._stop_requested.discard(run_id)
        captured["should_interrupt"] = {"before": before, "after": after}

        thread_id = f"thread-{slug}"
        await kwargs["on_thread_started"](thread_id)
        captured["thread_id"] = thread_id

        subject = {
            "cwd": f"{inputs['work_dir']}/nested",
            "paths": [f"{inputs['work_dir']}/nested/file.py"],
        }
        await kwargs["request_approval"](FILE_CHANGE_APPROVAL_METHOD, subject)

        if refusal_method is not None:
            await kwargs["on_refusal"](
                refusal_method,
                {"reason": "captured", "paths": [f"{inputs['work_dir']}/refused.py"]},
            )

        return TurnOutcome(thread_id=thread_id, status="completed")

    with patch.object(codex_appserver, "run_turn", AsyncMock(side_effect=_recorder)):
        with patch.object(
            agent_trigger,
            "_await_operator_permission",
            AsyncMock(side_effect=_fake_await_operator_permission),
        ):
            with patch.object(
                agent_trigger.sse_manager, "broadcast", AsyncMock(side_effect=_fake_broadcast)
            ):
                await agent_trigger._execute_rpc_run(
                    get_adapter("codex"),
                    CodexAppServerTransport(),
                    project_id=project_id,
                    agent=agent,
                    run_id=run_id,
                    conversation_id=conversation_id,
                    **inputs,
                )

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        run_session_id_after = run.session_id if run else None

    refusal_result: Optional[Dict[str, Any]] = None
    if refusal_method is not None:
        async with async_session_factory() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(EventLog)
                .where(EventLog.event_type == "permission_denied", EventLog.agent == agent)
                .order_by(EventLog.timestamp.desc())
            )
            row = result.scalars().first()
            persisted_tool_name = (row.data or {}).get("tool_name") if row else None
        broadcast_tool_name = next(
            (
                b["payload"].get("tool_name")
                for b in broadcasts
                if b["event_type"] == "permission_denied"
            ),
            None,
        )
        refusal_result = {
            "method": refusal_method,
            "persisted_tool_name": persisted_tool_name,
            "broadcast_tool_name": broadcast_tool_name,
        }

    return {
        "id": case_id,
        "input": inputs,
        "codex_run_turn_kwargs": captured["data_kwargs"],
        "request_approval": permission_calls[0] if permission_calls else None,
        "should_interrupt": captured["should_interrupt"],
        "bound_thread_id": captured["thread_id"],
        "run_session_id_after": run_session_id_after,
        "refusal": refusal_result,
    }


async def _build_rpc_kwargs_cases_async() -> List[Dict[str, Any]]:
    import hub.api.v1.agent_trigger  # noqa: F401 -- triggers the DATABASE_URL-requiring import chain early
    from hub.db.engine import engine
    from hub.db.models import Base, Project

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from hub.db.engine import async_session_factory

    async with async_session_factory() as db:
        db.add(Project(id=_rpc_project_id(), name="RPC capture (task 1.4)"))
        await db.commit()

    results = []
    for case in _rpc_cases():
        results.append(await _drive_rpc_case(case))
    return results


def build_rpc_kwargs_cases() -> List[Dict[str, Any]]:
    """Task 1.4's capture half: drive `_execute_rpc_run` for every case and record what reaches
    `codex_appserver.run_turn`, plus the four behaviours the design names. Needs
    `DATABASE_URL` in the environment (set for this run only -- see task 1.3's own note above),
    pointed at a throwaway sqlite file, since this drives the real executor end to end.
    """
    return asyncio.run(_build_rpc_kwargs_cases_async())


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

    rpc_kwargs_cases = build_rpc_kwargs_cases()
    RPC_KWARGS_OUTPUT_PATH.write_text(
        json.dumps(rpc_kwargs_cases, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rpc_kwargs_cases)} cases to {RPC_KWARGS_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
