"""The index must be writable, and say only what the product can produce.

Asserted here:

1. **Round trip.** `load_manifest(dump_manifest(m))` returns `m`. Before this change there was no
   writer at all — every reference to `index.json` in the repository was a read — so a format the
   product could parse but never produce went unnoticed for three weeks.

The CLI twin (`src/agentweave/spec_manifest.py`) had no importer and was deleted with its
agreement tests (`a-spec-document-is-stored-as-its-payload` D6); the vocabulary check against the
lifecycle stays.
"""

from __future__ import annotations

import json

import pytest

from hub import spec_manifest as hub_manifest

MODULES = [
    pytest.param(hub_manifest, id="hub"),
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


class TestVocabulary:
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
        # A capability holds `current` and wherever a transition from `current` leads (F536 added
        # `archived`). Any further edge out of `current` must be mirrored here, or this trips.
        reachable = {to for source, to in spec_lifecycle.TRANSITIONS if source == "current"}
        capability_phases = hub_manifest.CAPABILITY_PHASES
        assert capability_phases == {spec_lifecycle.CURRENT, *reachable}


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
