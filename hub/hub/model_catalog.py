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
  Every context window below was live-verified from Claude's own
  `result.modelUsage.<model>.contextWindow` (see `runner_parsing.py`'s docstring), on 2026-08-09:
  Opus 5, Sonnet 5 and Fable 5 at 1,000,000, Haiku 4.5 at 200,000.

  *(This paragraph previously said Opus 5 and Fable 5 declared `context_window=None` because no
  window had been verified for them, while the code declared 1,000,000 for both. The measurement
  above settles it in the code's favour; the prose was stale, and a docstring claiming this
  catalog's central rule is being followed where it visibly was not is worse than no docstring.)*

  **Window variants.** `--model` accepts a `[1m]` suffix selecting a long-context beta, and it is
  a real selector rather than ignored text: `claude-opus-5[bogus]` and `claude-opus-5[200k]` are
  both refused ("may not exist or you may not have access to it"), so the provider parses it.
  There is no suffix that selects a *smaller* window — a variant can only ever offer more.

  Only Haiku 4.5 declares variants, because it is the only model where the two windows differ:
  200,000 at its base id, 1,000,000 at `[1m]`. Opus 5, Sonnet 5 and Fable 5 accept the suffix but
  return the same 1,000,000 their base ids already give, and declaring two choices that produce
  one outcome would put a control on screen that changes nothing.

  **Availability is a property of the subscription, not the model**, which is why entitlement is
  not declared here. `claude-haiku-4-5-20251001[1m]` is refused on this machine with "The long
  context beta is not yet available for this subscription" — a refusal about the account, not the
  id. The same declaration would resolve on an entitled account, and the base windows for Opus and
  Sonnet would themselves read differently there. The Hub cannot know an account's entitlements
  without asking the provider, and spawning is how it asks.
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
class WindowVariant:
    """One selectable context window for a model, and the exact id that selects it.

    Declared on the model rather than as a `ControlDescriptor` because it is not a control: a
    control renders to argv through an `ApplySpec`, and this changes the model id itself, which
    `runner_commands.build_command` applies by its own dedicated path. Making the variant *be* a
    model id is what keeps the rest of the system out of it — validation, storage, command
    construction and the usage path all already work on a model id, and none of them learns a
    second concept.
    """

    id: str
    label: str
    context_window: Optional[int] = None
    default: bool = False


@dataclass(frozen=True)
class ModelDescriptor:
    id: str
    label: str
    aliases: Tuple[str, ...] = ()
    context_window: Optional[int] = None
    default: bool = False
    # Empty means one window and nothing to choose, which is every entry that does not say
    # otherwise — so adding this field changed no existing declaration.
    windows: Tuple[WindowVariant, ...] = ()


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
        """The model *model_id* names — by its own id, or by one of its selectable windows.

        A window variant is a model id in its own right (see `WindowVariant`), so everything that
        asks "is this a model this provider declares?" has to answer yes for one. That includes
        `validate_overrides` and `runners._reject_undeclared_model`, neither of which needs to
        learn what a window is to keep working.
        """
        for m in self.models:
            if m.id == model_id or any(w.id == model_id for w in m.windows):
                return m
        return None

    def window(self, model_id: str) -> Optional[WindowVariant]:
        """The selectable window *model_id* names, or None if it names no variant."""
        for m in self.models:
            for variant in m.windows:
                if variant.id == model_id:
                    return variant
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
            ModelDescriptor(
                id="claude-opus-5", label="Opus 5", aliases=("opus",), context_window=1_000_000
            ),
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
                windows=(
                    WindowVariant(
                        id="claude-haiku-4-5-20251001",
                        label="200K",
                        context_window=200_000,
                        default=True,
                    ),
                    WindowVariant(
                        id="claude-haiku-4-5-20251001[1m]",
                        label="1M",
                        context_window=1_000_000,
                    ),
                ),
            ),
            ModelDescriptor(
                id="claude-fable-5", label="Fable 5", aliases=("fable",), context_window=1_000_000
            ),
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
            # Codex's approvals are answered by the Hub over the app-server protocol, not
            # selected by a command-line flag, so this renders nothing to argv (style="none")
            # and is read at trigger time instead. The labels match Claude's deliberately: an
            # operator should not have to learn two vocabularies for the same choice.
            ControlDescriptor(
                id="permission_mode",
                label="Permissions",
                kind="enum",
                values=(
                    ControlValue(id="acceptEdits", label="Edit files"),
                    ControlValue(id=WORKSPACE_PERMISSION_MODE, label="Workspace only"),
                    ControlValue(id="manual", label="Ask me"),
                    ControlValue(id="bypassPermissions", label="Full access"),
                ),
                default="acceptEdits",
                apply=ApplySpec(style="none"),
            ),
        ),
    ),
}


def providers() -> List[ProviderDescriptor]:
    return list(CATALOG.values())


def get_provider(provider: str) -> Optional[ProviderDescriptor]:
    return CATALOG.get(provider)


def model_context_window(provider: str, model_id: str) -> Optional[int]:
    """The catalog's declared context window for *model_id*, or None if unknown or undeclared.

    A selectable window answers with its own size, not its base model's — that is the whole point
    of having selected it.
    """
    entry = get_provider(provider)
    if entry is None:
        return None
    variant = entry.window(model_id)
    if variant is not None:
        return variant.context_window
    model = entry.model(model_id)
    return model.context_window if model is not None else None


def context_window_for_model(model_id: str) -> Optional[int]:
    """The declared context window for *model_id*, searched across every provider.

    A usage sample carries the model the run actually used, not the provider — the CLI reports
    what it loaded, and nothing upstream re-derives which catalog entry that was. Matching is
    **selectable window, then** exact id, then alias, then longest declared id that the reported
    one starts with: providers report dated snapshots (`claude-haiku-4-5-20251001`) that the
    catalog may hold undated, and a window that is right for the family is a better answer than
    none. Returns None rather than guessing when nothing matches — an unknown window means no
    percentage, which is honest.

    **The variant pass must come first, and must be its own full sweep.** A selectable window's id
    extends its base model's (`claude-haiku-4-5-20251001[1m]` starts with
    `claude-haiku-4-5-20251001`), so the prefix rule below would otherwise answer 200,000 for the
    model the operator chose *because* it holds 1,000,000 — reporting a conversation as five times
    fuller than it is, and checkpointing it on that.
    """
    normalized = (model_id or "").strip()
    if not normalized:
        return None
    for entry in CATALOG.values():
        variant = entry.window(normalized)
        if variant is not None:
            return variant.context_window
    best: Optional[ModelDescriptor] = None
    for entry in CATALOG.values():
        for model in entry.models:
            if model.id == normalized or normalized in model.aliases:
                return model.context_window
            if normalized.startswith(model.id) and (best is None or len(model.id) > len(best.id)):
                best = model
    return best.context_window if best is not None else None


PERMISSION_MODE_CONTROL = "permission_mode"

# The posture applied when neither the conversation nor the agent states one. Named here rather
# than read off one provider's descriptor because it has to hold for an agent with no runner bound
# at all — there is no provider to ask.
DEFAULT_PERMISSION_MODE = "acceptEdits"


def permission_mode_values() -> List[ControlValue]:
    """Every posture any provider declares, in catalog order, deduplicated by id.

    An agent's *default* posture is a property of the agent, and an agent may have no runner
    bound — so it cannot be validated against one provider's control the way a per-run override
    is. Both providers deliberately declare the same four values with the same labels ("an
    operator should not have to learn two vocabularies for the same choice"), so the union is
    that same set; deriving it here rather than restating it means a provider that adds a fifth
    does not silently make it unofferable as a default.
    """
    seen: Dict[str, ControlValue] = {}
    for entry in CATALOG.values():
        control = entry.control(PERMISSION_MODE_CONTROL)
        if control is None:
            continue
        for value in control.values:
            seen.setdefault(value.id, value)
    return list(seen.values())


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
