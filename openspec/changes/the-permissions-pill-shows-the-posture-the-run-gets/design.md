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

### D2 — The agents list carries `permission_mode_at_rest`

The list route already resolves the bound runner (`agents.py:548`, `bound_runner.cli`; config merged at `:534`) and holds
the agent's config (`agent_meta`). `hub_client` comes from that config, as
`agent_trigger.py:1056` reads it; `yolo` likewise (`agent_trigger.py:805`). The value is computed by
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
- The requirement keeps its name, *"Introducing an enforced posture does not change existing runs"*,
  because a MODIFIED delta must match the header; its text now states the one built-in default. R2
  should decide whether a RENAMED delta is worth it.
- `hub_client` has no UI control (`DECISIONS.md` f299-f301); an agent with `hub_client: "cli"` will
  now correctly read "Edit files".

## Open questions

1. D4's first half itself (recommended (a)).
