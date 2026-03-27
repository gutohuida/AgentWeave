"""Templates for AgentWeave.

This module contains markdown templates for common collaboration scenarios.
"""

from pathlib import Path

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
        return template_file.read_text()
    raise FileNotFoundError(f"Template not found: {name}")


def list_templates() -> list:
    """List available templates.

    Returns:
        List of template names
    """
    return [f.stem for f in TEMPLATES_DIR.glob("*.md")]


SKILLS_DIR = TEMPLATES_DIR / "skills"


def get_skill_template(name: str) -> str:
    """Get a skill template by name.

    Args:
        name: Skill name (e.g., 'aw-delegate', 'aw-status')

    Returns:
        Skill template content as string
    """
    template_file = SKILLS_DIR / f"{name}.md"
    if template_file.exists():
        return template_file.read_text()
    raise FileNotFoundError(f"Skill template not found: {name}")


def list_skill_templates() -> list:
    """List available skill templates.

    Returns:
        List of skill template names
    """
    if not SKILLS_DIR.exists():
        return []
    return [f.stem for f in SKILLS_DIR.glob("*.md")]


__all__ = [
    "get_template",
    "list_templates",
    "get_skill_template",
    "list_skill_templates",
    "TEMPLATES_DIR",
    "SKILLS_DIR",
]
