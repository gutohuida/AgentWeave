"""The model catalog: what each spawnable provider offers, and how to reach it.

One descriptor per provider (`CATALOG`, keyed by `db.models.RUNNER_CLIS` / `runner_commands`'s
directly-spawnable providers). A provider declares its models — each with the context window it
actually has, never a substitute — and its runtime controls, each declaring its own permitted
values and how it is applied to that provider's command line (`ApplySpec`). Adding a control is a
catalog edit; `render_control_args` renders any `ApplySpec` into argv without knowing what the
control means, which is the whole extensibility claim (design.md).

Model IDs and context windows below are live-verified, not authored from memory:

- Claude: `claude --help` documents `--model`'s accepted full names and aliases; `--effort`'s
  five values (`low, medium, high, xhigh, max`) come directly from that same `--help` output.
  Sonnet 5 (1,000,000) and Haiku 4.5 (200,000) context windows were live-verified from Claude's
  own `result.modelUsage.<model>.contextWindow` (see `runner_parsing.py`'s docstring). Opus 5 and
  Fable 5 have no live-verified window on this machine, so they declare `context_window=None`
  (unknown) rather than a guessed value — the rule this catalog exists to enforce.
- Codex: read directly from `~/.codex/models_cache.json`, the CLI's own server-synced catalog
  (has a `fetched_at` timestamp and an `etag`) — not from the CLI's `--help` text, which lists no
  models. Only entries with `"visibility": "list"` are included (`codex-auto-review`, visibility
  `"hide"`, is an internal review model, not one an operator selects). Context windows are that
  file's own `context_window` field per model.

  The effort control's values are the INTERSECTION of every listed model's
  `supported_reasoning_levels` (`low, medium, high, xhigh`) — not the union. The cache shows
  `"minimal"` is not declared by any current model and `"ultra"` only by three of six; a shared
  provider-level control offering either would let the Hub accept a value that a specific model
  would actually reject or (per the CLI's own asymmetric validation — see proposal.md) silently
  discard, which is exactly the failure mode this catalog exists to prevent. Precise per-model
  control values would be the more accurate fix but requires extending the schema to scope a
  control's values by model, not just by provider — flagged as a follow-up, not done here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ModelDescriptor:
    id: str
    label: str
    aliases: Tuple[str, ...] = ()
    context_window: Optional[int] = None
    default: bool = False


@dataclass(frozen=True)
class ApplySpec:
    """How a control reaches the provider's command line.

    `style="flag"` renders `template.format(value=value)` and splits it into argv tokens
    directly (e.g. "--effort high" -> ["--effort", "high"]). `style="config"` renders the
    same formatted template as one `-c KEY=VALUE` pair (Codex's configuration-override
    syntax; no other provider uses this style today). `style="none"` renders nothing.
    """

    style: str
    template: str = ""


@dataclass(frozen=True)
class ControlValue:
    """One permitted value of an enum control.

    `apply`, when set, replaces the *control's* `ApplySpec` for this value alone. Almost every
    value renders through its control's single template, substituting itself for `{value}`; a
    value needs its own spec only when it does not name itself on the command line. Claude's
    "Workspace only" posture is the case that motivated this: it is a distinct choice to the
    operator but spells itself `--permission-mode manual`, the same mode as "Ask first", and is
    distinguished from it by a second flag that only `_build_claude_command` can decide to emit.
    """

    id: str
    label: str
    apply: Optional[ApplySpec] = None


@dataclass(frozen=True)
class ControlDescriptor:
    id: str
    label: str
    kind: str  # "enum" | "boolean" | "number"
    values: Tuple[ControlValue, ...] = ()
    default: Optional[str] = None
    apply: ApplySpec = field(default_factory=lambda: ApplySpec(style="none"))


@dataclass(frozen=True)
class ProviderDescriptor:
    provider: str
    label: str
    models: Tuple[ModelDescriptor, ...]
    controls: Tuple[ControlDescriptor, ...]

    def model(self, model_id: str) -> Optional[ModelDescriptor]:
        for m in self.models:
            if m.id == model_id:
                return m
        return None

    def control(self, control_id: str) -> Optional[ControlDescriptor]:
        for c in self.controls:
            if c.id == control_id:
                return c
        return None


def _enum(*ids: str) -> Tuple[ControlValue, ...]:
    return tuple(ControlValue(id=v, label=v.replace("_", " ").capitalize()) for v in ids)


# The `permission_mode` value naming the Hub as the answerer for a run's permission requests.
# Deliberately not one of Claude's own mode spellings: it selects Claude's `manual` mode *plus*
# `--permission-prompt-tool`, and needs an identity of its own to be distinguishable from a bare
# `manual` in stored overrides and in `_build_claude_command`.
WORKSPACE_PERMISSION_MODE = "workspace"

CATALOG: Dict[str, ProviderDescriptor] = {
    "claude": ProviderDescriptor(
        provider="claude",
        label="Claude Code",
        models=(
            ModelDescriptor(id="claude-opus-5", label="Opus 5", aliases=("opus",), context_window=None),
            ModelDescriptor(
                id="claude-sonnet-5",
                label="Sonnet 5",
                aliases=("sonnet",),
                context_window=1_000_000,
                default=True,
            ),
            ModelDescriptor(
                id="claude-haiku-4-5-20251001",
                label="Haiku 4.5",
                aliases=("haiku",),
                context_window=200_000,
            ),
            ModelDescriptor(id="claude-fable-5", label="Fable 5", aliases=("fable",), context_window=None),
        ),
        controls=(
            ControlDescriptor(
                id="effort",
                label="Effort",
                kind="enum",
                values=_enum("low", "medium", "high", "xhigh", "max"),
                default="medium",
                apply=ApplySpec(style="flag", template="--effort {value}"),
            ),
            # Values are written out rather than built with `_enum`, whose derived labels
            # (`id.replace("_"," ").capitalize()`) would read "Acceptedits" and "Bypasspermissions".
            # An operator picks by what the agent may do, not by the CLI's spelling.
            ControlDescriptor(
                id="permission_mode",
                label="Permissions",
                kind="enum",
                values=(
                    ControlValue(id="acceptEdits", label="Edit files"),
                    # Spells itself `manual` — the same mode as "Ask first" — and is separated
                    # from it by `--permission-prompt-tool`, which names the Hub as the answerer.
                    # Only `_build_claude_command` knows whether that answerer exists for a given
                    # run, so it appends that flag; the catalog declares the mode alone.
                    ControlValue(
                        id=WORKSPACE_PERMISSION_MODE,
                        label="Workspace only",
                        apply=ApplySpec(style="flag", template="--permission-mode manual"),
                    ),
                    # `manual` now means what the label always promised: each call is put to the
                    # operator through the Hub's approval tool. Until 2026-08-07 nothing could
                    # answer it, so it refused everything.
                    ControlValue(id="manual", label="Ask me"),
                    ControlValue(id="bypassPermissions", label="Full access"),
                ),
                default="acceptEdits",
                apply=ApplySpec(style="flag", template="--permission-mode {value}"),
            ),
        ),
    ),
    "codex": ProviderDescriptor(
        provider="codex",
        label="Codex CLI",
        models=(
            ModelDescriptor(id="gpt-5.6-sol", label="GPT-5.6-Sol", context_window=272_000, default=True),
            ModelDescriptor(id="gpt-5.6-terra", label="GPT-5.6-Terra", context_window=272_000),
            ModelDescriptor(id="gpt-5.6-luna", label="GPT-5.6-Luna", context_window=272_000),
            ModelDescriptor(id="gpt-5.5", label="GPT-5.5", context_window=272_000),
            ModelDescriptor(id="gpt-5.4", label="GPT-5.4", context_window=272_000),
            ModelDescriptor(id="gpt-5.4-mini", label="GPT-5.4-Mini", context_window=272_000),
        ),
        controls=(
            ControlDescriptor(
                id="effort",
                label="Effort",
                kind="enum",
                values=_enum("low", "medium", "high", "xhigh"),
                default="medium",
                apply=ApplySpec(style="config", template="model_reasoning_effort={value}"),
            ),
        ),
    ),
}


def providers() -> List[ProviderDescriptor]:
    return list(CATALOG.values())


def get_provider(provider: str) -> Optional[ProviderDescriptor]:
    return CATALOG.get(provider)


def model_context_window(provider: str, model_id: str) -> Optional[int]:
    """The catalog's declared context window for *model_id*, or None if unknown or undeclared."""
    entry = get_provider(provider)
    if entry is None:
        return None
    model = entry.model(model_id)
    return model.context_window if model is not None else None


@dataclass(frozen=True)
class OverrideRejection:
    control: str
    reason: str


def validate_overrides(
    provider: str, overrides: Dict[str, str]
) -> Tuple[Dict[str, str], Optional[OverrideRejection]]:
    """Validate *overrides* (control id -> value, plus the special key ``"model"``) against
    *provider*'s catalog entry.

    ``"model"`` is validated against the provider's declared `models[]` (it is not itself a
    member of `controls[]` in the schema — see `design.md`'s descriptor shape); every other key
    is validated against `controls[]`. Returns `(accepted, None)` when every override is
    permitted, or `({}, OverrideRejection)` on the first violation — the Hub's own backstop so
    an invalid value is refused before a provider process ever starts, rather than passed
    through to a CLI that might silently discard it (see proposal.md's "What the spike
    established").
    """
    entry = get_provider(provider)
    if entry is None:
        return {}, OverrideRejection(control="*", reason=f"unknown provider {provider!r}")

    accepted: Dict[str, str] = {}
    for key, value in overrides.items():
        if key == "model":
            if entry.model(value) is None:
                return {}, OverrideRejection(
                    control="model",
                    reason=f"{value!r} is not a model {provider!r} declares",
                )
            accepted["model"] = value
            continue
        control = entry.control(key)
        if control is None:
            return {}, OverrideRejection(
                control=key,
                reason=f"{provider!r} does not declare a {key!r} control",
            )
        permitted = {v.id for v in control.values}
        if control.kind == "enum" and value not in permitted:
            return {}, OverrideRejection(
                control=key,
                reason=f"{value!r} is not a permitted value for {provider!r}'s {key!r} "
                f"(permitted: {', '.join(sorted(permitted))})",
            )
        accepted[key] = value
    return accepted, None


def render_control_args(provider: str, overrides: Dict[str, str]) -> List[str]:
    """Render already-validated *overrides* into argv, per each control's `ApplySpec`.

    ``"model"`` is not itself a control (see `validate_overrides`) and has its own dedicated
    application path in `runner_commands.build_command` — it is skipped here, so a caller may
    pass the full override dict without stripping it out first. An unrecognised provider or an
    otherwise-unknown control also renders nothing rather than raising — callers that need the
    validation failure use `validate_overrides` first, which is what `agent_trigger.py` does
    before this ever runs; this function itself never rejects, it only renders.
    """
    entry = get_provider(provider)
    if entry is None:
        return []
    args: List[str] = []
    for control_id, value in overrides.items():
        if control_id == "model":
            continue
        control = entry.control(control_id)
        if control is None:
            continue
        # A value may override its control's spec (see `ControlValue.apply`). This stays generic:
        # the renderer still does not know what any control means, only that the value it was
        # given may carry its own rendering.
        selected = next((v for v in control.values if v.id == value), None)
        spec = selected.apply if selected is not None and selected.apply is not None else control.apply
        if spec.style == "none":
            continue
        rendered = spec.template.format(value=value)
        if spec.style == "config":
            args += ["-c", rendered]
        else:  # "flag"
            args += rendered.split(" ")
    return args
