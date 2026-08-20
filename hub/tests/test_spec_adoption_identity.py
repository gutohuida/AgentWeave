"""Reading a document's identity from its own file, before any row exists.

The unit half of adoption: given a file, what does the Hub think it is, and when
does it refuse to guess? Every case here is a string in and a dataclass out —
the route, the database and the read-only guarantee are covered separately.

The distinction these tests exist to hold: a document that *says* what phase it
is in and a document the Hub *assumed* a phase for must never be confused, even
though they produce the same phase for the same kind.
"""

from __future__ import annotations

import json

import pytest

from hub import spec_adoption, spec_lifecycle
from hub.spec_payload import PAYLOAD_ELEMENT_ID, PAYLOAD_MIME


def _document(
    *,
    payload: object = None,
    raw_payload: str | None = None,
    kind: str = "capability",
    status: str | None = "current",
    title: str = "Agent charter",
) -> str:
    """A rendered document, assembled the way `spec_render` assembles one."""
    if raw_payload is None:
        body = (
            payload if payload is not None else {"schema_version": 1, "kind": kind, "title": title}
        )
        raw_payload = json.dumps(body, indent=2)
    head = f"<title>{title}</title>\n"
    head += f'<meta name="aw-spec-kind" content="{kind}">\n'
    if status is not None:
        head += f'<meta name="aw-spec-status" content="{status}">\n'
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        f"{head}</head>\n<body>\n<h1>{title}</h1>\n"
        f'<script type="{PAYLOAD_MIME}" id="{PAYLOAD_ELEMENT_ID}">\n{raw_payload}\n</script>\n'
        "</body>\n</html>\n"
    )


def _read(**kwargs) -> spec_adoption.Adoptable:
    return spec_adoption.identity_from_content("spec/capabilities/x/spec.html", _document(**kwargs))


class TestIdentityFromAPayload:
    def test_title_and_kind_come_from_the_payload(self):
        identity = _read(title="Agent charter", kind="capability")
        assert isinstance(identity, spec_adoption.AdoptableIdentity)
        assert identity.title == "Agent charter"
        assert identity.kind == "capability"

    def test_the_payload_wins_over_the_meta_tag_for_kind(self):
        """Design D3: the meta tag is the payload's display copy, so where both
        carry a value the payload is what the submission actually supplied."""
        document = _document(payload={"schema_version": 1, "kind": "capability", "title": "T"})
        document = document.replace(
            '<meta name="aw-spec-kind" content="capability">',
            '<meta name="aw-spec-kind" content="roadmap">',
        )
        identity = spec_adoption.identity_from_content("spec/a.html", document)
        assert isinstance(identity, spec_adoption.AdoptableIdentity)
        assert identity.kind == "capability"

    def test_the_meta_tag_supplies_a_kind_the_payload_omits(self):
        identity = spec_adoption.identity_from_content(
            "spec/a.html",
            _document(payload={"schema_version": 1, "title": "T"}, kind="roadmap"),
        )
        assert isinstance(identity, spec_adoption.AdoptableIdentity)
        assert identity.kind == "roadmap"

    def test_the_file_is_carried_so_the_caller_digests_what_it_adopted(self):
        identity = _read()
        assert isinstance(identity, spec_adoption.AdoptableIdentity)
        assert identity.content == _document()


class TestPhase:
    def test_a_recorded_phase_is_read(self):
        identity = _read(kind="capability", status="current")
        assert isinstance(identity, spec_adoption.AdoptableIdentity)
        assert identity.phase == spec_lifecycle.CURRENT
        assert identity.phase_source == spec_adoption.READ
        assert identity.unrecognised_phase is None

    @pytest.mark.parametrize(
        "status",
        ["exploring", "proposed", "approved", "archived", "current"],
    )
    def test_every_phase_a_row_can_hold_is_readable_from_a_file(self, status):
        """Including `approved` and `archived`, which `transition()` cannot reach
        from a fresh document — the file is the only account of a phase the row
        was never walked through on this machine."""
        identity = spec_adoption.identity_from_content(
            "spec/a.html", _document(kind="change-spec", status=status)
        )
        assert isinstance(identity, spec_adoption.AdoptableIdentity)
        assert identity.phase == status
        assert identity.phase_source == spec_adoption.READ

    def test_an_absent_status_defaults_by_kind_and_says_so(self):
        capability = _read(kind="capability", status=None)
        change = _read(kind="change-spec", status=None)
        assert isinstance(capability, spec_adoption.AdoptableIdentity)
        assert isinstance(change, spec_adoption.AdoptableIdentity)

        assert capability.phase == spec_lifecycle.CURRENT
        assert change.phase == spec_lifecycle.EXPLORING
        for identity in (capability, change):
            assert identity.phase_source == spec_adoption.DEFAULTED
            # Absent, not unrecognised: there was no value to report back.
            assert identity.unrecognised_phase is None

    def test_an_unrecognised_status_defaults_and_reports_the_value(self):
        identity = _read(kind="capability", status="halfway-done")
        assert isinstance(identity, spec_adoption.AdoptableIdentity)
        assert identity.phase == spec_lifecycle.CURRENT
        assert identity.phase_source == spec_adoption.DEFAULTED
        assert identity.unrecognised_phase == "halfway-done"

    def test_the_fallback_matches_what_creating_the_document_would_have_done(self):
        """If these two rules ever diverge, an adopted document lands somewhere a
        created one would not, which is a difference nobody would think to look for."""
        assert spec_adoption.default_phase_for("capability") == spec_lifecycle.CURRENT
        for kind in ("change-spec", "baseline", "system-map", "roadmap"):
            assert spec_adoption.default_phase_for(kind) == spec_lifecycle.EXPLORING


class TestRefusals:
    def test_no_payload_block_is_refused_as_absent(self):
        refusal = spec_adoption.identity_from_content(
            "spec/a.html", "<html><head><title>T</title></head><body>hand written</body></html>"
        )
        assert isinstance(refusal, spec_adoption.AdoptionRefusal)
        assert refusal.code == "payload_absent"

    def test_a_malformed_payload_block_is_refused_as_unreadable(self):
        """Distinct from absent (task 1.3): the remedies differ — write the
        document through the Hub, versus repair a block that is already there."""
        refusal = spec_adoption.identity_from_content(
            "spec/a.html", _document(raw_payload="{not json,")
        )
        assert isinstance(refusal, spec_adoption.AdoptionRefusal)
        assert refusal.code == "payload_unreadable"

    def test_a_payload_that_is_not_an_object_is_refused_as_unreadable(self):
        refusal = spec_adoption.identity_from_content(
            "spec/a.html", _document(raw_payload='["a list is not a document"]')
        )
        assert isinstance(refusal, spec_adoption.AdoptionRefusal)
        assert refusal.code == "payload_unreadable"

    def test_a_payload_with_no_title_is_refused_rather_than_named_from_its_path(self):
        refusal = spec_adoption.identity_from_content(
            "spec/capabilities/quiet-hours/spec.html",
            _document(payload={"schema_version": 1, "kind": "capability"}),
        )
        assert isinstance(refusal, spec_adoption.AdoptionRefusal)
        assert refusal.code == "payload_identity_missing"
        assert "quiet-hours" not in refusal.message

    def test_a_blank_title_is_no_title(self):
        refusal = spec_adoption.identity_from_content(
            "spec/a.html",
            _document(payload={"schema_version": 1, "kind": "capability", "title": "   "}),
        )
        assert isinstance(refusal, spec_adoption.AdoptionRefusal)
        assert refusal.code == "payload_identity_missing"

    def test_an_unknown_kind_is_refused_and_names_what_is_allowed(self):
        """A kind outside the enum would reach `spec/index.json`, which travels."""
        refusal = spec_adoption.identity_from_content(
            "spec/a.html",
            _document(
                payload={"schema_version": 1, "kind": "invention", "title": "T"},
                kind="invention",
            ),
        )
        assert isinstance(refusal, spec_adoption.AdoptionRefusal)
        assert refusal.code == "payload_identity_missing"
        assert "capability" in refusal.message

    def test_every_refusal_reports_an_empty_difference_list(self):
        """Never omitted, so an absent list and an empty one are unambiguous."""
        refusal = spec_adoption.identity_from_content("spec/a.html", "<html></html>")
        assert isinstance(refusal, spec_adoption.AdoptionRefusal)
        assert refusal.to_dict()["differences"] == []


def _workspace(tmp_path):
    from hub.project_workspace import ProjectWorkspace

    return ProjectWorkspace(project_id="proj-test", root=tmp_path, path_key="test:proj-test")


class TestReadIdentityAgainstAWorkspace:
    def test_a_missing_file_is_refused_by_name(self, tmp_path):
        refusal = spec_adoption.read_identity(_workspace(tmp_path), "spec/nothing-here.html")
        assert isinstance(refusal, spec_adoption.AdoptionRefusal)
        assert refusal.code == "file_missing"

    def test_a_path_escaping_the_spec_tree_is_refused_before_the_file_is_read(self, tmp_path):
        workspace = _workspace(tmp_path)
        outside = tmp_path / "secrets.html"
        outside.write_text(_document(), encoding="utf-8")

        for path in ("secrets.html", "../secrets.html", "/etc/passwd", "spec/../../x.html"):
            refusal = spec_adoption.read_identity(workspace, path)
            assert isinstance(refusal, spec_adoption.AdoptionRefusal), path
            assert refusal.code == "unsafe_document_path", path

    def test_a_real_file_reads_its_identity(self, tmp_path):
        workspace = _workspace(tmp_path)
        target = tmp_path / "spec" / "capabilities" / "agent-charter" / "spec.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_document(title="Agent charter"), encoding="utf-8")

        identity = spec_adoption.read_identity(
            workspace, "spec/capabilities/agent-charter/spec.html"
        )
        assert isinstance(identity, spec_adoption.AdoptableIdentity)
        assert identity.title == "Agent charter"
        assert identity.phase == spec_lifecycle.CURRENT
