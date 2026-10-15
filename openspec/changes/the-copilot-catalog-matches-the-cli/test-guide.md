# Test guide — The Copilot catalog matches the CLI

## Agent-verifiable

| What | How | Pass |
|---|---|---|
| The catalog matches 1.0.94-3 | `py -3.11 scripts/check_model_catalog.py --provider copilot --help-config tests/fixtures/copilot/help-config-1.0.94-3.txt` | Exit 0, no drift. |
| The script compares against the newest build and names the Hub's (R3) | `py -3.11 scripts/check_model_catalog.py --provider copilot` | Exit 0 with no drift against the newest build's help (1.0.94-3 today). It prints that version, plus an information line naming the Hub's `copilot.exe --no-auto-update` build (1.0.89-1 on the work PC). R2 expected nine drifts here; R3 reverted the comparison (D2). |
| A newly documented model is accepted | `pytest hub/tests/test_model_catalog.py -q -k copilot` | Green. Task 1.2 failed before 2.1. |
| A stored removed model still sends | the trigger route test (task 1.4) | 200 for an unchanged stored model that neither catalog declares, 400 for a new undeclared one (R3: R2's version could not fail). |
| The pill names an unrecognised model (R3) | `cd hub/ui && npx vitest run ModelPicker` (task 1.12) | `claude-opus-4.7 — unrecognised`, never `— latest (now Auto)`. |
| Substitution is reported at session start | `pytest hub/tests/test_copilot_acp_mapper.py -q -k session_start` | One diagnostic for a mismatch, read after agent selection (task 1.7a). None for `auto`, for a match, or for a response with no `models`. |
| Usage records the model that ran | the same test | `usage.model == "claude-sonnet-5"` when `claude-opus-4.7` was requested. |
| One-shot workers on a stored removed model | the worker test (task 1.11) | The behaviour wpc3-f chose. |
| Trial Hub drive (tasks 3.1 and 3.2) | `POST /api/v1/projects/{id}/agent/trigger` on `:8010` with a Copilot agent | `claude-haiku-5.5` runs; a stored `claude-opus-4.7` runs as `claude-sonnet-5`, and the diagnostic is in the conversation. |
| A model-free ACP read of what this account offers | `evidence/r1_model_probe.py --model <id>` | Prints `currentModelId` and `availableModels`. Sends no prompt. |

## Human-only

- The answers to wpc3-a … wpc3-g.
- Whether the `copilot.model_substituted` / `copilot.effort_substituted` notice reads well in the conversation, and whether the pill's "— unrecognised" label (task 2.3a) reads well.
- After a future `copilot update`, rerun the drift script. It is manual by design (D13 R2), so someone has to remember to do it.
