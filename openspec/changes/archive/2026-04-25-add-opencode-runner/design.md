## Context

AgentWeave dispatches tasks to agents via a runner system defined in `constants.py`. Each runner type has a `RUNNER_CONFIGS` entry describing how to build CLI commands, register MCP servers, and parse session IDs. Today there are five runner types: `claude`, `native`, `claude_proxy`, `kimi`, `manual`.

OpenCode is a terminal-based AI coding agent with a non-interactive `opencode run` subcommand, session resumption via `--session`, and native MCP client support via `opencode.json`. It differs from existing runners in two ways: it uses a subcommand (`run`) rather than flags directly on the binary, and MCP registration is file-based rather than via a CLI command.

## Goals / Non-Goals

**Goals:**
- Add `opencode` as a valid runner type in `RUNNER_TYPES` and `RUNNER_CONFIGS`
- Watchdog can dispatch tasks to OpenCode agents via `opencode run`
- `agentweave mcp-setup` registers AgentWeave's MCP server in `opencode.json`
- Role guides and context files are injected at invocation via `--file`
- Session continuity is maintained across watchdog pings
- Any `provider/model` string works (local Ollama, cloud providers, etc.)

**Non-Goals:**
- Parsing OpenCode's streamed JSON output beyond exit-code monitoring
- Supporting OpenCode as an MCP *server* (closed upstream, not planned)
- Auto-installing OpenCode or Ollama (user responsibility)
- Modifying `agentweave.yml` schema structure (`AgentConfig` already covers all needed fields)

## Decisions

### D1: Stable session ID strategy (vs. parsing streamed output)

**Decision**: Use `agentweave-{agent}` as the session ID (e.g. `agentweave-opencode-dev`). Pass `--session agentweave-{agent}` on every invocation.

**Rationale**: OpenCode creates the session on first use and resumes it on subsequent uses with the same ID. This eliminates the need to parse session IDs from JSON output streams, which would require reverse-engineering OpenCode's event schema and add fragility across OpenCode version updates. The trade-off is that session history accumulates indefinitely per agent — acceptable since OpenCode manages its own storage.

**Alternative considered**: After each run, call `opencode session list -n 1 --format json` to extract the most recent session ID. Rejected: extra subprocess call, racey if two agents run concurrently against the same Ollama instance.

### D2: File-based MCP registration (vs. mcp_add_cmd subprocess)

**Decision**: When `mcp_add_cmd` is `None` in a runner config, `cmd_mcp_setup()` falls through to a file-based writer that reads/merges `opencode.json` in the project root.

**Rationale**: OpenCode has no `opencode mcp add` CLI command — MCP servers are configured via `opencode.json`. The `mcp_add_cmd: None` sentinel is the cleanest extension point: existing code paths for claude/kimi are unchanged, and the new branch is contained in `cmd_mcp_setup()`. The written file is project-local (`./opencode.json`) so it can be committed alongside `agentweave.yml`.

**Alternative considered**: Add a new `mcp_setup_type: "file"` key to RUNNER_CONFIGS. Rejected: over-engineered for a single runner; `None` on `mcp_add_cmd` is sufficient signal.

### D3: Context injection via `--file` (vs. prompt prepending)

**Decision**: Inject role guides and agent context as `--file .agentweave/roles/<role>.md --file .agentweave/context/<agent>.md` flags.

**Rationale**: OpenCode's `--file` flag attaches files as named context in the session, equivalent to Kimi's `--agent-file` and Claude's `--append-system-prompt-file`. Prepending context into the prompt string works but loses the structural separation that file attachment provides, and grows the prompt size on every ping.

### D4: `opencode` added to KNOWN_AGENTS (vs. only RUNNER_TYPES)

**Decision**: Add `"opencode"` to `KNOWN_AGENTS` in constants.py alongside the runner config.

**Rationale**: `KNOWN_AGENTS` drives autocomplete hints and documentation. Any agent name matching `AGENT_NAME_RE` is accepted, so this is advisory — but including `opencode` makes the intended usage self-documenting for users running `agentweave agent list`.

### D5: `subcommand` field in RUNNER_CONFIGS

**Decision**: Add a `"subcommand": "run"` key to the opencode runner config. The `_agent_ping_cmd()` function reads this and inserts it between the CLI binary and the flags.

**Rationale**: All current runners invoke their binary directly with flags (`claude --output-format ...`, `kimi --wire ...`). OpenCode requires `opencode run [flags] prompt`. Rather than hardcoding a special case in `_agent_ping_cmd()`, the `subcommand` key generalizes the pattern for any future runner that uses subcommands.

## Risks / Trade-offs

**[Risk] OpenCode session ID behavior is undocumented** → Mitigation: Test with `opencode run --session agentweave-test "hello"` twice before shipping. If session creation/resumption with custom IDs is unsupported, fall back to D1 alternative (post-run session list query).

**[Risk] Tool calling reliability at 7B model scale** → Mitigation: Document in the runner's warning output that small local models may have inconsistent tool-call behavior. AgentWeave cannot compensate for model capability limits. Recommend Qwen2.5-Coder:7b as the minimum viable local model.

**[Risk] `opencode.json` conflicts with user's existing config** → Mitigation: `cmd_mcp_setup()` reads the existing file, merges only the `mcp.agentweave` key, and writes back. It never overwrites unrelated keys. If the file is malformed JSON, print an error and show the manual config snippet instead of crashing.

**[Risk] `opencode run` output format changes across OpenCode versions** → Mitigation: AgentWeave only monitors exit code (0 = success, non-zero = failure). It does not parse OpenCode's streamed events. This makes the integration version-agnostic.

## Migration Plan

No migration needed. This is purely additive:
- Existing sessions with `runner: claude` or `runner: kimi` are unaffected
- `opencode` runner is opt-in via `agentweave.yml`
- `opencode.json` is only written when `agentweave mcp-setup` is run and an opencode agent is present in the session

## Open Questions

1. Does `opencode run --session <custom-id>` create the session if it doesn't exist, or does it require a prior `opencode session create`? (Needs hands-on testing.)
2. Should `agentweave switch opencode-dev` print a launch command the way it does for kimi/claude? (Probably yes — follow the same pattern.)
