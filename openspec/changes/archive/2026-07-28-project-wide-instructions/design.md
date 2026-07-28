## Context

AgentWeave agents load their behavioral context once at session start via `aw-collab-start`. For HTTP transport, this calls the `get_context` MCP tool → `GET /api/v1/agents/context?role=<role>` → `_load_role_content(role)` which returns the role guide markdown. For local transport, `aw-collab-start` reads `.agentweave/roles/<role>.md` directly as a file.

Once the role guide lands in the agent's context window it is immutable for that session — there is no live-refresh mechanism. This is the same behavior as CLAUDE.md.

## Goals / Non-Goals

**Goals:**
- Project-wide instructions are prepended to every agent's role guide at session start
- Instructions are editable via Hub UI without CLI or file access
- Local transport works without Hub (file-based)
- Editing instructions mid-session is safe — running agents are unaffected

**Non-Goals:**
- Live injection into running agent sessions
- Per-agent or per-role instruction overrides
- CLI command to manage instructions (`agentweave instructions`)
- Syncing Hub DB instructions back to the local file

## Decisions

**D1: Instructions prepended, not appended**

Instructions appear before the role guide so they frame the agent's context first — highest-priority rules read before role-specific behavior. Alternative (append) was rejected: role persona would be established before constraints are seen.

**D2: Hub is source of truth for HTTP transport; file is source of truth for local**

No bidirectional sync. When HTTP transport is active, `_load_role_content` fetches from `ProjectInstructions` DB. When local, `aw-collab-start` reads the file. If both exist and HTTP is active, Hub wins — the file is ignored.

Alternative considered: always sync file → Hub on init. Rejected because it creates a chicken-and-egg problem (instructions can't be edited before init) and adds sync complexity.

**D3: Separate DB table, not added to `ProjectSession`**

`ProjectSession` mirrors `session.json` from the CLI — adding instructions there would couple a Hub-editable field to a CLI-managed file. A standalone `ProjectInstructions` table keeps the ownership clear: only Hub writes it, CLI never touches it.

**D4: Silent prepend — no agent notification**

Instructions are invisible infrastructure, like a system prompt. Agents behave as if the instructions were always part of their role guide. No "you have project instructions active" callout — that would add noise and could confuse agents.

**D5: Hub UI disclaimer instead of forced refresh**

Since sessions are immutable once started, the UI shows: *"Changes take effect when agents start a new session."* No session invalidation or forced restart mechanism — that would be complex and disruptive.

## Hub API Design

```
GET  /api/v1/project/instructions
     → { "content": "..." }   (empty string if none set)

PUT  /api/v1/project/instructions
     body: { "content": "..." }
     → { "content": "..." }
```

Both endpoints use existing `get_project` dependency for auth/project scoping.

## Hub DB Schema

```python
class ProjectInstructions(Base):
    __tablename__ = "project_instructions"

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), primary_key=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )
```

Upserted on PUT. No row = empty instructions (same as empty content).

## `_load_role_content` Change

```python
# Pseudocode — before returning content:
instructions = await fetch_project_instructions(project_id)  # from DB
role_content = <existing logic>
if instructions:
    return instructions + "\n\n---\n\n" + role_content
return role_content
```

The separator `---` (horizontal rule) makes the boundary visible in markdown if an agent ever inspects the raw content.

## `aw-collab-start` Change (local transport)

Add as new step 1 (existing steps shift down):

> 1. If `.agentweave/project_instructions.md` exists and is non-empty, read it first — these are project-wide rules that apply to all agents.

## Risks / Trade-offs

**Instructions grow unbounded** → No size limit enforced. Mitigation: UI can show character count; no hard limit needed initially.

**Stale file after Hub edits** → Local file diverges from Hub when instructions are edited in UI. Mitigation: documented behavior (Hub wins for HTTP transport); file is a local-only fallback.

**No history / audit trail** → `updated_at` timestamp only; no version history. Acceptable for v1. A future changelog could be added to the DB table.

**Session-start-only delivery** → A long-running agent session won't pick up new instructions. Mitigation: clear UI disclaimer. Acceptable — same limitation as CLAUDE.md.
