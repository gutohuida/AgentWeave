## Why

AI-generated code produces 2.7x higher vulnerability density than human code, with 20% of package recommendations hallucinated and 29–45% of generated code containing security vulnerabilities. AgentWeave orchestrates multi-agent AI coding sessions but currently has no quality governance — no review gates, no decision documentation, no protection against AI-specific failure modes like slopsquatting, context poisoning, or echo-chamber testing.

## What Changes

- New `quality:` section in `agentweave.yml` with six configurable settings governing review gates, documentation thresholds, echo-chamber enforcement, attribution tagging, and dependency checking
- New `code_decision.md` template — an ADR-lite document that implementing agents produce alongside code, capturing the requirement used, decisions made, alternatives considered, and AI-generated file attribution
- Updated role templates: `code_reviewer`, `security_engineer`, `project_manager`, `backend_dev`, `frontend_dev`, `fullstack_dev`, `qa_engineer` — each gains AI-specific directives aligned to the quality config
- New `aw-verify` skill — the structured execution skill for the code reviewer agent (zero-trust sequence, dependency check, AI security checklist, doc cross-check, task status update)
- Updated `aw-spec-propose`, `aw-spec-apply`, `aw-spec-archive`, `aw-spec-explore` — quality-config-aware, with structural echo-chamber prevention baked into generated task assignments
- Updated `aw-done`, `aw-review`, `aw-delegate`, `aw-collab-start`, `aw-status`, `aw-sync`, `aw-revise`, `aw-relay` — quality-config-driven routing replacing manual review prompts
- Hub UI surface for quality health (review gate status, stalled reviews, missing docs)

## Capabilities

### New Capabilities

- `quality-config`: `quality:` section in `agentweave.yml` with `QualityConfig` dataclass, validation constants, and automatic serialization into `session.json` for Hub sync
- `code-decision-doc`: Decision document template, path resolution (inside vs. outside `.agentweave`), and lifecycle (produced at completion, archived with change, cross-checked at review)
- `ai-aware-review`: Zero-trust review sequence and AI-specific security checklist as the new `aw-verify` skill and enhanced `code_reviewer` role
- `quality-aware-skills`: Quality-config-driven behavior across all `aw-spec-*` and `aw-*` workflow skills

### Modified Capabilities

- `role-templates`: Existing roles gain AI-specific directives; no spec-level behavioral contract changes, only enhanced guidance

## Impact

- `src/agentweave/config.py` — new `QualityConfig` dataclass, added to `AgentWeaveConfig`
- `src/agentweave/constants.py` — `VALID_DOC_THRESHOLDS`, `VALID_ECHO_GUARD`
- `src/agentweave/session.py` — serialize `quality` into `session.json`
- `src/agentweave/templates/code_decision.md` — new file
- `src/agentweave/templates/roles/` — 7 updated role templates + no new roles
- `src/agentweave/templates/skills/` — 4 updated `aw-spec-*` skills, 8 updated `aw-*` skills, 1 new `aw-verify` skill
- Hub UI (`hub/ui/src/`) — new quality health components reading from existing session sync endpoint
- No new Hub API endpoints required — quality config flows via the existing `session.json` sync path
