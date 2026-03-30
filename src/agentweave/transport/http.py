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
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .base import BaseTransport

logger = logging.getLogger(__name__)


class HttpTransport(BaseTransport):
    """Transport that delegates to an AgentWeave Hub via HTTP REST API."""

    poll_interval: float = 5.0

    def __init__(self, url: str, api_key: str, project_id: str):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.project_id = project_id

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Make an authenticated request to the Hub.

        Injects project_id into every POST body and every GET query string.
        Raises RuntimeError on non-2xx responses.
        """
        url = f"{self.url}/api/v1{path}"

        # Inject project_id into GET params
        if method == "GET":
            qs: Dict[str, str] = {"project_id": self.project_id}
            if params:
                qs.update(params)
            url += "?" + urllib.parse.urlencode({k: v for k, v in qs.items() if v is not None})

        payload: Optional[bytes] = None
        if body is not None:
            if "project_id" not in body:
                body = {"project_id": self.project_id, **body}
            payload = json.dumps(body).encode()

        req = urllib.request.Request(url, data=payload, method=method)
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"Hub API {exc.code}: {exc.read().decode(errors='replace')}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Hub connection error: {exc.reason}") from exc

    # ------------------------------------------------------------------
    # BaseTransport implementation
    # ------------------------------------------------------------------

    def send_message(self, message_data: Dict[str, Any]) -> bool:
        """POST /api/v1/messages — persist a message."""
        try:
            # Map from/to keys to sender/recipient aliases expected by the Hub
            body = {
                "from": message_data.get("from", message_data.get("sender", "")),
                "to": message_data.get("to", message_data.get("recipient", "")),
                "subject": message_data.get("subject", ""),
                "content": message_data.get("content", ""),
                "type": message_data.get("type", "message"),
                "task_id": message_data.get("task_id"),
                "id": message_data.get("id"),
                "timestamp": message_data.get("timestamp"),
            }
            self._request("POST", "/messages", body)
            return True
        except RuntimeError as exc:
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": {"method": "send_message", "error": str(exc)},
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
                    "data": {"method": "get_pending_messages", "error": str(exc)},
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
                    "data": {"method": "archive_message", "error": str(exc)},
                },
            )
            return False

    def send_task(self, task_data: Dict[str, Any]) -> bool:
        """POST /api/v1/tasks."""
        try:
            self._request("POST", "/tasks", task_data)
            return True
        except RuntimeError as exc:
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": {"method": "send_task", "error": str(exc)},
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
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": {"method": "get_active_tasks", "error": str(exc)},
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
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": {"method": "get_task_by_id", "error": str(exc)},
                },
            )
            return None

    def update_task_status(self, task_id: str, status: str) -> bool:
        """PATCH /api/v1/tasks/{id} — update task status on Hub."""
        try:
            self._request("PATCH", f"/tasks/{task_id}", {"status": status})
            return True
        except RuntimeError as exc:
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": {"method": "update_task_status", "error": str(exc)},
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
            logger.error(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": {"method": "ask_question", "error": str(exc)},
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
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": {"method": "get_answer", "error": str(exc)},
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
                    "data": {"method": "push_heartbeat", "error": str(exc)},
                },
            )
            return False

    def post_agent_output(self, agent: str, content: str, session_id: Optional[str] = None) -> bool:
        """POST /api/v1/agents/{name}/output — stream one line of agent output to the Hub."""
        try:
            body: Dict[str, Any] = {"content": content}
            if session_id:
                body["session_id"] = session_id
            self._request("POST", f"/agents/{agent}/output", body)
            return True
        except RuntimeError as exc:
            logger.warning(
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": {"method": "post_agent_output", "error": str(exc)},
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
                "transport_error",
                extra={
                    "event": "transport_error",
                    "data": {"method": "push_session", "error": str(exc)},
                },
            )
            return False

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
