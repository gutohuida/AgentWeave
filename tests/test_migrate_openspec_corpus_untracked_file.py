"""F1095: the corpus importer reads only `document_exists` as "already imported".

A 409 for a file the Hub has no row for (`untracked_file_exists`) is a refusal: the file is not
the importer's, and its payload is not to be written over it.
"""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_openspec_corpus.py"
spec = importlib.util.spec_from_file_location("migrate_openspec_corpus", SCRIPT)
mc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mc
spec.loader.exec_module(mc)


def _import(monkeypatch, create_answer):
    calls = []

    def call(self, method, path, payload=None):
        calls.append((method, path))
        return create_answer if method == "POST" else (200, {"identifiers": {}})

    monkeypatch.setattr(mc.Hub, "_call", call)
    hub = mc.Hub("http://hub", "proj", "key")
    capability = mc.Capability(name="x", title="X", summary="")
    return hub.import_capability(capability, {"title": "X"}), calls


def test_an_untracked_file_refusal_is_not_read_as_already_imported(monkeypatch):
    refusal = (409, {"detail": {"code": "untracked_file_exists", "message": "m"}})
    (ok, message), calls = _import(monkeypatch, refusal)
    assert ok is False and "409" in message
    assert [method for method, _ in calls] == ["POST"]  # nothing was written


def test_a_tracked_document_is_still_already_imported(monkeypatch):
    exists = (409, {"detail": {"code": "document_exists", "message": "m"}})
    (ok, _), calls = _import(monkeypatch, exists)
    assert ok is True
    assert [method for method, _ in calls] == ["POST", "PUT"]
