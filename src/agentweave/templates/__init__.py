"""Templates for AgentWeave.

This module contains markdown templates for common collaboration scenarios.
"""

from pathlib import Path
from typing import Any, Dict, List

TEMPLATES_DIR = Path(__file__).parent


def get_template(name: str) -> str:
    """Get a template by name.

    Args:
        name: Template name (e.g., 'task_delegation', 'review_request')

    Returns:
        Template content as string
    """
    template_file = TEMPLATES_DIR / f"{name}.md"
    if template_file.exists():
        return template_file.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Template not found: {name}")


def list_templates() -> List[str]:
    """List available templates.

    Returns:
        List of template names
    """
    return [f.stem for f in TEMPLATES_DIR.glob("*.md")]


SKILLS_DIR = TEMPLATES_DIR / "skills"
SKILL_REFERENCES_DIR = SKILLS_DIR / "references"
ROLES_TEMPLATES_DIR = TEMPLATES_DIR / "roles"


def get_skill_template(name: str) -> str:
    """Get a skill template by name.

    Args:
        name: Skill name (e.g., 'aw-delegate', 'aw-status')

    Returns:
        Skill template content as string
    """
    template_file = SKILLS_DIR / f"{name}.md"
    if template_file.exists():
        return template_file.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Skill template not found: {name}")


def list_skill_templates() -> List[str]:
    """List available skill templates.

    Returns:
        List of skill template names
    """
    if not SKILLS_DIR.exists():
        return []
    return [f.stem for f in SKILLS_DIR.glob("*.md")]


def get_skill_reference(filename: str) -> str:
    """Get the content of a bundled skill reference document.

    Reference documents live in ``templates/skills/references/`` and are NOT
    skills themselves (``list_skill_templates`` only globs the top level).
    They are copied alongside the skills that link to them at generation time.

    Args:
        filename: Reference file name (e.g., 'html-spec-conventions.md')

    Returns:
        Reference document content as string
    """
    ref_file = SKILL_REFERENCES_DIR / filename
    if ref_file.exists():
        return ref_file.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Skill reference not found: {filename}")


def load_roles_template() -> Dict[str, Any]:
    """Load the roles config template (roles.json) from the package.

    Returns:
        Parsed JSON dict with all role definitions and metadata.
    """
    import json

    config_file = ROLES_TEMPLATES_DIR / "roles.json"
    if not config_file.exists():
        raise FileNotFoundError("templates/roles/roles.json not found in package")
    return json.loads(config_file.read_text(encoding="utf-8"))


def get_role_md(role_id: str) -> str:
    """Get the markdown behavioral guide for a role.

    Args:
        role_id: Role key (e.g., 'tech_lead', 'backend_dev')

    Returns:
        Role markdown content as string
    """
    role_file = ROLES_TEMPLATES_DIR / f"{role_id}.md"
    if role_file.exists():
        return role_file.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Role file not found: {role_id}.md")


__all__ = [
    "get_template",
    "list_templates",
    "get_skill_template",
    "list_skill_templates",
    "get_skill_reference",
    "load_roles_template",
    "get_role_md",
    "TEMPLATES_DIR",
    "SKILLS_DIR",
    "SKILL_REFERENCES_DIR",
    "ROLES_TEMPLATES_DIR",
]
