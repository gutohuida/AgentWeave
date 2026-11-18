"""delivered-text (`reference-a-spec-in-a-sentence-from-the-composer`, FR-6): a message carrying a
spec reference reaches the timeline and the runner's prompt as plain text naming the kind, the
document's id and its send-time title, with none of the document's contents and no leading at-sign.
"""

import pytest

from hub.db.models import InboundQueueEntry
from hub.inbound_queue import format_turn_prompt

from .test_agent_chat import _add_queue_entry, _add_run, _by_id, _project_id

DOCUMENT_ID = "spdoc-407caf5abcdb"
TITLE = "The spec header, redesigned"
STATEMENT = "The header SHALL show the document's phase beside its title."
REFERENCE = f"[spec: {TITLE}]({DOCUMENT_ID})"
SENT = f"The spec {REFERENCE} has issues"


def _assert_reference_only(text: str) -> None:
    assert REFERENCE in text
    assert "spec" in text and DOCUMENT_ID in text and TITLE in text
    assert STATEMENT not in text
    assert not REFERENCE.startswith("@")
    assert "@" + REFERENCE not in text and r"\@" not in text


@pytest.mark.asyncio
async def test_the_timeline_entry_carries_kind_id_and_title(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_spec_ref"
    await _add_run(project_id, run_id="run-spec-ref", agent=agent, session_id="sess-spec-ref")
    await _add_queue_entry(
        project_id,
        entry_id="entry-spec-ref",
        agent=agent,
        origin_type="operator",
        content=SENT,
        run_id="run-spec-ref",
    )
    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-spec-ref", headers=auth_headers
    )
    assert resp.status_code == 200
    entry = _by_id(resp.json()["entries"], "entry-spec-ref")
    assert entry["kind"] == "operator_input"
    assert entry["content"] == SENT
    _assert_reference_only(entry["content"])


def test_the_delivered_prompt_carries_kind_id_and_title():
    entry = InboundQueueEntry(
        id="e-spec-ref",
        project_id="p",
        agent="a",
        origin_type="operator",
        content=SENT,
        hop_depth=0,
    )
    prompt = format_turn_prompt([entry])
    assert prompt.endswith(f"Operator (hop 0):\n{SENT}")
    _assert_reference_only(prompt)
