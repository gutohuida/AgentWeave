# Tasks — A project without a git repository still runs its agents

Small change, one decision point. Section 1 exists because the same refusal is restated in four
places, and fixing the resolver while leaving the other three tells the operator a project is blocked
after it stops being blocked.

## 1. Confirm the blast radius before changing the resolver

- [ ] 1.1 Confirm `worktrees.resolve_agent_workspace` is the **only** production caller of
      `ensure_worktree`, and that `agent_trigger.py` is its only production caller. If either is
      wrong, a second path can still refuse and section 2 is incomplete.
- [ ] 1.2 Confirm nothing outside `worktrees.py` raises or constructs `IsolationUnavailableError`,
      so the two remaining raise sites are the whole surface.
- [ ] 1.3 Confirm `checkpoints.files_changed_in` is unreachable with a `None` worktree and that
      `checkpoints.py:125` is the guard. A run with no snapshot must produce an empty changed-file
      list, not an exception.

## 2. The resolver (D1, D2)

- [ ] 2.1 `resolve_agent_workspace` returns `repo_root` for a writing agent when
      `is_git_repo(repo_root)` is false. Update the docstring: fail-closed now describes
      provisioning failure, not the absence of a repository.
- [ ] 2.2 Leave `ensure_worktree`'s `IsolationUnavailableError` raise site untouched.
      **`test_resolve_agent_workspace_does_not_fall_back_after_git_failure`
      (`test_worktrees.py:112`) must keep passing without edit.** If it needs editing, stop — the
      change has gone wrong.
- [ ] 2.3 Update the module docstring (`worktrees.py:1-21`), which states isolation as unconditional.

## 3. Everywhere the refusal is restated

- [ ] 3.1 `api/v1/worktrees.py:129-141` — report `isolated=False`, `provisioned=True`,
      `working_dir=repo_root`, and a reason describing the absent repository rather than a refusal
      to come (D5).
- [ ] 3.2 `api/v1/inbound_queue.py:176-192` — delete the git-repo branch and the import added for
      it. Keep the launchable-is-not-startable comment above it (D4).
- [ ] 3.3 `agents.py:1000-1015` — when the working directory is the project root and no repository
      exists, say so in the `### Your workspace` block. A read-only agent's wording must not change
      (D3).
- [ ] 3.4 `agent_trigger.py:346-350` and the HTTP-layer copy at `:658-662` — refuse `work_dir` for a
      writing agent only where the project is a repository (D6). Check both; they are duplicated
      deliberately and drift silently.
- [ ] 3.5 `AgentSettingsPage.tsx:296-300` — the reason is information, not an alert. Drop
      `role="alert"` and the amber treatment for this case; keep them if a genuine failure reason is
      ever reported through the same field.

## 4. Tests — agent-verifiable

- [ ] 4.1 `test_worktrees.py:105` — invert
      `test_resolve_agent_workspace_refuses_writer_when_not_a_git_repo` into
      `..._runs_writer_in_place_when_not_a_git_repo`: returns `repo_root`, creates nothing on disk.
- [ ] 4.2 Assert the negative in the same file: running in place creates no `.git`, no
      `.agentweave/worktrees`, and no branch.
- [ ] 4.3 `test_agent_trigger.py:444` — invert
      `test_writing_agent_is_not_spawned_when_isolation_cannot_be_prepared`: the turn now starts,
      with the project root as its working directory and no `waiting_reason`. Add a sibling that
      keeps the refusal for a **real repository** whose provisioning raises.
- [ ] 4.4 `test_inbound_queue.py:429` — `test_queue_status_names_a_missing_git_repository` becomes an
      assertion that no waiting reason mentions a repository for that project.
- [ ] 4.5 A turn context test: a writing agent in a non-repository project is told it has no isolated
      checkout; a read-only agent's block is unchanged.
- [ ] 4.6 A workspace-endpoint test covering both ways of sharing (D5) — configuration versus no
      repository — asserting they are distinguishable.
- [ ] 4.7 `work_dir` accepted for a writing agent in a non-repository project and still refused in a
      repository (D6).
- [ ] 4.8 A checkpoint over a run with no snapshot reports an empty changed-file list and does not
      raise (1.3).
- [ ] 4.9 UI: `agentWorkspaceSection.test.tsx:113` — the no-repository case is reported without
      `role="alert"`. The two tests asserting no isolation control (`:124`,
      `agentCreationUi.test.tsx:89`) must keep passing unchanged.
- [ ] 4.10 `pytest hub/tests/ -q` and `pytest tests/ -q` **run separately** — together they fail
      collection. `npx vitest run` and `npx tsc --noEmit` from `hub/ui`.
- [ ] 4.11 `ruff check hub/ src/`, `black` on every file touched.
- [ ] 4.12 Rebuild `hub/ui/dist`, copy over `hub/hub/static/ui`, confirm with `diff -rq`.
- [ ] 4.13 `npx openspec validate --changes --strict` and `--specs --strict`.

## 5. Verification — human-only (the operator runs these)

Nothing below can be closed by an agent. Each needs a person looking at a running app.

- [ ] 5.1 **The original symptom is gone.** Create a project on a directory that is not a repository,
      create an agent, send a message. The turn should start, not queue.
- [ ] 5.2 Does the agent behave sensibly with no repository — does it avoid proposing branches and
      commits, and does it read a failed `git status` correctly rather than as a broken environment?
      This is what D3's sentence is for and no test can answer it.
- [ ] 5.3 Is the workspace panel's no-repository note legible as information rather than as a
      problem? It was an amber alert; confirm it no longer reads as one.
- [ ] 5.4 Run two writing agents in the same non-repository project and see whether the shared
      directory is tolerable in practice, or whether D7's accepted risk needs revisiting.
- [ ] 5.5 Confirm an existing repository-backed project is unchanged — its agents still get worktrees
      on their own branches.

## 6. User test guide

**Setup.** A directory that is not a git repository, and one that is. `C:\Users\huida\Documents\quicktest`
was made a repository during this session's resume — use a fresh directory, or remove its `.git`.

1. **Open the non-repository directory as a project.** Create an agent in it. Nothing should warn you
   about git.
2. **Send it a message.** It should start working. Before this change it queued with
   *"… is not a git repository, so an isolated worktree cannot be prepared."*
3. **Ask it where it is working.** It should name the project directory and know it has no isolated
   checkout and no branch.
4. **Open the agent's settings.** The workspace section should say it shares the project directory
   because there is no repository — as a note, not an amber alert, and with no branch named.
5. **Ask it to commit its work.** It should tell you there is no repository rather than trying and
   failing.
6. **Now open the repository-backed project.** Its agent should still get its own worktree on
   `agentweave/<agent>`, exactly as before.
7. **Optionally, run two agents at once in the non-repository project.** They share one directory,
   so they can overwrite each other. The Hub tells each of them so and does not stop them — check
   whether that is the trade you want.

**What is deliberately absent:** the Hub never runs `git init` for you; there is still no UI control
for isolation; and a non-repository project's checkpoints carry no changed-file list, because there
are no commits to read one from.
