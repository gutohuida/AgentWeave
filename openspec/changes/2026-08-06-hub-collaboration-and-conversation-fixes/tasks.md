# Tasks

## 1. Canonical agent context is built from Hub state

- [x] 1.1 Rewrite `_render_hub_agent_context` (`hub/hub/api/v1/agents.py`) to take the agent roster
      from the `agents` table joined to `runners`, not from `session_data`.
- [x] 1.2 Collapse the three-way `declared`/`registered` branch to two states keyed on
      `agent_row is not None`. Delete the "External Agent Rules" stand-down block entirely.
- [x] 1.3 Render `### Team` from the real roster: each peer's name, cli, model, and a `<- you`
      marker on the reading agent. Reuse `_runner_summary`, feeding it runner-derived metadata.
- [x] 1.4 Emit the quality-gates and scheduled-jobs sections only when the Hub actually holds that
      configuration; omit rather than render empty or invented sections.
- [x] 1.5 Keep the response's machine-readable fields working. `declared`/`provisional` are derived
      from Hub registration now; do not silently drop keys existing clients read.
- [x] 1.6 Simplify the `agent_trigger.py:305-314` call site if `session_data` is no longer needed.
      Not simplified, deliberately: `session_data` is still the only home for quality-gate
      configuration, which the UI's own quality panel already surfaces. Dropping the parameter
      would have deleted that section from context for the projects that do have it. It no longer
      decides identity or the roster, which was the defect.
- [x] 1.7 Test: context for a Hub-native agent contains every peer's name and **no** occurrence of
      "External Agent Rules", "principal", or "agentweave.yml".
- [x] 1.8 Test: context for an unknown agent still returns the unregistered notice and no
      work-taking guidance.

## 2. Agent summary reports its real runner and model

- [x] 2.1 Apply the `Agent.runner_id -> Runner` override before deriving `_runner`/`_display_model`
      (`agents.py:456`), matching the shape used by `get_agents_launchability`.
- [x] 2.2 Keep the legacy `agent_row.config` derivation for agents with no bound runner
      (self-registered agents launched outside the Hub's spawn path).
- [x] 2.3 Test: a runner-bound agent reports its real cli and model, not `"native"`/`"Native"`.
- [x] 2.4 Test: an unbound self-registered agent still derives from its stored config.

## 3. Codex collaborates by default

- [x] 3.1 Add a `--no-app-server` opt-out sentinel alongside `APP_SERVER_OPT_IN_FLAG` in
      `hub/hub/codex_appserver.py`.
- [x] 3.2 Invert `use_codex_app_server` (`agent_trigger.py:337`) to default `True` for
      `runner == "codex"`, selecting `exec` only on explicit opt-out.
- [x] 3.3 Strip **both** sentinels from `runner_flags` before `build_command` — neither is a real
      `codex exec` argument.
- [x] 3.4 Update `collaboration_ready`/`collaboration_reason` (`agents.py:207-220`) to the inverted
      rule so reported state and actual transport cannot disagree.
- [x] 3.5 Update `runner_commands.py`'s module docstring to state the default transport and the
      opt-out.
- [x] 3.6 Test: a codex runner with no flags selects app-server; `--no-app-server` selects exec;
      neither sentinel appears in the built argv.
- [x] 3.7 Test: `collaboration_ready` is `true` for a default codex runner and `false` for one that
      opted out without yolo.

## 4. Conversation chrome

- [x] 4.1 Operator bubble (`AgentTimeline.tsx:445`): background `var(--surface-2)`, border
      `1px solid var(--border)`. No `--blue`.
- [x] 4.2 Remove the outer `box-shadow` from `.conversation-composer-surface` (`index.css:458`);
      keep the `inset` top highlight and the `--border-hi` border.
- [x] 4.3 Flatten `.conversation-composer-fade` (`index.css:449`) to transparent padding.
- [x] 4.4 Update the design comment at `index.css:453` so it no longer cites a drop shadow that no
      longer exists.
- [x] 4.5 Test: the operator bubble's style declares no `--blue`; the composer surface declares no
      outer box-shadow.

## 5. Turns never fold themselves

- [x] 5.1 `AgentTimeline.tsx:115`: default `foldOverride[key] ?? false`.
- [x] 5.2 Make the per-turn fold control unconditional (`AgentTimeline.tsx:131`) so the last turn is
      foldable too.
- [x] 5.3 Test: appending a new turn leaves an earlier, un-toggled turn open.
- [x] 5.4 Test: "Fold all turns" and the per-turn control still fold, and a manually folded turn
      stays folded when a new turn arrives.

## 6. The cross-agent send picker is removed

- [ ] 6.1 Delete `hub/ui/src/components/agents/ComposerAgentSelector.tsx` and
      `hub/ui/src/__tests__/composerAgentSelector.test.tsx`.
- [ ] 6.2 Remove the `targetAgent`/`onTargetAgentChange` props and the selector render from
      `Composer.tsx`.
- [ ] 6.3 Remove the `targetAgent` state, its reset effect, and the `redirectsAgent` branch from
      `AgentOutputPanel.tsx`. Submissions always target `agent.name`.
- [ ] 6.4 Surface `collaboration_ready` on `AgentCard.tsx` beside the runner/model summary.
- [ ] 6.5 Test: the composer renders no agent selector; a submission posts the current agent's name.
- [ ] 6.6 Test: an agent that cannot collaborate is flagged on its card.

## 7. Verification

- [ ] 7.1 `pytest hub/tests/ -v` — baseline 766 passed / 9 skipped.
- [ ] 7.2 `cd hub/ui && npm test` — baseline 458 passed.
- [ ] 7.3 `npx tsc --noEmit`; `ruff check` on every touched Python file.
- [ ] 7.4 `openspec validate --specs --strict`.
- [ ] 7.5 `npm run build` + `pytest hub/tests/test_ui_staleness.py` to regenerate `hub/hub/static/ui`.
- [ ] 7.6 **Live** against `proj-a35df4bc` on a Hub restarted on this change's own built code:
      `GET /agents/agent-context?agent=claude-haiku-1` names `claude-haiku-2`, `codex-mini-1`,
      `codex-mini-2` and contains no stand-down block.
- [ ] 7.7 **Live**: send `claude-haiku-1` the operator's original failing instruction and confirm
      from chat history that it acts on it and a real message row appears for the recipient.
- [ ] 7.8 **Live**: same instruction to `codex-mini-1` — its `send_message` succeeds, proving the
      app-server default. This is the direct test of "we need codex collaborating".
- [ ] 7.9 **Live**: `GET /agents` reports real model names, not `"Native"`.
- [ ] 7.10 **Live** UI: neutral operator bubble in both themes; no halo or band around the composer;
      sending leaves earlier turns open; no target-agent picker.
