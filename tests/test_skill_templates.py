"""Tests for generated AgentWeave skill templates."""

from agentweave.cli import _generate_claude_skills, _generate_codex_skills
from agentweave.session import Session
from agentweave.templates import get_skill_template, list_skill_templates


def test_aw_spec_technical_explore_template_is_listed():
    skills = list_skill_templates()

    assert "aw-spec-technical-explore" in skills

    template = get_skill_template("aw-spec-technical-explore")
    assert "name: aw-spec-technical-explore" in template
    assert "/aw-spec-propose" in template


def test_skill_generation_includes_aw_spec_technical_explore(tmp_path):
    session = Session.create(
        name="SkillProject",
        principal="claude",
        agents=["claude", "codex"],
    )

    claude_count = _generate_claude_skills(session, tmp_path)
    codex_count = _generate_codex_skills(session, tmp_path)

    claude_skill = tmp_path / ".claude" / "skills" / "aw-spec-technical-explore" / "SKILL.md"
    codex_skill = tmp_path / ".agents" / "skills" / "aw-spec-technical-explore" / "SKILL.md"

    assert claude_count > 0
    assert codex_count > 0
    assert claude_skill.exists()
    assert codex_skill.exists()
    assert "SkillProject" in claude_skill.read_text(encoding="utf-8")
    assert "SkillProject" in codex_skill.read_text(encoding="utf-8")
