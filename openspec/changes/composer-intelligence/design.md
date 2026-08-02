## Context

The composer today (`hub/ui/src/components/agents/Composer.tsx`) is a controlled `<textarea>`
with autosize, Enter-to-submit, and per-`(project, agent, conversation)` draft persistence
(`hub/ui/src/lib/composerDrafts.ts`). It has no concept of a trigger character, no menu, and no
way to change which agent a message goes to — `agent` is a prop fixed by the parent conversation
view for the component's whole lifetime.

The umbrella `2026-07-30-hub-native-experience` change scoped this slice by direct reference to
T3's `packages/shared/src/composerTrigger.ts` (149 lines): "Adopt the behaviour and the boundary
rules; write our own implementation" (`openspec/changes/2026-07-30-hub-native-experience/design.md`,
section B). That file is not in this repository and is not to be copied in; its described
behavior is the spec this design follows.

Two things this repo does **not** have yet, discovered while grounding this design against the
code (not assumed from the umbrella doc):

- **No per-project working directory.** `openspec/changes/2026-07-30-hub-native-experience/tasks.md`
  task 10.2 ("Give each project a working directory and record it") is unchecked and out of scope
  here. Every existing filesystem-touching code path (`hub/hub/api/v1/agent_trigger.py:204`,
  `hub/hub/worktrees.py`) uses `Path.cwd()` — the directory the Hub process itself was started
  in — as the one working directory there is. The new path-listing endpoint follows the same
  convention rather than inventing a per-project one now.
- **No Hub-side skill-listing API.** Skill discovery today is a CLI-side template-copy step
  (`src/agentweave/templates/skills/*.md` → `.claude/skills/aw-*.md` in a project that ran
  `agentweave init`) — there is nothing the Hub currently serves that lists "available skills."
  `$skill` therefore cannot reuse an existing mechanism; it reuses the *new* path-listing endpoint
  instead (see Decision 2), since a project's skills are just files under `.claude/skills/` once
  `agentweave init` has run.

## Goals / Non-Goals

**Goals:**
- Trigger detection (`@path`, `/command`, `$skill`) with the boundary rules T3 specified: slash
  commands only at line start, `@`/`$` detected by walking back to the nearest whitespace
  boundary.
- Range replacement that repositions the cursor correctly, including quote-escaping for paths
  containing whitespace.
- A keyboard-navigable menu (move/accept/dismiss) wired to all three sources.
- An in-place, searchable agent/runner selector on the composer, using the existing
  `GET /api/v1/agents/launchability` probe for indicators.
- One new backend endpoint: list workspace paths (files and directories) under the Hub process's
  cwd, respecting `.gitignore`.

**Non-Goals:**
- Per-project working directories (task 10.2, a different slice). This endpoint lists under
  `Path.cwd()`, matching every other filesystem-touching code path today.
- A general Hub-side skill *registry* or skill CRUD. `$skill` only needs to list files that
  already exist on disk; it does not need to understand skill frontmatter, validate skills, or
  support skills that don't correspond to a file.
- Migrating a conversation's history or provider-session binding when the operator picks a
  different agent from the selector. `agent-conversation-workspace`'s immutable-scope requirement
  (`openspec/specs/agent-conversation-workspace/spec.md`) already forbids changing a
  conversation's `agent` after creation — the selector starts a *new* conversation with the newly
  chosen agent rather than reassigning the old one in place.
- Rich inline token rendering inside the composer body (T3's `ComposerPromptEditor`) — explicitly
  deferred by the umbrella design doc ("plain textarea + chips first"). This slice inserts plain
  text (quote-escaped where needed), not inline chips.

## Decisions

### 1. Path listing via `git ls-files`, not a hand-rolled `.gitignore` parser

`hub/hub/worktrees.py` already shells out to `git` for worktree management
(`_run_git`), so a git dependency at runtime is an established pattern, not a new one. The new
endpoint runs `git ls-files --cached --others --exclude-standard` against `Path.cwd()` (the same
root `agent_trigger.py` and `worktrees.py` already use) to get tracked-plus-untracked-but-not-
ignored paths in one call, correctly honoring `.gitignore`, nested `.gitignore` files, and global
excludes — all of which a from-scratch parser would have to reimplement and would likely get
wrong on nested-ignore edge cases. Falls back to an empty result (not an error) if `Path.cwd()` is
not a git repository, so a non-git project doesn't break the composer — it just gets no `@path`
matches.

**Alternative considered**: `os.walk` with a `.gitignore`-pattern matcher (e.g. a vendored
`pathspec`-equivalent). Rejected — adds a dependency-or-reimplementation burden `git ls-files`
already solves correctly, and this Hub already assumes git is on PATH for worktree isolation.

### 2. `$skill` reuses the path endpoint, scoped by prefix, rather than a second endpoint

Skills are files under `.claude/skills/**/*.md` in a project that has run `agentweave init` (a
CLI-side concern this Hub-repo change does not touch). Rather than build a second endpoint that
understands skill semantics, the frontend calls the same path-listing endpoint and filters
client-side to paths under `.claude/skills/`, stripping the directory prefix and `.md` suffix for
display. If no such directory exists (a project that hasn't run `agentweave init`, or is mid-
migration away from the `aw-*` skill workflow — see CLAUDE.md's roles-removal note for the general
direction), the `$skill` source simply returns no matches; this is not an error state the UI needs
to explain.

**Alternative considered**: a dedicated `/skills` endpoint that parses skill frontmatter (name,
description) for richer menu entries. Rejected for this slice — no such parsing exists anywhere in
the Hub today (`src/agentweave/spec_manifest.py` is CLI-side and unrelated), and the umbrella
scope for this phase is *wiring three sources*, not building skill metadata infrastructure. Revisit
if/when the roles-removal work (CLAUDE.md) settles what a "skill" means going forward.

### 3. `/command` source is a static frontend list, no backend call

The umbrella's own scope note says this source is "the commands the composer itself supports" —
there is no external registry of composer commands to query. A hardcoded array in the frontend
(e.g. `[{name: 'model', ...}]` mirroring T3's special-cased `/model` → `slash-model` kind) is
correct and sufficient; adding a backend round-trip for a fixed, code-defined list would be a
barrier (the organizing constraint from CLAUDE.md/proposal context) with no offsetting benefit.

### 4. Agent selector redirects by starting a new conversation, never mutates the current one

`agent-conversation-workspace`'s conversation identity is immutable in scope (`project_id`,
`agent` fixed at creation — enforced by `get_open_conversation`'s agent/project match check,
`hub/hub/conversations.py:27`, and tested directly in
`hub/tests/test_conversation_contract.py::test_conversation_scope_is_immutable_across_binding_and_followups`).
The selector must not fight that invariant. Selecting agent B while conversation A (bound to agent
A) is open: the next message is submitted as a *new* `POST /api/v1/agent/trigger` call with no
`conversation_id`, targeting agent B — exactly the same code path an operator switching
conversations in the sidebar already takes. The composer's `agent` prop changes (parent-driven,
same remount-on-identity-change contract the component already documents in its own docstring);
conversation A's history is untouched and still reachable.

**Alternative considered**: add a Hub-side "reassign conversation" operation that changes
`Conversation.agent` in place. Rejected outright — directly contradicts the already-shipped,
already-tested immutability contract; would require reopening `agent-conversation-workspace`'s
spec, which is out of scope for this slice.

## Risks / Trade-offs

- **[Risk] `git ls-files` on a large repo returns a large list on every keystroke of an `@` query.**
  → Mitigation: the endpoint returns the full path list once (cacheable, invalidated by nothing
  more exotic than a manual refresh for this slice — a repo's file list changing while someone is
  actively typing an `@` mention is an acceptable, rare staleness window); the *filtering* by query
  string happens client-side against that list, not as a new backend call per keystroke.
- **[Risk] A project's cwd is not a git repository** (e.g. a fresh, not-yet-initialized directory).
  → Mitigation: covered by Decision 1's fallback — empty result, not a 500.
- **[Trade-off] No skill metadata (description, args) in the `$skill` menu**, just the filename.
  → Accepted per Decision 2; revisit once the roles/skill-identity direction (CLAUDE.md) settles.
