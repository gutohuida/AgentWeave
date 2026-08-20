"""The index must be writable, and the two implementations must agree on what it may say.

Two properties are asserted here that nothing asserted before:

1. **Round trip.** `load_manifest(dump_manifest(m))` returns `m`. Before this change there was no
   writer at all — every reference to `index.json` in the repository was a read — so a format the
   product could parse but never produce went unnoticed for three weeks.

2. **Twin agreement.** `hub/hub/spec_manifest.py` and `src/agentweave/spec_manifest.py` are kept in
   sync by hand and deliberately have no import relationship (CLAUDE.md). That rule had no test,
   and the cost was concrete: *both* twins carried the identical `VALID_KINDS` omission that made
   every capability document unindexable. A test is the only thing that can hold two copies
   together, and importing both is legitimate here precisely because observing both sides is the
   job.
"""

from __future__ import annotations

import json

import pytest

from agentweave import spec_manifest as cli_manifest
from hub import spec_manifest as hub_manifest

MODULES = [
    pytest.param(hub_manifest, id="hub"),
    pytest.param(cli_manifest, id="cli"),
]


def _document(module, path, kind, status, *, parent=None, order=10):
    return module.ManifestDocument(
        path=path,
        title=path.rsplit("/", 1)[-1],
        kind=kind,
        status=status,
        parent=parent,
        order=order,
    )


def _legal_pairs(module):
    """Every kind/phase combination the product can actually produce."""
    return [
        (kind, phase)
        for kind in sorted(module.VALID_KINDS)
        for phase in sorted(module.permitted_phases(kind))
    ]


class TestTwinAgreement:
    def test_the_two_implementations_accept_the_same_kinds(self):
        assert hub_manifest.VALID_KINDS == cli_manifest.VALID_KINDS

    def test_the_two_implementations_accept_the_same_phases(self):
        assert hub_manifest.VALID_PHASES == cli_manifest.VALID_PHASES

    def test_the_two_implementations_pair_kinds_and_phases_identically(self):
        for kind in sorted(hub_manifest.VALID_KINDS):
            assert hub_manifest.permitted_phases(kind) == cli_manifest.permitted_phases(kind), kind

    def test_the_vocabulary_matches_the_hubs_lifecycle(self):
        """The phases are restated in both twins rather than imported, so they can drift from the
        lifecycle itself. This is the assertion that catches that — if a future change lets a
        capability be archived, this fails rather than the index silently being over-strict."""
        from hub import spec_lifecycle

        lifecycle_phases = {
            spec_lifecycle.EXPLORING,
            spec_lifecycle.PROPOSED,
            spec_lifecycle.APPROVED,
            spec_lifecycle.ARCHIVED,
        }
        assert lifecycle_phases == hub_manifest.LIFECYCLE_PHASES
        assert hub_manifest.CURRENT == spec_lifecycle.CURRENT
        # A capability's phase set is `{current}` only because no transition leaves it. If one is
        # ever added, this is the tripwire.
        assert not any(source == spec_lifecycle.CURRENT for source, _ in spec_lifecycle.TRANSITIONS)


@pytest.mark.parametrize("module", MODULES)
class TestRoundTrip:
    def test_every_legal_kind_and_phase_survives_a_round_trip(self, module):
        documents = [
            _document(module, f"spec/doc-{index}.html", kind, phase, order=index * 10)
            for index, (kind, phase) in enumerate(_legal_pairs(module))
        ]
        original = module.build_manifest(documents, home=documents[0].path)
        assert original is not None

        parsed, diagnostics = module.load_manifest(module.dump_manifest(original))
        assert diagnostics == []
        assert parsed == original

    def test_parent_and_order_survive_a_round_trip(self, module):
        parent = _document(module, "spec/parent.html", "baseline", "approved", order=10)
        child = _document(
            module, "spec/child.html", "change-spec", "proposed", parent=parent.path, order=20
        )
        original = module.build_manifest([parent, child], home=parent.path)
        parsed, _ = module.load_manifest(module.dump_manifest(original))

        assert parsed is not None
        assert parsed.by_path()["spec/child.html"].parent == "spec/parent.html"
        assert parsed.by_path()["spec/child.html"].order == 20

    def test_dumping_is_byte_stable(self, module):
        """A rebuild that changed nothing must produce an identical file, or every rebuild looks
        like an edit to whatever is watching the tree — git included."""
        documents = [
            _document(module, "spec/a.html", "capability", "current", order=10),
            _document(module, "spec/b.html", "change-spec", "archived", order=20),
        ]
        manifest = module.build_manifest(documents, home="spec/a.html")
        assert module.dump_manifest(manifest) == module.dump_manifest(manifest)

    def test_dump_is_valid_json_ending_in_a_newline(self, module):
        manifest = module.build_manifest(
            [_document(module, "spec/a.html", "capability", "current")], home="spec/a.html"
        )
        text = module.dump_manifest(manifest)
        assert text.endswith("\n")
        assert json.loads(text)["version"] == module.MANIFEST_VERSION

    def test_build_manifest_refuses_a_home_it_does_not_hold(self, module):
        """`build_manifest` never invents a home. The reader refuses to guess one on the grounds
        that a guess is indistinguishable from an operator's decision; the writer must not smuggle
        in the choice the reader declines to make."""
        documents = [_document(module, "spec/a.html", "capability", "current")]
        assert module.build_manifest(documents, home=None) is None
        assert module.build_manifest(documents, home="spec/missing.html") is None

    def test_build_manifest_refuses_an_empty_corpus(self, module):
        assert module.build_manifest([], home=None) is None


@pytest.mark.parametrize("module", MODULES)
def test_a_manifest_written_by_one_twin_parses_in_the_other(module):
    """The round trip must cross the module boundary, not just close within one twin."""
    other = cli_manifest if module is hub_manifest else hub_manifest
    documents = [
        _document(module, f"spec/doc-{index}.html", kind, phase, order=index * 10)
        for index, (kind, phase) in enumerate(_legal_pairs(module))
    ]
    text = module.dump_manifest(module.build_manifest(documents, home=documents[0].path))

    parsed, diagnostics = other.load_manifest(text)
    assert diagnostics == []
    assert parsed is not None
    assert len(parsed.documents) == len(documents)
