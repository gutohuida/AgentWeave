"""F632: the payload schema agents read says what propose does with an unresolved question.

`OpenQuestion.resolved`'s description told agents an unresolved question blocks proposing; since
the warn-don't-gate change (2026-10-08) propose answers `proposed: true` with an
`unresolved_question` warning.
"""

from hub.spec_payload import OpenQuestion


def test_the_resolved_field_says_an_open_question_warns_and_does_not_block():
    text = OpenQuestion.model_fields["resolved"].description
    assert "blocks" not in text
    assert "warn" in text
