"""Compose all v1 routers."""

from fastapi import APIRouter

from .messages import router as messages_router
from .tasks import router as tasks_router
from .questions import router as questions_router
from .status import router as status_router
from .events import router as events_router
from .logs import router as logs_router
from .agents import router as agents_router
from .agent_trigger import router as agent_trigger_router
from .agent_chat import router as agent_chat_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(messages_router)
v1_router.include_router(tasks_router)
v1_router.include_router(questions_router)
v1_router.include_router(status_router)
v1_router.include_router(events_router)
v1_router.include_router(logs_router)
v1_router.include_router(agents_router)
v1_router.include_router(agent_trigger_router)
v1_router.include_router(agent_chat_router)
