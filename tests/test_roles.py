"""Tests for the roles module."""

import json
import os

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

    def test_load_nonexistent_config(self, tmp_path, monkeypatch):
        """Loading a non-existent config returns None."""
        monkeypatch.chdir(tmp_path)
        os.makedirs(".agentweave", exist_ok=True)
        result = load_roles_config()
        assert result is None

    def test_save_and_load_config(self, tmp_path, monkeypatch):
        """Save and load a config."""
        monkeypatch.chdir(tmp_path)
        os.makedirs(".agentweave", exist_ok=True)

        config = {
            "version": 2,
            "agent_roles": {"claude": ["tech_lead"], "kimi": ["backend_dev", "code_reviewer"]},
            "roles": {},
        }

        save_roles_config(config)
        loaded = load_roles_config()

        assert loaded["version"] == 2
        assert loaded["agent_roles"]["claude"] == ["tech_lead"]
        assert loaded["agent_roles"]["kimi"] == ["backend_dev", "code_reviewer"]

    def test_backward_compatibility_legacy_format(self, tmp_path, monkeypatch):
        """Legacy agent_assignments format is converted to agent_roles."""
        monkeypatch.chdir(tmp_path)
        os.makedirs(".agentweave", exist_ok=True)

        # Write legacy config
        legacy_config = {
            "version": 1,
            "agent_assignments": {"claude": "tech_lead", "kimi": "backend_dev"},
            "roles": {},
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
        success, msg, config = set_agent_roles(
            "kimi", ["backend_dev", "backend_dev", "code_reviewer"], config
        )

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
        config = {"agent_roles": {"kimi": "backend_dev"}}  # Legacy: string instead of list
        roles = get_agent_roles("kimi", config)
        assert roles == ["backend_dev"]


AI_NATIVE_ROLE_IDS = [
    "coordinator",
    "model_router",
    "explorer",
    "implementer",
    "verifier",
    "guardian",
    "context_keeper",
]

ROLE_SKELETON_SECTIONS = [
    "## You Are Responsible For",
    "## You Are NOT Responsible For",
    "## Behavioral Rules",
    "## Anti-Patterns",
    "## Escalation Path",
]


class TestAINativeRoles:
    """Test the AI-native (function-first) roles added alongside the human-title roles."""

    def test_valid_role_ids_single_source_of_truth(self):
        """roles.py re-exports the canonical VALID_ROLE_IDS from constants.py."""
        from agentweave.constants import VALID_ROLE_IDS as CONSTANTS_IDS
        from agentweave.roles import VALID_ROLE_IDS as ROLES_IDS

        # Same object — defined once in constants.py, imported by roles.py.
        assert ROLES_IDS is CONSTANTS_IDS

    def test_all_new_roles_in_valid_role_ids(self):
        """All seven AI-native role IDs are registered as valid."""
        from agentweave.constants import VALID_ROLE_IDS

        for role_id in AI_NATIVE_ROLE_IDS:
            assert role_id in VALID_ROLE_IDS

    def test_human_title_roles_still_present(self):
        """The 13 human-title roles remain valid (additive, non-breaking)."""
        from agentweave.constants import VALID_ROLE_IDS

        for role_id in [
            "tech_lead",
            "architect",
            "backend_dev",
            "frontend_dev",
            "fullstack_dev",
            "qa_engineer",
            "devops_engineer",
            "security_engineer",
            "data_engineer",
            "ml_engineer",
            "technical_writer",
            "code_reviewer",
            "project_manager",
        ]:
            assert role_id in VALID_ROLE_IDS

    def test_roles_json_entries_well_formed(self):
        """Each new role has a well-formed roles.json entry with _default_for: []."""
        from agentweave.templates import load_roles_template

        roles = load_roles_template()["roles"]
        for role_id in AI_NATIVE_ROLE_IDS:
            assert role_id in roles, f"{role_id} missing from roles.json"
            entry = roles[role_id]
            assert entry["label"]
            assert entry["version"] == 1
            assert entry["responsibilities_short"]
            assert entry["file"] == f"roles/{role_id}.md"
            assert entry["_default_for"] == []

    def test_no_agent_auto_assigned_new_role(self):
        """No known agent is defaulted to any of the new AI-native roles."""
        from agentweave.templates import load_roles_template

        roles = load_roles_template()["roles"]
        for role_id, entry in roles.items():
            if role_id in AI_NATIVE_ROLE_IDS:
                assert entry["_default_for"] == [], f"{role_id} must not be a default"

    def test_new_roles_pass_validation(self):
        """Each new role ID passes validate_role()."""
        for role_id in AI_NATIVE_ROLE_IDS:
            is_valid, error = validate_role(role_id)
            assert is_valid is True, f"{role_id}: {error}"

    def test_get_available_roles_lists_all_twenty(self):
        """get_available_roles() returns all 20 roles (13 human + 7 AI-native)."""
        role_ids = [r[0] for r in get_available_roles()]
        for role_id in AI_NATIVE_ROLE_IDS:
            assert role_id in role_ids
        assert len(role_ids) == 20

    def test_role_md_files_load_with_skeleton(self):
        """Each new role .md loads and contains all six skeleton sections."""
        from agentweave.templates import get_role_md

        for role_id in AI_NATIVE_ROLE_IDS:
            content = get_role_md(role_id)
            assert content.startswith("# "), f"{role_id} missing title heading"
            assert "> **Scope:**" in content, f"{role_id} missing Scope blockquote"
            for section in ROLE_SKELETON_SECTIONS:
                assert section in content, f"{role_id} missing section: {section}"

    def test_assign_new_role_copies_md_file(self, tmp_path, monkeypatch):
        """Assigning a new role copies its .md guide to .agentweave/roles/."""
        from agentweave.roles import copy_role_md_file

        monkeypatch.chdir(tmp_path)
        os.makedirs(".agentweave", exist_ok=True)

        for role_id in AI_NATIVE_ROLE_IDS:
            assert copy_role_md_file(role_id) is True
            copied = tmp_path / ".agentweave" / "roles" / f"{role_id}.md"
            assert copied.exists(), f"{role_id}.md was not copied"
            assert "> **Scope:**" in copied.read_text(encoding="utf-8")

    def test_set_agent_roles_accepts_new_roles(self):
        """set_agent_roles accepts the new roles and records role definitions."""
        config = None
        success, msg, config = set_agent_roles(
            "router-agent", ["model_router", "coordinator"], config
        )
        assert success is True
        roles = get_agent_roles("router-agent", config)
        assert "model_router" in roles
        assert "coordinator" in roles

    def test_model_router_can_layer_on_domain_role(self):
        """AI-native and human-title roles can be combined on one agent (add-on pattern)."""
        config = None
        config = add_role_to_agent("worker", "implementer", config)[2]
        success, msg, config = add_role_to_agent("worker", "frontend_dev", config)
        assert success is True
        roles = get_agent_roles("worker", config)
        assert "implementer" in roles
        assert "frontend_dev" in roles
