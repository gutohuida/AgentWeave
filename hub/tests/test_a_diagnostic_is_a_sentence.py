"""F643: refusals and diagnostics in the corpus and drift routes say what is wrong in a sentence.

Drift resolve answered "unknown resolution 'whatever'" naming none of the three it accepts;
arrange answered "this placement is not allowed" with only a code; the Spec page's drift strip
printed `unfiled_document — <path>`. Every diagnostic now carries a `message` beside its code.
"""

from types import SimpleNamespace

import pytest

from hub import requirement_evidence
from hub.spec_documents import _diag
from hub.spec_lifecycle import Actor
from hub.spec_manifest import ManifestDiagnostic


def test_unfiled_and_missing_documents_are_described():
    unfiled = _diag("unfiled_document", path="spec/changes/x/spec.json")
    assert "spec/changes/x/spec.json" in unfiled["message"]
    assert "not in the index" in unfiled["message"]
    missing = _diag("missing_document", path="spec/gone.json")
    assert "spec/gone.json" in missing["message"] and "no file" in missing["message"]


def test_a_metadata_conflict_names_the_field_and_both_values():
    message = ManifestDiagnostic(
        code="intrinsic_metadata_conflict",
        path="spec/a.json",
        field="status",
        expected="exploring",
        actual="approved",
    ).to_dict()["message"]
    assert "status" in message and "exploring" in message and "approved" in message


def test_an_unknown_code_still_reads_as_a_sentence():
    message = ManifestDiagnostic(code="manifest_something_new", path="spec/a.json").to_dict()[
        "message"
    ]
    assert "spec/a.json" in message


@pytest.mark.asyncio
async def test_an_unknown_drift_resolution_names_the_ones_it_accepts():
    with pytest.raises(requirement_evidence.EvidenceRefusedError) as refusal:
        await requirement_evidence.resolve_drift(
            None,
            SimpleNamespace(state="candidate"),
            resolution="whatever",
            actor=Actor(kind="operator", name="operator"),
        )
    text = str(refusal.value)
    for word in ("specification_updated", "implementation_corrected", "no_change_required"):
        assert word in text
