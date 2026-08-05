# Cross-agent detection and portability

Read this when the repo is worked by more than one agent CLI. Skip it entirely when it is not —
adding portability machinery to a single-agent repo is exactly the generic scaffolding this
skill exists to prevent.

## Detection

The presence of any of these settles the "is this multi-agent" question without asking:

| Path | Agent |
|---|---|
| `AGENTS.md` | Cross-tool convention (Codex and others) |
| `.cursor/rules/`, `.cursorrules` | Cursor |
| `.github/copilot-instructions.md` | GitHub Copilot |
| `opencode.json`, `.opencode/` | OpenCode |
| `.agents/` | Kimi, OpenCode (shared convention) |
| `.kimi-code/` | Kimi |
| `.codex/` | Codex |
| `.windsurf/rules/`, `.windsurfrules` | Windsurf |
| `.clinerules` | Cline |
| `.aider.conf.yml`, `.aider*` | Aider |

Claude Code's own `/init` already reads `.cursor/rules/`, `.cursorrules`, and
`.github/copilot-instructions.md` when generating instructions; with `CLAUDE_CODE_NEW_INIT=1` it
also reads `AGENTS.md`, `.devin/rules/`, `.windsurf/rules/`, and `.clinerules`. For a migration
into Claude Code, delegate to it rather than hand-translating.

## The split that prevents drift

| Goes in the shared file (`AGENTS.md`) | Goes in `.claude/` |
|---|---|
| What the project is, and its layout surprises | Hook configuration |
| Build, test, lint commands | Permission rules |
| Conventions and their rationale | Subagent definitions |
| Pitfalls and non-obvious constraints | Path-scoped rules |
| Verification steps | Skill frontmatter beyond the portable six |

The test for any line: *would this still be true and useful if a different agent read it?* If
yes it is project knowledge and belongs in the shared file. If it names a lifecycle event, a
permission pattern, or a tool-specific directory, it is harness mechanics.

## Wiring Claude Code to a shared file

Claude Code **does not read `AGENTS.md`.** It reads `CLAUDE.md`. Import rather than duplicate:

```markdown
@AGENTS.md

## Claude Code

<Claude-specific additions only>
```

A symlink also works, but on **Windows it requires Administrator rights or Developer Mode** — so
the import is the portable recommendation. (For linking skill *directories* on Windows, a
junction works without elevation: `cmd /c mklink /J link target`.)

Imports resolving outside the working directory trigger a one-time approval dialog, and
declining disables them permanently. `@AGENTS.md` is inside the repo, so it does not.

## Skill reach

Four CLIs converged on the `SKILL.md` format but not on where they look for it:

| Agent | User-level | Project-level |
|---|---|---|
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex | `~/.codex/skills/` | **none — user-level only** |
| Kimi | `~/.kimi-code/skills/`, `~/.agents/skills/` | `.kimi-code/skills/`, `.agents/skills/` |
| OpenCode | `~/.config/opencode/skill{,s}/` | `.opencode/skills/`, `.claude/skills/`, `.agents/skills/` |

Two facts that change recommendations:

- **`.agents/skills/` is the closest thing to a neutral project-level convention** — honoured by
  Kimi and OpenCode, ignored by Claude Code and Codex.
- **Codex has no project-level discovery.** A skill the repo depends on will silently not exist
  for a Codex session unless it is installed at `~/.codex/skills/`. Flag this whenever a repo's
  documented workflow depends on a project-level skill and Codex is in use.

Minimum covering set: `~/.claude/skills/` + `~/.codex/skills/` + `<project>/.agents/skills/`.
`AICollective/skills/install.sh` fans a directory out to every agent detected on the machine.

## Portable skill authoring

- Restrict frontmatter to `name`, `description`, `license`, `compatibility`, `metadata`,
  `allowed-tools` if the skill must also load in claude.ai, the Skills API, or a stricter CLI.
  Other keys produce a hard validation error there, not a warning.
- Claude Code-only body features — `` !`cmd` `` injection, `${CLAUDE_SKILL_DIR}` — do nothing
  elsewhere. Never put a skill's core loop on them.
- Do not reference another agent's slash commands. Describe the action; let the running agent
  pick the mechanism.
- Skill directories copy whole, so bundled references and scripts travel. That is the portable
  way to ship depth.

## The three checks

1. **Divergence.** Do two instruction files exist with overlapping, separately-maintained
   content? That is two sources of truth and one is already wrong. Collapse to one plus imports.
2. **Misplacement.** Is harness-specific mechanics sitting in the shared file, where other
   agents read it as noise and may act on it? Move it into `.claude/`.
3. **Reach.** Are the skills the documented workflow depends on discoverable by the agents
   actually used on this repo? Check Codex first — it fails silently and per-machine.
