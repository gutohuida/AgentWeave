"""HTTP transport — delegates to AgentWeave Hub via REST API.

Uses stdlib urllib.request only (zero new CLI dependencies).

Expected transport.json:
    {
        "type": "http",
        "url": "http://localhost:8000",
        "api_key": "aw_live_...",
        "project_id": "proj-default"
    }
"""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .base import BaseTransport

logger = logging.getLogger(__name__)

# H3: retry tunables for Hub requests
HUB_MAX_ATTEMPTS = 3
HUB_INITIAL_BACKOFF = 0.5  # seconds; doubled on each retry
HUB_MAX_BACKOFF = 8.0  # seconds; cap for exponential backoff
HUB_RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}

# S10: cap Hub response body size to prevent OOM on a misbehaving Hub
# (e.g. one compromised and now serving 10 GB). 10 MB is 10x the
# legitimate worst case (a list of messages or a single task).
HUB_MAX_RESPONSE_BODY = 10 * 1024 * 1024


class HubTransportError(RuntimeError):
    """Classified Hub transport failure."""

    def __init__(self, message: str, classification: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.classification = classification
        self.status_code = status_code

    def to_log_data(self, method: str) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "method": method,
            "error": str(self),
            "classification": self.classification,
        }
        if self.status_code is not None:
            data["status_code"] = self.status_code
        return data


def _transport_error_data(method: str, exc: RuntimeError) -> Dict[str, Any]:
    if isinstance(exc, HubTransportError):
        return exc.to_log_data(method)
    return {"method": method, "error": str(exc), "classification": "transport_error"}


def _redact_body(body_text: str, max_length: int = 200) -> str:
    """S7 (PR 3): strip api_key= query strings and truncate body text.

    Avoids leaking the API key into the structured log file when a
    misconfigured Hub (or reverse proxy) echoes the request URL inside
    its error response body.
    """
    import re as _re

    redacted = _re.sub(r"(api_key=)[^&\s]+", r"\1<redacted>", body_text)
    if len(redacted) > max_length:
        redacted = redacted[:max_length] + "..."
    return redacted


def _sleep_with_retry_after(http_error: urllib.error.HTTPError, default_backoff: float) -> None:
    """Honor the Retry-After header on 429 (or any retryable status).

    Retry-After may be a delta-seconds int or an HTTP-date. We only
    support the delta-seconds form (the common case); otherwise fall
    back to the default exponential backoff.
    """
    retry_after = http_error.headers.get("Retry-After") if http_error.headers else None
    if retry_after is not None:
        try:
            seconds = float(retry_after)
            time.sleep(max(0.0, min(seconds, HUB_MAX_BACKOFF)))
            return
        except (TypeError, ValueError):
            pass
    time.sleep(default_backoff)


class HttpTransport(BaseTransport):
    """Transport that delegates to an AgentWeave Hub via HTTP REST API."""

    poll_interval: float = 5.0

    def __init__(
        self,
        url: str,
        api_key: str,
        project_id: str,
        max_attempts: int = HUB_MAX_ATTEMPTS,
        initial_backoff: float = HUB_INITIAL_BACKOFF,
        source_id: Optional[str] = None,
    ):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.project_id = project_id
        self.max_attempts = max_attempts
        self.initial_backoff = initial_backoff
        # Stable, non-secret identifier for this workspace's spec sync source.
        # Used by reconcile_specs to let the Hub tell apart snapshots from
        # different machines/checkouts of the same project.
        self.source_id = source_id

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    @staticmethod
    def _run_token() -> str:
        return os.environ.get("AW_RUN_TOKEN", "").strip()

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Make an authenticated request to the Hub.

        Injects project_id into every GET query string. POST bodies are sent as-is
        because the Hub's get_project auth dependency already extracts project_id
        from the API key, and most writeable schemas use extra="forbid".
        Retries on 5xx, 408, 425, 429, and URLError with exponential backoff
        (honors Retry-After header on 429). Raises HubTransportError on
        non-2xx, non-retryable errors or after exhausting retries.
        """
        run_token = self._run_token()
        agent_mode = bool(run_token)
        route_prefix = "/api/v1/agent-actions" if agent_mode else "/api/v1"
        url = f"{self.url}{route_prefix}{path}"

        # Inject project_id into GET params
        if method == "GET":
            qs: Dict[str, str] = {} if agent_mode else {"project_id": self.project_id}
            if params:
                qs.update(params)
            url += "?" + urllib.parse.urlencode({k: v for k, v in qs.items() if v is not None})

        payload: Optional[bytes] = None
        if body is not None:
            # NOTE: do NOT inject project_id into the body. The Hub's
            # get_project auth dependency extracts project_id from the API
            # key (see hub/hub/auth.py), and most writeable schemas use
            # extra="forbid" — injecting here triggers 422 on POST /tasks,
            # /messages, /jobs and PATCH /tasks/{id}, /jobs/{id}.
            if agent_mode:
                body = dict(body)
                for identity_field in (
                    "from",
                    "sender",
                    "assigner",
                    "from_agent",
                    "requester",
                    "run_id",
                    "project_id",
                    "source",
                ):
                    body.pop(identity_field, None)
                if path == "/messages":
                    recipient = body.pop("to", body.pop("recipient", None))
                    body["recipient"] = recipient
            payload = json.dumps(body).encode()

        req = urllib.request.Request(url, data=payload, method=method)
        req.add_header("Authorization", f"Bearer {run_token or self.api_key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        attempt = 0
        backoff = self.initial_backoff
        while True:
            attempt += 1
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    # S10: cap body size to prevent OOM. resp.read(n) reads
                    # up to n bytes and returns fewer at EOF. The +1 lets us
                    # detect overflow without reading the full body.
                    raw = resp.read(HUB_MAX_RESPONSE_BODY + 1)
                if len(raw) > HUB_MAX_RESPONSE_BODY:
                    raise HubTransportError(
                        f"Hub response exceeds {HUB_MAX_RESPONSE_BODY} bytes",
                        classification="hub_response_too_large",
                    )
                # H6: 2xx with a non-JSON body (e.g. an HTML 502 page returned
                # by a misconfigured reverse proxy) must not crash the agent.
                # Classify it so callers can decide how to handle it.
                if not raw:
                    return {}
                try:
                    return json.loads(raw)
                except (ValueError, json.JSONDecodeError) as decode_exc:
                    raise HubTransportError(
                        "Hub returned a non-JSON body",
                        classification="hub_invalid_response",
                    ) from decode_exc
            except urllib.error.HTTPError as exc:
                body_text = exc.read().decode(errors="replace")
                # S7 (PR 3): redact api_key= in body text and truncate.
                redacted = _redact_body(body_text)
                if exc.code in (401, 403):
                    classification = "hub_auth_failed"
                elif exc.code == 404:
                    classification = "hub_project_missing"
                elif exc.code == 408:
                    classification = "hub_timeout"
                else:
                    classification = "hub_api_error"
                err = HubTransportError(
                    f"Hub API {exc.code}: {redacted}",
                    classification,
                    status_code=exc.code,
                )
                if exc.code in HUB_RETRY_STATUSES and attempt < self.max_attempts:
                    _sleep_with_retry_after(exc, backoff)
                    backoff = min(backoff * 2, HUB_MAX_BACKOFF)
                    continue
                raise err from exc
            except urllib.error.URLError as exc:
                reason = str(exc.reason)
                classification = (
                    "hub_timeout" if "timed out" in reason.lower() else "hub_unreachable"
                )
                err = HubTransportError(f"Hub connection error: {exc.reason}", classification)
                if attempt < self.max_attempts:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, HUB_MAX_BACKOFF)
                    continue
                raise err from exc

    # ------------------------------------------------------------------
    # BaseTransport implementation
    # ------------------------------------------------------------------

    def send_message(self, message_data: Dict[str, Any]) -> bool:
        """POST /api/v1/messages — persist a message."""
        try:
            # Map from/to keys to sender/recipient aliases expected by the Hub.
            # The Hub's MessageCreate schema has `extra: "forbid"`, so we
            # MUST NOT include `id` or `timestamp` (server-assigned) — including
            # them produces a 422 and the MCP `send_message` tool returns
            # `{"error": "Failed to send message via active transport"}` to
            # the calling agent.
            body = {
                "from": message_data.get("from", message_data.get("sender", "")),
                "to": message_data.get("to", message_data.get("recipient", "")),
                "subject": message_data.get("subject", ""),
                "content": message_data.get("content", ""),
                "type": message_data.get("type", "message"),
                "task_id": message_data.get("task_id"),
                "run_id": os.environ.get("AW_RUN_ID") or None,
            }
            self._request("POST", "/messages", body)
            return True
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("send_message", exc),
                },
            )
            return False

    def get_pending_messages(self, agent: str) -> List[Dict[str, Any]]:
        """GET /api/v1/messages?agent=X — return unread messages."""
        try:
            result = self._request("GET", "/messages", params={"agent": agent})
            if isinstance(result, list):
                return result
            return []
        except RuntimeError as exc:
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("get_pending_messages", exc),
                },
            )
            return []

    def archive_message(self, message_id: str) -> bool:
        """PATCH /api/v1/messages/{id}/read."""
        try:
            self._request("PATCH", f"/messages/{message_id}/read")
            return True
        except RuntimeError as exc:
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("archive_message", exc),
                },
            )
            return False

    def send_task(self, task_data: Dict[str, Any], error: Optional[List[str]] = None) -> bool:
        """POST /api/v1/tasks."""
        try:
            # The Hub's TaskCreate schema has `extra: "forbid"`, so we MUST
            # NOT pass server-managed `created_at` / `updated` — the Hub
            # assigns those. The client-generated `id` IS accepted by the Hub
            # (see TaskCreate.id) so we keep it through: this lets the MCP
            # `create_task` tool return the same id the Hub stored, so
            # subsequent get_task / update_task calls by the agent find the
            # task. Stripping it produced a misleading id mismatch where the
            # Hub silently generated a different id and subsequent calls by
            # id failed with "not found".
            body = {k: v for k, v in task_data.items() if k not in ("created_at", "updated")}
            self._request("POST", "/tasks", body)
            return True
        except RuntimeError as exc:
            if self._run_token():
                raise
            message = str(exc)
            if error is not None:
                error.append(message)
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("send_task", exc),
                },
            )
            return False

    def get_active_tasks(self, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        """GET /api/v1/tasks?agent=X — return active tasks."""
        try:
            params: Dict[str, str] = {}
            if agent:
                params["agent"] = agent
            result = self._request("GET", "/tasks", params=params)
            if isinstance(result, list):
                return result
            return []
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("get_active_tasks", exc),
                },
            )
            return []

    def get_transport_type(self) -> str:
        return "http"

    # ------------------------------------------------------------------
    # Extended Hub methods (not in BaseTransport ABC)
    # ------------------------------------------------------------------

    def get_task_by_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """GET /api/v1/tasks/{id} — fetch a single task from Hub."""
        try:
            return self._request("GET", f"/tasks/{task_id}")
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("get_task_by_id", exc),
                },
            )
            return None

    def update_task_status(self, task_id: str, status: str) -> bool:
        """PATCH /api/v1/tasks/{id} — update task status on Hub."""
        try:
            self._request("PATCH", f"/tasks/{task_id}", {"status": status})
            return True
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("update_task_status", exc),
                },
            )
            return False

    def ask_question(self, from_agent: str, question: str, blocking: bool = False) -> Optional[str]:
        """POST /api/v1/questions — post a question for the human user.

        Returns the question ID, or None on failure.
        """
        try:
            result = self._request(
                "POST",
                "/questions",
                {"from_agent": from_agent, "question": question, "blocking": blocking},
            )
            return result.get("id")
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("ask_question", exc),
                },
            )
            return None

    def get_answer(self, question_id: str) -> Optional[Dict[str, Any]]:
        """GET /api/v1/questions/{id} — check if a question has been answered.

        Returns the question dict (with 'answered' and 'answer' fields), or None on failure.
        """
        try:
            return self._request("GET", f"/questions/{question_id}")
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("get_answer", exc),
                },
            )
            return None

    def push_heartbeat(
        self, agent: str, status: str = "active", message: Optional[str] = None
    ) -> bool:
        """POST /api/v1/agents/{name}/heartbeat — publish agent status to the Hub."""
        try:
            body: Dict[str, Any] = {"status": status}
            if message:
                body["message"] = message
            self._request("POST", f"/agents/{agent}/heartbeat", body)
            return True
        except RuntimeError as exc:
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("push_heartbeat", exc),
                },
            )
            return False

    def post_agent_output(
        self,
        agent: str,
        content: str,
        session_id: Optional[str] = None,
        *,
        kind: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        sequence: Optional[int] = None,
    ) -> bool:
        """Post output with optional structure and a legacy text fallback."""
        try:
            body: Dict[str, Any] = {"content": content}
            if session_id:
                body["session_id"] = session_id
            structured = any(value is not None for value in (kind, payload, run_id, sequence))
            if kind is not None:
                body["kind"] = kind
            if payload is not None:
                body["payload"] = payload
            if run_id is not None:
                body["run_id"] = run_id
            if sequence is not None:
                body["sequence"] = sequence
            try:
                self._request("POST", f"/agents/{agent}/output", body)
            except HubTransportError as exc:
                if not structured or exc.status_code not in (400, 422):
                    raise
                legacy_body: Dict[str, Any] = {"content": content}
                if session_id:
                    legacy_body["session_id"] = session_id
                self._request("POST", f"/agents/{agent}/output", legacy_body)
            return True
        except RuntimeError as exc:
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("post_agent_output", exc),
                },
            )
            return False

    def post_context_usage(self, agent: str, data: Dict[str, Any]) -> bool:
        """POST /api/v1/agents/{name}/context-usage — update context usage in Mission Control."""
        try:
            self._request("POST", f"/agents/{agent}/context-usage", data)
            return True
        except RuntimeError as exc:
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("post_context_usage", exc),
                },
            )
            return False

    def push_session(self, session_data: Dict[str, Any]) -> bool:
        """POST /api/v1/session/sync — push session.json config to the Hub.

        Called on every Session.save() and at watchdog startup so the Hub
        always has the latest agent configuration (names, roles, yolo flags).
        """
        try:
            self._request("POST", "/session/sync", {"data": session_data})
            return True
        except RuntimeError as exc:
            logger.warning(
                "push_session failed: %s",
                str(exc),
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("push_session", exc),
                },
            )
            return False

    def push_spec(self, path: str, content: str) -> bool:
        """POST /api/v1/project/specs/sync — push a spec HTML file to the Hub.

        Called at watchdog startup and whenever a spec file changes, plus
        manually via `agentweave spec push`. `path` is the repo-relative
        path (e.g. "spec/spec.html") the Hub uses to upsert the spec.
        """
        try:
            self._request("POST", "/project/specs/sync", {"path": path, "content": content})
            return True
        except RuntimeError as exc:
            logger.warning(
                "push_spec failed: %s",
                str(exc),
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("push_spec", exc),
                },
            )
            return False

    def reconcile_specs(
        self,
        manifest_text: Optional[str],
        manifest_state: str,
        discovered_paths: List[str],
        prune: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """POST /api/v1/project/specs/reconcile — submit a complete source snapshot.

        `manifest_state` is one of "valid", "absent", "unreadable", "invalid".
        Returns the Hub's diagnostics payload, or None on failure (the caller
        must not treat that as "no drift" — it means the snapshot was not
        recorded and reconciliation should be retried).
        """
        try:
            body: Dict[str, Any] = {
                "source_id": self.source_id,
                "manifest_state": manifest_state,
                "discovered_paths": discovered_paths,
                "prune": prune,
            }
            if manifest_text is not None:
                body["manifest_text"] = manifest_text
            return self._request("POST", "/project/specs/reconcile", body)
        except RuntimeError as exc:
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("reconcile_specs", exc),
                },
            )
            return None

    def push_roles_config(self, roles_config: Dict[str, Any]) -> bool:
        """PUT /api/v1/agents/roles/config — push roles.json to the Hub.

        Called at agentweave init so the Hub knows each agent's dev role.
        """
        try:
            self._request("PUT", "/agents/roles/config", roles_config)
            return True
        except RuntimeError as exc:
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("push_roles_config", exc),
                },
            )
            return False

    def is_agent_registered(self, agent: str) -> bool:
        """Check whether an agent exists in the Hub (configured or self-registered)."""
        try:
            agents = self._request("GET", "/agents")
            if isinstance(agents, list):
                return any(a.get("name") == agent for a in agents)
            return False
        except RuntimeError as exc:
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": {**_transport_error_data("is_agent_registered", exc), "agent": agent},
                },
            )
            return False

    def get_agent_registration(self, agent: str) -> Optional[Dict[str, Any]]:
        """Return registration metadata for an agent from the Hub.

        Returns a dict with 'self_registered' and 'contact_mode' if found,
        otherwise None.
        """
        try:
            agents = self._request("GET", "/agents")
            if isinstance(agents, list):
                match = next((a for a in agents if a.get("name") == agent), None)
                if match:
                    return {
                        "self_registered": bool(match.get("self_registered", False)),
                        "contact_mode": match.get("contact_mode"),
                        "config": match.get("config", {}),
                    }
            return None
        except RuntimeError as exc:
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": {
                        **_transport_error_data("get_agent_registration", exc),
                        "agent": agent,
                    },
                },
            )
            return None

    def push_log(
        self,
        event_type: str,
        agent: str,
        data: Optional[Dict[str, Any]],
        severity: str,
    ) -> None:
        """POST /api/v1/logs — push a log event to the Hub.

        Silently swallows ALL exceptions — never logs a log failure.
        """
        try:
            body: Dict[str, Any] = {
                "event_type": event_type,
                "agent": agent,
                "data": data or {},
                "severity": severity,
            }
            self._request("POST", "/logs", body)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # AI Jobs
    # ------------------------------------------------------------------

    def create_job(self, job_data: Dict[str, Any]) -> Optional[str]:
        """POST /api/v1/jobs — create a new job on the Hub."""
        try:
            result = self._request("POST", "/jobs", job_data)
            return result.get("id")
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("create_job", exc),
                },
            )
            return None

    def list_jobs(self, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        """GET /api/v1/jobs — list jobs from the Hub."""
        try:
            params: Dict[str, str] = {}
            if agent:
                params["agent"] = agent
            result = self._request("GET", "/jobs", params=params)
            if isinstance(result, list):
                return result
            return []
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("list_jobs", exc),
                },
            )
            return []

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """GET /api/v1/jobs/{id} — get job details with history."""
        try:
            return self._request("GET", f"/jobs/{job_id}")
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("get_job", exc),
                },
            )
            return None

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """PATCH /api/v1/jobs/{id} — update job on the Hub."""
        try:
            self._request("PATCH", f"/jobs/{job_id}", updates)
            return True
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("update_job", exc),
                },
            )
            return False

    def delete_job(self, job_id: str) -> bool:
        """DELETE /api/v1/jobs/{id} — delete job from the Hub."""
        try:
            self._request("DELETE", f"/jobs/{job_id}")
            return True
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("delete_job", exc),
                },
            )
            return False

    def fire_job(self, job_id: str, trigger: str = "manual") -> bool:
        """POST /api/v1/jobs/{id}/run — fire job immediately on the Hub."""
        try:
            self._request("POST", f"/jobs/{job_id}/run", {"trigger": trigger})
            return True
        except RuntimeError as exc:
            if self._run_token():
                raise
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": _transport_error_data("fire_job", exc),
                },
            )
            return False

    def sync_local_jobs(self) -> int:
        """Sync local jobs to Hub when transport switches to HTTP.

        Returns:
            Number of jobs synced
        """
        from ..jobs import Job

        synced = 0
        local_jobs = Job.list_all()

        for job in local_jobs:
            if job.synced:
                continue

            try:
                result = self._request("POST", "/jobs", job.to_dict())
                if result.get("id"):
                    job.synced = True
                    job.source = "hub"
                    job.save()
                    synced += 1
            except RuntimeError as exc:
                # 409 Conflict means job already exists - mark as synced
                if "409" in str(exc) or "Conflict" in str(exc):
                    job.synced = True
                    job.source = "hub"
                    job.save()
                    synced += 1
                else:
                    logger.warning(
                        "job_sync_failed",
                        extra={
                            "event": "job_sync_failed",
                            "data": {"job_id": job.id, "error": str(exc)},
                        },
                    )

        return synced
