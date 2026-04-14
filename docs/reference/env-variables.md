# Environment Variables Reference

## Hub Variables

Set these in the Hub's `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `AW_BOOTSTRAP_API_KEY` | *(required)* | API key for Hub authentication. Format: `aw_live_{random32}` |
| `AW_BOOTSTRAP_PROJECT_ID` | `proj-default` | Default project ID |
| `AW_BOOTSTRAP_PROJECT_NAME` | `Default Project` | Display name for the default project |
| `AW_PORT` | `8000` | Port the Hub listens on |
| `AW_CORS_ORIGINS` | *(empty)* | Comma-separated allowed origins for CORS. Leave empty in production if UI is served from same origin |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/agentweave.db` | Database URL. SQLite default; PostgreSQL supported |

## CLI Variables

Set these in your shell for CLI behavior:

| Variable | Description |
|----------|-------------|
| `AW_LOG_LEVEL` | Developer tracing log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Default: `WARNING` |
| `AW_LOG_FILE` | Optional file path for developer tracing logs |

## Proxy Agent Variables

Set these in your shell before running proxy agents, or place them in a `.env` file at the project root:

| Variable | Provider |
|----------|----------|
| `MINIMAX_API_KEY` | MiniMax |
| `ZHIPU_API_KEY` | Zhipu GLM |
| `YOUR_CUSTOM_VAR` | Any custom `claude_proxy` provider |

AgentWeave automatically loads a `.env` file from the current working directory. Shell-exported variables always take precedence over `.env` values.

## Security Notes

- Never commit `AW_BOOTSTRAP_API_KEY` to version control
- API keys for proxy agents are resolved at runtime from environment variables or a `.env` file in the project root
- Only the environment variable *name* is stored in AgentWeave config files
