"""What the board calls a task a document declared.

The decomposition approval produces is good; the names are not. From the run that found it, a real
board read:

    Add automated examples covering the public API, strict input types, exception split, on-time and
    early return, Sunday exclusion, grace boundaries, charging, the cap with an uncapped day count,
    explici

That is a description with the last word cut in half, and three of those is not a board. The cause
is that a declared `description` is a sentence written to be read in the document, and the fallback
took the whole first sentence — which, for a decomposition written as one sentence per task, is the
whole thing.

`test_spec_declared_tasks.py` asserts short descriptions come through unchanged. Those assertions
are correct and are not touched here; this file covers the long case and the declared title.
"""

from hub.spec_tasks import ELLIPSIS, MAX_TITLE, _title_for, _title_from

# The description that produced the 200-character title above, verbatim.
REAL = (
    "Add automated examples covering the public API, strict input types, exception split, "
    "on-time and early return, Sunday exclusion, grace boundaries, charging, the cap with an "
    "uncapped day count, explicit as-of behavior, returned values, and invalid input."
)


def test_a_description_short_enough_to_be_a_name_is_unchanged():
    """Shortening what is already short would be a change with no reader."""
    assert _title_from("Build the listing command") == "Build the listing command"


def test_a_trailing_period_is_dropped():
    assert _title_from("Build the export.") == "Build the export"


def test_the_first_sentence_still_wins_when_there_is_one():
    assert _title_from("Build the listing command. It shows what is due.") == (
        "Build the listing command"
    )


def test_a_long_single_sentence_becomes_a_name():
    title = _title_from(REAL)

    assert len(title) <= MAX_TITLE + len(ELLIPSIS)
    assert title.endswith(ELLIPSIS)
    # The point of the exercise: it reads as a name, not as the start of a paragraph.
    assert title.startswith("Add automated examples covering the public API")


def test_a_derived_title_never_ends_mid_word():
    """A cut that splits a word reads as a defect in the board, not as an abbreviation.

    The property: what remains is a whole-word prefix of the description, so the character the
    description continues with is a boundary rather than the middle of the word we kept.
    """
    for description in (REAL, "word " * 60, "Implement the fixed Sunday grace-period rules " * 5):
        title = _title_from(description)
        assert title.endswith(ELLIPSIS), f"expected {description[:30]!r} to be shortened"
        body = title[: -len(ELLIPSIS)]

        assert description.startswith(body), "the title is not a prefix of what it names"
        assert description[len(body)] == " ", "the last kept word was cut in half"


def test_a_clipped_title_does_not_end_on_dangling_punctuation():
    title = _title_from("Implement the public API with a dataclass, strict inputs, " + "x " * 60)
    body = title[: -len(ELLIPSIS)]
    assert not body.endswith((",", ";", ":", "-", "("))


def test_a_single_word_longer_than_the_limit_is_still_cut():
    """No boundary exists to find, so a hard cut is the only honest answer."""
    title = _title_from("x" * (MAX_TITLE * 2))
    assert title.endswith(ELLIPSIS)
    assert len(title) == MAX_TITLE + len(ELLIPSIS)


def test_an_empty_description_is_named_rather_than_blank():
    assert _title_from("") == "Untitled task"
    assert _title_from("   ") == "Untitled task"
    assert _title_from(".") == "Untitled task"


def test_a_declared_title_wins_over_the_description():
    entry = {"title": "Verify the fee policy", "description": REAL}
    assert _title_for(entry) == "Verify the fee policy"


def test_a_blank_declared_title_falls_back():
    for declared in ("", "   ", None, 7):
        entry = {"title": declared, "description": "Build the export."}
        assert _title_for(entry) == "Build the export"


def test_a_declared_title_is_still_bounded():
    entry = {"title": "y" * (MAX_TITLE * 2), "description": "Build the export."}
    assert len(_title_for(entry)) <= MAX_TITLE


def test_a_task_declaring_no_title_at_all_still_gets_one():
    assert _title_for({"description": "Build the export."}) == "Build the export"
    assert _title_for({}) == "Untitled task"
