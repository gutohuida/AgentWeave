"""A run's registered secrets are scrubbed from what its agent sends through its Hub tools (F490).

`run_secrets` holds, for each live run, the values that run must never have recorded: a Copilot
provider runner's key, which is in the run's environment because the CLI needs it there (slice 5
D7). The run's own output is scrubbed where it is recorded. What the agent sends through its
AgentWeave tools is not run output: `send_message`, `ask_user`, task updates, checkpoint notes,
permission cards, spec documents and evidence each reach their own route and their own table, and
an agent that read the key and passed it to any of them stored it in the Hub's database and sent it
to the app.

Every one of those calls is a request to `/api/v1/agent-actions` under the run's own credential, and
no other route accepts that credential (`agent_auth.get_agent_actor`). So the scrub is here, once,
on the request body before any route parses it, rather than in each route: a tool added later is
covered without anyone remembering to.

Only a request whose run has something registered pays for more than a dictionary check: the run is
resolved from its credential (one indexed read) and its body read whole, scrubbed and replayed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from . import run_secrets
from .agent_auth import _RUN_TOKEN_PREFIX, hash_run_token
from .db.engine import async_session_factory
from .db.models import Run

AGENT_ACTIONS_PATH = "/api/v1/agent-actions"
_READS = ("GET", "HEAD", "OPTIONS", "TRACE")


def _credential(scope: Dict[str, Any]) -> Optional[str]:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and token.startswith(_RUN_TOKEN_PREFIX):
                return token.strip()
    return None


async def _run_for(token: str) -> Optional[str]:
    async with async_session_factory() as session:
        return (
            await session.execute(
                select(Run.id).where(Run.capability_token_hash == hash_run_token(token))
            )
        ).scalar_one_or_none()


class AgentActionScrubMiddleware:
    """ASGI middleware: the body of a run's write to its agent-actions routes, scrubbed."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive, send) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method", "GET") in _READS
            or not scope.get("path", "").startswith(AGENT_ACTIONS_PATH)
            or not run_secrets.any_registered()
        ):
            await self.app(scope, receive, send)
            return
        token = _credential(scope)
        run_id = await _run_for(token) if token else None
        if not run_secrets.registered(run_id):
            await self.app(scope, receive, send)
            return

        chunks: List[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # The client went away before sending its body; nothing will be stored.
                await self.app(scope, receive, send)
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        scrubbed = run_secrets.scrub_body(run_id, body)

        headers = [
            (name, value) for name, value in scope.get("headers", []) if name != b"content-length"
        ]
        headers.append((b"content-length", str(len(scrubbed)).encode()))
        delivered = False

        async def replay() -> Dict[str, Any]:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": scrubbed, "more_body": False}

        await self.app({**scope, "headers": headers}, replay, send)
