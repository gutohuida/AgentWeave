# Evidence — the-copilot-catalog-matches-the-cli (R1 and R2, 2026-10-12, work PC)

No prompt was sent in any capture: no `session/prompt`, no premium request.

| File | What it is |
|---|---|
| `help-config-1.0.94-3.txt` | `copilot help config` via the npm shim on PATH. The native binary auto-updates to 1.0.94-3 when `--no-auto-update` is absent. Written by PowerShell 5 with a UTF-8 BOM; strip the BOM before copying it to `tests/fixtures`. |
| `help-config-no-auto-update-1.0.89-1.txt` | `copilot.exe --no-auto-update help config`. This is the binary `copilot_probe.resolve_copilot_executable` returns, run with the flag `build_acp_argv` always passes (`copilot_acp.py:1944`). So it is the version the Hub actually spawns on this machine. |
| `help-model-and-effort-flags-1.0.94-3.txt` | The `--model`, `--reasoning-effort` and `--context` sections of `copilot --help`. |
| `r1_model_probe.py` | Spawns the Hub's binary with the Hub's flags and sends only `initialize` and `session/new`. It prints the `model` and `reasoning_effort` config options and `models.availableModels` / `currentModelId`. |
| `r1-probe-<model>.log` | One run per requested model: `claude-opus-4.7` (removed), `grok-4.7` (added in 1.0.94-3), `claude-haiku-5.5` (the WPC-3 model), `gpt-5-mini`, `gpt-5.5`, no `--model` (Auto), and `gpt-5-mini --reasoning-effort max`. |
| `r2_model_probe.py` | R2's copy of `r1_model_probe.py`. The only change: it prints `result keys (as sent)` in the order the result arrived, where R1's printed them sorted. Same flags, still `initialize` and `session/new` only. Note that `r1_model_probe.py`'s docstring says "CLI 1.0.94-3", but it spawns `resolve_copilot_executable` with `--no-auto-update`, which is 1.0.89-1 here (its own logs' `agentInfo.version`). |
| `r2-probe-claude-opus-4.7.log` | R2 rerun of the removed model. Same silent `claude-sonnet-5`, and the raw key order of `session/new`'s result: `models`, `configOptions`, `modes`, `sessionId`. Fixtures must use that order (tasks 1.7, 1.8). |
| `r2-probe-gpt-5.5-effort-high.log` | R2's control for the effort fallback: `gpt-5.5 --reasoning-effort high` reports `reasoning_effort` `high`. So the flag is honoured, and `gpt-5-mini`'s `max`→`medium` is a fallback. |

The probes ran under the operator's own `~/.copilot` (no `COPILOT_HOME`), on the same GitHub account the Hub's `copilot-home` uses. Neither config sets a default `model`.

## What the probes show

| Requested | `currentModelId` at `session/new` | Effort options offered |
|---|---|---|
| `claude-opus-4.7` | `claude-sonnet-5`, silently | low, medium, high, xhigh, max |
| `grok-4.7` | `claude-sonnet-5`, silently | low, medium, high, xhigh, max |
| `claude-haiku-5.5` | `claude-haiku-5.5` | low, medium, high, xhigh, max |
| `gpt-5-mini` | `gpt-5-mini` | low, medium, high |
| `gpt-5.5` | `gpt-5.5` | none, low, medium, high, xhigh |
| *(none: Auto)* | `claude-sonnet-5`. This is not a resolution: Auto resolves mid-turn. | low, medium, high, xhigh, max |
| `gpt-5-mini --reasoning-effort max` | `gpt-5-mini`; effort `currentValue` is `medium`, silently | low, medium, high |

None of the runs emitted a `session.warning`, a `session.error` or a `session.model_change` event before the probe closed. That covers only the seconds after `session/new` with no prompt; whether a prompted turn emits one is untested (task 3.2).

**R2: what the probes do not cover.** None selected an agent. The Hub selects its own agent with `session/set_config_option` before every first prompt, and the agent file carries `model:` and `reasoningEffort:` frontmatter, so the model the Hub's sessions report after selection is UNVERIFIED (design D3). The probes also ran under the operator's `~/.copilot`, not the Hub's `copilot-home`.

The session's `models.availableModels` (22 entries, `auto` included) is the account's entitled list. Every entry carries `_meta.copilotUsage`, the premium multiplier. The list is identical to the list in the parent session's own environment.

**R3: what these logs say about which build to follow.** R3 added no evidence files and sent no prompt. Its reading of the existing logs:
- The 21 live non-`auto` models are all in 1.0.94-3's help.
- `claude-haiku-5.5` and `claude-sonnet-5.5`, absent from 1.0.89-1's help, run on 1.0.89-1 (`r1-probe-claude-haiku-5.5.log`, `currentModelId` `claude-haiku-5.5`).
- `claude-opus-4.7`, present in 1.0.89-1's help, is not offered.

So the model list is the service's, and both the catalog and the drift script follow the newest help (design D1, D2 R3).

The only captured agent-selection answer is 1.0.88's (`{"configOptions":[mode, agent, allow_all]}`, no `model`). The 1.0.89-1 answer is uncaptured, and task 3.2 records it.
