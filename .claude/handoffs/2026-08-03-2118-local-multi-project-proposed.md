# Handoff: Local multi-project workspace proposed

**Date:** 2026-08-03T21:18:46+01:00 · **Branch:** hub-native-experience · **HEAD:** 37a6854
**Agent:** Codex gpt-5.6-sol (T3 Code)
**Previous handoff:** `.claude/handoffs/2026-08-03-1913-runner-agent-charter-complete.md`
**Status:** chunk complete — proposal awaiting explicit user approval

## Goal

Continue the Hub-native programme after runner/agent/charter separation. The selected successor is
a local multi-project workspace: one local AgentWeave instance owns multiple directory-backed
projects safely, which also supplies the working-directory prerequisite for the specification
authority/traceability programme.

## Current state

- Resumed from the completed runner/agent/charter handoff at HEAD `37a6854`; branch and protected
  untracked files matched that handoff.
- Inspected the remaining umbrella phases and selected the specification programme by priority.
- Completed a technical exploration of specification authority. It found a hard prerequisite:
  current `Project` rows have no working directory and the removed watchdog was the only live spec
  sync producer, so file-authoritative specifications cannot be safe yet.
- Completed a second technical exploration for local multi-project support, covering directory
  identity, operator auth, explicit project APIs, CLI lifecycle, runtime/worktree path isolation,
  SSE, cache keys, navigation/tabs, migration, Docker, security, and testing.
- Authored the active OpenSpec change
  `openspec/changes/2026-08-03-local-multi-project-workspace/` with proposal, design, traced tasks,
  a new `local-project-workspace` capability delta, and modifications to `app-lifecycle` and
  `agent-conversation-workspace`.
- Resolved all five product choices in the proposal: retain the invisible local bearer credential;
  refuse new input while a directory is unavailable but retain queued work; place Questions on
  Overview, Logs in Activity, and Quality/configuration in Environment; retain Docker only through
  an explicit mounted workspace root; defer archive/unregister and permanent deletion.
- The change is valid and ready for review. No runtime implementation has started and every item in
  its `tasks.md` remains pending. Explicit user approval is required before phase 0.

## Files touched

- `openspec/explorations/2026-08-03-specification-authority-technical.md` — new, finished technical
  exploration; defines file/DB authority, stable IDs, evidence, drift, rigor, authoring, and the
  dependency on directory-backed projects.
- `openspec/explorations/2026-08-03-local-multi-project-technical.md` — new, finished technical
  exploration; source audit and full technical direction for the selected successor.
- `openspec/changes/2026-08-03-local-multi-project-workspace/proposal.md` — new, finished proposal;
  includes why/what, resolved choices, explicit non-goals, capabilities, and impact.
- `openspec/changes/2026-08-03-local-multi-project-workspace/design.md` — new, finished design;
  eleven decisions, migration, risks, and no remaining design questions.
- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — new, finished pending
  implementation plan; phases 0–6 are test-first and all checkboxes remain unchecked.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md`
  — new, finished capability delta with directory, API, runtime, SSE/cache, navigation, migration,
  and Docker requirements.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/app-lifecycle/spec.md` — new,
  finished delta modifying bare invocation and instance status/stop/reset behavior.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/agent-conversation-workspace/spec.md`
  — new, finished delta modifying project-collection and URL-backed navigation behavior.
- `src/agentweave/templates/skills/handoff.md` — pre-existing unrelated untracked user-owned file;
  not read or modified during this chunk.
- `src/agentweave/templates/skills/resume.md` — pre-existing unrelated untracked user-owned file;
  not read or modified during this chunk.
- `tests/test_handoff_resume_templates.py` — pre-existing unrelated untracked user-owned file; not
  read or modified during this chunk.
- `.claude/handoffs/2026-08-03-2118-local-multi-project-proposed.md` — this session handoff.
- `.claude/handoffs/LATEST.md` — updated pointer to this handoff.

## Key decisions

- **Local multi-project precedes the specification programme.** The specification programme needs a
  trustworthy project filesystem root. Rejected folding `working_directory` into the spec change
  because that would duplicate the owner of the already-defined multi-project slice.
- **Project is stable ID + canonical directory.** The ID survives rename/relocation; a non-secret
  `.agentweave/project.json` marker enables explicit moved-directory recovery. Rejected path-derived
  IDs because relocation would rewrite identity.
- **One instance-local operator credential, explicit project resource paths.** The current bootstrap
  secret becomes an operator credential with no project selection; run tokens remain project-bound.
  Rejected switching project-specific browser keys and rejected nullable `ApiKey.project_id` as an
  implicit administrator privilege.
- **One project workspace resolver.** All run, context, worktree, workspace-search, diagnostic, and
  later spec paths resolve from the project row. Rejected every project-aware `Path.cwd()` fallback
  and arbitrary absolute `work_dir`.
- **Unavailable directory preserves DB state but starts nothing.** New input is refused, existing
  queue/jobs remain, and autonomous work is reconsidered after repair. Rejected silently disabling
  jobs or deleting/withdrawing work.
- **One operator SSE stream with server-stamped `project_id`.** This keeps inactive project state
  live. Rejected one stream per project and caller-supplied identity.
- **All frontend server-state keys include project ID.** Rejected clearing global keys on switch
  because in-flight requests can repopulate the wrong project.
- **URL-backed navigation uses existing destination types.** Rejected adding a router dependency;
  search parameters plus History API are sufficient.
- **Rail lists only projects/agents; project views are content tabs.** Overview owns Questions,
  Activity owns Logs, and Environment owns Quality/Instructions/Runners/Charters/worktrees/
  diagnostics/settings.
- **Docker support is explicit and bounded.** It works only under a configured mounted container
  workspace root. Rejected Docker socket access and host/container path guessing.
- **No archive or delete in this successor.** Reset remains instance-wide and never deletes source
  directories.

## Constraints and user directives (verbatim)

- “This repo has no AgentWeave session, and must not acquire one.”
- “Do the work directly.”
- “Write to `openspec/changes/<date>-<name>/`.”
- “Nothing under `.agentweave/`, `agentweave.yml`, or `spec/` should exist at the repository root at
  all.”
- “Also: stage paths explicitly. `git add -A` sweeps in untracked `.claude/handoffs/` scratch.”
- User command: “continue”.
- User command ending this chunk: “$handoff”.
- Inherited constraint from the previous handoff: preserve
  `src/agentweave/templates/skills/handoff.md`,
  `src/agentweave/templates/skills/resume.md`, and
  `tests/test_handoff_resume_templates.py` unless their owner asks otherwise.
- The repository instructs contributors to use `openspec-*` skills, but none was available in this
  session. The work used repository-native OpenSpec conventions manually; do not invoke shipped
  `aw-*` product skills against this repository.
- Do not implement the active proposal until the user explicitly approves it.

## Dead ends

- The resumed roadmap initially suggested the specification programme as the next priority. Source
  inspection showed it cannot safely own files because projects have no working-directory binding
  and spec-sync production calls disappeared with the watchdog. The result was an ordering
  correction, not implementation of a workaround.
- PowerShell commands using Unix-style wildcard paths such as `hub/hub/api/v1/*.py` caused `rg` IO
  errors on Windows. Use directory arguments plus `-g '*.py'` instead.
- `git diff --stat HEAD` shows nothing for the new proposal/exploration files because they are
  untracked. `git status --short` and explicit file enumeration are the authoritative touched-file
  list until they are staged.
- Do not preserve project-specific API keys and merely swap the browser key on selection; the
  proposal explicitly rejects that architecture.

## Verification

Ran and passed:

- `openspec validate 2026-08-03-local-multi-project-workspace --strict --no-interactive` — change
  valid.
- `openspec validate --all --strict --no-interactive` — 21 passed, 0 failed.
- `git diff --check` — passed with no output.
- `git status --short` — only the two exploration artifacts, the active change, and the three
  protected pre-existing untracked files were present before writing this handoff.

Not tested:

- No CLI, Hub, frontend, Ruff, Black, mypy, production build, browser, migration, Docker, or live
  testbed verification was run because this chunk created design/spec artifacts only.
- No implementation scenario in the proposed `tasks.md` has been exercised.
- No user approval has been given.

## Git state

- Branch: `hub-native-experience`.
- HEAD: `37a6854` (`handoff: runner agent charter separation complete`).
- Worktree: dirty only through untracked files; no tracked application/runtime file was modified.
- New untracked work: `openspec/changes/2026-08-03-local-multi-project-workspace/`, both 2026-08-03
  exploration files, and this handoff file.
- Modified tracked file: `.claude/handoffs/LATEST.md`, now pointing at this handoff.
- Protected pre-existing untracked files: the two shipped handoff/resume template files and their
  test named above.
- Upstream: `git rev-parse --abbrev-ref --symbolic-full-name '@{u}'` returned no upstream; unpushed
  commit comparison is unavailable.

## Next steps

1. Ask the user to review and explicitly approve or request revisions to
   `openspec/changes/2026-08-03-local-multi-project-workspace/proposal.md`; do not edit runtime code
   before that answer.
2. If approved, re-read `proposal.md`, `design.md`, all three delta specs, and `tasks.md`, then begin
   task 0.1 by adding failing migration/model tests for project directory fields, unique `path_key`,
   directory states/timestamps, and the separate operator credential.
3. Complete phase 0 test-first, verify its identity/directory scenarios, update only genuinely
   completed checkboxes, and write the required phase handoff.
4. Preserve the two exploration documents as design sources for the later specification programme;
   do not propose that child until this directory-backed successor lands.

## Open questions for the user

- Do you explicitly approve `openspec/changes/2026-08-03-local-multi-project-workspace/` for
  implementation, or do you want revisions first?

## Read on resume

- `openspec/changes/2026-08-03-local-multi-project-workspace/proposal.md` — approval boundary and
  resolved scope.
- `openspec/changes/2026-08-03-local-multi-project-workspace/design.md` — implementation decisions
  and rejected alternatives.
- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — exact phase/task order and
  verification protocol.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md`
  — primary scenarios phase 0 must implement.
- `openspec/explorations/2026-08-03-local-multi-project-technical.md` — source audit and detailed
  technical evidence when design rationale needs expansion.
- `AGENTS.md` — repository guardrails, especially no root AgentWeave state and explicit staging.
