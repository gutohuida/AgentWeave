---
name: aw-sync
description: Sync the AgentWeave project context — regenerate all agent context files (CLAUDE.md, AGENTS.md, GEMINI.md) from the source at .agentweave/ai_context.md. Run this after editing ai_context.md to make sure all agents see updated context.
---

Sync the project context so all agents see up-to-date information.

**Project:** Agentweave
**Agents:** claude, kimi, minimax

The source of truth for project context is `.agentweave/ai_context.md`. Agent context files at the project root (e.g., `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`) are generated from it and must be regenerated whenever it changes.

Steps:

1. Check whether `.agentweave/ai_context.md` exists and show the user its last few lines so they can confirm it is up to date.
2. Run `agentweave sync-context` to regenerate all agent context files.
3. Show which files were updated (the command prints this).
4. Remind the user:
   > Agent context files have been updated. Each agent will see the new context on their **next session start** — no action needed if sessions are already running.

If `agentweave sync-context` is not available, instruct the user to run it manually or check that AgentWeave is installed correctly (`agentweave --help`).
