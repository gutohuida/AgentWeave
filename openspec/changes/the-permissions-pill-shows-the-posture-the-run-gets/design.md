# Design — the Permissions pill shows the posture the run gets

**Built on the recommended answer to D4's first half** (*"one built-in default: `acceptEdits` vs
`workspace`?"*): **`workspace` for a Claude run the Hub can answer, stated in one function that the
spawn and every display read; Codex keeps its own truthful default.** If the operator answers
`acceptEdits` instead, `posture_at_rest` returns `acceptEdits` for Claude and the spawn changes with
it (the display fix stands unchanged) — but see option (b) for what that costs.

**R1, 2026-09-24.** file:line at `ce086b6`.

## D4 (first half) — the options

| Option | Effect on runs | Evidence | Verdict |
|---|---|---|---|
| (a) **`workspace` for Claude; the display follows the spawn** | none | the spawn already does this (`runner_commands.py:74`, since `72afb3c`) | **recommended** |
| (b) `acceptEdits` for Claude | Bash prompts headlessly with nothing to answer; every unattended run can edit but not execute | `runner_commands.py:22-28, 62-73`: *"`acceptEdits` still prompts for `Bash`… an agent could write code and never run it"*; the same agent under `workspace` ran 14/14 tests (2026-08-13). F362's 262 refusals are the cost of the other side, and `the-shell-judge-reads-a-word-whole` removes most of them | rejected: reintroduces a measured failure |
| (c) `workspace` for Codex too | a Codex escalation whose `cwd` is inside the workspace becomes accepted (`codex_appserver.decide_approval`, `:280-283`) where today it is declined (`:291`); the escalation is exactly a request to leave the sandbox | Codex is undrivable since 2026-08-29 (memory: *Codex is undrivable*), so the widening cannot be measured | rejected for now; Codex's display is made truthful instead |

**Why the same answer serves D5.** Under (a) the shell judge decides every unattended Claude
command. That is why B4 recommends fixing its false refusals (S3) and keeping D5 narrow: strictness
that refuses ordinary shell costs every agent by default.

## Decisions

### D1 — One function, read by the spawn and by the display

`posture_at_rest(provider: str, access_path: str, yolo: bool) -> str` lives in
`runner_commands.py`, beside `DEFAULT_CLAUDE_PERMISSION_MODE` (kept as the name of the Claude value
it returns). `build_command` (`:238-242`) computes `default_posture` through it; the yolo branch
(`:275-276`) is unchanged in effect. A test asserts that for each provider and each
(`access_path`, `yolo`) combination, the argv `build_command` emits with no override is the argv the
same posture produces as an explicit override (the approver flag included) — so a change to either
side fails it.

**R3: the equivalence holds for two of three postures as argv, not for `yolo`.** The override
renders `control_args` where they are spliced, before `--mcp-config` (`runner_commands.py:216`),
while the default appends `--permission-mode` near the end (`:275-282`), so the comparison is of the
multiset of flag/value pairs, not the list. And a `yolo` run at rest emits
`--dangerously-skip-permissions` (`:276`) while an explicit `bypassPermissions` renders
`--permission-mode bypassPermissions` (`model_catalog.py:232`): the same Claude posture, different
argv. Task 1.2 asserts pair-equality for `workspace` and `acceptEdits`, and for `yolo` asserts
`posture_at_rest(...) == "bypassPermissions"` and that the at-rest argv holds
`--dangerously-skip-permissions` and no approver flag.

### D2 — The agents list carries `permission_mode_at_rest`

The list route already resolves the bound runner (`agents.py:548`, `bound_runner.cli`; config merged at `:534`) and holds
the agent's config (`agent_meta`). `hub_client` comes from that config, as
`agent_trigger.py:1056` reads it; `yolo` likewise (`agent_trigger.py:805`).

**R2 correction — the list must apply the spawn's whole `hub_client` resolution.** The trigger reads
`config` from `launchability.get_agent_config` (`agent_trigger.py:718`), which merges the session's
per-agent entry over `Agent.config` exactly as the list does (`launchability.py:484-485`,
`agents.py:533-534`) **and** then falls back to the session-wide `hub_client`
(`launchability.py:476-479`). The list route has no such fallback, so for a project whose
session.json sets a top-level `hub_client: "cli"`, the list would say `workspace` while every run
spawns `acceptEdits`: the drift this change exists to end. Build: extract that fallback into one
pure helper in `launchability.py` (`effective_hub_client(meta, session_data)`), used by
`get_agent_config` and by the list route (which already holds `session_data`, `agents.py:296`).
Task 1.3 gains a row for it.

**R3 correction — the precedence inside that merge.** `get_agent_config` applies the session-wide
fallback to the session's per-agent entry **before** laying that entry over `Agent.config`
(`launchability.py:474-485`: `meta["hub_client"] = session_data["hub_client"]`, then
`meta = {**agent_row.config, **meta}`), so the session-wide value **beats** a `hub_client` stored in
`Agent.config`. A helper that merges first and falls back after (the natural reading of
`effective_hub_client(merged_meta, session_data)`) gets that case backwards. The helper is therefore
the whole merge, `agent_config(session_data, agent_name, agent_config) -> dict`, lifted out of
`get_agent_config` unchanged and called by both. Task 1.3 row: `Agent.config` `hub_client: "mcp"`,
session top-level `"cli"`, no per-agent entry → the spawn uses `cli` → the list reads
`acceptEdits`. The value is computed by
`posture_at_rest(catalog_provider_for_runner(cli), resolve_access_path(cli, hub_client), yolo)`.
Unknown cli → `null`.

**What the route returns if this raises:** it cannot — dictionary lookups and a pure function over
strings; an unknown provider maps to `null`, not an exception. The route's other fields are
unaffected.

### D3 — The UI reads it, and nothing is recorded

`AgentOutputPanel` builds `agentDefaultControls` from
`default_permission_mode ?? permission_mode_at_rest` (today: `default_permission_mode` only,
`:393-395`). The Composer keeps sending only `pendingOverrides`, so showing the value records
nothing (the existing requirement's second half). `PermissionDefaultSetting`
(`AgentSettingsControls.tsx:178-214`) labels its blank option from the same field.

**R3: there is a third place, and it disagrees today even for an agent that states a default.**
`NewConversationSurface.tsx:201-218` renders a second `<Composer>` and passes **no**
`effectiveControls` at all (`Composer.tsx:96` defaults it to `{}`), so its pill reads
`control.default` for every agent: an agent whose default is "Ask me" shows "Edit files" on the
surface that starts its conversation, and its first run is spawned under "Ask me"
(`agent_trigger.py:765-766`). Built only in `AgentOutputPanel`, this change would leave the pill
wrong on exactly the first message. So the at-rest value is one exported helper,
`postureAtRest(agentRow)` in `hub/ui/src/api/agents.ts` →
`{permission_mode: agentRow.default_permission_mode ?? agentRow.permission_mode_at_rest}` or `{}`
when neither is known, read by **both** composer hosts; the settings select's blank label reads
`permission_mode_at_rest` through the same module. A grep for `effectiveControls=` then finds one
source. Server side, `posture_at_rest` is the one function the spawn and the list read. With those,
every place the posture is shown (the two composer pills, the settings select) and the run agree
through one helper per side; there is no other display (grep `permission_mode` over `hub/ui/src`:
`AgentOutputPanel`, `AgentSettingsControls`, `modelCatalog`, `agents.ts` only).

### D4 — The catalog default is kept, and made true

The catalog default is still what the pill shows when neither field is known (no roster row yet).
Claude's becomes `workspace`; Codex's stays `acceptEdits`. `DEFAULT_PERMISSION_MODE` (`:344`) is
deleted; its comment's premise ("an agent with no runner bound at all") is what `null` now says.

## Risks

- A committed UI bundle reaches `:8000` on reload, while the Python half (the new field and the
  catalog's new default, both served by the Hub) arrives only on the operator's next restart. In
  that window the UI finds no `permission_mode_at_rest` and a catalog still saying `acceptEdits`, so
  the pill reads "Edit files" exactly as it does today: no regression, and no fix until the restart.
  The UI must treat a missing field as unknown, never as an error (task 1.4 covers it).
- **R2:** the requirement *"Introducing an enforced posture does not change existing runs"* is
  RENAMED to *"The built-in posture a run receives is the posture shown for it"* (a RENAMED plus a
  MODIFIED block; `openspec validate --strict` passes). Its old name states the opposite of what
  its text now says, and nothing outside the spec cites it (grep over `openspec/specs`, `hub/`).
- `hub_client` has no UI control (`DECISIONS.md` f299-f301); an agent with `hub_client: "cli"` will
  now correctly read "Edit files".
- **Two of the seven posture reads B3 lists (B3 R2, "every place a run's permission posture is
  read") are outside this function, on purpose, and stay residuals:** `Runner.flags` are appended
  raw after `--permission-mode` (`runner_commands.py:285`), so a runner whose flags name a posture
  wins over what the pill shows; and an agent's `config["env_vars"]` can carry
  `AW_PERMISSION_POSTURE=operator`, which the spawn leaves in place unless the run is `manual`
  (`agent_trigger.py:1195-1196`) and the approver honours (`mcp_server.py:1699`), turning a
  "Workspace only" run into "Ask me". Neither is a built-in default; both are operator-written
  configuration. The other five agree: `default_permission_mode` and `runtime_overrides` sit above
  `posture_at_rest` in the pill's precedence exactly as in the spawn (`agent_trigger.py:760-768`),
  `yolo` and `hub_client` are its inputs, and `read_only` moves the boundary, not the posture.

## Open questions

1. D4's first half itself (recommended (a)).
