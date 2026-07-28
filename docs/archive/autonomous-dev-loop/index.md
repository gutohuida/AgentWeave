# Autonomous Dev Loop (shelved)

**Status:** Shelved 2026-07-28 — planned, never implemented.
**Archived changes:** `openspec/changes/archive/2026-07-28-*` (five change folders)

!!! warning "This describes a plan, not a feature"
    Nothing on this page shipped. It is kept as a record of an idea and of the
    investigation work that was completed before the idea was set aside. Do not
    read any of it as a description of how AgentWeave behaves today.

---

## The idea

Run a near-continuous development loop on the AgentWeave repo itself, using three
agents — `opencode`, `kimi`, and `codex` — coordinated through a **second Hub on
port 8001**, separate from the interactive Hub on 8000.

The agents would research, design, implement, review, and document changes on
feature branches. The human role would shrink to two decisions: **topic selection**
and **the final merge to `master`**. The loop would be pausable overnight and
resumable the next morning with a single command.

Planned shape:

- A dev Hub on `:8001` with its own database
- One git worktree per agent, each on a long-lived agent branch, each with a
  long-lived CLI session pointed at the dev Hub
- An `autonomous_dev` role assigned to all three agents
- Staggered cron: kickoff jobs, then steady-state jobs
- A kickoff message template briefing each agent on every wake
- Hub task templates for implementation, peer review, research proposal, escalation
- Reviewer assignment by round-robin among agents that did not author the change
- An operator runbook

## Why it was blocked

The loop needed three runtime guarantees that AgentWeave did not have:

| # | Required guarantee | Planned fix |
|---|---|---|
| 0 | The Hub can read a trustworthy context-window percentage for every active session | `fix-context-tracking` |
| 1 | The watchdog can force a checkpoint and fresh session at a context threshold, including force-kill for agents that ignore it | `add-auto-reset-mode` |
| 2 | The watchdog never silently loses a trigger message | `add-durable-trigger-retry` |

An investigation change (`investigate-blockers`, 21/25 tasks complete) shipped
findings only — deliberately no fixes. The three fix changes and the loop itself
never started (0 tasks complete each).

## What the investigation actually found

The findings are worth keeping. They are in
`openspec/changes/archive/2026-07-28-investigate-blockers/findings/`
(`blocker-0.md`, `blocker-1.md`, `blocker-2.md` — 732 lines total).

Confirmed defects:

- **OpenCode context usage never reaches the Hub.**
  `_parse_opencode_stdout_line` (`src/agentweave/watchdog.py`) returns
  `usage_data=None` and ignores `step_finish.tokens`. Because
  `usage_data_for_context` stays `None`, the branch that writes
  `context_usage/<agent>.json` never fires for opencode.
- **`load_json` fails on a UTF-8 BOM.** `src/agentweave/utils.py` opens with
  `encoding="utf-8"`; a BOM raises `JSONDecodeError` and the function returns
  `None`. The watchdog's `_check_context_usage` reads `None or {}` as "no data"
  and silently skips the warning. Found when an external script wrote the file
  with PowerShell `Set-Content`, which emits a BOM by default.
- The Claude, Kimi-wire, and Codex paths were all left **UNTESTED** (no CLI
  available / auth failure at the time), not cleared.

### A later finding, not in the investigation

The Claude path has a separate bug that the investigation never reached.
`_write_context_usage()` computes:

```python
percent = min(100, int((input_tokens / context_limit) * 100))
```

…but the `result`-event parser extracts only `input_tokens` and `output_tokens`
from `usage`, discarding `cache_read_input_tokens` and
`cache_creation_input_tokens`. Claude Code uses prompt caching on essentially
every turn, so most of the real context comes back as *cache reads* and
`input_tokens` is only the small uncached delta. The percentage is therefore
computed from a fraction of the true context and reads near zero regardless of
how full the window actually is.

The Codex writer (`_write_codex_context_usage`) does track `cached_input_tokens`,
so the two runners disagree about what "context usage" means.

**Implication:** context tracking looks broken because the CLIs hide the data, but
at least for Claude the data is present in the stream and is being dropped during
parsing.

## If this is ever revived

Start from the findings, not from the change proposals. Specifically:

1. Re-test the three UNTESTED runner paths — the investigation could not.
2. Fix the cache-token accounting before anything else; a context percentage that
   under-reports makes auto-reset actively dangerous, because the watchdog would
   never fire a reset until the session was already blown.
3. Settle what "context usage" means across runners *once*, then make every writer
   agree, rather than fixing each path independently.
