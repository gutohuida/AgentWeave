## Progress

35/35 tasks complete ✓

## 1. Config & Constants

- [x] 1.1 Add `QualityConfig` dataclass to `src/agentweave/config.py` with fields: `review_required`, `docs_path`, `docs_threshold`, `echo_chamber_guard`, `attribution_tag`, `dependency_check`
- [x] 1.2 Add `VALID_DOC_THRESHOLDS = ["all", "non_trivial", "never"]` and `VALID_ECHO_GUARD = ["off", "warn", "enforce"]` to `src/agentweave/constants.py`
- [x] 1.3 Add `quality: Optional[QualityConfig]` field to `AgentWeaveConfig` dataclass in `config.py`
- [x] 1.4 Add validation for `docs_threshold` and `echo_chamber_guard` in `_validate_config()` — raise `ConfigValidationError` on invalid values
- [x] 1.5 Serialize `quality` into `session.json` in `src/agentweave/session.py` so it syncs to Hub via existing path
- [x] 1.6 Add tests for `QualityConfig` parsing, defaults, and validation errors in `tests/test_config.py`

## 2. Decision Document Template

- [x] 2.1 Create `src/agentweave/templates/code_decision.md` with header fields (`task_id`, `requirement`, `agent`, `model`, `session`, `date`, `files_modified`, `ai_generated`) and body sections (`## What Was Done`, `## Why This Approach`, `## Alternatives Considered`, `## Risks / Known Limitations`)
- [x] 2.2 Verify `get_template("code_decision")` returns the template without error

## 3. Role Template Updates

- [x] 3.1 Update `src/agentweave/templates/roles/code_reviewer.md` — add zero-trust review sequence (code first → dependency check → AI security checklist → test echo-chamber check → read decision doc → cross-check → prompt audit trail) and escalation rules for doc/code mismatch and missing docs
- [x] 3.2 Update `src/agentweave/templates/roles/security_engineer.md` — add "AI-Generated Code" section with slopsquatting check, overly broad permissions scan, prompt injection vectors checklist, and hardcoded secrets scan
- [x] 3.3 Update `src/agentweave/templates/roles/project_manager.md` — add review routing logic (route to `code_reviewer` if role exists, respect `echo_chamber_guard`), doc/code mismatch escalation, hallucinated package escalation
- [x] 3.4 Update `src/agentweave/templates/roles/backend_dev.md` — add TDD directive, decision doc threshold judgment, attribution listing
- [x] 3.5 Update `src/agentweave/templates/roles/frontend_dev.md` — same as 3.4
- [x] 3.6 Update `src/agentweave/templates/roles/fullstack_dev.md` — same as 3.4
- [x] 3.7 Update `src/agentweave/templates/roles/qa_engineer.md` — add echo-chamber rule (independently derive test cases; never treat implementing agent's tests as proof of correctness)

## 4. New aw-verify Skill

- [x] 4.1 Create `src/agentweave/templates/skills/aw-verify.md` with structured review execution steps: read quality config → locate decision doc → read code first → dependency check → AI security checklist → check tests independently → read decision doc → cross-check → update task status → notify principal
- [x] 4.2 Ensure the skill handles both `approved` and `revision_needed` outcomes with itemized notes

## 5. aw-spec-* Skill Updates

- [x] 5.1 Update `src/agentweave/templates/skills/aw-spec-propose.md` — read quality config at start; structure tasks.md with quality gates (test spec → impl → decision doc → review task assigned to `code_reviewer` agent); add `## Security Considerations` to design.md template; flag missing `code_reviewer` as quality gate blocker in team.md
- [x] 5.2 Update `src/agentweave/templates/skills/aw-spec-apply.md` — read quality config before implementing; produce decision doc before marking non-trivial tasks complete; include quality expectations in delegation messages
- [x] 5.3 Update `src/agentweave/templates/skills/aw-spec-archive.md` — check `agentweave task list --status under_review` and `--status revision_needed` before archiving; warn if pending; ensure decision docs move with the change to archive
- [x] 5.4 Update `src/agentweave/templates/skills/aw-spec-explore.md` — load and display quality config in team map; include `code_reviewer` in team recommendations when `review_required: true`; surface quality implications when converging to proposal

## 6. aw-* Skill Updates

- [x] 6.1 Update `src/agentweave/templates/skills/aw-done.md` — replace manual review prompt with config-driven routing; check decision doc exists before routing; use `echo_chamber_guard` when assigning reviewer
- [x] 6.2 Update `src/agentweave/templates/skills/aw-review.md` — add echo-chamber guard check before assigning reviewer; enrich review task description with decision doc location and quality checklist
- [x] 6.3 Update `src/agentweave/templates/skills/aw-collab-start.md` — read quality config; add role-specific quality orientation (implementer / reviewer / PM each see relevant rules and paths)
- [x] 6.4 Update `src/agentweave/templates/skills/aw-delegate.md` — add quality expectations footer to delegated task descriptions; add echo-chamber pre-check for review delegations
- [x] 6.5 Update `src/agentweave/templates/skills/aw-revise.md` — surface doc update directive when revision notes include doc/code mismatch flag
- [x] 6.6 Update `src/agentweave/templates/skills/aw-status.md` — add Quality Health section (under-review tasks + wait time, missing docs, flagged mismatches, stale review alert)
- [x] 6.7 Update `src/agentweave/templates/skills/aw-sync.md` — note that quality config is propagated to agent context files on sync
- [x] 6.8 Update `src/agentweave/templates/skills/aw-relay.md` — add role-aware relay content (reviewer gets decision doc location; implementing agent gets quality expectations)

## 7. Hub UI

- [x] 7.1 Add quality health data reading from `data.quality` in the existing `GET /api/v1/session/sync` response — no new endpoint needed
- [x] 7.2 Create `hub/ui/src/components/quality/QualityHealthPanel.tsx` — displays review gate status, under-review task count and wait times, missing decision docs, active quality settings
- [x] 7.3 Wire `QualityHealthPanel` into the main dashboard layout (sidebar or status bar); show only when `data.quality.review_required` is true or docs are configured

## 8. Documentation & Tests

- [x] 8.1 Add tests for `QualityConfig` session serialization — verify `quality` key appears in serialized `session.json`
- [x] 8.2 Add tests for `echo_chamber_guard` degradation in single-agent sessions
- [x] 8.3 Update `agentweave.yml` generation in `generate_agentweave_yml()` to include a commented-out `quality:` section as a template for new projects
