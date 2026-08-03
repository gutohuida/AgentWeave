"""Compose all v1 routers."""

from fastapi import APIRouter

from .accounting import router as accounting_router
from .agent_chat import router as agent_chat_router
from .agent_actions import router as agent_actions_router
from .agent_trigger import router as agent_trigger_router
from .agents import router as agents_router
from .charters import router as charters_router
from .events import router as events_router
from .inbound_queue import router as inbound_queue_router
from .instructions import router as instructions_router
from .jobs import router as jobs_router
from .logs import router as logs_router
from .messages import router as messages_router
from .questions import router as questions_router
from .runners import router as runners_router
from .session_sync import router as session_sync_router
from .setup import router as setup_router
from .spec import router as spec_router
from .status import router as status_router
from .tasks import router as tasks_router
from .workspace import router as workspace_router
from .worktrees import router as worktrees_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(accounting_router)
v1_router.include_router(agent_actions_router)
v1_router.include_router(messages_router)
v1_router.include_router(tasks_router)
v1_router.include_router(questions_router)
v1_router.include_router(status_router)
v1_router.include_router(events_router)
v1_router.include_router(logs_router)
v1_router.include_router(agents_router)
v1_router.include_router(agent_trigger_router)
v1_router.include_router(agent_chat_router)
v1_router.include_router(session_sync_router)
v1_router.include_router(jobs_router)
v1_router.include_router(setup_router)
v1_router.include_router(instructions_router)
v1_router.include_router(spec_router)
v1_router.include_router(worktrees_router)
v1_router.include_router(inbound_queue_router)
v1_router.include_router(workspace_router)
v1_router.include_router(runners_router)
v1_router.include_router(charters_router)
