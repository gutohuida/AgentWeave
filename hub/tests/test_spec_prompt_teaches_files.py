"""A planner is told to declare `files` and chain same-file tasks with `depends_on`.

Slice 1b (F509): the teaching text lived only where aw-tool agents never read it. Both the
exploring duty and the `submit_spec_document` entry of the tool section must carry the step, in
every rendering a run can be handed.
"""

import pytest

from hub.api.v1.agents import SPEC_PHASE_DUTIES, _operations, _tool_surface_lines


def _submit_entry(access_path: str) -> str:
    """The `submit_spec_document` entry: from its own line up to the next operation's."""
    tools = [op.tool for op in _operations()]
    following = tools[tools.index("submit_spec_document") + 1]
    lines = _tool_surface_lines(access_path=access_path)
    start = next(
        i
        for i, line in enumerate(lines)
        if line.startswith("- ") and "submit_spec_document" in line
    )
    end = next(
        (
            i
            for i, line in enumerate(lines)
            if i > start and line.startswith("- ") and following in line
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def test_exploring_duty_teaches_files_and_depends_on():
    duty = SPEC_PHASE_DUTIES["exploring"]
    assert "`files`" in duty
    assert "`depends_on`" in duty
    assert "share a path" in duty


@pytest.mark.parametrize("access_path", ["shim", "mcp", "http"])
def test_submit_entry_names_task_fields(access_path):
    entry = _submit_entry(access_path)
    assert "`depends_on`" in entry
    assert "`files`" in entry
