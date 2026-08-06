# Design

## The descriptor

One schema carries the whole capability. A provider declares its models and its controls; a control
declares how it reaches the command line.

```
ProviderDescriptor
  provider        "claude" | "codex"          matches Runner.cli / RUNNER_CLIS
  label           "Claude Code"
  models[]        ModelDescriptor
  controls[]      ControlDescriptor

ModelDescriptor
  id              "claude-sonnet-5"           the value passed to the CLI
  label           "Sonnet 5"
  aliases[]       ["sonnet"]                  CLI-accepted shorthand
  context_window  1000000 | null              null = unknown, provider self-report only
  default         bool

ControlDescriptor
  id              "effort"
  label           "Effort"
  kind            "enum" | "boolean" | "number"
  values[]        [{id:"low", label:"Low"}, …]     enum only
  default         "medium" | null
  apply           ApplySpec

ApplySpec
  style           "flag" | "config" | "none"
  template        "--effort {value}"  |  "model_reasoning_effort={value}"
```

`style` exists because the two providers reach the same setting differently, and the difference is
not incidental:

```
  claude   effort   →  style: flag     →  --effort high
  codex    effort   →  style: config   →  -c model_reasoning_effort=high
  claude   model    →  style: flag     →  --model claude-sonnet-5
  codex    model    →  style: flag     →  -m gpt-5-codex
```

`build_command` renders an `ApplySpec` into argv without knowing what the control *means*. That is
the whole extensibility claim: `model_verbosity` becomes `{id:"verbosity", kind:"enum", apply:{style:
"config", template:"model_verbosity={value}"}}` and it works end to end — command line, API
validation, and composer UI — with no new code in any of the three.

### Effort values are per provider, not shared

Verified against the installed CLIs:

```
  claude --effort   low, medium, high, xhigh, max
  codex   effort    minimal, low, medium, high, xhigh, max, ultra
```

The overlap is large enough to be a trap. A shared enum would either forbid `minimal`/`ultra` on
Codex or offer them on Claude, where they silently degrade (see validation, below). Values live on
the control, and the control lives on the provider.

### Where the catalog lives

A Python module in the Hub, exposed read-only over HTTP. Rejected alternatives:

- **A database table.** Needs a migration, a seeder, reconciliation on upgrade, and management UI,
  to hold data that changes when the Hub upgrades anyway. The descriptor is versioned with the code
  that consumes it — which is the correct coupling, because a new control usually *requires* a
  matching CLI version.
- **A config file in the data directory.** Same shape as the module but editable at runtime, which
  invites a catalog that disagrees with the installed CLI. Deferred, not foreclosed: the endpoint
  returns descriptors, so the source can change without the frontend noticing.

The endpoint is not project-scoped. The catalog is static and identical for every project, and
scoping it would imply a per-project catalog that does not exist.

## Validation happens in the Hub, before spawn

The spike found the providers disagree about strictness, and one of them fails silently:

```
  claude --model bogus     →  hard error, run does not start
  claude --effort bogus    →  "Warning: Unknown --effort value … using the default effort"
                              run proceeds, operator's choice discarded
  codex  -c unknown_key=1  →  rejected under --strict-config
```

A silent fallback is the worst of the three: the operator selects `max`, the turn runs at the
default, and the transcript records nothing about it. The Hub therefore validates every override
against the catalog before building the command, and refuses the trigger with a stated reason rather
than passing an unvalidated value through. The CLI's own validation becomes a backstop, not the
mechanism.

## Overrides are stored per conversation

`Conversation` gains one column:

```
  runtime_overrides   JSON   nullable    {"model": "claude-opus-5", "effort": "high"}
```

Keyed by control `id`, so adding a control is a value in an existing column rather than a migration.
Resolution order for a turn:

```
  conversation.runtime_overrides  →  runner.model / runner defaults  →  catalog control defaults
```

A new conversation starts with no overrides and therefore inherits its agent's runner — which keeps
the runner meaningful as "this agent's default capability" rather than making it vestigial.

Rejected: typed `model` and `effort` columns. Two columns today, a migration per control forever.
Rejected: overrides on the agent. The operator's ask was per-conversation, and per-agent overrides
would silently rewrite the shared runner binding for every conversation that agent has.

### Model changes are legal mid-conversation

Established by spike, so the design does not need a fallback path: a resumed session accepts a
different model. `_build_codex_command` already emits exec-level flags before the `resume`
subcommand — the ordering it adopted for `--sandbox` — so `codex exec -m X … resume <id>` needs no
restructuring.

What the design *does* need is honesty in accounting: a conversation whose model changed has turns
measured against different context windows. Usage is already recorded per turn, so per-turn model
capture is sufficient; the conversation-level figure must not assume one denominator.

## Context windows move to the catalog

```
  NOW     CODEX_MODEL_CONTEXT_LIMITS = {2 entries}, default 128000
          Claude table described by its own docstring as stale
          → codex-beta displays 136,550 / 128,000 = 100%

  TARGET  provider self-report (Claude's result event carries modelUsage.<model>.contextWindow)
            ↓ when absent
          catalog ModelDescriptor.context_window
            ↓ when null
          report usage as unknown, not as a percentage of a guess
```

The third branch is the behavioural change. Displaying a percentage of a fabricated denominator is
worse than displaying no percentage, because it drives the budget pause.

## Agent creation provisions its runner

The dialog asks for provider and model. On submit the Hub finds a runner in the project matching
that provider and model, and creates one only if none matches — so ten agents on Sonnet share one
runner rather than creating ten identical records.

```
  operator picks  provider + model + name (+ charter)
        ↓
  find Runner where project_id, cli=provider, model=model
        ↓ none
  create Runner (named from provider + model)
        ↓
  create Agent bound to it
```

Both records are created in one transaction: a runner left behind by a failed agent creation is
invisible debris in the Runners section. Launchability is probed for the *provider* before enabling
submit, as the current dialog already does per runner.

The Runners section keeps full CRUD. This adds a second path to the same records; it does not
replace runner management or weaken the separation the `runner-registry` capability specifies.

## Directory browsing

Browsers do not give a web page an absolute filesystem path — `showDirectoryPicker()` returns a
handle and withholds the path by design — so a client-side picker cannot produce what project
registration needs. The listing comes from the Hub process:

```
  GET /api/v1/fs/list?path=<absolute>   →  { path, parent, entries: [{name, path}] }
```

Directories only; never file contents, never file names. It requires the same API key as every other
endpoint. Symlinks are not followed out of the listed directory. Where a workspace root is
configured, listings stay beneath it; where one is not — the local case, which is the one that
matters — any readable directory may be listed. Unreadable directories return an empty listing with
a stated reason rather than an error that ends browsing.

The picker supplements the text input rather than replacing it, because typing or pasting a known
path is faster than navigating to it.

## Verification approach

- **Catalog and command building** are pure functions of the descriptor: table-driven tests assert
  that each control renders the argv the provider documents, including Codex's exec-before-`resume`
  ordering.
- **Validation** is asserted negatively: an override outside the catalog is refused with a reason,
  and specifically an effort value valid for one provider is refused for the other — the exact case
  the CLI would accept silently.
- **Context usage** is asserted at the three branches: self-reported wins; catalog fills the gap;
  unknown reports unknown rather than a percentage.
- **Provisioning** is asserted for reuse and isolation: a second agent on the same provider and
  model reuses the runner, and a failed agent creation leaves no runner behind.
- **Live** covers the composer controls, conversation routing, and the directory picker.
