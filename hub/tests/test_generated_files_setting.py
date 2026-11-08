"""The generated-files setting is the operator's alone (`generated-files-are-rebuilt-when-work-lands-
instead-of-sending-it-back`, FR-1, FR-2)."""

import pytest
from pydantic import ValidationError

from hub.api.v1.projects import GeneratedFiles, ProjectSettings, ProjectSettingsUpdate
from hub.db.models import Project


def test_defaults_and_cleaning():
    value = GeneratedFiles(paths=[" gen.txt ", "gen.txt", "dist\**"], command=" py gen.py ")
    assert value.paths == ["gen.txt", "dist/**"]
    assert value.command == "py gen.py"
    assert value.timeout_seconds == 600


@pytest.mark.parametrize(
    "bad",
    [
        {"paths": [], "command": "x"},
        {"paths": ["  "], "command": "x"},
        {"paths": ["/abs"], "command": "x"},
        {"paths": ["../up"], "command": "x"},
        {"paths": ["a"], "command": "  "},
        {"paths": ["a"], "command": "x", "timeout_seconds": 0},
        {"paths": ["a"], "command": "x", "timeout_seconds": 3601},
        {"paths": ["a"], "command": "x", "extra": 1},
    ],
)
def test_bad_shapes_are_refused(bad):
    with pytest.raises(ValidationError):
        GeneratedFiles(**bad)


def test_unset_is_null_and_round_trips_through_the_settings_model():
    assert Project.__table__.c.generated_files.nullable
    assert ProjectSettings.model_fields["generated_files"].default is None
    assert "generated_files" in ProjectSettingsUpdate.model_fields


def test_agent_surfaces_do_not_mention_the_setting():
    import pathlib

    root = pathlib.Path(__file__).parent.parent / "hub"
    for rel in ("mcp_server.py", "api/v1/agent_actions.py", "api/v1/agents.py"):
        assert "generated_files" not in (root / rel).read_text(encoding="utf-8"), rel
