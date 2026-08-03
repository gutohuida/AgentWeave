"""Templates for AgentWeave.

This module contains markdown templates for common collaboration scenarios.
"""

from pathlib import Path
from typing import List

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


__all__ = [
    "get_template",
    "list_templates",
    "get_skill_template",
    "list_skill_templates",
    "get_skill_reference",
    "TEMPLATES_DIR",
    "SKILLS_DIR",
    "SKILL_REFERENCES_DIR",
]
