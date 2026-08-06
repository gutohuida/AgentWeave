# Design

## Decision 1 — Canonical context is built from Hub tables, and the three-state model collapses to two

`_render_hub_agent_context` currently branches three ways on a pair of booleans:

| `declared` | `registered` | Rendered |
|---|---|---|
| true | — | "Runtime Context" + Communication Mode |
| false | true | "Onboarding Context" + **External Agent Rules** stand-down |
| false | false | "Onboarding Context" + unregistered notice |

`declared` is sourced from `project_sessions`, which nothing writes any more. The first row is
therefore unreachable in practice, and every real agent gets the second.

**The fix is not to repair `declared`.** There is no `agentweave.yml` in a Hub-native project and
there is no reason to reintroduce one — `2026-08-03-single-runtime` removed that runtime deliberately.
The concept the branch was reaching for is "does the Hub know this agent?", and the Hub's `agents`
table answers that directly and correctly.

So the model collapses to two states, keyed on `agent_row is not None`:

- **Known** (a row exists in `agents`) → full runtime context: project profile, real team roster,
  project instructions, charter, Communication Mode.
- **Unknown** → a short notice explaining the agent is not registered, with no work-taking guidance.

The stand-down block is deleted outright rather than moved behind a narrower condition. Its stated
purpose was to keep an *undeclared* agent from acting before a principal assigned it work; with the
principal concept gone and every Hub agent created deliberately by the operator through
`POST /projects/{id}/agents`, there is no population it should apply to. An agent the operator
created and then messaged is, by construction, one the operator wants to act.

### The roster is the part that matters most

The empty `### Team` is what made collaboration impossible independent of the stand-down text: an
agent cannot message a peer whose name it was never told, which is exactly why `claude-haiku-1`
invented `principal` and got a 404. The rebuilt roster reads from `agents` joined to `runners`, so
each entry can state the peer's name, CLI, and model, and mark the reader with `<- you`.

`_runner_summary` (`agents.py:715`) is kept and reused; only its input changes, from a session-derived
dict to one built from the `Runner` row. That keeps the `runner=`/`model=`/`flags=`/`env=` rendering
and its existing secret-safety behaviour (env var *names* only, never values) intact.

### Quality gates and scheduled jobs

The existing spec requires the profile to include quality-gate and scheduled-job sections sourced
from `agentweave.yml`/session `quality` settings. Those inputs no longer exist in a Hub-native
project. Rather than emit empty or invented sections, the code omits them when the Hub holds no such
configuration, and the spec is amended to require them only when that configuration is present. This
is a narrowing of an existing requirement to match a runtime that already changed, not a new
decision.

## Decision 2 — `display_model` derives from the bound runner, with the legacy probe kept for unbound agents

`_display_model` maps a runner name to a label using `agent_meta`, which is assembled from
`session_agents_meta` merged over `agent_row.config`. Neither carries the runner binding, so the
lookup falls through to its `"native"` default.

The fix mirrors the shape `2026-08-06-agent-messaging-delivery` already used for
`/agents/launchability` (commit `1936206`): apply the `Agent.runner_id -> Runner` override *before*
deriving display fields, for any agent that has one. An agent with **no** bound runner — a
self-registered agent launched outside the Hub's spawn path — keeps deriving from `agent_row.config`,
because for those agents that path is still real and correct. This preserves the one legitimate
consumer of the old behaviour instead of breaking it in the name of consistency.

## Decision 3 — Codex app-server becomes the default, selected by absence rather than presence

Three options were considered:

1. Provision new codex runners with `flags: ["--app-server"]`. Rejected: leaves every existing runner
   broken, and encodes the correct default as data that can drift per-row.
2. Invert the sentinel — app-server unless `--no-app-server` is present. **Chosen.**
3. Invert and backfill existing rows with a migration. Rejected as unnecessary: existing codex
   runners carry `flags: None`, which the inverted default already reads as "use app-server".

Option 2 puts the correct behaviour in code, where it applies uniformly to every runner that has not
deliberately opted out, and needs no data change. `codex app-server` is labelled `[experimental]` by
Codex itself, which is why the opt-out exists and stays documented rather than being removed.

Both sentinels are stripped from `runner_flags` before `build_command`, because neither is a real
`codex exec` argument and either would otherwise leak into argv. That stripping already exists for
`--app-server`; it is extended to cover `--no-app-server`.

`collaboration_ready` follows the same rule so the reported state and the actual transport cannot
disagree: a Codex agent is ready unless it has explicitly opted out of app-server *and* lacks yolo.

### This satisfies an existing requirement rather than adding one

`agent-tool-surface`'s "One tool surface, configured automatically" already requires that a
configured surface be invocable, that the Hub not start a run whose surface it knows cannot be
called, and that where a provider offers per-request approvals the Hub use that mode. The app-server
transport was built to satisfy exactly this and then left opt-in, so the requirement has been
unmet by default since it shipped. The delta adds one scenario making the default explicit, so the
gap cannot silently reopen.

## Decision 4 — The composer separates by border alone

`index.css:453` already documents the intent: *"The resting border is already `--border-hi` — the
elevated end of the border scale — plus its own drop shadow, so the surface already reads as
distinct."* The drop shadow was doing the opposite of its job. `rgba(2, 5, 18, 0.28)` spread over
52px is a near-black, blue-cast halo; against `--bg` (`#0a0a0b`) it cannot read as a shadow, only as
a darker region surrounding a lighter one — precisely "a charcoal chat box and then a black box
around it".

Removed: the outer `box-shadow`. Kept: `inset 0 1px rgba(255,255,255,0.05)`, the top highlight that
actually produces the lift, and the `--border-hi` border.

The `.conversation-composer-fade` gradient is flattened for the same reason — it paints `--bg` at 70%
opacity across the strip, producing a second visible boundary. It is replaced with transparent
padding. The gradient existed so content scrolling under the composer would dissolve rather than
collide; if that collision proves visible in practice, the fallback is a solid `--bg` backing (one
uniform colour, no gradient edge), not a reinstated gradient.

## Decision 5 — Folding becomes state, not a derived function of recency

`folded = foldOverride[key] ?? !isLastTurn` makes foldedness a *function of position*, so appending a
turn silently restyles an earlier one. The operator's complaint is a direct consequence: they were
reading a turn, sent a message, and the thing they were reading collapsed.

The default becomes `foldOverride[key] ?? false` — every turn open unless the operator folded it.
Folding is thereby entirely operator-controlled through affordances that already exist and need no
change: the per-turn `fold` control and the "Fold all turns" button, both of which already write
`foldOverride`.

The alternative — fold on initial load, never on send — was offered and declined. It keeps a
position-derived rule alive and reintroduces the same class of surprise whenever the load boundary
and the operator's attention disagree.

The per-turn fold control is currently rendered only for `!isLastTurn` (`AgentTimeline.tsx:131`).
With no automatic folding, that condition is wrong: the last turn must be foldable too, or a
conversation with one turn offers no way to fold it. The control becomes unconditional.

## Decision 6 — The cross-agent picker is deleted, not disabled

`POST /agent/trigger` is `(agent, message) -> run` and has no notion of a "sending screen"; the picker
was purely additive UI over a send path that was never scoped to the visible conversation. Removing
it therefore requires no backend change and cannot regress handoffs or deliver-now, which use the
same endpoint.

`targetAgent` defaults to `agent` and `onTargetAgentChange` defaults to a no-op, so deletion leaves
`handleComposerSubmit` correct by construction: it already sends to `agent.name` when nothing has
been retargeted.

The picker was the only surface rendering `collaboration_ready`. That indicator moves to `AgentCard`,
beside the runner/model summary it already shows — the place an operator looks to understand an
agent's configuration, rather than a control they only see while composing. After Decision 3 the
not-ready state should be rare, which is a reason to keep it visible somewhere honest, not a reason
to drop it.

## Risks

- **Agents become more autonomous.** Removing the stand-down block means an agent that previously
  refused to modify files now will. This is the intended product behaviour, and sandboxing —
  unchanged by this work — remains the actual protection.
- **`codex app-server` is experimental.** Its own CLI says so. Mitigated by the retained
  `--no-app-server` opt-out and by the fact that the alternative default is known-broken.
- **Roster disclosure.** Every agent now learns the names, CLIs, and models of its peers. That is the
  minimum required for collaboration and matches what the spec already asked for; no secrets are
  added, and `_runner_summary`'s env-name-only behaviour is preserved.
