# Claude Code — exact syntax for what you write

Only what is needed to produce *correct* configuration, plus the sharp edges that make
plausible-looking config silently not work. Verified 2026-08-06 against v2.1.221. Background and
the fuller picture: `AICollective/ResearchClub/agent-harness-configuration/`.

## Hooks

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/format.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

`matcher` is a regex over tool names (`Bash`, `Write|Edit`, `mcp__server__.*`). An optional `if`
field scopes further using permission-rule syntax, e.g. `"if": "Bash(rm *)"`.

**Signalling from a `command` hook:**

| Exit | Meaning |
|---|---|
| 0 | Proceed. Plain stdout goes to the **debug log, not the transcript** |
| 2 | Block. stderr is shown to the agent as feedback |
| other | Non-blocking error; the call proceeds |

Or exit 0 with JSON: `{"decision":"block","reason":"..."}`; for `PreToolUse` specifically
`{"hookSpecificOutput":{"permissionDecision":"allow"|"deny"|"ask"|"defer"}}`, and
`updatedInput` to **rewrite** the call rather than judge it.

**Events, with what they are actually for:**

| Event | Blocks | Use |
|---|---|---|
| `SessionStart` | No | Inject dynamic context at startup |
| `UserPromptSubmit` | Yes | Rewrite or reject prompts |
| `PreToolUse` | Yes | Block, or rewrite via `updatedInput` |
| `PermissionRequest` | Yes | Route or auto-decide approvals |
| `PostToolUse` | No (exit 2 still feeds back) | Lint, format, test after writes |
| `Stop` | Yes | Completion gates |
| `PreCompact` / `PostCompact` | Yes / No | Preserve and re-inject around compaction |
| `SubagentStop`, `TaskCompleted`, `TeammateIdle` | Yes | Gates on delegated work |
| `InstructionsLoaded` | No | **Debug** which instruction files loaded and when |

Types beyond `command`: `http` (POST JSON; 2xx + `{"decision":"block"}` to block), `mcp_tool`,
`prompt` (model yes/no), `agent` (verifier subagent).

**Do not write a `PostCompact` hook to preserve a root instruction file.** Project-root
`CLAUDE.md` and unscoped rules are already re-injected from disk. Only path-scoped rules and
nested instruction files are lost.

### Windows

Every upstream example is bash + `jq`. On Windows:

- Set `"shell"` explicitly on the hook rather than relying on resolution. The `defaultShell`
  setting is `powershell` on Windows.
- If you write a bash script, confirm Git Bash is on PATH and that the script is invoked through
  it; otherwise the hook fails silently, which reads exactly like "the hook did nothing".
- Do not assume `jq` exists. Prefer a script in a language the repo already depends on.
- Verify with `/hooks` (it should be listed) and `claude --debug` (it should fire). A hook you
  cannot see fire is not installed.

## Permission rules

`Tool(pattern)`. Precedence **deny > ask > allow**; a broad deny cannot carry exceptions.

| Write | Means |
|---|---|
| `Bash(npm run *)` | Prefix match; the space enforces a word boundary |
| `Bash(ls*)` | Matches `ls -la` **and** `lsof` — usually not what you want |
| `Bash(ls:*)` | Same as `Bash(ls *)`; valid only at the end of a pattern |
| `Bash(git * main)` | Wildcards span arguments |
| `Read(./.env)`, `Edit(docs/**)` | File paths |
| `WebFetch(domain:example.com)` | Host-scoped fetches |
| `mcp__github__get_*` | Allow globs need a literal `mcp__<server>__` prefix |
| `mcp__*` / `*` | **deny/ask only** — skipped with a warning in `allow` |

Sharp edges:

- Bare `Bash` in `deny` **removes the tool from context entirely**. `Bash(rm *)` leaves it
  available and blocks matching calls. Choose deliberately.
- Shell operators are parsed: `Bash(safe *)` does not authorize `safe && evil`. Separators
  `&& || ; | |& &` and newlines each need to match.
- Stripped before matching: `timeout time nice nohup stdbuf command builtin noglob`, and bare
  `xargs`. **Not** stripped: `npx`, `docker exec`, `devbox run`, `mise exec` — so
  `Bash(devbox run *)` authorizes `devbox run rm -rf .`. Write runner+command pairs instead.
- `watch`, `setsid`, `flock`, `find -exec`, `find -delete` always prompt; prefix rules cannot
  cover them.
- **File rules are only consulted for `Edit(...)` and `Read(...)`.** A path rule on `Write`,
  `Glob`, or `NotebookEdit` is accepted, never consulted, and warns at startup (v2.1.210+). Use
  `Edit(docs/**)` where you mean Write.
- Argument-constraining patterns are fragile. To limit network egress, `deny` curl/wget in Bash
  and allow specific `WebFetch(domain:...)`.

## Rules files

```yaml
---
paths:
  - "src/api/**/*.ts"
  - "hub/**/*.{py,tsx}"
---
```

- No `paths` → loads every session at the same priority as `.claude/CLAUDE.md`.
- With `paths` → loads when a matching file is **read**; **lost after compaction** until read
  again.
- Brace groups multiply against a shared budget of 1,000 expanded patterns; over-budget patterns
  are used unexpanded and match nothing.
- A `[` that is not a valid bracket expression makes that pattern match nothing — escape as
  `\[`.
- Directory symlinks are resolved, which is the supported way to share one rule set across
  repos. On Windows use a junction (`cmd /c mklink /J`) — no elevation needed, unlike symlinks.

## Skill frontmatter

Fields you will actually reach for:

```yaml
---
name: <label>
description: <key use case first; description + when_to_use truncated at 1,536 chars>
disable-model-invocation: true   # user-only; zero context cost until invoked
user-invocable: false            # hides from / menu; does NOT block Skill-tool access
allowed-tools: Bash(git add *)   # pre-approved for the invoking turn only
model: sonnet
effort: high
context: fork                    # run in a subagent; body becomes the prompt
agent: Explore
paths: ["hub/**"]                # limit auto-activation
shell: powershell                # for !`cmd` blocks on Windows
---
```

- The command name comes from the **directory name** (plugin skills excepted).
- Bodies are rendered once and never re-read. Write standing instructions.
- On re-injection after compaction the body is **truncated from the end**. Most important
  instructions go at the top of the file.
- Only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are part
  of the portable standard; other fields error on stricter validators.

## Subagent frontmatter

```yaml
---
name: test-runner              # required; lowercase+hyphens, no ":"
description: <when to delegate>
tools: Read, Grep, Bash        # omit to inherit
model: haiku                   # sonnet|opus|haiku|fable|full ID|inherit (default)
permissionMode: plan
skills: [project-conventions]  # FULL content preloaded, not just descriptions
memory: project                # persistent cross-session memory
isolation: worktree
effort: low
color: cyan
---
```

Built-in **Explore** and **Plan** skip CLAUDE.md and git status. A project subagent named
`Explore` overrides the built-in — the supported way to force `model: haiku` for exploration.

## Settings

Precedence, highest first: managed → CLI flags → `.claude/settings.local.json` →
`.claude/settings.json` → `~/.claude/settings.json`.

Put in **project** settings (committed): `permissions`, `hooks`, `env`, `additionalDirectories`.
Put in **local** (gitignored): machine-specific paths, personal overrides, `skillOverrides`.

Add `"$schema": "https://json.schemastore.org/claude-code-settings.json"` to any file you
create.

Keys most likely to be relevant: `permissions`, `hooks`, `env`, `model`, `effortLevel`,
`autoCompactWindow`, `claudeMdExcludes`, `skillOverrides`, `defaultShell`,
`additionalDirectories`, `cleanupPeriodDays`.

## Verification commands

| Check | Command |
|---|---|
| What actually loaded | `/context` — see the **Memory files** list |
| What is consuming usage | `/usage` — attributed per skill, subagent, plugin, MCP server |
| Is my hook registered | `/hooks` |
| Is my hook firing | `claude --debug` |
| Which instruction files loaded, and why | an `InstructionsLoaded` hook |
| Setup problems, plus instruction-file trims | `/doctor` (trim proposals v2.1.206+) |
| Generate an allowlist from real usage | `/fewer-permission-prompts` |
