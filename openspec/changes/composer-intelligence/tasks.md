# Implementation plan

## Working protocol — read before starting any phase

1. Re-read `proposal.md`, `design.md`, and `specs/agent-composer/spec.md` before starting a phase
   — the reasoning behind each decision lives in `design.md` and is not repeated below.
2. Tests first within each phase — every phase opens with the test task for the behavior it adds.
3. Each phase ends with a verification task naming the requirement whose scenarios must pass.
4. Run `/handoff` at every threshold — after each numbered phase, and after any substantial chunk
   within a long one.
5. Never mark a task complete on the strength of a plan existing — only verified implementation
   closes a task.

## 0. Backend: workspace path listing endpoint

- [x] 0.1 Write backend tests for the new endpoint: excludes gitignored paths (including a nested
      `.gitignore`), returns an empty list (not an error) when `Path.cwd()` is not a git
      repository, and requires the same auth every other `/api/v1/*` route requires.
      `hub/tests/test_workspace_paths.py` — 7 tests: module-level (tracked, untracked-not-
      ignored, gitignored, nested-gitignore, non-git-empty) + HTTP-level (lists paths for the
      Hub's cwd, empty on non-git cwd). Auth is the identical `Depends(get_project)` every other
      `/api/v1/*` route uses (`hub/hub/api/v1/workspace.py`), not re-tested per-endpoint — no
      sibling endpoint file (e.g. `test_worktrees.py`) does either.
- [x] 0.2 Implement the endpoint in `hub/hub/api/v1/` via `git ls-files --cached --others
      --exclude-standard` against `Path.cwd()` (design.md Decision 1), following the existing
      `_run_git`-style subprocess pattern in `hub/hub/worktrees.py`.
      `hub/hub/workspace_paths.py` (`list_workspace_paths`) + `hub/hub/api/v1/workspace.py`
      (`GET /api/v1/workspace/paths`), registered in `hub/hub/api/v1/__init__.py`.
- [x] 0.3 Verify against `agent-composer`'s "Workspace path listing endpoint" requirement. Both
      scenarios pass: gitignored paths excluded (incl. nested `.gitignore`), non-git cwd returns
      `[]` not an error. Full `hub` suite: 405 passed, 4 skipped.

## 1. Trigger detection

- [ ] 1.1 Write tests for `detectComposerTrigger(text, cursor)`: slash-command only matches at
      line start (not mid-sentence), `@path`/`$skill` match at any position via backward
      whitespace-walk, and detection returns `null` once the cursor has moved past a completed
      token.
- [ ] 1.2 Implement `detectComposerTrigger` as a new, self-contained module (own implementation,
      not a port — design.md Context) returning `{kind, query, rangeStart, rangeEnd} | null` for
      `path` | `slash-command` | `skill`.
- [ ] 1.3 Verify against `agent-composer`'s "Composer trigger detection" requirement.

## 2. Range replacement

- [ ] 2.1 Write tests for `replaceTextRange`: the returned cursor position lands immediately after
      the inserted value (not at the end of the full text), and a value containing whitespace is
      quote-escaped in the inserted text.
- [ ] 2.2 Implement `replaceTextRange(text, start, end, replacement)` and the quote-escape helper
      for values containing whitespace.
- [ ] 2.3 Verify against `agent-composer`'s "Trigger range replacement" requirement.

## 3. Trigger menu

- [ ] 3.1 Write tests for the menu: arrow-key navigation changes the active result without
      inserting anything, Enter/Tab accepts the active result, Escape dismisses while leaving text
      and focus untouched.
- [ ] 3.2 Build the trigger menu component and wire it into
      `hub/ui/src/components/agents/Composer.tsx`, opened/closed by `detectComposerTrigger`'s
      result.
- [ ] 3.3 Verify against `agent-composer`'s "Keyboard-navigable trigger menu" requirement.

## 4. Result sources

- [ ] 4.1 Write tests for source wiring: `@` results come from the path-listing endpoint
      unfiltered; `$` results come from the same endpoint filtered to `.claude/skills/` paths with
      the prefix and `.md` suffix stripped for display, and are empty (not an error) when no such
      directory exists; `/` results come from a static list requiring no network call.
- [ ] 4.2 Add a frontend API hook for the new path-listing endpoint (React Query, matching the
      pattern in `hub/ui/src/api/`).
- [ ] 4.3 Implement the three source adapters (path, skill, command) feeding the menu built in
      phase 3.
- [ ] 4.4 Verify against `agent-composer`'s "Trigger result sources" requirement.

## 5. In-place agent selector

- [ ] 5.1 Write tests for the selector: lists every configured agent with a launchability
      indicator from `GET /api/v1/agents/launchability`, search filters the list, and — critically
      — selecting a different agent then submitting does not alter the current conversation's
      `agent` field (asserted against the conversation-immutability contract in
      `hub/tests/test_conversation_contract.py`, not just a UI-level check).
- [ ] 5.2 Build the agent selector component consuming the existing launchability endpoint (no new
      backend route — design.md Goals).
- [ ] 5.3 Wire the selector into the composer chrome: selecting a different agent than the current
      conversation's own changes what the *next* submission targets (new conversation, no
      `conversation_id`), per design.md Decision 4 — never mutates the open conversation.
- [ ] 5.4 Verify against `agent-composer`'s "In-place agent selector" requirement.

## 6. Integration

- [ ] 6.1 Wire trigger detection, range replacement, the menu, all three sources, and the agent
      selector together into `Composer.tsx` end-to-end.
- [ ] 6.2 Manually verify in a running instance under `testbed/` (never at the repo root — see
      CLAUDE.md): typing `@`, `/`, `$` each open the right source; accepting a result inserts and
      repositions the cursor correctly; the agent selector shows real launchability state.
- [ ] 6.3 Full `hub/ui` and `hub` test suites green.
- [ ] 6.4 `/handoff`
