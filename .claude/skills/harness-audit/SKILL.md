---
name: harness-audit
description: Audit and improve how this repository configures its coding agent — instruction files, scoped rules, skills, subagents, hooks, permissions, and cross-agent portability. Measures what actually loads, finds rules stated as absolutes that sit in a layer which cannot enforce them, finds context paid for on every request that is only needed sometimes, and proposes repo-specific fixes ranked by impact. Works on a repo with no configuration at all and on one with a lot. Use when the user says "audit my claude setup", "set up this repo for agents", "why is my context so full", "am I using claude code well", "fix my CLAUDE.md", "should this be a hook", "make this repo work with other agents", or after adopting a new agent CLI.
---

Make a repository's agent configuration *earn its context*, and move its inviolable rules into
layers that can actually enforce them.

**Core principle: no evidence, no proposal.** Every recommendation must cite something in *this*
repository — a line number in an instruction file, a measured token cost, a rule that exists,
a command in the build. Generic scaffolding is the failure mode of this entire exercise: stock
hooks, stock rules, and stock subagents copied into a repo that did not ask for them cost
context on every request forever and dilute the artifacts that matter. A short audit that
proposes three justified changes beats a long one that proposes twenty plausible ones.

**Second principle: never silently widen what the agent may do.** This skill edits the control
plane — permissions, hooks, instruction files — while running under it. Anything that loosens
safety, blocks tool calls, or rewrites a file a human maintains is proposed and confirmed, never
applied on your own initiative. See *Tiering* below; it is not optional.

Agent-agnostic: works in any CLI agent that can read files and run shell commands. It audits
whichever harness it finds, and it does not assume it is running inside the one it is auditing.

## Step 0 — Establish the target and say it out loud

Before reading anything, state: the repo root, whether it is a git repo, the agent CLI and
version you are running under (if determinable — e.g. `claude --version`), and the platform.
Platform matters: hook scripts, symlinks, and shell selection all differ on Windows.

Then ask, once, unless the answer is already obvious from the files:

> Is this repo worked on exclusively with Claude Code, or do other agents (Codex, Cursor,
> Copilot, OpenCode, Kimi, Windsurf, Cline, Aider) touch it too?

Do not ask if detection already answers it — the presence of `.cursor/rules/`, `AGENTS.md`,
`.github/copilot-instructions.md`, `opencode.json`, `.agents/`, `.codex/`, `.windsurf/`,
`.clinerules`, or `.aider.conf.yml` settles it. If the repo is multi-agent, load
`references/cross-agent.md` and include the portability checks in Step 4.

## Step 1 — Inventory what exists

Read, do not guess. Record which of these are present, absent, or empty:

```
CLAUDE.md · .claude/CLAUDE.md · CLAUDE.local.md · AGENTS.md
.claude/rules/**       .claude/skills/**       .claude/commands/**
.claude/agents/**      .claude/settings.json   .claude/settings.local.json
~/.claude/settings.json (user layer — read it; it changes what the project layer needs)
MCP config · .gitignore coverage for local/scratch artifacts
```

Note line counts for every instruction file and rule. Note which skills exist and whether
anything in the repo references them.

If **nothing** exists, this is the greenfield case. Do not scaffold from a template — go to
Step 2 and derive from the codebase, exactly as you would for an existing setup. Mention that
`CLAUDE_CODE_NEW_INIT=1 /init` exists and does interactive first-time scaffolding with a
codebase exploration phase; offer it as an alternative starting point rather than duplicating
it badly.

## Step 2 — Measure the always-on cost

This is the number that makes the rest of the audit concrete.

- Total lines across everything loaded on **every** request: root instruction file(s) plus every
  rule **without** `paths:` frontmatter. Compare against the 200-line target per instruction
  file. State the actual number.
- If the running harness supports it, `/context` is ground truth for what actually loaded, and
  `/usage` attributes recent consumption to individual skills, subagents, plugins, and MCP
  servers. Prefer measured numbers over counted lines when available.
- Identify MCP servers configured but unused in this repo's workflow.
- Identify skills whose descriptions load every session but which nothing has ever invoked.

## Step 3 — Derive proposals (the actual work)

Apply the heuristics in `references/heuristics.md`. Each one turns an observation into a
specific proposal with a specific target layer. In summary, you are looking for:

1. **Absolutes in a layer that cannot enforce them.** Any NEVER / ALWAYS / ALL / "must" rule
   with a mechanical trigger is a hook or permission-rule candidate. Name the event and matcher,
   or the exact deny rule.
2. **Derivable content.** Directory trees, dependency lists, architecture overviews — the agent
   can read these from the codebase, and they go stale silently. If the harness ships `/doctor`,
   it already proposes exactly this trim; say so and delegate rather than reimplementing it.
3. **Sometimes-content charged always.** Sections that only matter inside one directory →
   path-scoped rules. **State the trade-off**: path-scoped rules are lost after compaction until
   a matching file is read again, so an invariant that must survive hour six stays unscoped.
4. **Procedures in a facts file.** Multi-step workflows → skills.
5. **Context floods.** Verbose recurring operations (test suites, log analysis, dependency
   audits) → subagents, or a `PreToolUse` hook that filters output before it is ever seen.
6. **Missing enforcement of the build.** Format/lint/typecheck that exists but is not wired to
   `PostToolUse`.
7. **Permission friction or permission over-reach.** Repeated prompts → a scoped allowlist.
   A blanket bypass → the narrower allowlist that would replace it.
8. **Portability defects**, if multi-agent — divergence, misplacement, reach. See
   `references/cross-agent.md`.

For each proposal record: **the evidence** (file and line, or measured number), **the change**,
**the layer it moves to**, and **what it buys** (tokens per request, an invariant made
enforceable, a feedback loop shortened). A proposal missing any of the four is not ready.

## Step 4 — Report, ranked

Present findings ordered by impact, not by category. For each: evidence → change → benefit →
tier. Keep the whole report scannable; a table plus a short paragraph per item beats prose.

Say explicitly what you are **not** proposing and why, when a plausible-looking gap is
deliberate — a repo with no hooks because it has no invariants worth enforcing is correctly
configured, and should be told so rather than given hooks.

## Step 5 — Apply, by tier

**Tier 1 — apply directly.** Purely additive, reversible, and creating something that did not
exist: a new path-scoped rule file, a new subagent definition, a new skill, a first
`.claude/settings.json`, a `.gitignore` entry, an `@AGENTS.md` import line. Report each file
written.

**Tier 2 — confirm first, one at a time.** Anything that modifies or removes existing content,
or that changes what the agent may do:

- rewriting or trimming an instruction file a human maintains
- any hook that can **block** (`PreToolUse`, `Stop`, `UserPromptSubmit`, `PermissionRequest`)
- any change to `permissions`, especially `deny`, or to a permission mode
- moving content that is currently compaction-durable into a path-scoped rule
- anything under `~/.claude/` — the user layer affects every repo on the machine, not just
  this one

Show the exact diff. Get a yes. Apply that one. Then move to the next.

**Never.** Do not delete an instruction file. Do not disable an existing hook you did not write
without being asked. Do not commit. Do not push.

## Step 6 — Verify what you wrote

Configuration that silently does not load is the normal failure, not the exception.

- Hooks: `/hooks` should list it; `claude --debug` shows it firing. On Windows, confirm the
  interpreter — upstream examples are all bash + `jq` and will silently never fire under the
  wrong shell. Set the hook's `shell` explicitly.
- Rules and instruction files: `/context` lists what loaded under **Memory files**. A
  path-scoped rule only appears after a matching file is read.
- Skills: they appear in the `/` menu; `disable-model-invocation: true` ones are invisible to
  the model by design, which is not a bug.
- Permission rules: a rule for `Write(...)`, `Glob(...)`, or `NotebookEdit(...)` paths is
  accepted, never consulted, and warns at startup. Use `Edit(...)` and `Read(...)`.

Report anything you could not verify as unverified. Do not claim a hook works because you wrote
it.

## Reference files

Loaded on demand — read the one you need, not all three.

| File | Use |
|---|---|
| `references/heuristics.md` | The derivation rules in full, with the phrasing patterns that trigger each |
| `references/claude-code.md` | Exact syntax for what you write: hook config, permission patterns, frontmatter, and the sharp edges |
| `references/cross-agent.md` | Detection paths, `AGENTS.md` mechanism, what ports and what does not |

Background and sources: `AICollective/ResearchClub/agent-harness-configuration/`.

## Scope

This skill configures the harness. It does not write application code, does not review code
quality (`/review-iteration` does that), and does not author specifications. If the audit
surfaces a code problem, note it in one line and move on.
