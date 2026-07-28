## Context

AgentWeave orchestrates multi-agent AI coding sessions. Currently there is no quality governance layer: agents implement tasks and mark them complete without any mandated review gate, documentation of decisions, or protection against AI-specific failure modes (package hallucinations, echo-chamber testing, overly broad permissions, prompt injection vectors).

Research shows AI-generated code has 2.7x higher vulnerability density than human code, with 20% of package recommendations pointing to non-existent packages (slopsquatting). The industry response is multi-agent validation chains — one agent writes, another independently reviews — but AgentWeave has no first-class support for this workflow.

The system is model-agnostic (Claude, Kimi, Gemini, Minimax) and must remain so. The Hub already syncs `session.json` to all connected agents via an existing endpoint.

## Goals / Non-Goals

**Goals:**
- Configurable quality gates via `agentweave.yml` — projects opt into the level of governance they need
- Decision documentation (ADR-lite) produced alongside code, stored in a configurable path
- Structural echo-chamber prevention baked into spec task assignments, not just runtime checks
- AI-specific review checklist (slopsquatting, permissions, injection vectors, secrets) in role templates and the new `aw-verify` skill
- All quality config syncs to Hub automatically via the existing `session.json` path
- Model-agnostic attribution (agent name + session ID, not model-specific commit footers)

**Non-Goals:**
- Automated static analysis tooling or CI/CD integration (out of scope — this governs agent behavior)
- Enforcing quality settings on non-AgentWeave workflows
- New Hub API endpoints — the existing session sync path handles config propagation
- Mutation testing tooling — the reviewer role gets the concept as a manual checklist item

## Decisions

### Decision 1: `quality:` as a top-level section in `agentweave.yml`
**Chosen over**: separate `quality.yml`, environment variables, or per-agent config.
**Rationale**: `agentweave.yml` is already the single source of truth for project config. A top-level section keeps all project settings co-located, version-controlled, and synced to the Hub via the existing `session.json` path. Per-agent config would make cross-agent consistency impossible.

### Decision 2: Existing `session.json` sync path — no new endpoint
**Chosen over**: dedicated `/api/v1/quality` endpoint.
**Rationale**: `session.py` already serializes the full `AgentWeaveConfig` into `session.json`, which is synced to the Hub on every `Session.save()`. Adding `QualityConfig` to `AgentWeaveConfig` means zero Hub backend changes. The Hub UI reads `data.quality` from the existing `GET /api/v1/session/sync` response.

### Decision 3: Enhance existing `code_reviewer` role — no new `ai_code_reviewer` role
**Chosen over**: new dedicated role.
**Rationale**: A new role adds friction (users must explicitly assign it) and fragments the reviewer concept. The existing `code_reviewer` already owns this domain. Adding AI-specific directives as a new section keeps the role count clean and ensures existing sessions that already assign `code_reviewer` automatically get the enhanced behavior after `aw-sync`.

### Decision 4: Structural echo-chamber prevention in `aw-spec-propose`
**Chosen over**: runtime-only guard in `aw-review` / `aw-done`.
**Rationale**: If `tasks.md` assigns implementation to `backend_dev/agent-a` and review to `code_reviewer/agent-b`, the separation is enforced at spec time before a line of code is written. Runtime guards (`echo_chamber_guard: enforce`) remain as a safety net for tasks created outside `aw-spec-propose`, but structural assignment is stronger and earlier.

### Decision 5: `docs_path` outside `.agentweave` for committable decision docs
**Chosen over**: always inside `.agentweave` (gitignored).
**Rationale**: Decision docs are most valuable when committed alongside the code they document. Omitting `docs_path` defaults to `.agentweave/code-docs/` (gitignored, ephemeral). Setting `docs_path: "code-docs"` places docs outside `.agentweave` in a committable directory. Users choose based on project needs.

### Decision 6: Decision doc header includes `requirement` field (prompt audit trail)
**Chosen over**: doc body only.
**Rationale**: Knowing what the agent was asked to do is essential for reviewing whether the code matches the intent. If a reviewer finds a mismatch, the requirement field shows whether the bug is a misunderstanding of the spec or a pure implementation failure.

## Risks / Trade-offs

- **Mechanical doc fill-in**: AI will complete the decision doc template formulaically. Mitigation: the `docs_threshold: non_trivial` setting limits docs to genuinely complex changes; the reviewer's zero-trust sequence reads code *before* the doc to form an independent view.
- **Verbosity tax**: Strict `docs_threshold: all` setting will produce noise on trivial tasks. Mitigation: default to `non_trivial`; document the threshold options clearly.
- **Single-agent sessions**: `echo_chamber_guard: enforce` deadlocks if only one agent is active. Mitigation: enforce degrades to `warn` + notice when no alternative reviewer exists.
- **Template drift**: Role templates updated here will drift from future AgentWeave versions if not maintained. Mitigation: changes are additive sections, not rewrites — reducing merge conflict surface.

## Migration Plan

1. `agentweave activate` with an existing `agentweave.yml` that has no `quality:` section continues to work — `QualityConfig` fields all have defaults (review_required=false, docs_threshold=never, echo_chamber_guard=off)
2. Existing sessions are unaffected until `agentweave.yml` is updated with a `quality:` section
3. Run `aw-sync` after deploying updated role templates so all agent context files pick up the new directives
4. Hub UI quality health section renders as empty/hidden when `quality` is absent from session data

## Open Questions

- Should `docs_path` support per-change overrides, or is one project-level setting sufficient?
- Should stale review detection threshold (tasks under_review for > N minutes) be configurable or hardcoded?
