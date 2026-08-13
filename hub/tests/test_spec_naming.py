"""Where a document's path comes from, before and after anyone knows what it is.

The placeholder's whole job is to carry no meaning, so most of what is asserted
here is an absence: the name does not come from the title, it is not the same
twice, and it does not encode anything a later reader could mistake for a
decision. The slug's job is the opposite — it must be derivable from prose and
must refuse prose that is not a name.
"""

import re

import pytest

from hub.spec_manifest import SPEC_PATH_MAX_LENGTH, validate_spec_path
from hub.spec_naming import (
    COLOURS,
    MAX_SLUG_LENGTH,
    MYTHIC_ANIMALS,
    NamingExhaustedError,
    document_path_for,
    mint_placeholder_path,
    slugify,
)

_FREE = lambda path: False  # noqa: E731 - a predicate this small reads better inline

PLACEHOLDER_RE = re.compile(r"^spec/changes/([a-z]+)-([a-z]+)/spec\.html$")


# ---------------------------------------------------------------------------
# Minting a placeholder


def test_a_minted_path_is_a_colour_and_an_animal():
    path = mint_placeholder_path(_FREE)
    match = PLACEHOLDER_RE.match(path)
    assert match, path
    assert match.group(1) in COLOURS
    assert match.group(2) in MYTHIC_ANIMALS


def test_a_minted_path_satisfies_the_path_contract():
    for _ in range(50):
        validate_spec_path(mint_placeholder_path(_FREE))


def test_minting_does_not_return_the_same_name_every_time():
    names = {mint_placeholder_path(_FREE) for _ in range(40)}
    assert len(names) > 1


def test_minting_skips_names_that_are_taken():
    seen = []

    def is_taken(path):
        seen.append(path)
        return len(seen) <= 5

    path = mint_placeholder_path(is_taken)
    assert path == seen[-1]
    assert len(seen) == 6


def test_a_full_namespace_refuses_rather_than_hanging():
    """The property that matters is termination; the message is secondary."""
    with pytest.raises(NamingExhaustedError):
        mint_placeholder_path(lambda path: True)


def test_a_crowded_namespace_falls_back_to_a_suffix():
    plain = {
        f"spec/changes/{colour}-{animal}/spec.html"
        for colour in COLOURS
        for animal in MYTHIC_ANIMALS
    }
    path = mint_placeholder_path(lambda candidate: candidate in plain)
    assert path not in plain
    validate_spec_path(path)


# ---------------------------------------------------------------------------
# Slugifying a subject


@pytest.mark.parametrize(
    "subject,expected",
    [
        ("Personal houseplant watering tracker", "personal-houseplant-watering-tracker"),
        ("Budget App", "budget-app"),
        ("  spaced   out  ", "spaced-out"),
        ("Already-hyphenated", "already-hyphenated"),
        ("Punctuation! Everywhere?", "punctuation-everywhere"),
        ("CAPS LOCK", "caps-lock"),
        ("version 2.0 of it", "version-2-0-of-it"),
    ],
)
def test_prose_becomes_a_slug(subject, expected):
    assert slugify(subject) == expected


@pytest.mark.parametrize("subject", ["", "   ", "???", "!!!", "---", "…", None])
def test_a_subject_that_is_not_a_name_yields_nothing(subject):
    assert slugify(subject) == ""
    assert document_path_for(subject) is None


def test_accents_are_folded_rather_than_dropped():
    assert slugify("Café Münchén") == "cafe-munchen"


def test_a_long_subject_is_truncated_within_the_path_budget():
    subject = "word " * 200
    path = document_path_for(subject)
    assert len(path) <= SPEC_PATH_MAX_LENGTH
    validate_spec_path(path)


def test_truncation_does_not_leave_a_trailing_hyphen():
    # Truncating mid-separator is the case that produces `.../a-b-/spec.html`,
    # which is legal but reads as a mistake.
    subject = "ab " * 400
    slug = slugify(subject)
    assert len(slug) <= MAX_SLUG_LENGTH
    assert not slug.endswith("-")


def test_a_subject_becomes_a_valid_document_path():
    assert (
        document_path_for("Personal houseplant watering tracker")
        == "spec/changes/personal-houseplant-watering-tracker/spec.html"
    )


def test_a_subject_cannot_express_a_traversal():
    for hostile in ["../../etc/passwd", "..", ".hidden", "a/b/c", "spec/../../x"]:
        path = document_path_for(hostile)
        if path is not None:
            validate_spec_path(path)
            assert path.count("/") == 3
            assert ".." not in path
