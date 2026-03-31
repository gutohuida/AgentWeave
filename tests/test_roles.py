"""Tests for the roles module."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from agentweave.roles import (
    add_role_to_agent,
    format_agent_roles,
    get_agent_roles,
    get_available_roles,
    load_roles_config,
    remove_role_from_agent,
    save_roles_config,
    set_agent_roles,
    validate_role,
)


class TestRolesConfig:
    """Test roles configuration loading and saving."""

    def test_load_nonexistent_config(self, monkeypatch):
        """Loading a non-existent config returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            os.makedirs(".agentweave", exist_ok=True)
            result = load_roles_config()
            assert result is None

    def test_save_and_load_config(self, monkeypatch):
        """Save and load a config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            os.makedirs(".agentweave", exist_ok=True)
            
            config = {
                "version": 2,
                "agent_roles": {
                    "claude": ["tech_lead"],
                    "kimi": ["backend_dev", "code_reviewer"]
                },
                "roles": {}
            }
            
            save_roles_config(config)
            loaded = load_roles_config()
            
            assert loaded["version"] == 2
            assert loaded["agent_roles"]["claude"] == ["tech_lead"]
            assert loaded["agent_roles"]["kimi"] == ["backend_dev", "code_reviewer"]

    def test_backward_compatibility_legacy_format(self, monkeypatch):
        """Legacy agent_assignments format is converted to agent_roles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            os.makedirs(".agentweave", exist_ok=True)
            
            # Write legacy config
            legacy_config = {
                "version": 1,
                "agent_assignments": {
                    "claude": "tech_lead",
                    "kimi": "backend_dev"
                },
                "roles": {}
            }
            with open(".agentweave/roles.json", "w") as f:
                json.dump(legacy_config, f)
            
            loaded = load_roles_config()
            
            # Should have normalized to agent_roles
            assert "agent_roles" in loaded
            assert loaded["agent_roles"]["claude"] == ["tech_lead"]
            assert loaded["agent_roles"]["kimi"] == ["backend_dev"]


class TestRoleManagement:
    """Test adding, removing, and setting roles."""

    def test_add_role_to_agent(self):
        """Add a role to an agent."""
        config = None
        success, msg, config = add_role_to_agent("kimi", "backend_dev", config)
        
        assert success is True
        assert "Added" in msg
        assert "backend_dev" in config["agent_roles"]["kimi"]

    def test_add_multiple_roles(self):
        """Add multiple roles to an agent."""
        config = None
        config = add_role_to_agent("kimi", "backend_dev", config)[2]
        config = add_role_to_agent("kimi", "code_reviewer", config)[2]
        
        roles = get_agent_roles("kimi", config)
        assert "backend_dev" in roles
        assert "code_reviewer" in roles

    def test_add_duplicate_role_fails(self):
        """Adding a duplicate role fails."""
        config = None
        config = add_role_to_agent("kimi", "backend_dev", config)[2]
        success, msg, config = add_role_to_agent("kimi", "backend_dev", config)
        
        assert success is False
        assert "already has role" in msg

    def test_add_invalid_role_fails(self):
        """Adding an invalid role fails."""
        config = None
        success, msg, config = add_role_to_agent("kimi", "invalid_role", config)
        
        assert success is False
        assert "Invalid role" in msg

    def test_remove_role(self):
        """Remove a role from an agent."""
        config = None
        config = add_role_to_agent("kimi", "backend_dev", config)[2]
        config = add_role_to_agent("kimi", "code_reviewer", config)[2]
        
        success, msg, config = remove_role_from_agent("kimi", "backend_dev", config)
        
        assert success is True
        assert "Removed" in msg
        assert "backend_dev" not in config["agent_roles"]["kimi"]
        assert "code_reviewer" in config["agent_roles"]["kimi"]

    def test_remove_nonexistent_role_fails(self):
        """Removing a role the agent doesn't have fails."""
        config = None
        config = add_role_to_agent("kimi", "backend_dev", config)[2]
        
        success, msg, config = remove_role_from_agent("kimi", "code_reviewer", config)
        
        assert success is False
        assert "does not have role" in msg

    def test_set_agent_roles(self):
        """Set multiple roles at once."""
        config = None
        success, msg, config = set_agent_roles("claude", ["tech_lead", "architect"], config)
        
        assert success is True
        assert "tech_lead" in config["agent_roles"]["claude"]
        assert "architect" in config["agent_roles"]["claude"]

    def test_set_roles_replaces_existing(self):
        """Setting roles replaces existing roles."""
        config = None
        config = add_role_to_agent("kimi", "backend_dev", config)[2]
        config = add_role_to_agent("kimi", "code_reviewer", config)[2]
        
        success, msg, config = set_agent_roles("kimi", ["qa_engineer"], config)
        
        roles = get_agent_roles("kimi", config)
        assert roles == ["qa_engineer"]

    def test_set_roles_deduplicates(self):
        """Setting roles with duplicates removes duplicates."""
        config = None
        success, msg, config = set_agent_roles("kimi", ["backend_dev", "backend_dev", "code_reviewer"], config)
        
        roles = get_agent_roles("kimi", config)
        assert roles == ["backend_dev", "code_reviewer"]


class TestRoleValidation:
    """Test role validation."""

    def test_valid_role(self):
        """Valid roles pass validation."""
        is_valid, error = validate_role("tech_lead")
        assert is_valid is True
        assert error == ""

    def test_invalid_role(self):
        """Invalid roles fail validation."""
        is_valid, error = validate_role("invalid_role")
        assert is_valid is False
        assert "Invalid role" in error

    def test_empty_role(self):
        """Empty role fails validation."""
        is_valid, error = validate_role("")
        assert is_valid is False

    def test_get_available_roles(self):
        """Get available roles returns list."""
        roles = get_available_roles()
        assert len(roles) > 0
        
        # Each role is a tuple of (id, label, description)
        for role in roles:
            assert len(role) == 3
            assert isinstance(role[0], str)
            assert isinstance(role[1], str)


class TestAgentRolesDisplay:
    """Test role display formatting."""

    def test_format_agent_roles_with_roles(self):
        """Format agent with roles."""
        config = None
        config = add_role_to_agent("kimi", "backend_dev", config)[2]
        
        formatted = format_agent_roles("kimi", config)
        assert "Backend Developer" in formatted or "backend_dev" in formatted

    def test_format_agent_roles_no_roles(self):
        """Format agent with no roles."""
        config = {"agent_roles": {}}
        formatted = format_agent_roles("kimi", config)
        assert formatted == "none"

    def test_get_agent_roles_empty(self):
        """Get roles for agent with no roles."""
        config = {"agent_roles": {}}
        roles = get_agent_roles("kimi", config)
        assert roles == []

    def test_get_agent_roles_legacy_string(self):
        """Handle legacy string role format."""
        config = {
            "agent_roles": {
                "kimi": "backend_dev"  # Legacy: string instead of list
            }
        }
        roles = get_agent_roles("kimi", config)
        assert roles == ["backend_dev"]
