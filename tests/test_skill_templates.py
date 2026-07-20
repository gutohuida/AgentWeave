"""Tests for generated AgentWeave skill templates."""

from agentweave.cli import _generate_claude_skills, _generate_codex_skills
from agentweave.session import Session
from agentweave.templates import (
    get_skill_reference,
    get_skill_template,
    list_skill_templates,
)

SETUP_SKILLS = [
    "aw-setup",
    "aw-setup-agent",
    "aw-setup-hub",
    "aw-setup-transport",
    "aw-setup-roles",
    "aw-setup-proxy",
    "aw-setup-security",
]


def test_setup_skill_templates_are_listed():
    skills = list_skill_templates()

    for name in SETUP_SKILLS:
        assert name in skills, f"missing setup skill template: {name}"
        template = get_skill_template(name)
        assert f"name: {name}" in template
        assert "description:" in template


def test_setup_skill_templates_reference_real_commands():
    assert "agentweave activate" in get_skill_template("aw-setup")
    assert "agentweave hub start" in get_skill_template("aw-setup-hub")
    assert "transport setup --type git" in get_skill_template("aw-setup-transport")
    assert "roles set" in get_skill_template("aw-setup-roles")
    assert "--runner claude_proxy" in get_skill_template("aw-setup-proxy")
    assert "agent configure" in get_skill_template("aw-setup-agent")


def test_setup_security_skill_covers_quality_guards():
    template = get_skill_template("aw-setup-security")
    assert "echo_chamber_guard" in template
    assert "dependency_check" in template
    assert "review_required" in template
    assert "attribution_tag" in template
    assert "guardian" in template


def test_skill_generation_includes_setup_skills(tmp_path):
    session = Session.create(
        name="SetupProject",
        principal="claude",
        agents=["claude", "kimi"],
    )

    _generate_claude_skills(session, tmp_path)
    _generate_codex_skills(session, tmp_path)

    for name in SETUP_SKILLS:
        claude_skill = tmp_path / ".claude" / "skills" / name / "SKILL.md"
        codex_skill = tmp_path / ".agents" / "skills" / name / "SKILL.md"
        assert claude_skill.exists(), f"missing .claude skill: {name}"
        assert codex_skill.exists(), f"missing .agents skill: {name}"
        assert "SetupProject" in claude_skill.read_text(encoding="utf-8")
        assert "SetupProject" in codex_skill.read_text(encoding="utf-8")


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


def test_reference_docs_are_not_listed_as_skills():
    # Files under templates/skills/references/ are reference docs, not skills.
    skills = list_skill_templates()
    assert "html-spec-conventions" not in skills


def test_html_spec_conventions_reference_is_available():
    ref = get_skill_reference("html-spec-conventions.md")
    assert "aw-spec-status" in ref
    assert "data-status" in ref
    assert "data-requirements" in ref


def test_propose_skill_targets_html_spec_and_approval_gate():
    template = get_skill_template("aw-spec-propose")
    assert "spec.html" in template
    # HTML replaces the old markdown artifacts.
    assert "replaces" in template
    # SDD conventions and approval gate must be present.
    assert "FR-" in template
    assert "aw-spec-status" in template
    assert "Approval" in template or "approval" in template


def test_apply_skill_enforces_hard_approval_gate():
    template = get_skill_template("aw-spec-apply")
    assert "spec.html" in template
    assert 'aw-spec-status="approved"' in template
    # Task state is tracked inside the HTML.
    assert "data-status" in template


def test_archive_skill_reads_html_spec():
    template = get_skill_template("aw-spec-archive")
    assert "spec.html" in template
    assert "data-status" in template


def test_skill_generation_bundles_html_spec_reference(tmp_path):
    session = Session.create(
        name="RefProject",
        principal="claude",
        agents=["claude", "codex"],
    )

    _generate_claude_skills(session, tmp_path)
    _generate_codex_skills(session, tmp_path)

    for root, marker in (
        (tmp_path / ".claude" / "skills", "claude"),
        (tmp_path / ".agents" / "skills", "codex"),
    ):
        for skill in ("aw-spec-propose", "aw-spec-apply", "aw-spec-archive"):
            ref = root / skill / "html-spec-conventions.md"
            assert ref.exists(), f"{marker}: missing reference in {skill}"
            assert "aw-spec-status" in ref.read_text(encoding="utf-8")

    # A skill without declared support files should not get the reference doc.
    assert not (
        tmp_path / ".claude" / "skills" / "aw-spec-explore" / "html-spec-conventions.md"
    ).exists()
