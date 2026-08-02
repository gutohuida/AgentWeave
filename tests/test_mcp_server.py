"""The CLI package keeps no second MCP implementation after Phase 7."""

import inspect


def test_cli_module_reexports_canonical_hub_surface():
    from agentweave.mcp import server as cli_server
    from hub import mcp_server as canonical

    assert cli_server.mcp is canonical.mcp
    assert cli_server.send_message is canonical.send_message
    assert cli_server.request_agent is canonical.request_agent


def test_cli_shim_exposes_no_removed_bypass_functions():
    from agentweave.mcp import server

    for name in (
        "get_inbox",
        "mark_read",
        "register_agent",
        "get_agent_config",
        "update_agent_config",
        "get_context",
        "get_agent_context",
        "heartbeat",
        "get_status",
        "save_checkpoint",
    ):
        assert not hasattr(server, name)


def test_canonical_signatures_have_no_caller_identity():
    from agentweave.mcp import server

    assert "from_agent" not in inspect.signature(server.send_message).parameters
    assert "assigner" not in inspect.signature(server.create_task).parameters
    assert "from_agent" not in inspect.signature(server.ask_user).parameters
    assert "requester" not in inspect.signature(server.request_agent).parameters
