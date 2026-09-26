"""Neutralising the at-sign in text the operator did not write.

The `claude` CLI expands `@<path>` in a prompt into a file attachment, whatever the agent's
sandbox posture, so an agent that writes `@/some/path` into a message can make another agent's
harness read a file outside that agent's view (F409). A backslash before the at-sign stops the
expansion. Measured on the CLI in `scripts/drive/d2_0923_at_mention_tokeniser.py`: the rows
`escaped` and `escaped_twice` (design D2). The character before every at-sign in the output is a
backslash, including after U+FEFF, U+3000 and a newline, and an escape already in the text gains a
second backslash rather than collapsing.
"""

from __future__ import annotations

# Design D6. Hub text, so it is not itself neutralised: it spells the character out and holds no
# literal at-sign.
MENTION_NOTICE = (
    "In text the operator did not write, every at-sign is shown with a backslash before it, so "
    "that the text cannot make your harness attach a file; the original has no backslash."
)


def neutralise_file_mentions(text: str) -> str:
    return text.replace("@", r"\@")


def restore_file_mentions(text: str) -> str:
    """The exact inverse of `neutralise_file_mentions`."""
    return text.replace(r"\@", "@")
