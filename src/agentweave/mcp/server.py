"""Compatibility import for the single Hub-owned AgentWeave tool surface.

The former CLI-side implementation duplicated the Hub server and allowed local/git state
reads around Hub governance. Phase 7 deliberately keeps no tools here: source checkouts and
combined installs re-export the canonical Hub surface, while CLI-only installs should use the
ordinary ``agentweave`` commands until a Hub starts and injects that surface.
"""

try:
    from hub.mcp_server import (  # type: ignore[import-not-found]
        archive_job,
        ask_user,
        create_job,
        create_task,
        get_answer,
        get_task,
        list_tasks,
        main,
        mcp,
        request_agent,
        run_job,
        send_message,
        toggle_job,
        update_task,
    )
except ImportError:
    # Repository-root imports see ``hub`` as the outer namespace package.
    from hub.hub.mcp_server import (  # type: ignore[import-not-found,no-redef]
        archive_job,
        ask_user,
        create_job,
        create_task,
        get_answer,
        get_task,
        list_tasks,
        main,
        mcp,
        request_agent,
        run_job,
        send_message,
        toggle_job,
        update_task,
    )

__all__ = [
    "archive_job",
    "ask_user",
    "create_job",
    "create_task",
    "get_answer",
    "get_task",
    "list_tasks",
    "main",
    "mcp",
    "request_agent",
    "run_job",
    "send_message",
    "toggle_job",
    "update_task",
]
