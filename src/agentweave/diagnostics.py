"""Runtime readiness diagnostics for AgentWeave.

These helpers intentionally use only the Python standard library so they can be
used by the zero-dependency CLI, watchdog, and tests.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .constants import (
    AGENT_CONTEXT_DIR,
    RUNNER_CONFIGS,
    SESSION_FILE,
    TRANSPORT_CONFIG_FILE,
    WATCHDOG_HEARTBEAT_FILE,
    WATCHDOG_PID_FILE,
)

SECRET_FIELD_RE = re.compile(r"(api[_-]?key|token|secret|password|authorization)", re.I)
SECRET_VALUE_RE = re.compile(r"(aw_live_[A-Za-z0-9_=-]+|sk-[A-Za-z0-9_=-]+|[A-Za-z0-9_=-]{32,})")

STATUS_ORDER = {"pass": 0, "warn": 1, "fail": 2}


@dataclass
class DiagnosticResult:
    """One runtime readiness check result."""

    id: str
    target: str
    status: str
    severity: str
    message: str
    hint: str | None = None
    category: str = "runtime"
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if result["hint"] is None:
            result.pop("hint")
        if result["data"] is None:
            result.pop("data")
        else:
            result["data"] = redact_secrets(result["data"])
        return result


def ok(
    check_id: str,
    target: str,
    message: str,
    *,
    category: str = "runtime",
    data: dict[str, Any] | None = None,
) -> DiagnosticResult:
    return DiagnosticResult(check_id, target, "pass", "info", message, category=category, data=data)


def warn(
    check_id: str,
    target: str,
    message: str,
    *,
    hint: str | None = None,
    category: str = "runtime",
    data: dict[str, Any] | None = None,
) -> DiagnosticResult:
    return DiagnosticResult(
        check_id, target, "warn", "warn", message, hint=hint, category=category, data=data
    )


def fail(
    check_id: str,
    target: str,
    message: str,
    *,
    hint: str | None = None,
    category: str = "runtime",
    data: dict[str, Any] | None = None,
) -> DiagnosticResult:
    return DiagnosticResult(
        check_id, target, "fail", "error", message, hint=hint, category=category, data=data
    )


def redact_secrets(value: Any) -> Any:
    """Return a copy of value with obvious secret fields and values redacted."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_FIELD_RE.search(str(key)):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, str):
        return SECRET_VALUE_RE.sub("<redacted>", value)
    return value


def _load_json_raw(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return None, "not a JSON object"
        return data, None
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)


def check_session() -> list[DiagnosticResult]:
    data, error = _load_json_raw(SESSION_FILE)
    if error == "missing":
        return [
            fail(
                "session_missing",
                "session",
                "No AgentWeave session found.",
                hint="Run agentweave init or agentweave activate.",
                category="session",
            )
        ]
    if error:
        return [
            fail(
                "session_invalid",
                "session",
                f"Could not parse {SESSION_FILE}: {error}",
                hint="Repair or regenerate .agentweave/session.json.",
                category="session",
            )
        ]
    agent_count = len((data or {}).get("agents", {}))
    return [
        ok(
            "session_present",
            "session",
            f"Session is present with {agent_count} configured agent(s).",
            category="session",
            data={"agent_count": agent_count},
        )
    ]


def check_project_config() -> list[DiagnosticResult]:
    try:
        from .config import AGENTWEAVE_YML_PATH, ConfigValidationError, load_agentweave_yml

        if not AGENTWEAVE_YML_PATH.exists():
            return [
                warn(
                    "config_missing",
                    "agentweave.yml",
                    "agentweave.yml is missing.",
                    hint="Run agentweave init to create a declarative config.",
                    category="config",
                )
            ]
        config = load_agentweave_yml()
        return [
            ok(
                "config_valid",
                "agentweave.yml",
                f"agentweave.yml is valid with {len(config.agents)} agent(s).",
                category="config",
                data={"agents": sorted(config.agents.keys())},
            )
        ]
    except ConfigValidationError as exc:
        return [
            fail(
                "config_invalid",
                "agentweave.yml",
                f"agentweave.yml is invalid: {exc}",
                hint="Fix the configuration error and rerun agentweave activate.",
                category="config",
            )
        ]
    except ImportError as exc:
        return [
            warn(
                "config_yaml_unavailable",
                "agentweave.yml",
                str(exc),
                hint="Install the mcp/all extra if you want agentweave.yml support.",
                category="config",
            )
        ]


def _http_status_check(config: dict[str, Any]) -> DiagnosticResult:
    url = str(config.get("url", "")).rstrip("/")
    api_key = str(config.get("api_key", ""))
    project_id = str(config.get("project_id", ""))
    if not url:
        return fail(
            "transport_http_url_missing",
            "transport",
            "HTTP transport is missing its Hub URL.",
            hint="Run agentweave transport setup --type http.",
            category="transport",
        )
    if not api_key:
        return fail(
            "transport_http_api_key_missing",
            "transport",
            "HTTP transport is missing its API key.",
            hint="Run agentweave transport setup --type http or agentweave activate.",
            category="transport",
        )
    if not project_id:
        return warn(
            "transport_http_project_missing",
            "transport",
            "HTTP transport has no project_id.",
            hint="Refresh transport configuration with agentweave activate.",
            category="transport",
        )

    status_url = f"{url}/api/v1/status?project_id={project_id}"
    req = urllib.request.Request(status_url, method="GET")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            response.read()
        return ok(
            "transport_http_reachable",
            "transport",
            f"Hub is reachable at {url}.",
            category="transport",
            data={"url": url, "project_id": project_id},
        )
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return fail(
                "hub_auth_failed",
                "transport",
                f"Hub rejected the configured API key with HTTP {exc.code}.",
                hint="Refresh the transport API key with agentweave activate.",
                category="transport",
            )
        if exc.code == 404:
            return fail(
                "hub_project_missing",
                "transport",
                "Hub status endpoint or project was not found.",
                hint="Confirm the Hub URL and project_id in .agentweave/transport.json.",
                category="transport",
            )
        return fail(
            "transport_http_error",
            "transport",
            f"Hub returned HTTP {exc.code}.",
            hint="Check Hub logs and transport configuration.",
            category="transport",
        )
    except urllib.error.URLError as exc:
        return fail(
            "hub_unreachable",
            "transport",
            f"Hub is unreachable: {exc.reason}",
            hint="Start the Hub or update .agentweave/transport.json.",
            category="transport",
        )
    except TimeoutError:
        return fail(
            "hub_timeout",
            "transport",
            "Timed out while checking Hub status.",
            hint="Check that the Hub is running and reachable.",
            category="transport",
        )


def check_transport() -> list[DiagnosticResult]:
    config, error = _load_json_raw(TRANSPORT_CONFIG_FILE)
    if error == "missing":
        return [
            ok(
                "transport_local",
                "transport",
                "No transport.json found; local filesystem transport is active.",
                category="transport",
            )
        ]
    if error:
        return [
            fail(
                "transport_config_invalid",
                "transport",
                f"Could not parse {TRANSPORT_CONFIG_FILE}: {error}",
                hint="Regenerate transport config with agentweave transport setup.",
                category="transport",
            )
        ]
    transport_type = str((config or {}).get("type", "local"))
    if transport_type == "http":
        return [
            ok(
                "transport_http_configured",
                "transport",
                "HTTP transport is configured.",
                category="transport",
                data={
                    "url": (config or {}).get("url"),
                    "project_id": (config or {}).get("project_id"),
                },
            ),
            _http_status_check(config or {}),
        ]
    if transport_type == "git":
        return [
            ok(
                "transport_git_configured",
                "transport",
                "Git transport is configured.",
                category="transport",
            )
        ]
    return [
        ok(
            "transport_local",
            "transport",
            f"Transport type is {transport_type}.",
            category="transport",
        )
    ]


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def check_watchdog(stale_after_seconds: int = 120) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []
    if not WATCHDOG_PID_FILE.exists():
        results.append(
            warn(
                "watchdog_pid_missing",
                "watchdog",
                "No watchdog PID file found.",
                hint="Run agentweave start to enable automatic agent execution.",
                category="watchdog",
            )
        )
    else:
        try:
            pid = int(WATCHDOG_PID_FILE.read_text(encoding="utf-8").strip())
            if _process_exists(pid):
                results.append(
                    ok(
                        "watchdog_process_running",
                        "watchdog",
                        f"Watchdog process is running with PID {pid}.",
                        category="watchdog",
                        data={"pid": pid},
                    )
                )
            else:
                results.append(
                    warn(
                        "watchdog_process_stale",
                        "watchdog",
                        f"Watchdog PID file points at a non-running process ({pid}).",
                        hint="Run agentweave start to refresh the watchdog.",
                        category="watchdog",
                        data={"pid": pid},
                    )
                )
        except (OSError, ValueError) as exc:
            results.append(
                warn(
                    "watchdog_pid_invalid",
                    "watchdog",
                    f"Could not read watchdog PID: {exc}",
                    hint="Run agentweave start to recreate the PID file.",
                    category="watchdog",
                )
            )

    if not WATCHDOG_HEARTBEAT_FILE.exists():
        results.append(
            warn(
                "watchdog_heartbeat_missing",
                "watchdog",
                "No watchdog heartbeat has been recorded.",
                hint="Start or restart the watchdog.",
                category="watchdog",
            )
        )
        return results
    try:
        raw_ts = WATCHDOG_HEARTBEAT_FILE.read_text(encoding="utf-8").strip()
        heartbeat_at = datetime.fromisoformat(raw_ts)
        age = (datetime.now(heartbeat_at.tzinfo) - heartbeat_at).total_seconds()
        if age > stale_after_seconds:
            results.append(
                warn(
                    "watchdog_heartbeat_stale",
                    "watchdog",
                    f"Watchdog heartbeat is stale ({int(age)}s old).",
                    hint="Restart the watchdog if automatic execution is not working.",
                    category="watchdog",
                    data={"age_seconds": int(age)},
                )
            )
        else:
            results.append(
                ok(
                    "watchdog_heartbeat_fresh",
                    "watchdog",
                    f"Watchdog heartbeat is fresh ({int(age)}s old).",
                    category="watchdog",
                    data={"age_seconds": int(age)},
                )
            )
    except (OSError, ValueError) as exc:
        results.append(
            warn(
                "watchdog_heartbeat_invalid",
                "watchdog",
                f"Could not parse watchdog heartbeat: {exc}",
                hint="Restart the watchdog to refresh heartbeat state.",
                category="watchdog",
            )
        )
    return results


def _runner_cli(agent: str, runner: str) -> str | None:
    if runner == "manual":
        return None
    config = RUNNER_CONFIGS.get(runner, RUNNER_CONFIGS["native"])
    cli = config.get("cli") or agent
    return str(cli) if cli else None


def check_agent_readiness(agent: str, session: Any | None = None) -> list[DiagnosticResult]:
    if session is None:
        from .session import Session

        session = Session.load()
    if session is None:
        return [
            fail(
                "session_missing",
                agent,
                "Cannot check agent readiness because no session is loaded.",
                hint="Run agentweave init or agentweave activate.",
                category="agent",
            )
        ]
    if agent not in session.agent_names:
        return [
            fail(
                "agent_missing",
                agent,
                f"Agent {agent!r} is not in the current session.",
                category="agent",
            )
        ]

    results: list[DiagnosticResult] = []
    runner_config = session.get_runner_config(agent)
    runner = runner_config.get("runner", "native")
    model = runner_config.get("model")
    results.append(
        ok(
            "agent_runner_configured",
            agent,
            f"Agent uses runner {runner!r}.",
            category="agent",
            data={"runner": runner, "model": model},
        )
    )

    if session.get_agent_pilot(agent):
        results.append(
            warn(
                "agent_pilot_mode",
                agent,
                "Agent is in pilot mode; automatic execution is disabled.",
                hint="Disable pilot mode if watchdog execution is expected.",
                category="agent",
            )
        )
    if runner == "manual":
        results.append(
            warn(
                "agent_manual_runner",
                agent,
                "Agent uses the manual runner; automatic CLI execution is unavailable.",
                hint="Use relay/manual handling or configure a runnable agent runner.",
                category="agent",
            )
        )
    cli = _runner_cli(agent, runner)
    if cli:
        if shutil.which(cli):
            results.append(
                ok(
                    "agent_cli_available",
                    agent,
                    f"Runner CLI {cli!r} is available.",
                    category="runner",
                    data={"cli": cli},
                )
            )
        else:
            results.append(
                fail(
                    "agent_cli_missing",
                    agent,
                    f"Runner CLI {cli!r} was not found in PATH.",
                    hint=f"Install {cli} or update the runner for {agent}.",
                    category="runner",
                    data={"cli": cli},
                )
            )

    context_path = AGENT_CONTEXT_DIR / f"{agent}.md"
    if context_path.exists():
        results.append(
            ok(
                "agent_context_present",
                agent,
                f"Agent context file exists at {context_path}.",
                category="context",
            )
        )
    else:
        results.append(
            warn(
                "agent_context_missing",
                agent,
                f"Agent context file is missing at {context_path}.",
                hint=f"Run agentweave sync-context --agent {agent}.",
                category="context",
            )
        )

    if runner == "claude_proxy":
        env_vars = runner_config.get("env_vars", {})
        api_key_var = env_vars.get("ANTHROPIC_API_KEY_VAR")
        base_url = env_vars.get("ANTHROPIC_BASE_URL")
        if not base_url:
            results.append(
                fail(
                    "proxy_base_url_missing",
                    agent,
                    "Proxy runner is missing ANTHROPIC_BASE_URL.",
                    hint="Reconfigure the agent with agentweave agent configure.",
                    category="proxy",
                )
            )
        if not api_key_var:
            results.append(
                fail(
                    "proxy_api_key_var_missing",
                    agent,
                    "Proxy runner is missing ANTHROPIC_API_KEY_VAR.",
                    hint="Reconfigure the agent with --api-key-var.",
                    category="proxy",
                )
            )
        elif os.environ.get(api_key_var):
            results.append(
                ok(
                    "proxy_api_key_present",
                    agent,
                    f"Required proxy API key variable ${api_key_var} is set.",
                    category="proxy",
                    data={"api_key_var": api_key_var},
                )
            )
        else:
            results.append(
                fail(
                    "proxy_api_key_missing",
                    agent,
                    f"Required proxy API key variable ${api_key_var} is not set.",
                    hint=f"Add {api_key_var}=... to .env or export it before starting AgentWeave.",
                    category="proxy",
                    data={"api_key_var": api_key_var},
                )
            )
    return results


def check_agents(session: Any | None = None) -> list[DiagnosticResult]:
    if session is None:
        from .session import Session

        session = Session.load()
    if session is None:
        return []
    results: list[DiagnosticResult] = []
    for agent in session.agent_names:
        results.extend(check_agent_readiness(agent, session))
    return results


def check_jobs() -> list[DiagnosticResult]:
    try:
        from .config import AGENTWEAVE_YML_PATH, load_agentweave_yml

        if not AGENTWEAVE_YML_PATH.exists():
            return []
        config = load_agentweave_yml()
        if not config.jobs:
            return [
                ok(
                    "jobs_not_configured",
                    "jobs",
                    "No jobs are configured.",
                    category="jobs",
                )
            ]
        return [
            ok(
                "jobs_configured",
                "jobs",
                f"{len(config.jobs)} job(s) configured.",
                category="jobs",
                data={"job_count": len(config.jobs)},
            )
        ]
    except Exception as exc:
        return [
            warn(
                "jobs_config_unavailable",
                "jobs",
                f"Could not inspect jobs: {exc}",
                category="jobs",
            )
        ]


def collect_diagnostics(*, include_network: bool = True) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []
    results.extend(check_session())
    results.extend(check_project_config())
    if include_network:
        results.extend(check_transport())
    else:
        config, error = _load_json_raw(TRANSPORT_CONFIG_FILE)
        if error == "missing":
            results.append(
                ok(
                    "transport_local",
                    "transport",
                    "Local transport is active.",
                    category="transport",
                )
            )
        elif error:
            results.append(
                fail(
                    "transport_config_invalid",
                    "transport",
                    f"Could not parse {TRANSPORT_CONFIG_FILE}: {error}",
                    category="transport",
                )
            )
        else:
            results.append(
                ok(
                    f"transport_{(config or {}).get('type', 'local')}_configured",
                    "transport",
                    f"Transport type is {(config or {}).get('type', 'local')}.",
                    category="transport",
                )
            )
    results.extend(check_watchdog())
    results.extend(check_agents())
    results.extend(check_jobs())
    return results


def has_failures(results: Iterable[DiagnosticResult]) -> bool:
    return any(result.status == "fail" for result in results)


def summarize(results: Iterable[DiagnosticResult]) -> dict[str, int]:
    summary = {"pass": 0, "warn": 0, "fail": 0}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    return summary


def worst_status(results: Iterable[DiagnosticResult]) -> str:
    worst = "pass"
    for result in results:
        if STATUS_ORDER.get(result.status, 0) > STATUS_ORDER[worst]:
            worst = result.status
    return worst


def format_results(results: Iterable[DiagnosticResult]) -> str:
    grouped: dict[str, list[DiagnosticResult]] = {}
    for result in results:
        grouped.setdefault(result.category, []).append(result)

    lines: list[str] = []
    for category in sorted(grouped):
        lines.append(f"[{category.upper()}]")
        for result in grouped[category]:
            marker = {"pass": "[OK]", "warn": "[WARN]", "fail": "[ERR]"}.get(
                result.status, "[INFO]"
            )
            lines.append(f"  {marker} {result.target}: {result.message}")
            if result.hint:
                lines.append(f"       Hint: {result.hint}")
        lines.append("")
    return "\n".join(lines).rstrip()


def launch_blockers(agent: str, session: Any | None = None) -> list[DiagnosticResult]:
    """Return deterministic failures that should block an automatic launch."""
    return [
        result
        for result in check_agent_readiness(agent, session)
        if result.id
        in {
            "agent_cli_missing",
            "proxy_api_key_missing",
            "proxy_api_key_var_missing",
            "proxy_base_url_missing",
        }
        and result.status == "fail"
    ]
