"""The rule that decides whether a turn ended on a question nobody was asked."""

import pytest

from hub.unasked_question import MAX_QUESTION_CHARS, trailing_question


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Which package manager should I use?", "Which package manager should I use?"),
        ("I've set up the scaffold.\n\nWhich database should I use?", "Which database should I use?"),
        # Trailing blank lines are how most CLIs end a stream; they must not hide the question.
        ("Which one?\n\n\n", "Which one?"),
        ("- Should I use npm or pnpm?", "Should I use npm or pnpm?"),
        ("1. Should I use npm or pnpm?", "Should I use npm or pnpm?"),
        ("> Should I proceed?", "Should I proceed?"),
        ("**Which one do you want?**", "Which one do you want?"),
        ("`Which one?`", "Which one?"),
        ("## Which one?", "Which one?"),
    ],
)
def test_a_turn_ending_on_a_question_is_detected(text, expected):
    assert trailing_question(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n\n  ",
        "I finished the migration and ran the tests.",
        # Asked, then answered by the agent itself — nothing is stranded.
        "Which database should I use? I'll go with Postgres, since it is already in the compose file.",
        # A question mid-turn followed by more work is not a turn that stopped and waited.
        "Should I use npm?\n\nI checked, and the lockfile is pnpm's, so I used pnpm.\nDone.",
        # Punctuation-only final lines: a horizontal rule, or bare marks.
        "Done.\n\n---",
        "Done.\n\n???",
    ],
)
def test_a_turn_that_did_not_end_on_a_question_is_not_detected(text):
    assert trailing_question(text) == ""


def test_a_question_mark_inside_an_unclosed_code_fence_is_code_not_a_question():
    text = "Here is the glob I used:\n\n```bash\nls src/**/*.?s\n"
    assert trailing_question(text) == ""


def test_a_closed_code_fence_does_not_suppress_a_later_question():
    text = "Here is what I ran:\n\n```bash\nnpm test\n```\n\nShould I commit this?"
    assert trailing_question(text) == "Should I commit this?"


def test_the_captured_question_is_bounded():
    text = "Which of these " + "very " * 400 + "long options?"
    captured = trailing_question(text)
    assert len(captured) == MAX_QUESTION_CHARS
    assert captured.startswith("Which of these very")
