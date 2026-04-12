# CLI Commands Reference

## Session

```bash
agentweave init --project "Name" --agents claude,kimi
agentweave status                          # show full session status with watchdog state
agentweave summary                         # quick overview for relay decisions
agentweave session register --agent <name> --session <id>   # register pilot agent session
```

### Summary Output

The `summary` command provides a quick status overview before delegation:
- Tasks by status (waiting, in progress, ready for review)
- Unread messages per agent
- Action items (who to notify, what to review)

## Delegation

```bash
agentweave quick --to kimi "Task description"       # quick task delegation
agentweave delegate --to kimi "Task description"    # alias for 'quick'
agentweave relay --agent kimi                       # generate relay prompt
agentweave relay --agent minimax --run              # auto-run for claude_proxy agents
agentweave inbox --agent claude                     # check agent inbox
```

## Messages

```bash
agentweave msg send --to kimi --subject "Update" --message "Task is done"
agentweave msg read <message_id>           # mark message as read
```

## Agent Runner

### Claude Proxy Agents (Minimax, GLM, etc.)

```bash
agentweave agent configure minimax                      # use built-in defaults
agentweave agent configure glm                          # use built-in defaults
agentweave agent configure mymodel \                    # custom OpenAI-compatible provider
  --runner claude_proxy \
  --base-url https://api.example.com/v1 \
  --api-key-var MY_MODEL_API_KEY
agentweave agent set-session minimax <session-id>       # register Claude resume ID manually
agentweave agent set-model minimax <model-name>         # set model for claude_proxy agent

agentweave switch minimax        # output eval-able export commands
agentweave run --agent minimax   # set env vars + launch Claude with relay prompt
```

### Pilot Mode

```bash
agentweave agent configure kimi --pilot                 # enable pilot mode
agentweave agent configure kimi --no-pilot              # disable pilot mode
agentweave session register --agent kimi --session <id> # register session ID
```

Pilot mode disables auto-triggering, giving you manual control over agent sessions. See [Pilot Mode Guide](../guides/pilot-mode.md) for details.

## Tasks

```bash
agentweave task create --title "Feature X" --assignee kimi --priority high
agentweave task list
agentweave task show <task_id>
agentweave task update <task_id> --status in_progress
agentweave task update <task_id> --status completed
agentweave task update <task_id> --status approved
agentweave task update <task_id> --status revision_needed --note "Fix X"
```

## Transport

```bash
agentweave transport setup --type http --url ... --api-key ... --project-id ...
agentweave transport setup --type git --cluster yourname
agentweave transport status
agentweave transport pull
agentweave transport disable
agentweave hub-heartbeat         # publish agent status to Hub (HTTP transport only)
```

## Context Management

```bash
agentweave sync-context          # regenerate agent files from .agentweave/ai_context.md
agentweave update-template       # generate prompt to update template with new best practices
```

## Yolo Mode

```bash
agentweave yolo --agent claude --enable    # allow agent to act without confirmations
agentweave yolo --agent claude --disable   # re-enable confirmation prompts
```

## Human Interaction (Hub only)

```bash
agentweave reply --id <question_id> "Your answer"
```

## Watchdog

```bash
agentweave start       # start background watchdog
agentweave stop        # stop background watchdog
```

## Logs

```bash
agentweave log         # view structured event log
agentweave log -f      # watch log in real-time
```

## Roles

```bash
agentweave roles list                          # show all agents and their roles
agentweave roles add <agent> <role_id>         # add a role to an agent
agentweave roles remove <agent> <role_id>      # remove a role from an agent
agentweave roles set <agent> <role1,role2,...> # set multiple roles (replaces existing)
agentweave roles available                     # list available role types
```

**Available roles:** `tech_lead`, `architect`, `backend_dev`, `frontend_dev`, `fullstack_dev`, `qa_engineer`, `devops_engineer`, `security_engineer`, `data_engineer`, `data_scientist`, `mobile_dev`, `docs_writer`, `product_manager`, `project_manager`, `ui_designer`, `ux_researcher`

### Multi-Role Examples

```bash
# Add backend_dev role to claude (claude already has tech_lead)
agentweave roles add claude backend_dev

# Set multiple roles at once (replaces any existing roles)
agentweave roles set kimi backend_dev,frontend_dev

# Remove a specific role
agentweave roles remove claude backend_dev
```

When an agent has multiple roles, they receive all corresponding role guides at session start.

## Jobs (Scheduled Tasks)

```bash
# Create a scheduled job
agentweave jobs create \
  --name "Daily Report" \
  --agent claude \
  --message "Generate daily summary" \
  --cron "0 9 * * 1-5" \
  --session-mode new

# Manage jobs
agentweave jobs list                    # list all jobs
agentweave jobs list --agent kimi       # filter by agent
agentweave jobs get <job_id>            # show details and run history
agentweave jobs pause <job_id>          # disable a job
agentweave jobs resume <job_id>         # re-enable a job
agentweave jobs run <job_id>            # run immediately (manual trigger)
agentweave jobs delete <job_id>         # delete a job (--force to skip confirm)
```

See [AI Jobs Guide](../guides/ai-jobs.md) for detailed usage and examples.

## Session Management

```bash
# Save a context checkpoint before compacting or handoffs
agentweave checkpoint --agent claude --reason pre_handoff --note "Mid-implementation"
```

Creates a checkpoint file at `.agentweave/shared/checkpoints/<agent>-<timestamp>.md` with:
- Active tasks at time of checkpoint
- Files modified this session
- Decisions made with rationale
- Next steps for resuming
- Blockers and open questions

## MCP

```bash
agentweave mcp setup   # register MCP server with all session agents
```
