"""F1132: a task view reads the spec documents behind it off the event loop.

`_attach_requirements`, which every task view runs, read each linked document on the loop's thread
(`spec_reading.payloads_for_documents`: a `realpath` and a full `read_text` per document), and a
task move asked `slice_drafting.offer_for`, which read one more. Idle that is well under a
millisecond; on a busy disk it held the whole Hub 265 ms. Whether a read runs on the loop's thread
does not depend on the machine, so that is what this counts.
"""

from __future__ import annotations

import threading

import pytest

from hub import spec_documents

from .test_task_integration import (  # noqa: F401 -- `builder` is a fixture
    TASKS,
    builder,
    linked_task,
    make_document,
)


@pytest.mark.asyncio
async def test_viewing_and_moving_a_task_reads_its_documents_off_the_loop(
    app, auth_headers, builder, monkeypatch  # noqa: F811
):
    await make_document(app, auth_headers, builder)
    task = await linked_task(app, auth_headers)

    loop_thread = threading.current_thread()
    reads: "list[tuple[str, bool]]" = []
    real = spec_documents.read_document

    def spy(workspace, path):  # noqa: ANN001, ANN202
        reads.append((path, threading.current_thread() is loop_thread))
        return real(workspace, path)

    monkeypatch.setattr(spec_documents, "read_document", spy)

    viewed = await app.get(f"{TASKS}/{task}", headers=auth_headers)
    listed = await app.get(TASKS, headers=auth_headers)
    moved = await app.patch(f"{TASKS}/{task}", json={"status": "rejected"}, headers=auth_headers)

    assert viewed.status_code == 200, viewed.text
    assert listed.status_code == 200, listed.text
    assert moved.status_code == 200, moved.text
    # The wording still comes from the document.
    assert viewed.json()["requirement_links"][0]["statement"] == "It lists what is due today"
    assert reads, "no document was read: this test exercised nothing"
    assert not [path for path, on_loop in reads if on_loop], reads
