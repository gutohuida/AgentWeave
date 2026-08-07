"""Compose all v1 routers."""

from fastapi import APIRouter

from .accounting import router as accounting_router
from .agent_actions import router as agent_actions_router
from .agent_chat import router as agent_chat_router
from .agent_trigger import router as agent_trigger_router
from .agents import router as agents_router
from .charters import router as charters_router
from .events import instance_router as instance_events_router
from .events import router as events_router
from .fs_browse import router as fs_browse_router
from .inbound_queue import router as inbound_queue_router
from .instructions import router as instructions_router
from .jobs import router as jobs_router
from .logs import router as logs_router
from .messages import router as messages_router
from .model_catalog import router as model_catalog_router
from .native_dialog import router as native_dialog_router
from .permissions import router as permissions_router
from .projects import router as projects_router
from .questions import router as questions_router
from .runners import router as runners_router
from .session_sync import router as session_sync_router
from .setup import router as setup_router
from .spec import router as spec_router
from .status import router as status_router
from .tasks import router as tasks_router
from .unasked_questions import router as unasked_questions_router
from .workspace import router as workspace_router
from .worktrees import router as worktrees_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(projects_router)
v1_router.include_router(instance_events_router)
v1_router.include_router(model_catalog_router)
v1_router.include_router(fs_browse_router)
v1_router.include_router(native_dialog_router)

project_resources_router = APIRouter(prefix="/projects/{project_id}")
project_resources_router.include_router(accounting_router)
project_resources_router.include_router(messages_router)
project_resources_router.include_router(tasks_router)
project_resources_router.include_router(questions_router)
project_resources_router.include_router(permissions_router)
project_resources_router.include_router(unasked_questions_router)
project_resources_router.include_router(status_router)
project_resources_router.include_router(events_router)
project_resources_router.include_router(agent_trigger_router)
project_resources_router.include_router(agents_router)
project_resources_router.include_router(agent_chat_router)
project_resources_router.include_router(session_sync_router)
project_resources_router.include_router(jobs_router)
project_resources_router.include_router(instructions_router)
project_resources_router.include_router(spec_router)
project_resources_router.include_router(logs_router)
project_resources_router.include_router(worktrees_router)
project_resources_router.include_router(inbound_queue_router)
project_resources_router.include_router(workspace_router)
project_resources_router.include_router(runners_router)
project_resources_router.include_router(charters_router)
v1_router.include_router(project_resources_router)

v1_router.include_router(agent_actions_router)
v1_router.include_router(setup_router)
