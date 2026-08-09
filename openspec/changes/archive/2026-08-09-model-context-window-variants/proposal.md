# A model may offer more than one context window, and the operator picks

## Why

The catalog assumes one model means one context window. That is not true of the providers it
already describes: Claude accepts a `[1m]` suffix on a model id that selects a long-context beta,
so `claude-haiku-4-5-20251001` and `claude-haiku-4-5-20251001[1m]` are the same model with
200,000 and 1,000,000 tokens respectively. The catalog can express only the first, so the second
is unreachable from any Hub surface.

The window is not cosmetic here. It is the denominator of every proportional checkpoint threshold,
it is what `describe_threshold` reads to show a threshold in both units, and it is what
`threshold_error` refuses an unreachable token threshold against. A model whose window the
operator can change is a model whose checkpoint policy changes with it.

The operator asked for this directly: *"Some models have the context window that we can chose.
Like opus has both 200k and 1M. This should be a config in chat like the model."*

## What the live probe established

Run against this machine's `claude` CLI, reading each run's self-reported
`result.modelUsage.<model>.contextWindow` — the same method the catalog's existing windows came
from, not authored from memory:

| model id | window |
|---|---|
| `claude-opus-5` | 1,000,000 |
| `claude-opus-5[1m]` | 1,000,000 |
| `claude-sonnet-5` | 1,000,000 |
| `claude-sonnet-5[1m]` | 1,000,000 |
| `claude-fable-5` | 1,000,000 |
| `claude-haiku-4-5-20251001` | 200,000 |
| `claude-haiku-4-5-20251001[1m]` | refused: *"The long context beta is not yet available for this subscription"* |
| `claude-opus-5[200k]` | refused: *"may not exist or you may not have access to it"* |
| `claude-opus-5[bogus]` | refused, identically |

Three things follow, and they shape the whole design:

1. **The suffix is a real, validated selector.** `[bogus]` and `[200k]` are both refused, so the
   provider is parsing it rather than ignoring it. It is not a free-text field.
2. **There is no way to select a *smaller* window.** `[200k]` does not exist. A variant can only
   ever offer more.
3. **Availability is a property of the subscription, not the model.** Haiku's `[1m]` is refused
   here by entitlement, not by the id being wrong — and Opus and Sonnet already resolve to
   1,000,000 without any suffix on this subscription, where on another they would not. **The
   catalog cannot know this statically**, which is why entitlement is left to the provider to
   report rather than guessed at by a Hub that would have to be told.

## What changes

A model entry MAY declare more than one selectable context window. Each declares the exact model
id that selects it, its own window, and a label. A model that declares none is unchanged: one id,
one window, nothing to choose.

Because a variant *is* a model id, selecting one is expressed as the existing model override.
Nothing downstream of the picker learns a new concept — command construction, validation, storage,
and the usage path all keep working on a model id, which is what they already work on.

The operator interface renders a context control beside the model control, and renders it **only
when the selected model declares more than one window**. A control offering one choice is not a
choice, and the surfaces here are already dense.

Validation accepts a variant id exactly as it accepts a model id; window resolution resolves one
to its own declared window rather than to its base model's.

### What is declared today, and what is not

Only Haiku 4.5 declares variants: 200,000 at its base id, 1,000,000 at `[1m]`. It is the one model
where the two windows are genuinely different.

Opus 5, Sonnet 5, and Fable 5 declare **no** variants. Their `[1m]` ids are accepted, but they
resolve to the same 1,000,000 the base id already gives on this subscription, and declaring two
choices that produce one outcome would put a control on screen that does nothing. When a
subscription is observed where they differ, that is a catalog edit and nothing more — which is the
point of declaring this rather than coding it.

**Selecting an unentitled variant fails at spawn with the provider's own message.** That is a
deliberate exception to "the Hub validates before spawning": that rule exists so an *invalid*
value cannot be silently swallowed by a provider running at its default. An unentitled one is not
invalid, the provider refuses it loudly rather than falling back, and the Hub has no way to know
an account's entitlements without asking the provider — which is what spawning does.

## Also in scope: the catalog's docstring contradicts its own code

`model_catalog.py` states that Opus 5 and Fable 5 "have no live-verified window on this machine, so
they declare `context_window=None` (unknown) rather than a guessed value — the rule this catalog
exists to enforce." Both in fact declare `1_000_000`.

Live-verified above: both really are 1,000,000, so the code is correct and the prose is stale. It
is fixed here because this change is the reason anyone would read that paragraph, and because a
docstring claiming a rule is being followed where it visibly is not is worse than no docstring.

## Impact

- `hub/hub/model_catalog.py` — a window-variant declaration, resolution, validation, the corrected
  docstring
- `hub/hub/schemas/model_catalog.py` and the catalog endpoint — variants reach the interface
- `hub/ui/src/api/modelCatalog.ts` — the variant type
- `hub/ui/src/components/agents/ComposerModelControls.tsx` and `ModelPicker.tsx` — the context
  control, and a current-model lookup that recognises a variant id
- No migration: a variant is stored as the model id it already was
