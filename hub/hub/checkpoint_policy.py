"""When a checkpoint should be taken, and who decides.

A threshold is **one mode plus one value**, never two nullable value columns. "50%" and
"150 000 tokens" are the same setting expressed differently, and giving each its own column makes
"both set" representable — a state with no meaning that every reader would then have to
disambiguate.

Both modes exist because context windows differ by an order of magnitude. A percentage is the
natural unit when you think in terms of "most of the way full"; an absolute count is the natural
unit when you know from experience that a particular model degrades past 150k regardless of what
fraction of its window that is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from .model_catalog import context_window_for_model

THRESHOLD_MODES = ("percent", "tokens")
CHECKPOINT_MODES = ("off", "offered", "automatic")

# Claude Code auto-compacts near 95%. If it fires first the provider session survives but its
# context is now the CLI's own summary — ours never happened, and the conversation continues on a
# compaction nobody authored and nothing can inspect. 80% leaves room to act before that.
DEFAULT_THRESHOLD_MODE = "percent"
DEFAULT_THRESHOLD_VALUE = 80

# Notes are requested earlier than cutover, because notes composed from an already-exhausted
# context are themselves exhausted. Ten points of headroom by default.
DEFAULT_NOTES_VALUE = 70

# The point past which a dismissal is no longer respected — see `needs_final_warning`. Sits between
# the 80% default above and the ~95% compaction that comment is reasoning about: far enough past
# any ordinary threshold that reaching it means the operator really did keep going, and far enough
# short of compaction that there is still a conversation left to checkpoint when they act.
FINAL_WARNING_PERCENT = 92


@dataclass(frozen=True)
class CheckpointPolicy:
    """The effective policy for one conversation: agent ?? project ?? built-in."""

    mode: str
    threshold_mode: str
    threshold_value: int
    notes_value: Optional[int]
    runner_id: Optional[str]
    model: Optional[str]
    # Where the threshold came from, for a surface that wants to say "inherited from the project".
    threshold_source: str = "default"

    @property
    def automatic(self) -> bool:
        return self.mode == "automatic"

    @property
    def enabled(self) -> bool:
        return self.mode in ("offered", "automatic")


def _threshold_of(holder: Any) -> Optional[Tuple[str, int, Optional[int]]]:
    """A holder's threshold, or None when it states none.

    The mode is what marks a threshold as stated. A value without a mode is not half a
    threshold — it is an incomplete one, and inheriting the missing half from elsewhere is how
    `percent` meets a value of `150`.
    """
    if holder is None:
        return None
    mode = getattr(holder, "checkpoint_threshold_mode", None)
    value = getattr(holder, "checkpoint_threshold_value", None)
    if mode not in THRESHOLD_MODES or not isinstance(value, int):
        return None
    return mode, value, getattr(holder, "checkpoint_notes_value", None)


def resolve_policy(agent: Any, project: Any) -> CheckpointPolicy:
    """Agent overrides project overrides built-in default.

    `mode` and the threshold resolve independently: an agent may sensibly turn checkpointing off
    for itself while accepting the project's threshold, or tighten its threshold while leaving
    the project to decide whether checkpoints are automatic.
    """
    mode = getattr(agent, "checkpoint_mode", None) or getattr(project, "checkpoint_mode", None)
    if mode not in CHECKPOINT_MODES:
        mode = "off"

    threshold = _threshold_of(agent)
    source = "agent"
    if threshold is None:
        threshold = _threshold_of(project)
        source = "project"
    if threshold is None:
        threshold = (DEFAULT_THRESHOLD_MODE, DEFAULT_THRESHOLD_VALUE, DEFAULT_NOTES_VALUE)
        source = "default"

    threshold_mode, threshold_value, notes_value = threshold
    return CheckpointPolicy(
        mode=mode,
        threshold_mode=threshold_mode,
        threshold_value=threshold_value,
        notes_value=notes_value,
        runner_id=getattr(project, "checkpoint_runner_id", None),
        model=getattr(project, "checkpoint_model", None),
        threshold_source=source,
    )


def threshold_error(mode: str, value: int, *, context_window: Optional[int] = None) -> Optional[str]:
    """Why this threshold is unusable, or None.

    The window check is **conditional on the window being known**, which is what reconciles
    "refuse a threshold at or above the window" with "token mode must work where the limit is
    unknown". Where the catalog declares nothing, there is nothing to compare against and the
    threshold is accepted — an unknown window is not evidence that a number is wrong.
    """
    if mode not in THRESHOLD_MODES:
        return f"Threshold mode must be one of {THRESHOLD_MODES}."
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return "Threshold must be a positive whole number."
    if mode == "percent":
        if value > 99:
            # 100% has already happened by the time anything could act on it.
            return "A percentage threshold must be below 100."
        return None
    if context_window is not None and value >= context_window:
        return (
            f"A threshold of {value:,} tokens is at or above this model's "
            f"{context_window:,}-token window, so it would never fire."
        )
    return None


def describe_threshold(mode: str, value: int, *, context_window: Optional[int] = None) -> str:
    """The threshold in both readings where both are knowable, e.g. "150k — 75% of 200k".

    An operator setting one unit is reasoning about the other, and making them work it out is how
    a threshold gets set somewhere it will never fire.
    """
    if mode == "percent":
        if context_window:
            return f"{value}% — {round(context_window * value / 100 / 1000):,}k of {context_window // 1000:,}k"
        return f"{value}%"
    thousands = f"{round(value / 1000):,}k"
    if context_window:
        return f"{thousands} — {round(value / context_window * 100)}% of {context_window // 1000:,}k"
    return thousands


def crosses(
    mode: str,
    value: int,
    *,
    context_tokens: Optional[int],
    percent: Optional[float],
) -> bool:
    """Whether a reading has reached the threshold.

    Token mode reads `context_tokens` alone and so keeps working where the provider never
    reported a limit — which is the case this mode exists to serve. Percent mode needs a
    percentage, and returns False rather than guessing when there is none: acting on an invented
    denominator is worse than not acting.
    """
    if mode == "tokens":
        return context_tokens is not None and context_tokens >= value
    return percent is not None and percent >= value


def should_checkpoint(
    policy: CheckpointPolicy, *, context_tokens: Optional[int], percent: Optional[float]
) -> bool:
    """Whether to *generate* a checkpoint — which `offered` does too.

    `offered` withholds the **cutover**, not the generation. The offer this change specifies is
    "I made one, here it is, cut over?", not "shall I ask the agent to write one?" — generation no
    longer depends on the agent, so there is nothing to seek permission for beforehand, and
    offering to make one later would mean offering it from a context that has since degraded.
    """
    if not policy.enabled:
        return False
    return crosses(
        policy.threshold_mode,
        policy.threshold_value,
        context_tokens=context_tokens,
        percent=percent,
    )


def should_request_notes(
    policy: CheckpointPolicy, *, context_tokens: Optional[int], percent: Optional[float]
) -> bool:
    """Whether the agent should be asked for notes yet.

    Only meaningful strictly below cutover: at or past it the conversation is about to be
    succeeded, and notes written there are written from the context the cutover exists to escape.
    A notes value that is not below the threshold is ignored rather than honoured, because
    honouring it would ask for notes at the worst possible moment.
    """
    if not policy.enabled or policy.notes_value is None:
        return False
    if policy.notes_value >= policy.threshold_value:
        return False
    return crosses(
        policy.threshold_mode,
        policy.notes_value,
        context_tokens=context_tokens,
        percent=percent,
    ) and not crosses(
        policy.threshold_mode,
        policy.threshold_value,
        context_tokens=context_tokens,
        percent=percent,
    )


def needs_final_warning(policy: CheckpointPolicy, *, percent: Optional[float]) -> bool:
    """Whether a conversation whose warning was dismissed must be warned once more.

    Deliberately takes no `context_tokens`. Every other predicate here accepts both readings
    because both can answer their question; this one cannot. "Near the window" is a statement
    about the *proportion* in use, and a token count with no window to divide by does not make a
    smaller version of that statement — it makes none at all. Accepting the argument would invite
    a caller to pass it and assume it was used.

    The caller is responsible for having established that the operator already dismissed a
    warning. A conversation still sitting on an undismissed one has the warning on screen, and
    replacing it with the same banner is not a second warning.
    """
    if not policy.enabled or policy.automatic:
        return False
    return percent is not None and percent >= FINAL_WARNING_PERCENT


def window_for(model: Optional[str]) -> Optional[int]:
    """The catalog's window for *model*, or None. Thin wrapper so callers need one import."""
    return context_window_for_model(model) if model else None
