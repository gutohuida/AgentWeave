# Adding a New Agent to AgentWeave

This guide explains how to add support for a new AI agent (e.g., MiniMax, GLM, or any other CLI-based AI assistant) to the AgentWeave framework.

## Overview

AgentWeave uses a flexible agent system where any agent name matching the pattern `^[a-zA-Z0-9_-]{1,32}$` is accepted. However, to provide first-class support with custom context files, optimized CLI integration, and role assignments, you'll need to modify several files.

## Quick Start: Minimal Support

For basic support, you only need to add the agent name to `KNOWN_AGENTS`:

```python
# src/agentweave/constants.py
KNOWN_AGENTS = [
    # ... existing agents ...
    "minimax",  # NEW
]
```

With just this change:
- The agent name will be validated as legitimate
- The agent will use the generic `AGENTS.md` context file
- The agent will use default CLI handling (same as Claude)
- The agent can fully participate in the collaboration framework

## Full First-Class Support

For complete integration with custom templates and optimized CLI handling, follow all steps below.

---

## Step-by-Step Implementation

### Step 1: Register the Agent in Constants

**File:** `src/agentweave/constants.py`

#### 1.1 Add to KNOWN_AGENTS list

Locate the `KNOWN_AGENTS` list (around line 52) and add your agent:

```python
KNOWN_AGENTS = [
    "claude",     # Claude Code (Anthropic)
    "kimi",       # Kimi Code (Moonshot AI)
    "gemini",     # Gemini CLI (Google)
    # ... other agents ...
    "minimax",    # MiniMax AI
    "glm",        # ChatGLM (Zhipu AI)
]
```

#### 1.2 Add default role mapping (optional)

Locate `DEFAULT_AGENT_ROLES` (around line 108) and add a suggested role:

```python
DEFAULT_AGENT_ROLES = {
    "claude": "tech_lead",
    "kimi": "backend_dev",
    # ... other agents ...
    "minimax": "backend_dev",
    "glm": "fullstack_dev",
}
```

Available roles: `tech_lead`, `architect`, `backend_dev`, `frontend_dev`, `fullstack_dev`, `qa_engineer`, `devops_engineer`, `security_engineer`, `data_engineer`, `ml_engineer`, `technical_writer`, `code_reviewer`, `project_manager`

#### 1.3 Add agent-specific context file mapping (optional)

Locate `AGENT_CONTEXT_FILES` (around line 125) and add a mapping:

```python
AGENT_CONTEXT_FILES: dict = {
    "claude": "CLAUDE.md",
    "gemini": "GEMINI.md",
    "minimax": "MINIMAX.md",  # NEW
    "glm": "GLM.md",          # NEW
}
```

If not specified, the agent will use `AGENTS.md` (the default).

---

### Step 2: Create Agent Context Template

**File:** `src/agentweave/templates/<agent>_context.md`

Create a new template file for your agent. Use the existing templates as a reference:
- `claude_context.md` - Full-featured template with all sections
- `kimi_context.md` - Same structure, adjusted for Kimi's workflow

#### Template Structure

Your template should include:

```markdown
<!-- {version} — auto-generated from .agentweave/ai_context.md -->
<!-- You MAY edit this file directly for project-specific updates. -->
<!-- To regenerate from ai_context.md, run: agentweave sync-context --agent <agent> -->
<!-- To update with latest AI best practices, run: agentweave update-template --agent <agent> -->

> **Token-saving note:** Do NOT read `.agentweave/ai_context.md` — this file already contains all necessary project context. Reading it again wastes tokens.

# AI Workflow Context

## Session Start Checklist (REQUIRED)

**Before doing ANY work, complete these steps in order:**

1. **Read `.agentweave/roles.json`** — find your assigned role in `agent_assignments.<your_name>`, then read the corresponding guide in `.agentweave/roles/<role_key>.md`.
2. **Read `.agentweave/protocol.md`** — learn the collaboration protocol.
3. **Read `.agentweave/shared/context.md`** — see current focus.
4. **Check for AgentWeave MCP tools** — look for `send_message`, `get_inbox`, etc.
5. **Run `agentweave status`** — see pending tasks.

## Role Adherence Rules

[Include MUST/MUST NOT rules for agent behavior]

## Project Overview

[Template sections for users to fill in]

## Tech Stack

## Essential Commands

## Architecture

## Code Standards

### Quality
### Security
### Workflow
### Security Guardrails
### Performance Guardrails

## Multi-Agent Workflow

[Critical section: explain how to work with other agents]

### If MCP tools are available
### Parallel Execution (When Principal)
### Phase Discipline
### If no MCP tools

## Sub-Agent Setup

## When Compacting
```

#### Key Customizations

1. **Update agent references**: Change references like "Claude is building backend" to match your agent's perspective
2. **Adjust capabilities**: Add or remove sections based on what your agent can do
3. **CLI-specific instructions**: Include any unique CLI commands or flags your agent supports

---

### Step 3: Update CLI Template Selection

**File:** `src/agentweave/cli.py`

Two functions need updating: `cmd_init()` and `cmd_sync_context()`.

#### 3.1 Update cmd_init() (around line 190)

Locate this line:
```python
template_name = "claude_context" if ag == "claude" else "kimi_context"
```

Replace with:
```python
if ag == "claude":
    template_name = "claude_context"
elif ag == "kimi":
    template_name = "kimi_context"
elif ag == "minimax":
    template_name = "minimax_context"
elif ag == "glm":
    template_name = "glm_context"
else:
    template_name = "kimi_context"  # Default fallback
```

#### 3.2 Update cmd_sync_context() (around line 1028)

Find the same pattern and update it identically.

#### 3.3 Update MCP setup commands (around line 1221)

Locate the `_mcp_args()` function and add your agent:

```python
def _mcp_args(agent: str) -> list:
    if agent == "claude":
        return ["claude", "mcp", "add", "agentweave", "--", server_cmd]
    if agent == "kimi":
        return ["kimi", "mcp", "add", "--transport", "stdio", "agentweave", "--", server_cmd]
    if agent == "minimax":
        return ["minimax", "mcp", "add", "agentweave", "--", server_cmd]
    if agent == "glm":
        return ["glm", "mcp", "add", "agentweave", "--", server_cmd]
    # Generic fallback
    return [agent, "mcp", "add", "agentweave", "--", server_cmd]
```

**Note:** Adjust the command based on your agent's actual MCP configuration CLI.

#### 3.4 Update yolo mode flag hint (around line 1670)

Locate `cmd_yolo()` and update the flag hint logic:

```python
if enabled:
    if agent == "claude":
        flag_hint = "--dangerously-skip-permissions"
    elif agent == "minimax":
        flag_hint = "--no-confirm"  # Example: MiniMax-specific flag
    else:
        flag_hint = "--yolo"
    print_success(f"Yolo mode ENABLED for {agent} ({flag_hint} will be used)")
```

---

### Step 4: Update Watchdog CLI Integration

**File:** `src/agentweave/watchdog.py`

#### 4.1 Update _agent_ping_cmd() (around line 446)

This function builds the CLI command to ping agents. Add your agent's specific CLI format:

```python
def _agent_ping_cmd(agent: str, prompt: str, session_id: Optional[str] = None) -> list:
    """Return the CLI command to ping an agent with a prompt."""
    if agent == "kimi":
        cmd = ["kimi", "--print"]
        if session_id:
            cmd += ["--session", session_id]
        cmd += ["-p", prompt]
        return cmd
    
    if agent == "minimax":
        # MiniMax CLI format - adjust to match actual CLI
        cmd = ["minimax", "--print"]
        if session_id:
            cmd += ["--session", session_id]
        cmd += ["-p", prompt]
        return cmd
    
    if agent == "glm":
        # GLM CLI format - adjust to match actual CLI
        cmd = ["glm", "chat"]
        if session_id:
            cmd += ["--resume", session_id]
        cmd += ["--prompt", prompt]
        return cmd
    
    # Default for Claude and other CLIs
    cmd = [agent, "--output-format", "stream-json", "--verbose"]
    if session_id:
        cmd += ["--resume", session_id]
    cmd += ["-p", prompt]
    return cmd
```

#### 4.2 Update _check_cli_available() (around line 880)

If your agent's CLI executable name differs from its agent name, update this function:

```python
def _check_cli_available(agent: str) -> bool:
    """Check if an agent's CLI is available in PATH."""
    import shutil
    
    # Map agent names to their CLI executable names
    cli_names = {
        "kimi": "kimi",
        "minimax": "minimax-cli",  # Example: different CLI name
        "glm": "glm",
    }
    cli_name = cli_names.get(agent, agent)
    return shutil.which(cli_name) is not None
```

#### 4.3 Update session persistence handling (around line 795)

Some agents (like Kimi) don't support session persistence. If your agent is similar, exclude it:

```python
# Agents that don't support session persistence
NO_SESSION_AGENTS = {"kimi", "minimax"}  # Add your agent here

saved_session = _load_agent_session(agent) if agent not in NO_SESSION_AGENTS else None
```

#### 4.4 Add output parsing (optional)

If your agent has a unique output format, you need to add a parser. Here's how:

**Option A: Use existing parsers (simplest)**

If your agent outputs JSONL like Claude, use `_parse_claude_stream_line()`. If it outputs Python-repr like Kimi, use `_KimiParser`.

**Option B: Create a custom parser**

Add a new parser function and call it in `_run_agent_subprocess()`:

```python
def _parse_minimax_stream_line(line: str) -> list:
    """Parse one line from MiniMax output.
    
    Returns a list of human-readable strings to display.
    Empty list means the line carries no user-visible content.
    """
    # Example: Parse JSON output
    try:
        data = json.loads(line)
        if "content" in data:
            return [data["content"]]
        if "tool_call" in data:
            return [f"🔧 {data['tool_call']}"]
    except json.JSONDecodeError:
        pass
    return []
```

Then in `_run_agent_subprocess()` (around line 744), add:

```python
# Around line 639: Initialize your parser
minimax_parser = None
if agent == "minimax":
    minimax_parser = True  # Or your parser object

# Around line 744: Use your parser
if kimi_parser is not None:
    readable_lines = kimi_parser.feed(line)
elif agent == "minimax":
    readable_lines = _parse_minimax_stream_line(line)
else:
    readable_lines = _parse_claude_stream_line(line)
```

#### 4.5 Add session detection (optional)

If your agent stores sessions in a custom location, add detection logic. See `_detect_kimi_session()` (line 669) and `_get_kimi_session_from_json()` (line 586) as examples.

```python
def _detect_minimax_session() -> None:
    """Background thread: poll for new MiniMax session."""
    # Implement session detection for your agent
    pass
```

Then start the detection thread in `_run_agent_subprocess()` (around line 731):

```python
if agent == "kimi":
    threading.Thread(target=_detect_kimi_session, daemon=True).start()
elif agent == "minimax":
    threading.Thread(target=_detect_minimax_session, daemon=True).start()
```

---

### Step 5: Update MCP Server Documentation (Optional)

**File:** `src/agentweave/mcp/server.py`

Update the docstring (around line 11-14) to include your agent:

```python
"""AgentWeave MCP server.

Exposes AgentWeave messaging and task management as MCP tools.

Usage:
    agentweave-mcp                         # stdio (default)

Configure in Claude Code:
    claude mcp add agentweave -- agentweave-mcp

Configure in Kimi Code:
    kimi mcp add --transport stdio agentweave -- agentweave-mcp

Configure in MiniMax:
    minimax mcp add agentweave -- agentweave-mcp
"""
```

---

### Step 6: Update Help Text Examples (Optional)

**File:** `src/agentweave/cli.py`

In `create_parser()` (around line 1777-1824), update help texts to include your agent:

```python
help="Assign to agent (any agent name, e.g. kimi, gemini, minimax)"
help="Which agent receives... (e.g. claude, kimi, gemini, minimax)"
```

---

### Step 7: Test Your Integration

After making all changes:

1. **Install in development mode:**
   ```bash
   pip install -e ".[dev]"
   ```

2. **Initialize a test session:**
   ```bash
   agentweave init --project "Test Project" --agents claude,minimax
   ```

3. **Verify the agent context file was created:**
   ```bash
   ls MINIMAX.md  # or your agent's context file
   ```

4. **Test task delegation:**
   ```bash
   agentweave quick --to minimax "Test task for new agent"
   agentweave relay --agent minimax
   ```

5. **Test MCP setup (if applicable):**
   ```bash
   agentweave mcp setup
   ```

6. **Test watchdog auto-ping:**
   ```bash
   agentweave start --auto-ping
   # Send a message to the new agent and verify it gets pinged
   ```

---

## Reference: Files Modified

| File | Change | Purpose |
|------|--------|---------|
| `src/agentweave/constants.py` | Add to lists | Register agent name, role, context file |
| `src/agentweave/templates/<agent>_context.md` | Create | Agent-specific context template |
| `src/agentweave/cli.py` | Edit 4 places | Template selection, MCP setup, yolo flag |
| `src/agentweave/watchdog.py` | Edit 3-6 places | CLI command, availability check, parsing, sessions |
| `src/agentweave/mcp/server.py` | Edit docstring | MCP configuration examples |

---

## Example: Adding MiniMax Agent

Here's a complete example of adding the MiniMax agent:

### 1. constants.py changes

```python
KNOWN_AGENTS = [
    # ... existing agents ...
    "minimax",
]

DEFAULT_AGENT_ROLES = {
    # ... existing roles ...
    "minimax": "backend_dev",
}

AGENT_CONTEXT_FILES = {
    "claude": "CLAUDE.md",
    "gemini": "GEMINI.md",
    "minimax": "MINIMAX.md",
}
```

### 2. Create templates/minimax_context.md

Copy `kimi_context.md` and adjust:
- Change Kimi-specific references to MiniMax
- Update parallel execution examples
- Adjust sub-agent setup instructions if needed

### 3. cli.py changes

```python
# In cmd_init() and cmd_sync_context():
if ag == "claude":
    template_name = "claude_context"
elif ag == "kimi":
    template_name = "kimi_context"
elif ag == "minimax":
    template_name = "minimax_context"
else:
    template_name = "kimi_context"
```

```python
# In _mcp_args():
if agent == "minimax":
    return ["minimax", "mcp", "add", "agentweave", "--", server_cmd]
```

```python
# In cmd_yolo():
if agent == "claude":
    flag_hint = "--dangerously-skip-permissions"
elif agent == "minimax":
    flag_hint = "--no-confirm"  # MiniMax-specific
else:
    flag_hint = "--yolo"
```

### 4. watchdog.py changes

```python
# In _agent_ping_cmd():
if agent == "minimax":
    cmd = ["minimax", "--print"]
    if session_id:
        cmd += ["--session", session_id]
    cmd += ["-p", prompt]
    return cmd
```

```python
# In _check_cli_available():
cli_names = {
    "kimi": "kimi",
    "minimax": "minimax-cli",  # If CLI name differs
}
cli_name = cli_names.get(agent, agent)
```

```python
# Session persistence (if MiniMax doesn't support it):
NO_SESSION_AGENTS = {"kimi", "minimax"}
saved_session = _load_agent_session(agent) if agent not in NO_SESSION_AGENTS else None
```

---

## Troubleshooting

### Agent not recognized
- Verify the agent name is added to `KNOWN_AGENTS` in `constants.py`
- Ensure the name matches the regex `^[a-zA-Z0-9_-]{1,32}$`

### Context file not generated
- Check that template selection logic in `cli.py` includes your agent
- Verify the template file exists in `src/agentweave/templates/`

### CLI not responding to pings
- Verify `_agent_ping_cmd()` returns the correct command format
- Check that the agent CLI is installed and in PATH
- Test the command manually: `<agent> -p "test prompt"`
- If CLI name differs from agent name, check `_check_cli_available()`

### MCP setup fails
- Verify the MCP setup command in `_mcp_args()` matches the agent's CLI
- Check that the agent supports MCP server configuration

### Session persistence not working
- If your agent doesn't support session resumption, add it to `NO_SESSION_AGENTS`
- Verify session detection logic if using custom session storage

### Output not showing in watchdog
- Check if your agent needs a custom output parser
- Verify the parser is being called in `_run_agent_subprocess()`
- Check logs for parsing errors

---

## Advanced: Complete Integration Checklist

Use this checklist when adding full support for a new agent:

- [ ] Add to `KNOWN_AGENTS` in `constants.py`
- [ ] Add to `DEFAULT_AGENT_ROLES` (optional)
- [ ] Add to `AGENT_CONTEXT_FILES` (optional)
- [ ] Create `<agent>_context.md` template
- [ ] Update template selection in `cmd_init()`
- [ ] Update template selection in `cmd_sync_context()`
- [ ] Add MCP setup command in `_mcp_args()`
- [ ] Update yolo flag hint in `cmd_yolo()` (if needed)
- [ ] Add CLI command in `_agent_ping_cmd()`
- [ ] Update `_check_cli_available()` (if CLI name differs)
- [ ] Handle session persistence (if agent doesn't support it)
- [ ] Add output parser (if agent has unique output format)
- [ ] Add session detection (if agent uses custom session storage)
- [ ] Update MCP server docstring
- [ ] Update help text examples (optional)
- [ ] Test all commands: init, relay, quick, mcp setup, start (watchdog)

---

## Contributing Back

If you've added support for a new agent that others might find useful:

1. Follow this guide completely
2. Test all functionality (init, sync-context, relay, mcp setup, watchdog)
3. Submit a pull request with:
   - Clear description of the agent
   - Link to agent's CLI documentation
   - Confirmation that you've tested the integration
   - List of any agent-specific limitations or requirements

---

## Questions?

- Check the main [AGENTS.md](https://github.com/gutohuida/AgentWeave/blob/master/AGENTS.md) for framework overview
- Review existing agent implementations as reference
- Open an issue on GitHub for help
