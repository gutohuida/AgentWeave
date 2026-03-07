# InterAgent

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/yourusername/interagent/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/interagent/actions)
[![PyPI version](https://badge.fury.io/py/interagent.svg)](https://badge.fury.io/py/interagent)

> **A collaboration framework for Claude Code and Kimi Code**

InterAgent enables Claude Code and Kimi Code to collaborate effectively on software development projects through structured protocols, task delegation, and shared state management.

---

## 🎯 Why InterAgent?

Claude and Kimi are both powerful coding assistants, but they have different strengths:

- **Claude** excels at architecture, system design, and documentation
- **Kimi** shines at implementation, tool usage, and optimization

**InterAgent** lets you leverage both by providing:

- 🎭 **Role-based collaboration** (Principal, Delegate, Reviewer)
- 📋 **Structured task delegation** with capability-based routing
- 👀 **Code review workflows** between agents
- 💬 **Discussion protocols** for complex decisions
- 📁 **Shared state** via Git-trackable files

---

## 🚀 Quick Start

### Installation

```bash
pip install interagent
```

### Initialize a Session

```bash
interagent init --project "My API" --principal claude
```

This creates an `.interagent/` directory with:
- Session configuration
- Task management
- Message queue
- Shared context

### Quick Start - Single Command

```bash
interagent quick --to kimi "Design database schema"
```

This single command:
- Creates a task
- Assigns it to Kimi
- Generates a message
- Prints what to tell Kimi

### Check Status

```bash
interagent status        # Detailed status
interagent summary       # Quick overview
```

---

## 💡 How It Works

InterAgent uses a **file-based protocol** where both agents read and write to a shared `.interagent/` directory:

```
Your Project/
├── .interagent/
│   ├── session.json          # Current session
│   ├── tasks/
│   │   ├── active/           # Active tasks
│   │   └── completed/        # Completed tasks
│   ├── messages/
│   │   ├── pending/          # Unread messages
│   │   └── archive/          # Message history
│   └── shared/
│       └── context.md        # Project context
└── [your code...]
```

**The user acts as the orchestrator**, prompting each agent to check the shared state:

1. **You:** "@Claude - You're Principal. Check `.interagent/` and delegate tasks to Kimi"
2. **Claude:** Reads files, creates task for Kimi
3. **You:** "@Kimi - Check `.interagent/` inbox"
4. **Kimi:** Reads task, implements, updates status
5. **You:** "@Claude - Kimi completed the task. Please review"

---

## 📚 Commands

### Quick Commands (Reduced Friction)

```bash
interagent quick --to kimi "Implement user auth"       # Single-command delegation
interagent relay --to kimi                              # Generate prompt to copy
interagent summary                                      # Quick overview for decisions
```

### Session Management

```bash
interagent init --project "Name" --principal claude    # Initialize session
interagent status                                       # Show status
interagent summary                                      # Quick summary for relay
```

### Task Management

```bash
interagent task create --title "Task" --assignee kimi   # Create task
interagent task list                                    # List all tasks
interagent task show task-xxx                           # Show task details
interagent task update task-xxx --status completed      # Update status
```

### Messaging

```bash
interagent inbox --agent kimi                           # Check inbox
interagent msg send --to kimi --message "Hello"         # Send message
interagent msg read msg-xxx                             # Mark as read
```

### Quick Delegation

```bash
interagent delegate --to kimi --task "Implement auth"   # Quick delegation
```

### Template Maintenance

Keep your project kickoff template current with new AI capabilities:

| Command | Description |
|---|---|
| `interagent update-template --agent claude` | Generate research prompt for Claude |
| `interagent update-template --agent kimi` | Generate research prompt for Kimi |
| `interagent update-template --agent claude --focus "sub-agents"` | Focus on a specific area |
| `interagent update-template --agent kimi --template-path ~/projects/template.txt` | Specify template path |

The generated prompt instructs the agent to search for new best practices,
review the current template, apply improvements, and write a `TEMPLATE_UPDATE.md`
summary of what changed.

---

## 🎭 Roles

### Principal Engineer
- Makes architectural decisions
- Delegates tasks to the Delegate
- Reviews completed work

### Delegate
- Executes assigned tasks
- Reports progress to Principal
- Requests help when needed

### Reviewer
- Reviews code from another agent
- Provides structured feedback
- Approves or requests revisions

---

## 🛡️ Safety Features

### Schema Validation
All JSON files are validated before saving:
- ✅ Task status must be valid
- ✅ Agent names must be "claude" or "kimi"
- ✅ Required fields present
- ✅ Type checking

### File Locking
Prevents race conditions when both agents work simultaneously:
- 🔒 Tasks are locked during updates
- 🔒 Messages are locked during sending
- 🔒 Automatic lock timeout (5 minutes)
- 🔒 Stale lock detection

### Input Sanitization
- String length limits
- Type coercion
- Invalid character filtering

---

## 📖 Example Workflow

### 1. Initialize Session

```bash
interagent init --project "E-commerce API" --principal claude
```

### 2. Claude (as Principal) Plans Architecture

**You:** "@Claude - You're Principal Engineer. Check `.interagent/` and plan the API architecture."

**Claude:** Reviews project, delegates with quick command:

```bash
# Single command creates task and message
interagent quick --to kimi "Design database schema"

# Check what to tell Kimi
interagent relay --to kimi
```

Output:
```
RELAY PROMPT FOR KIMI
--------------------
@kimi - You have work in the InterAgent collaboration system.
Your role: delegate

📋 You have 1 new task(s):
   - Design database schema (task-xxx)

Please:
1. Check .interagent/tasks/active/ for details
2. Run: interagent task update task-xxx --status in_progress
3. Do the work
4. Run: interagent task update task-xxx --status completed
5. Send a message when done
```

**Copy-paste the relay prompt to Kimi.**

### 3. Kimi (as Delegate) Implements

**Kimi:** Receives the prompt, runs the commands:

```bash
interagent task update task-xxx --status in_progress
# Implements schema

interagent task update task-xxx --status completed
interagent msg send --to claude --subject "Schema ready" --message "Done!"
```

### 4. You Check Summary

```bash
interagent summary
```

Output:
```
INTERAGENT SUMMARY
==================

[TASKS]
  ✅ 1 task(s) approved
  👀 1 task(s) ready for review

[MESSAGES]
  📬 Claude: 1 unread message(s)
     - From kimi: Schema ready

[ACTION ITEMS]
  → Tell claude to review 1 completed task(s)

[QUICK COMMANDS]
  interagent relay --to claude
```

### 5. Claude Reviews

**You:** Copy-paste the relay prompt to Claude:

```bash
interagent relay --to claude
```

**Claude:** Reviews and approves:

```bash
interagent inbox --agent claude
interagent task show task-xxx
# Reviews work

interagent task update task-xxx --status approved
interagent msg send --to kimi --message "Approved! Great work."
```

---

## 🧩 Capabilities

InterAgent automatically routes tasks based on agent capabilities:

| Capability | Best Agent |
|------------|------------|
| Architecture Design | Claude |
| System Design | Claude |
| Implementation | Kimi |
| Code Refactoring | Kimi |
| Performance Optimization | Kimi |
| Testing | Kimi |
| Code Review | Claude |
| Documentation | Claude |
| Security Analysis | Claude |
| Tool Use | Kimi |

---

## 🐍 Python API

InterAgent can also be used as a Python library:

```python
from interagent import Session, Task, Message

# Initialize session
session = Session.create("My Project", principal="claude")
session.save()

# Create task
task = Task.create(
    title="Implement API",
    assignee="kimi",
    priority="high",
)
task.save()

# Send message
msg = Message.create(
    sender="claude",
    recipient="kimi",
    content="Task assigned!",
)
msg.save()
```

See `examples/` for more complete examples.

---

## 📁 Project Structure

```
.interagent/
├── session.json              # Session configuration
├── README.md                 # Session documentation
├── agents/
│   ├── claude.json          # Claude's status & inbox
│   └── kimi.json            # Kimi's status & inbox
├── tasks/
│   ├── active/              # Active tasks (*.json)
│   └── completed/           # Completed tasks (*.json)
├── messages/
│   ├── pending/             # Unread messages (*.json)
│   └── archive/             # Read messages (*.json)
└── shared/
    ├── context.md           # Project context
    ├── architecture.md      # Architecture decisions
    └── decisions.md         # Decision log
```

---

## 🎓 Best Practices

### DO ✅
- **Check inbox first** before starting work
- **Update task status** as you progress (in_progress → completed)
- **Include context** when delegating tasks
- **Use descriptive subjects** for messages
- **Document decisions** in `shared/decisions.md`
- **Commit `.interagent/` to Git** for history

### DON'T ❌
- Work without checking inbox first
- Leave tasks in "in_progress" when blocked
- Send vague messages without context
- Forget to mark messages as read
- Work on tasks you haven't accepted

---

## 🤝 Integration with Claude and Kimi

### For Claude Code

Claude can use the CLI directly:

```bash
interagent inbox --agent claude
interagent task list
interagent task update task-xxx --status in_progress
```

### For Kimi Code

Kimi can use the CLI or create a skill for slash commands:

```yaml
# .kimi/skills/interagent/skill.yaml
name: interagent
description: InterAgent collaboration
commands:
  - name: inbox
    description: Check inbox
  - name: task_create
    description: Create task
```

Then use:
```
/interagent inbox
/interagent task_create --title "Task" --assignee claude
```

---

## 📊 Comparison

| Feature | InterAgent | Manual Coordination |
|---------|------------|---------------------|
| Task tracking | ✅ Structured | ❌ Ad-hoc |
| Message history | ✅ Persistent | ❌ Lost |
| Role clarity | ✅ Defined | ❌ Ambiguous |
| Code reviews | ✅ Structured | ❌ Informal |
| Git integration | ✅ Tracked | ❌ Manual notes |
| Audit trail | ✅ Complete | ❌ Fragmented |

---

## 📦 Installation Options

### From PyPI (Recommended)

```bash
pip install interagent
```

### From Source

```bash
git clone https://github.com/yourusername/interagent.git
cd interagent
pip install -e .
```

### Development Install

```bash
git clone https://github.com/yourusername/interagent.git
cd interagent
pip install -e ".[dev]"
```

---

## 🔔 Watchdog (Optional)

Monitor for new messages and tasks automatically:

```bash
# Start watching for changes
python -m interagent.watchdog

# Or with custom poll interval
python -m interagent.watchdog --interval 10
```

This prints notifications when:
- 📬 New messages arrive
- 📋 New tasks are assigned
- ✅ Tasks are completed

Useful for running in a separate terminal while you work.

---

## 🔮 Roadmap

- [x] Quick mode (single-command delegation)
- [x] Relay prompt generation
- [x] Summary command
- [x] Schema validation
- [x] File locking
- [x] Watchdog script
- [ ] Web dashboard for visualizing collaboration
- [ ] Desktop notifications for new messages
- [ ] Integration with GitHub/GitLab PRs
- [ ] Slack/Discord notifications
- [ ] More agent profiles (GPT-4, Copilot, etc.)

---

## 🤔 FAQ

**Q: Do Claude and Kimi talk directly?**  
A: No, they communicate through shared files in `.interagent/`. The user prompts each agent to check the files.

**Q: Can I use this with other AI assistants?**  
A: Yes! Just add their profiles to the agent configuration.

**Q: Is the `.interagent/` directory required?**  
A: Yes, it's where all collaboration state is stored.

**Q: Should I commit `.interagent/` to Git?**  
A: Yes, it provides a complete audit trail of your collaboration.

**Q: Can agents work in parallel?**  
A: Yes! Each can work on their assigned tasks independently.

**Q: What if agents disagree?**  
A: The Principal Engineer makes the final decision.

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file.

---

## 🙏 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 💬 Support

- **Issues:** [GitHub Issues](https://github.com/yourusername/interagent/issues)
- **Discussions:** [GitHub Discussions](https://github.com/yourusername/interagent/discussions)
- **Documentation:** [Full Documentation](https://github.com/yourusername/interagent#readme)

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=yourusername/interagent&type=Date)](https://star-history.com/#yourusername/interagent&Date)

---

**Happy collaborating! 🎉**
