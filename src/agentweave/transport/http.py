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
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .base import BaseTransport


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
            raise RuntimeError(f"Hub API {exc.code}: {exc.read().decode(errors='replace')}")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Hub connection error: {exc.reason}")

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
        except RuntimeError:
            return False

    def get_pending_messages(self, agent: str) -> List[Dict[str, Any]]:
        """GET /api/v1/messages?agent=X — return unread messages."""
        try:
            result = self._request("GET", "/messages", params={"agent": agent})
            if isinstance(result, list):
                return result
            return []
        except RuntimeError:
            return []

    def archive_message(self, message_id: str) -> bool:
        """PATCH /api/v1/messages/{id}/read."""
        try:
            self._request("PATCH", f"/messages/{message_id}/read")
            return True
        except RuntimeError:
            return False

    def send_task(self, task_data: Dict[str, Any]) -> bool:
        """POST /api/v1/tasks."""
        try:
            self._request("POST", "/tasks", task_data)
            return True
        except RuntimeError:
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
        except RuntimeError:
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
        except RuntimeError:
            return None

    def update_task_status(self, task_id: str, status: str) -> bool:
        """PATCH /api/v1/tasks/{id} — update task status on Hub."""
        try:
            self._request("PATCH", f"/tasks/{task_id}", {"status": status})
            return True
        except RuntimeError:
            return False

    def ask_question(
        self, from_agent: str, question: str, blocking: bool = False
    ) -> Optional[str]:
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
        except RuntimeError:
            return None

    def get_answer(self, question_id: str) -> Optional[Dict[str, Any]]:
        """GET /api/v1/questions/{id} — check if a question has been answered.

        Returns the question dict (with 'answered' and 'answer' fields), or None on failure.
        """
        try:
            return self._request("GET", f"/questions/{question_id}")
        except RuntimeError:
            return None
