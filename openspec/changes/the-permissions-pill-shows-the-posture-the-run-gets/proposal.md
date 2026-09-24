# Proposal — the Permissions pill shows the posture the run gets

**Round 1, 2026-09-24** (bundle B4, spec track S10). Finding: **F283 (B)**. **Built on the
recommended answer to operator decision D4, first half** (see `design.md`). Nothing here is
implemented.

## Why

There are two built-in defaults for one decision, and they disagree (re-verified at `ce086b6`):

- The catalog declares `default="acceptEdits"` ("Edit files") on both providers' `permission_mode`
  control (`hub/hub/model_catalog.py:231` Claude, `:271` Codex), and a module constant
  `DEFAULT_PERMISSION_MODE = "acceptEdits"` (`:344`) that nothing imports (grep: only its own line).
- The spawn uses `DEFAULT_CLAUDE_PERMISSION_MODE = WORKSPACE_PERMISSION_MODE`
  (`hub/hub/runner_commands.py:74`) whenever the Hub injects its MCP server (`:238-242`), which
  `launchability.resolve_access_path` does for every Claude agent unless its config says
  `hub_client: "cli"` (`hub/hub/launchability.py:243-247`). Only then does it fall back to
  `acceptEdits` (`runner_commands.py:81`).
- Codex maps "no posture" and `acceptEdits` to the same thread pair (`_codex_posture`,
  `hub/hub/api/v1/agent_trigger.py:2742-2745`; `codex_appserver._thread_policy`, `:215-241`), so for
  Codex "Edit files" is the truth.

The composer's pill reads `effectiveValue ?? control.default` (`ComposerModelControls.tsx:140`);
with no agent default, `AgentOutputPanel` passes `EMPTY_CONTROLS` (`AgentOutputPanel.tsx:393-395`),
so a fresh Claude agent's pill reads **"Edit files"** while its run is **"Workspace only"**. The agent
settings select hard-codes the same claim: `"Built-in default (Edit files)"`
(`AgentSettingsControls.tsx:199`). Two tests pin the wrong display: `test_the_catalog_default_still
_accepts_edits` (`hub/tests/test_permission_approver.py:1051-1052`) and the UI test
*"reads the catalog default when the agent states none"* (`composerPermissionDefault.test.tsx:132-136`).

The existing requirement already forbids this (`agent-configuration`, *"Where the posture is shown
at rest … it SHALL show what the run will actually do"*). And `agent-run-sandboxing`'s scenario
*"The default is unchanged — … uses the same default posture as before the enforced posture
existed"* has been false since `72afb3c` (2026-08-13) moved the Claude default to `workspace`.

## What changes

1. **One function decides the posture a run gets when nobody chose one**:
   `runner_commands.posture_at_rest(provider, access_path, yolo) -> str` —
   Claude: `bypassPermissions` if `yolo`, else `workspace` with the Hub's server, else `acceptEdits`;
   Codex: `bypassPermissions` if `yolo`, else `acceptEdits`. `build_command` uses it for its fallback
   instead of the two constants, so the spawn and the display cannot drift.
2. **The agents list states it per agent**: `AgentSummary` gains `permission_mode_at_rest`, computed
   from the bound runner's cli, the agent's `hub_client` and `yolo`, by that function. It is `null`
   for an agent with no runner bound (there is no run to describe). Beside it,
   `permission_mode_built_in` is the same function with `yolo=False`: what clearing the agent's
   default would give (operator review 2026-09-24; clearing the posture clears the flag).
3. **Both composers' pills and the settings select read it** (R3: the new-conversation surface's composer, `NewConversationSurface.tsx:201`, passes no agent value today and shows the catalog default even for an agent with a stated default), through one UI helper. At rest the pill shows
   `default_permission_mode ?? permission_mode_at_rest ?? control.default`; the select's blank option
   reads "Built-in default (<label of permission_mode_built_in>)", or "Built-in default (depends on
   the runner)" when none is bound. Nothing is recorded as a choice.
4. **The catalog's declared default matches**: Claude's control default becomes `workspace`;
   Codex's stays `acceptEdits`. `DEFAULT_PERMISSION_MODE` is deleted. A test asserts each catalog
   default equals `posture_at_rest(provider, "mcp", False)`.

Behaviour of every run is unchanged. Only what the app says about it changes.

## Impact

- **Code:** `hub/hub/runner_commands.py`, `hub/hub/model_catalog.py`, `hub/hub/api/v1/agents.py`
  (list serializer, `:595-615`), `hub/hub/schemas/agents.py`; `hub/ui/src/api/agents.ts`,
  `AgentOutputPanel.tsx`, `AgentSettingsControls.tsx`. **A UI bundle** (`make ui`; commit
  `hub/ui/src` and `hub/hub/static/ui` together) — it reaches the operator's `:8000` on reload; the
  Python half reaches it on their next restart. No migration.
- **Tests:** the two pinned tests flip; new tests below.
- **Spec:** `agent-configuration` (at-rest scenario for an agent with no default) and
  `agent-run-sandboxing` (the stale "default is unchanged" requirement restated).
