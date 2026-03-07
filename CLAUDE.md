# InterAgent Framework

## Project Overview
File-based collaboration protocol enabling Claude Code and Kimi Code to work together through a shared `.interagent/` directory. Zero external dependencies — pure Python stdlib.

## Tech Stack
- Python 3.8+
- No external dependencies
- Package manager: pip (editable install: `pip install -e .`)
- Entry points: `interagent`, `iaf` → `interagent.cli:main`
- Watchdog entry point: `interagent-watch` → `interagent.watchdog:main`

## Essential Commands
```bash
pip install -e .                             # install in dev mode
interagent --help                            # verify install
interagent init --project "Name" --principal claude
interagent summary
interagent relay --agent kimi
interagent quick --to kimi "task"
interagent update-template --agent claude --template-path ~/Documents/projects/template.txt
```

## Architecture
```
src/interagent/
  cli.py          All CLI commands (argparse). Add new commands here + in create_parser() + main()
  session.py      Session lifecycle (create, load, save, add_task, complete_task)
  task.py         Task CRUD; Task.load() validates task_id with ^[a-zA-Z0-9_-]+$
  messaging.py    MessageBus (send, get_inbox, mark_read) + Message class
  locking.py      File-based mutex; use `with lock("name"):` context manager
  validator.py    validate_task/message/session + sanitize_task_data — run before every save
  watchdog.py     Polls .interagent/ for new files; entry point interagent-watch
  constants.py    All valid values and directory Path constants — source of truth
  utils.py        load_json, save_json, generate_id, now_iso, print_* helpers
  templates/      Markdown prompt templates; load via get_template("name") from templates/__init__.py

.interagent/      Runtime state — gitignored except README.md
```

## Critical Rules
- VALID_AGENTS = `["claude", "kimi"]` — adding a new agent requires updating `constants.py` AND `validator.py`
- VALID_MODES = `["hierarchical", "peer", "review"]`
- NEVER commit `.interagent/tasks/`, `messages/`, `agents/`, `session.json` (already gitignored)
- ALL saves must pass through `validator.py` sanitize functions first
- ALL task file operations that modify state must use `locking.py` context manager
- Templates use `get_template("name")` from `templates/__init__.py` — never hardcode template strings in cli.py
- `is_locked()` is read-only — it must never delete files (only `acquire_lock()` cleans stale locks)
- `kimichanges.md` and `kimiwork.md` are gitignored working files — never commit them

## When Compacting
Keep in context: current task IDs being worked on, session mode, which agent is principal, any pending messages in `.interagent/messages/pending/`, which CLI command is being added/modified.
