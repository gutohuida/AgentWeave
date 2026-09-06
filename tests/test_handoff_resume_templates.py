"""Distribution contracts for the agent-agnostic handoff/resume skill pair."""

from agentweave.templates import get_skill_template, list_skill_templates


def test_handoff_and_resume_are_packaged_skill_templates():
    names = set(list_skill_templates())

    assert {"handoff", "resume"} <= names


def test_handoff_template_has_valid_discovery_metadata_and_durable_contract():
    template = get_skill_template("handoff")

    assert template.startswith("---\nname: handoff\n")
    assert "description:" in template.split("---", 2)[1]
    assert "handoff-NNNN" in template
    assert "DEAD-ENDS.md" in template
    assert "Git state" in template
    assert "Pairs with /resume" in template


def test_resume_template_has_valid_discovery_metadata_and_reality_check():
    template = get_skill_template("resume")

    assert template.startswith("---\nname: resume\n")
    assert "description:" in template.split("---", 2)[1]
    assert "handoff-*.md" in template
    assert "DEAD-ENDS.md" in template
    assert "git status --short" in template
    assert "Pairs with /handoff" in template
