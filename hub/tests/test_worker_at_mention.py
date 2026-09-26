"""F409, design D7: text a worker reads is text the operator did not write.

The `claude` CLI expands `@<path>` in a prompt into a file attachment, so a worker's prompt
argument is neutralised, the answer's escapes are restored, and the probe's grader accepts the
escaped and Windows-separator spellings of a path.
"""

import json

import pytest

from hub.checkpoint_generation import (
    _GENERATION_PROMPT,
    _PROBE_PROMPT,
    CheckpointBody,
    ProbeAnswers,
    grade_probe,
)
from hub.checkpoints import CheckpointEnvelope
from hub.conversation_titles import _PROMPT as _TITLE_PROMPT
from hub.conversation_titles import build_title_command
from hub.file_mentions import neutralise_file_mentions, restore_file_mentions
from hub.worker import _interpret, _Spawn, build_worker_command

RAW = "see @/etc/passwd"
ESCAPED = r"see \@/etc/passwd"


def _prompt_argument(cli: str, cmd: list) -> str:
    return cmd[cmd.index("-p") + 1] if cli == "claude" else cmd[-1]


@pytest.mark.parametrize("cli", ["claude", "codex"])
@pytest.mark.parametrize("builder", ["worker", "title"])
def test_the_prompt_argument_is_neutralised_and_nothing_else_moves(cli, builder) -> None:
    def build(prompt):
        if builder == "worker":
            return build_worker_command(cli=cli, model="m", prompt=prompt)
        return build_title_command(cli=cli, model="m", prompt=prompt)

    cmd, plain = build(RAW), build("see nothing")
    assert _prompt_argument(cli, cmd) == ESCAPED
    index = cmd.index(ESCAPED)
    assert cmd[:index] == plain[:index] and cmd[index + 1 :] == plain[index + 1 :]


def test_no_hub_worker_prompt_holds_an_at_sign() -> None:
    for prompt in (_GENERATION_PROMPT, _PROBE_PROMPT, _TITLE_PROMPT):
        assert "@" not in prompt


def _envelope():
    return CheckpointEnvelope(
        files_changed=["packages/@scope/x.ts", "node_modules/@types/y.d.ts", "@root/z.md"],
        tasks={"scope": "agent", "note": "n", "items": []},
        open_questions=[],
    )


@pytest.mark.parametrize(
    "answered",
    [
        ["packages/@scope/x.ts", "node_modules/@types/y.d.ts", "@root/z.md"],
        [r"packages/\@scope/x.ts", "node_modules/@types/y.d.ts", "@root/z.md"],
        ["packages/@scope/x.ts", r"node_modules\@types\y.d.ts", "@root/z.md"],
        ["packages/@scope/x.ts", "node_modules/@types/y.d.ts", r"\@root/z.md"],
    ],
)
def test_a_probe_answer_grades_the_same_however_the_at_sign_is_spelled(answered) -> None:
    answers = ProbeAnswers(files_changed=answered, task_ids=[], unanswered_question_ids=[])
    assert grade_probe(answers, _envelope()) == ("passed", [])
    restored = ProbeAnswers(
        files_changed=[restore_file_mentions(a) for a in answered],
        task_ids=[],
        unanswered_question_ids=[],
    )
    assert grade_probe(restored, _envelope()) == ("passed", [])


@pytest.mark.parametrize("text", ["a@b", r"a\@b", r"a\@b", "@x", "no at sign"])
def test_restore_inverts_neutralise(text) -> None:
    assert restore_file_mentions(neutralise_file_mentions(text)) == text


def _claude_stdout(payload: dict) -> str:
    return json.dumps({"type": "result", "result": json.dumps(payload), "usage": {}})


def test_interpret_restores_the_escapes_in_the_answer() -> None:
    payload = {
        "objective": "o",
        "state": r"see packages/\@scope/x and ops\@example.com",
    }
    result = _interpret(_Spawn("ok", stdout=_claude_stdout(payload)), "claude", CheckpointBody, 1)
    assert result.outcome == "ok"
    assert result.parsed.state == "see packages/@scope/x and ops@example.com"


def test_interpret_restores_only_strings_and_does_not_raise() -> None:
    payload = {
        "objective": r"o\@x",
        "state": "s",
        "decisions": [r"a\@b", "c"],
        "confidence": 3,
        "flag": True,
        "nothing": None,
        "nested": [[r"x\@y"], ["z"]],
    }
    result = _interpret(_Spawn("ok", stdout=_claude_stdout(payload)), "claude", CheckpointBody, 1)
    assert result.outcome == "ok"
    assert result.parsed.objective == "o@x"
    assert result.parsed.decisions == ["a@b", "c"]


def test_the_checkpoint_prompt_version_is_unchanged() -> None:
    from hub.checkpoint_generation import CHECKPOINT_PROMPT_VERSION

    assert CHECKPOINT_PROMPT_VERSION == "checkpoint/1"
