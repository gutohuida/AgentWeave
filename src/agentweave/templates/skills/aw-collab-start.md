---
name: aw-collab-start
description: Orient yourself at the start of an AgentWeave session — read your assigned role from roles.json, check your inbox for unread messages, and list your active tasks. Run this automatically at the beginning of any session in an AgentWeave project.
---

You are working inside an AgentWeave collaboration session. Orient yourself before doing anything else.

**Project:** {project_name}
**Mode:** {mode}
**Principal agent:** {principal}
**All agents:** {agents_list}

Run the following steps in order:

1. Read `.agentweave/roles.json` to find your assigned role in `agent_assignments.<your_name>`, then read the corresponding guide in `.agentweave/roles/<role_key>.md`.
2. Read `agentweave.yml` `quality:` section (or check `session.json` `quality` key if no yml) — note the active settings.
3. Run `agentweave inbox` to see unread messages addressed to you.
4. Run `agentweave task list` to see all active tasks, then filter by your agent name if needed.
5. Read `.agentweave/shared/context.md` for today's focus and any recent decisions.
6. Check `.agentweave/shared/checkpoints/` for any checkpoint file matching your agent name (e.g. `claude-*.md`). If one exists, read the most recent file — your "Next Steps" from the last session is your starting point for this session.

After completing the steps above, briefly report:
- Your assigned role and responsibilities
- Active quality settings (see role-specific guidance below)
- Number of unread messages (and from whom)
- Your assigned tasks and their current status
- Any blockers or items needing attention
- Whether you found a prior checkpoint (and if so, what the next step is)

**Role-specific quality orientation (when quality is configured):**

If your role is an **implementing role** (backend_dev, frontend_dev, fullstack_dev, etc.):
- Write tests before implementing (TDD)
- Produce a decision doc before marking tasks complete if `docs_threshold` applies
- Doc path: `<docs_path>/<task-id>.md` (or `.agentweave/code-docs/<task-id>.md` if `docs_path` unset)

If your role is **code_reviewer**:
- Tasks in your queue are in `under_review` status — run `agentweave task list --status under_review`
- Use `/aw-verify <task-id>` for the structured zero-trust review sequence
- Decision docs are at: `<docs_path>/<task-id>.md`

If you are the **principal** or **project_manager**:
- After tasks are marked `completed`, route to `code_reviewer` if `review_required: true`
- Check `echo_chamber_guard` before routing — reviewer must differ from implementer if `enforce`
- Check for tasks stuck in `under_review` — these may need a nudge to the reviewer

If quality is not configured: no governance active, proceed normally.
