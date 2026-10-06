"""An agent drafting a spec is told about `depends_on` and the shared-file rule.

Change `same-file-tasks-build-in-order`, task docs-name-depends-on: the guidance an agent reads while
exploring (the `submit_spec_document` description and the exploring duty) must name `depends_on` and
say same-file tasks are chained, or the agent never writes the dependency the flow honours.
"""

import re

from hub.api.v1.agents import SPEC_PHASE_DUTIES


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _assert_taught(text: str) -> None:
    flat = _flat(text)
    assert "depends_on" in flat
    assert re.search(r"same file.*chained|same-file tasks are (built in order|chained)", flat)


def test_submit_spec_document_description_teaches_depends_on():
    from hub.mcp_server import submit_spec_document

    fn = getattr(submit_spec_document, "fn", submit_spec_document)
    _assert_taught(fn.__doc__)


def test_exploring_duty_teaches_depends_on():
    _assert_taught(SPEC_PHASE_DUTIES["exploring"])
