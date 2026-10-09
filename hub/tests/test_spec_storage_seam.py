"""One storage seam: no Hub module parses a stored specification file itself.

`a-spec-document-is-stored-as-its-payload` FR-4. Every reader of a document's payload goes through
`spec_documents.parse_stored` / `read_payload`, so changing what a stored file is (now `spec.json`)
is an edit to that one function. Twenty call sites parsed file content before.
"""

from __future__ import annotations

import ast
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent / "hub"

# The parser's own module, and the seam that wraps it.
ALLOWED = {"spec_payload.py", "spec_documents.py"}


def _calls_extract_payload(source: str) -> list:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "extract_payload":
                found.append(node.lineno)
    return found


def test_only_the_seam_parses_a_stored_file():
    offenders = {}
    for path in sorted(HUB.rglob("*.py")):
        if path.name in ALLOWED and path.parent == HUB:
            continue
        lines = _calls_extract_payload(path.read_text(encoding="utf-8"))
        if lines:
            offenders[path.relative_to(HUB).as_posix()] = lines
    assert offenders == {}, (
        "parse a stored document through spec_documents.parse_stored / read_payload, "
        f"not extract_payload: {offenders}"
    )


def test_the_seam_reads_what_a_save_wrote(tmp_path):
    from hub.project_workspace import ProjectWorkspace
    from hub.spec_documents import parse_stored, read_payload, write_payload

    stored = {
        "schema_version": 1,
        "kind": "change-spec",
        "title": "A ping route",
        "summary": "Answer ping.",
        "requirements": [{"key": "pong", "statement": "The service MUST answer.", "modal": "MUST"}],
    }
    workspace = ProjectWorkspace(project_id="p", root=tmp_path, path_key="test:p")
    hub = {"phase": "exploring", "rigor": "sketch", "step": "intake", "size": None}
    content = write_payload(workspace, "spec/changes/ping/spec.json", stored, hub)

    assert read_payload(workspace, "spec/changes/ping/spec.json") == stored
    assert parse_stored(content) == stored
    assert read_payload(workspace, "spec/changes/absent/spec.json") is None
    assert parse_stored(None) is None and parse_stored("") is None
