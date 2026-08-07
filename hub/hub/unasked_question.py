"""Detect a turn that ended on a question the agent never routed through `ask_user`.

Deliberately free of Hub imports: the rule is the part worth testing exhaustively, and it should
be testable without a database, a run, or the trigger machinery around it.

The rule is narrow on purpose. A false positive puts a card in front of the operator for a turn
that was fine; a false negative leaves an agent stalled on a question nobody can see. Those are
not symmetric, but neither is free, so this errs toward the cheap one only where the text is
genuinely question-shaped.
"""

import re

# Long enough for any real question, short enough that a pathological final line cannot bloat
# the row or the card that renders it.
MAX_QUESTION_CHARS = 400

# Leading markdown that carries no meaning for this decision: list markers, blockquote markers,
# and heading hashes. Stripped so "- Which database should I use?" reads as a question.
_LEADING_MARKUP = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|>\s*|#{1,6}\s+)+")

# Emphasis and inline-code wrappers, stripped from both ends so "**Which one?**" reads as one.
_WRAPPING_MARKUP = re.compile(r"^[*_`~\s]+|[*_`~\s]+$")

# A line with no letter or digit anywhere is punctuation or a rule ("---", "???"), not a question.
_HAS_WORD_CHARACTER = re.compile(r"[^\W_]", re.UNICODE)


def _ends_inside_code_fence(text: str) -> bool:
    """True if the text finishes inside an unclosed ``` block.

    A trailing `?` inside code is part of a snippet — a ternary, a glob, a regex — and asking the
    operator about it would be noise.
    """
    return sum(1 for line in text.splitlines() if line.lstrip().startswith("```")) % 2 == 1


def trailing_question(text: str) -> str:
    """Return the question a turn ended on, or `""` if it did not end on one.

    Only the final non-empty line is considered. An agent that asks something mid-turn and then
    answers it, or asks rhetorically and keeps working, has not stranded anything — only a turn
    whose *last* word is a question has stopped and waited.
    """
    if not text or not text.strip():
        return ""
    if _ends_inside_code_fence(text):
        return ""

    last_line = ""
    for line in reversed(text.splitlines()):
        if line.strip():
            last_line = line
            break
    if not last_line:
        return ""

    candidate = _WRAPPING_MARKUP.sub("", _LEADING_MARKUP.sub("", last_line))
    if not candidate.endswith("?"):
        return ""
    if not _HAS_WORD_CHARACTER.search(candidate):
        return ""
    return candidate[:MAX_QUESTION_CHARS]
