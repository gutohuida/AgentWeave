"""Which runner flags would override what the Hub owns: the model, or the permission posture.

`runner_commands` appends a runner's `flags` after the Hub's own `--model` and posture flags, so
one of these in `flags` wins over both: a runner holding `--dangerously-skip-permissions` wrote
outside the workspace while the roster said `workspace` (F599). The rule here is the one create,
PATCH and the launchability probe all ask (`a-runner-s-flags-cannot-override-the-posture`, D1).

Copilot's widening flags are not listed: the posture strips them at run time
(`copilot_acp.strip_widening_flags`), and under Full access they are legitimate. Only its
`--model` is the runner's `model` field's to set.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

_MODEL = "the runner's model field"
_POSTURE = "the agent's permission posture (its permission mode, set per agent or per run)"

#: Per CLI: a flag's name, in its `--flag` and `--flag=value` forms, and what owns it.
_OWNED: Dict[str, Dict[str, str]] = {
    "claude": {
        "--model": _MODEL,
        "--permission-mode": _POSTURE,
        "--dangerously-skip-permissions": _POSTURE,
        "--allowedTools": _POSTURE,
        "--allowed-tools": _POSTURE,
        "--disallowedTools": _POSTURE,
        "--disallowed-tools": _POSTURE,
        "--permission-prompt-tool": _POSTURE,
        "--add-dir": _POSTURE,
        "--settings": _POSTURE,
    },
    "codex": {
        "--model": _MODEL,
        "-m": _MODEL,
        "--sandbox": _POSTURE,
        "-s": _POSTURE,
        "--ask-for-approval": _POSTURE,
        "-a": _POSTURE,
        "--dangerously-bypass-approvals-and-sandbox": _POSTURE,
        "--full-auto": _POSTURE,
        "--add-dir": _POSTURE,
    },
    "copilot": {"--model": _MODEL},
}

#: Per CLI: the flags that take a `key=value` config override, and the keys among them that set
#: what `_OWNED` guards (Codex's `-c sandbox_mode=...`).
_CONFIG_OVERRIDES: Dict[str, Tuple[Tuple[str, ...], Dict[str, str]]] = {
    "codex": (
        ("-c", "--config"),
        {
            "model": _MODEL,
            "model_provider": _MODEL,
            "sandbox_mode": _POSTURE,
            "sandbox_workspace_write": _POSTURE,
            "approval_policy": _POSTURE,
        },
    ),
}


def posture_flags_problem(cli: Optional[str], flags: Optional[Iterable[Any]]) -> Optional[str]:
    """The refusal for the first flag in *flags* that overrides the model or the posture, naming
    the flag and what owns it; None when every flag may stand."""
    owned = _OWNED.get(cli or "", {})
    config_flags, config_keys = _CONFIG_OVERRIDES.get(cli or "", ((), {}))
    words = [str(flag) for flag in (flags or [])]
    for index, word in enumerate(words):
        name, _, glued = word.partition("=")
        owner = owned.get(name)
        if owner is None and name in config_flags:
            value = glued if glued else (words[index + 1] if index + 1 < len(words) else "")
            key = value.split("=", 1)[0].strip().split(".", 1)[0]
            owner = config_keys.get(key)
            if owner is not None:
                name = f"{name} {key}"
        if owner is not None:
            return (
                f"A runner's flags cannot include {name}: it would override {owner}, because "
                "the runner's flags are passed after the Hub's own. Set it there instead, or "
                "remove the flag."
            )
    return None
