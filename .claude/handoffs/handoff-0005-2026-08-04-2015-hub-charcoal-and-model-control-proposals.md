# Handoff: Two new openspec proposals — charcoal visual refresh and model control/provisioning

**Date:** 2026-08-04T20:15:00 · **Branch:** hub-native-experience · **HEAD:** ad5ce01
**Agent:** Claude Sonnet 5 (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0004-2026-08-04-1900-hub-contextual-navigation-complete.md`
**Status:** chunk complete — two proposals written and `openspec validate --strict` clean; both
await user approval before any implementation starts

## Goal

The user reviewed the running Hub UI (built from the now-complete `hub-contextual-navigation`
change) and named eight further problems: the palette should be black/charcoal, the composer's text
is misaligned, there's no way to change model/effort per turn or per conversation, the rail
permanently highlights the open project, there's no folder picker for a new project's path, agent
creation can't pick provider+model, the "work" block in a turn renders out of execution order, and
the project header feels boxed with an ugly raw path string. The user's explicit process: **"explore
first. After exploring we'll write the spec and after the spec is approved we'll execute."** This
handoff captures the end of that explore-then-spec arc — implementation has not started.

## Current state

**Exploration (done, this session):** Every one of the eight complaints was verified against actual
code or the live running app before writing anything — none were taken on faith. Full findings table
and live-measured composer offset are in the conversation; the key surprises were that #2 (composer
alignment) is structural (a flex *row*, not just a CSS nudge) and worse than described, and that a
spike into "does the CLI allow switching models mid-session" (user's instinct, contested initially)
turned out to be **conclusively yes** — proven from this very machine's own Claude Code session
transcripts (three model switches recorded inside one continuous session) and from Codex's own
`--help` text (`codex exec resume` documents `-c model="o3"` as its own example).

**Two openspec change proposals now exist, both `openspec validate --strict` clean, neither
approved:**

1. `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/` — UI-only, no backend, no migration.
   42 tasks. Covers: neutral graphite palette (both modes), monochrome primary + single accent
   reserved for state only, composer row→column layout, rail active-state fill→leading-marker,
   project header debox + segmented path, turn work-block execution-order rendering, removal of the
   dead 5-theme picker (writes `data-theme`, which **zero CSS rules read** — confirmed by grep).

2. `openspec/changes/2026-08-04-hub-model-control-and-provisioning/` — backend + UI, migration
   `0027`. 53 tasks. Core is a new `model-catalog` capability: a declarative descriptor
   (provider → models + controls; each control declares its `kind`, permitted `values`, and an
   `apply` spec of `flag` or `config` style) that both providers' command-building, request
   validation, context-window accounting, and the composer UI all read from — so a new control
   (Codex also exposes `model_verbosity`, `model_reasoning_summary`; Claude exposes
   `--max-budget-usd`) is a catalog edit, not new code anywhere.

Neither proposal has any task checked. Both `proposal.md` files carry `**Approved:** _pending_`.

## Files touched

All new files this session — nothing pre-existing was modified except as noted:

- `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/proposal.md` — new, complete.
- `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/design.md` — new, complete. Documents the
  exact token ramp values, the composer slot design, the rail marker mechanics, and the work-block
  reduction algorithm.
- `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/tasks.md` — new, 42 tasks across 8
  sections, none checked.
- `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/specs/hub-workspace-shell/spec.md` — new.
  2 `MODIFIED` requirements (superseding the mock's literal "indigo rail / ink content" wording,
  which this change's palette contradicts), 6 `ADDED`.
- `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/specs/agent-conversation-workspace/spec.md`
  — new. 2 `ADDED` (composer leading-edge text, extensible control-row slots).
- `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/specs/agent-stream-events/spec.md` — new.
  2 `ADDED` (execution-order rendering, independent per-block state/duration/pairing).
- `openspec/changes/2026-08-04-hub-model-control-and-provisioning/proposal.md` — new, complete,
  including the spike findings written as established fact, not an open question.
- `openspec/changes/2026-08-04-hub-model-control-and-provisioning/design.md` — new, complete.
  Documents the descriptor schema, why `style: flag | config` exists, the per-conversation
  `runtime_overrides` JSON-column design (rejected: typed columns, per-agent overrides), the
  context-window resolution order, and the atomic runner-provisioning flow for agent creation.
- `.../specs/model-catalog/spec.md` — new capability. 5 `ADDED` requirements.
- `.../specs/agent-conversation-workspace/spec.md` — new. 3 `ADDED` (composer model/effort control,
  per-conversation override persistence, explicit message routing to new-vs-current conversation).
- `.../specs/operator-agent-creation/spec.md` — new. 2 `MODIFIED`, 1 `ADDED` (atomic runner
  provisioning, reuse-not-duplicate).
- `.../specs/agent-context-usage/spec.md` — new. 3 `ADDED` (resolution order, unknown-reports-as-
  unknown — never a fabricated percentage, per-turn model attribution). **Had one strict-validator
  failure** (a requirement missing SHALL/MUST) — fixed in place; validator is clean now.
- `.../specs/local-project-workspace/spec.md` — new. 2 `ADDED` (directory browsing, auth + symlink +
  workspace-root bounding).
- `.../specs/runner-registry/spec.md` — new. 1 `ADDED` (runner models drawn from catalog, existing
  unrecognised models keep working).
- `.../specs/2026-08-04-hub-model-control-and-provisioning/tasks.md` — new, 53 tasks across 8
  sections, none checked. Task 5 explicitly notes it depends on Change A's composer control-row
  slots landing first.

**No code was written this session.** Explore mode and then proposal-writing only, per the user's
explicit process — this is deliberate, not an omission.

## Key decisions

- **Split into two changes, not one.** Reason: palette/layout/ordering is pure frontend and
  low-risk; model control needs a migration, new endpoints, and touches the runner/agent/charter
  separation. Bundling them would block the safe half on review of the riskier half. Rejected:
  one combined change — user didn't object but I judged the split served "spec approved, then
  execute" better by letting each be approved and shipped independently.
- **`style: flag | config` in the `ApplySpec`**, not a single "always a flag" model. Reason: Claude's
  effort is `--effort high` (a flag); Codex's is `-c model_reasoning_effort=high` (a config
  override), a genuine difference in shape, not just syntax. Rejected: forcing both through a flag
  template — would have required Codex to fake a flag or the descriptor to lie about `apply.style`.
- **Effort values are per-provider, not a shared enum.** Reason: spike-verified — Claude has
  `low, medium, high, xhigh, max`; Codex has `minimal, low, medium, high, xhigh, max, ultra`. A
  shared enum would either forbid Codex's `minimal`/`ultra` or silently offer them to Claude, which
  (see next point) would not reject them loudly.
- **Hub validates overrides before spawning; never delegates to the CLI.** Reason: spike found Claude
  rejects a bad `--model` hard, but a bad `--effort` **only warns and silently uses the default** —
  proven live: `claude --effort bogus -p "x"` printed the warning and answered anyway. Relying on
  CLI validation risks a turn silently running under settings the operator didn't choose.
- **`Conversation.runtime_overrides` as one nullable JSON column**, keyed by control id — not typed
  `model`/`effort` columns. Reason: a new control (verbosity, reasoning summary, etc.) becomes a
  value in an existing column instead of a migration. Rejected: overrides on the Agent instead of
  the Conversation — user explicitly wants **sticky per conversation**, and per-agent would silently
  rewrite the shared runner binding for every conversation that agent has.
- **Agent creation does atomic find-or-create of the runner**, not "require a runner to exist
  first". Reason: user's exact complaint — "it only adds models that already exist." Runner/agent/
  charter separation (a hard project rule, see CLAUDE.md) is preserved by still creating a real
  Runner record, just provisioned inline rather than requiring a prior trip to Runners.
- **Directory browsing is a new Hub-side endpoint, not a browser API.** Reason: `showDirectoryPicker()`
  deliberately withholds the absolute path from the page; there is no browser-only way to satisfy
  "open the file explorer" for an absolute-path field. User explicitly said Docker/workspace-root
  containment "is a non-issue because I think nobody will use it" — the spec still requires the
  bound-when-configured behavior (belt-and-braces, cheap to keep), but this is not weighted as a
  real risk per the user's own assessment.
- **Context-window fix folded into Change B**, not filed separately, even though the user didn't ask
  for it. Reason: it's a live, currently-manifesting bug discovered incidentally while researching
  the catalog (`codex-beta` shows 136,550/128,000 = 100%+ against a stale-by-design default table
  whose own docstring admits it's wrong) — the catalog is the correct, and only sane, fix location.
  I flagged this explicitly to the user as scope beyond the ask rather than silently expanding scope.

## Constraints and user directives (verbatim)

- "explore first. After exploring we'll write the spec and after the spec is approved we'll
  execute. You can add things to the current spec being executed or create a new one only if it's
  the best approach." — governs the whole arc this handoff covers. **Nothing is to be implemented
  yet.**
- "Do the research for the spike. But I believe the providers allow model switching. T3 does it and
  claude and codex accept /model to change the model, you can check t3's code to discover how this
  is done. You need to find how to implement this." — spike was run against the installed CLIs and
  this machine's own session transcripts, since no local T3 source existed to inspect (confirmed:
  `ls ~/Documents/projects/` has no t3-chat checkout).
- "Docker mode is a non issue because I think nobody will use it." — directly shapes how much weight
  the workspace-root containment requirement in Change B carries; kept in the spec but not treated
  as the design's central risk.
- "I don't understand the number 2?" — user asking about the `/api/v1/fs/list` risk flag; answered
  inline (a new local network-reachable directory-listing endpoint) rather than assumed understood.
- From the prior handoff chain, still governing this repo generally (CLAUDE.md, unchanged):
  "Never mark a task complete on the strength of a plan existing. Only real, verified implementation
  closes a task." — relevant to *future* sessions picking up these tasks.md files: writing them is
  not implementing them.
- Palette/accent/active-state/override-scope choices were made via `AskUserQuestion` and are final,
  not tentative: neutral graphite (not true black, not warm charcoal), monochrome primary + single
  state-only accent, left accent bar for the active rail row (not text-only, not no-indicator), and
  sticky-per-conversation overrides (not per-message, not per-agent).

## Dead ends

- None this session in the technical-investigation sense — the spike resolved cleanly in the
  direction the user predicted. The one near-thing worth recording: I initially considered a shared
  effort enum across providers before checking both CLIs directly; the `claude --effort bogus`
  and `codex -c model_reasoning_effort=bogus` probes (see Verification) are what closed that off
  before it reached the spec, so it never became a written mistake — but a future session must not
  re-introduce a shared enum without re-checking, since the two scales look similar enough to invite
  the shortcut.
- One openspec strict-validator failure while drafting: the `agent-context-usage` `ADDED` requirement
  "A conversation whose model changed reports usage per turn" initially had no sentence containing
  SHALL/MUST in its body (only in the scenarios). Fixed by rewording the opening sentence to include
  SHALL. Validator is clean now; flagging so a future session drafting further deltas in this file
  knows the validator checks the *requirement body*, not just its scenarios.

## Verification

**Ran and passed:**
- `openspec validate 2026-08-04-hub-charcoal-visual-refresh --strict` — valid.
- `openspec validate 2026-08-04-hub-model-control-and-provisioning --strict` — valid (after the one
  fix above).
- `openspec list` — both changes appear, 0/42 and 0/53 tasks respectively, confirming no task was
  accidentally pre-checked.
- Live composer measurement via `mcp__t3-code__preview_evaluate` against the running Hub at
  `127.0.0.1:8010`: at 359px viewport, composer surface `x=30,w=299`; agent selector `x=43,w=111`;
  textarea `x=162,w=110` — confirms the offset claim precisely and shows it's structural (present at
  any width), not a narrow-viewport-only issue.
- CLI spike, all run directly against locally installed binaries (`claude 2.1.221`,
  `codex-cli 0.146.0`):
  - `claude --help` grep confirmed `--model <model>` and `--effort <level>` both exist, both
    described as "for the current session".
  - `claude --effort bogus -p "x"` → printed
    `Warning: Unknown --effort value 'bogus' — ignoring it and using the default effort. Valid
    values: low, medium, high, xhigh, max.` then answered anyway — **proves silent fallback**.
  - `claude --model bogus-xyz -p "x"` → hard error — **proves model validation is strict, asymmetric
    with effort**.
  - `codex exec resume --help` → documents `-c model="o3"` as its own example.
  - `codex exec --help` → confirmed `-m, --model <MODEL>`.
  - `codex exec --strict-config -c totally_bogus_key=1 "x"` → rejected (unknown field) — control
    baseline for the next check.
  - `codex exec --strict-config -c model_reasoning_effort=bogus "x"` → **not** rejected as an unknown
    key (got past config validation to a different, expected "not a trusted directory" prompt) —
    proves `model_reasoning_effort` is a real, recognized Codex config key.
  - Binary string-grep on the installed Codex executable found the literal effort enum
    `minimal, low, medium, high, xhigh, max, ultra` and adjacent keys `model_verbosity`,
    `model_reasoning_summary`, `plan_mode_reasoning_effort`, `model_catalog_json` — all informing
    the "descriptor pays for itself" argument in design.md.
  - Grepped this machine's own Claude Code session JSONL transcripts:
    `~/.claude/projects/C--Users-huida-Documents-projects-AgentWeave/8993f2f4-*.jsonl` (this very
    conversation) contains 479 `claude-sonnet-5` + 155 `claude-opus-5` messages, switching at
    line 9 (opus) → line 154 (sonnet) → line 1193 (opus) — **empirical proof of clean mid-session
    model switching**, not just documentation-reading.

**Explicitly NOT run — nothing to run yet, since no implementation exists:**
- No backend tests, no frontend tests, no `tsc`, no build, no migration — Change B's migration
  `0027` doesn't exist as a file yet, only as a task description.
- No live check of an actual model switch on a *resumed* Codex/Claude session inside AgentWeave's
  own trigger/spawn path — the spike verified the CLIs support it, not that AgentWeave's
  `runner_commands.py`/`agent_trigger.py` will apply it correctly once built. That's task 2.3/2.4/8.8
  in Change B.
- No check of the `RUNNER_CLIS = ("claude", "codex")` enum or `CheckConstraint` in `db/models.py`
  against the new catalog-driven runner-model validation in Change B task 6.5 — read but not
  modified this session.

## Git state

- Branch: `hub-native-experience`
- HEAD: `ad5ce01` "Hub contextual navigation: complete live verification pass" (clean, from the
  prior session, unchanged this session)
- **Nothing from this session is committed.** `git status --short` shows only new/untracked openspec
  directories for both changes, plus the same pre-existing dirty/untracked set from every prior
  handoff in this chain (handoff-tooling scratch, `data/`, `scripts/`, older un-numbered handoff
  files, `openspec/explorations/`) — none of which this session touched.
- Untracked from this session specifically:
  `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/` (proposal.md, design.md, tasks.md,
  specs/hub-workspace-shell/, specs/agent-conversation-workspace/, specs/agent-stream-events/)
  `openspec/changes/2026-08-04-hub-model-control-and-provisioning/` (proposal.md, design.md,
  tasks.md, specs/model-catalog/, specs/agent-conversation-workspace/,
  specs/operator-agent-creation/, specs/agent-context-usage/, specs/local-project-workspace/,
  specs/runner-registry/)
- No commit was made this session — the user has not been asked to approve a commit of proposal-only
  work, and per CLAUDE.md git discipline, committing wasn't requested.

## Next steps

1. **Get explicit user approval on both proposals** before any implementation. Neither
   `proposal.md`'s `**Approved:** _pending_` line has been changed. This is the literal next action
   — nothing else in either tasks.md should be started until this happens, per the user's own stated
   process and the "Approval gate" section each proposal ends with.
2. Once Change A is approved: start at `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/tasks.md`
   section 1 (token ramp swap in `hub/ui/src/index.css`), using the exact hex values already written
   in that change's `design.md`.
3. Once Change B is approved: start at
   `openspec/changes/2026-08-04-hub-model-control-and-provisioning/tasks.md` section 1 — write
   `hub/hub/model_catalog.py` per the descriptor shape in that change's `design.md`. Task 1.2/1.3
   need real, current model IDs and context windows filled in from an authoritative source (Anthropic
   / OpenAI docs) — these were deliberately left as work, not invented from memory.
4. If Change B is approved before Change A, do Change B's section 5 (composer controls) last or defer
   it — it's written assuming Change A's composer control-row slots (leading/trailing) already exist;
   tasks.md says this explicitly at the top of Change B.
5. Consider whether to commit the two new openspec directories as their own checkpoint (proposal-only,
   pre-implementation) — not done this session since it wasn't requested, but worth asking, especially
   since `hub-contextual-navigation` (43/45) hasn't been archived yet either.

## Open questions for the user

Carried forward from handoff-0004, still unaddressed — none of these were touched this session:

1. `data/agentweave.db` at the repository root is untracked and not gitignored. Delete it, gitignore
   it, or is it intentional scratch?
2. Should the staged-but-uncommitted handoff-tooling work (`Makefile`, `scripts/sync_skills.py`, the
   `.claude/skills/` files, the `src/agentweave/templates/skills/` files,
   `tests/test_handoff_resume_templates.py`, the `LATEST.md` delete, and the `handoff-0001` rename)
   be committed as its own checkpoint?
3. Should the `review-0002` finding (no `UniqueConstraint` on `agents(project_id, name)`, allowing
   concurrent agent creation to produce a duplicate-named agent) be fixed inside a change or proposed
   separately? It remains open and untouched.

New this session:

4. Do you approve `2026-08-04-hub-charcoal-visual-refresh` as written?
5. Do you approve `2026-08-04-hub-model-control-and-provisioning` as written? In particular: the
   real Claude/Codex model IDs and context windows for catalog task 1.2/1.3 need to come from you or
   from an authoritative external source at implementation time — I did not invent them.
6. Should `2026-08-04-hub-contextual-navigation` (43/45 tasks, only the unverifiable
   reduced-motion task 7.7 outstanding) be archived now, before starting either new change? It's
   otherwise complete and blocking nothing, but three finished changes sitting un-archived is worth
   a deliberate decision rather than accretion.

## Read on resume

- `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/proposal.md` and `design.md` — the full
  rationale and exact token/design values for Change A; tasks.md section 1 is the first executable
  step once approved.
- `openspec/changes/2026-08-04-hub-model-control-and-provisioning/proposal.md` and `design.md` —
  same for Change B, including the full spike write-up under "What the spike established."
- `hub/hub/runner_parsing.py` — contains the currently-live context-window bug this session found
  (`CODEX_MODEL_CONTEXT_LIMITS`, stale Claude substring table per its own docstring) that Change B
  task 4 fixes.
- `hub/ui/src/components/agents/Composer.tsx` — the file with the structural row-layout bug Change A
  task 4 fixes; read this session, not yet modified.
- `hub/ui/src/index.css` lines ~16-160 — the current blue-navy token ramp Change A task 1 replaces.
- `openspec/changes/2026-08-04-hub-contextual-navigation/tasks.md` — prior change, 43/45, not yet
  archived; open question 6 above concerns it.
