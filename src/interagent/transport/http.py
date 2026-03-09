"""HTTP/MCP transport stub — interface contract for the InterAgent Hub.

This module defines the HttpTransport class but does NOT implement it yet.
It exists to specify the API contract that the InterAgent Hub must satisfy,
allowing the CLI and Hub to be developed independently.

When the Hub is built (Phase 3 in ROADMAP.md), this stub will be replaced
with a real implementation. The Hub will be exposed as an MCP server, and
this transport will use the MCP protocol to communicate with it.

See ROADMAP.md for the full Hub architecture and phasing plan.

Expected transport.json for HTTP/MCP mode:
    {
        "type": "http",
        "url": "https://hub.interagent.dev",
        "api_key": "iaf_live_xxxxxxxxxxxx",
        "project_id": "proj-abc123"
    }

API contract the Hub must expose (REST or MCP tool equivalents):
    POST   {url}/api/v1/messages           body: message_data dict
    GET    {url}/api/v1/messages?agent=X   → list of pending message dicts
    PATCH  {url}/api/v1/messages/{id}/read
    POST   {url}/api/v1/tasks              body: task_data dict
    GET    {url}/api/v1/tasks?agent=X      → list of active task dicts
    PATCH  {url}/api/v1/tasks/{id}         body: {status: ...}

All requests include: Authorization: Bearer {api_key}
"""

from typing import Any, Dict, List, Optional

from .base import BaseTransport


class HttpTransport(BaseTransport):
    """Transport that delegates to an InterAgent Hub via HTTP/MCP.

    NOT YET IMPLEMENTED. All methods raise NotImplementedError.
    This class is a placeholder that defines the interface the Hub must satisfy.
    """

    def __init__(self, url: str, api_key: str, project_id: str):
        self.url = url
        self.api_key = api_key
        self.project_id = project_id

    def _not_implemented(self) -> None:
        raise NotImplementedError(
            "HTTP/MCP transport is not yet implemented. "
            "See ROADMAP.md for the InterAgent Hub plan. "
            "Use 'interagent transport disable' to revert to local transport."
        )

    def send_message(self, message_data: Dict[str, Any]) -> bool:
        self._not_implemented()

    def get_pending_messages(self, agent: str) -> List[Dict[str, Any]]:
        self._not_implemented()

    def archive_message(self, message_id: str) -> bool:
        self._not_implemented()

    def send_task(self, task_data: Dict[str, Any]) -> bool:
        self._not_implemented()

    def get_active_tasks(self, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        self._not_implemented()

    def get_transport_type(self) -> str:
        return "http"
