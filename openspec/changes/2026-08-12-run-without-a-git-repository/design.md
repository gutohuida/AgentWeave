# Design — A project without a git repository still runs its agents

## Context

Isolation is the default, expressed as `not config.get("read_only")`. Every agent an operator can
create through the Hub is therefore a writing agent, and every writing agent is refused in a
directory that is not a git repository. There is no UI control that would let the operator opt out,
so `git init` at a shell is the only available answer — for a blocker the Hub reports at the first
turn, not at project creation.

The single decision point is `worktrees.resolve_agent_workspace`. Everything else is a consequence.

## Decisions

### D1 — Absence of a repository is a degradation; failure to provision one is still an error

`resolve_agent_workspace` returns `repo_root` when `is_git_repo(repo_root)` is false, and continues
to raise `IsolationUnavailableError` from `ensure_worktree`.

The two cases look alike and are not. In the first, isolation was never on offer: no branch exists,
no primary checkout is at risk, and running in place is the only thing the Hub could do. In the
second, the project *has* isolation and something went wrong obtaining it — a path collision, a git
failure, a worktree registered to the wrong ref. Falling back there would put a writing agent on the
operator's primary checkout, mutating the working copy that CI and the operator's own editor read.
That is precisely the lost update `worktrees.py:3-9` exists to prevent, and it would happen silently.

`test_worktrees.py:112` (`test_resolve_agent_workspace_does_not_fall_back_after_git_failure`) already
pins the distinction. **It must keep passing unchanged.** If a change to this module makes that test
need editing, the change is wrong.

**Rejected:** falling back on every failure. It reads as more forgiving and is strictly more
dangerous — the one case where the fallback destroys something is the case it would newly cover.

**Rejected:** a per-agent `allow_shared_checkout` opt-in. It puts a decision in front of the operator
that has exactly one sensible answer, in a UI that deliberately exposes no isolation control at all.

### D2 — `is_git_repo` already fails safe, so no new detection is needed

`worktrees.is_git_repo` (`:73-91`) runs `git rev-parse --is-inside-work-tree` and returns `False` for
a missing path, an absent `git` binary, or any `OSError`/`SubprocessError`. Under D1 a `False` now
means "run in place" rather than "refuse", so a machine with no `git` on `PATH` becomes a machine
where every agent runs in the project directory — which is the correct behaviour for that machine and
was previously a total outage.

Note the asymmetry this creates deliberately: no `git` binary degrades, a broken `git` command
raises. `is_git_repo` swallowing the former is what makes it a detection and not a provisioning step.

### D3 — The context block distinguishes "shares by choice" from "no isolation available"

`_render_hub_agent_context` (`agents.py:1000-1015`) already branches on `isolated`, and
`agent_trigger.py:390` already derives that from `isolated_workspace is not None`. So a non-repository
run already produces *"This is the project's shared checkout, not an isolated worktree."* — true, and
not the whole truth: it is the same sentence a read-only agent gets, and it leaves an agent that
tries to branch or commit to discover the absence itself.

The block gains one sentence naming the reason. An agent that knows there is no repository does not
propose a branch, and does not read a failed `git status` as a broken environment.

**Rejected:** leaving it alone because the existing sentence is technically true. The whole cost of
this defect was a reason nobody could see.

### D4 — Removing the queue's git-repo reason, rather than rewording it

`inbound_queue.py:176-192` exists only to explain a wait. Under D1 there is no wait, so the probe
would be describing a state that does not stop anything — and it costs a `resolve_project_workspace`
call plus a `git rev-parse` subprocess on every queue-status poll. The whole branch goes, including
the `project_workspace` import added for it.

What is *not* removed is the ordering comment above it explaining that launchable ≠ startable. That
observation outlived its example.

### D5 — The workspace endpoint reports the state, and `isolated` becomes false

`api/v1/worktrees.py:129-141` currently returns `isolated=True` with an `unavailable_reason` — a
promise of isolation the agent will not get. Under D1 it will get the project directory, so the
honest report is `isolated=False`, `provisioned=True`, `working_dir=repo_root`, with a reason field
explaining why there is no branch.

This makes `unavailable_reason` mean "here is why you have no isolated checkout" rather than "here is
why your turns will fail". The UI (`AgentSettingsPage.tsx:296-300`) renders it via `role="alert"` in
amber; it becomes a note, not an alert, because nothing is failing.

**Rejected:** dropping the field and reporting a bare shared checkout. The operator would then see no
difference between an agent sharing by configuration and a project that cannot isolate anything, and
would have no way to discover that `git init` would change it.

### D6 — `work_dir` is refused only where there is isolation to override

`agent_trigger.py:346-350` refuses `work_dir` for any writing agent, justified as *"a custom work_dir
cannot override that isolation"*. In a project with no repository there is no isolation, so the
refusal has no subject. The guard gains the repository condition, in both places it appears
(`:346` and the HTTP-layer copy at `:658`).

Kept deliberately: the refusal for a writing agent in a real repository. Nothing in this change makes
that safer.

**This uncovered a live gap.** `ProjectWorkspace.resolve_relative` accepted a leading `~`: Python
does not expand it, so `~/projects/secret` resolved to a literal directory under the project root
and passed every containment check. It had never mattered because a writing agent's `work_dir` was
refused before reaching the validator — so the test asserting the refusal
(`test_agents.py::test_agent_trigger_rejects_work_dir_with_tilde`) had been passing on a different
guard than the one it names. Relaxing this refusal made the path reachable and the test fail, which
is the test doing its job late rather than a regression this change introduced.

Fixed at `resolve_relative` rather than in the `work_dir` guard: it is the single containment
chokepoint every caller passes through, and a rule that lives in one caller is a rule the next
caller does not get.

### D7 — Concurrent writers in a non-repository project are permitted and stated, not prevented

Two writing agents sharing one directory can produce a lost update. Worktrees do not remove that
risk; they convert it into a visible conflict — and that conversion needs a repository. Without one
the Hub has no mechanism, and the alternatives are all worse than the risk: serialising every writing
agent in the project would silently halve throughput for a reason the operator never asked for, and
refusing the second agent is the refusal this change exists to remove.

So it is permitted, and D3's sentence tells the agent it is sharing. This is the operator's call to
make, and making it requires them to know — which they now do.

## Risks / Trade-offs

- **A project that loses its repository silently changes posture.** If `.git` is deleted or the
  directory is copied without it, agents that were isolated start sharing the project directory,
  and only D3's context sentence and D5's endpoint field report it. Accepted: the alternative is
  refusing every turn for a project whose repository the operator removed on purpose, which is the
  defect this change fixes, one level up.
- **Uncommitted work in an existing worktree becomes unreachable if the repository is removed.**
  Pre-existing, and not made worse — `release_worktree` never deletes a branch.
- **A snapshot-free run records `Run.snapshot_commit_sha = NULL`**, so its checkpoint carries no
  changed-file list. `checkpoints.py:125` already returns `[]` for a `None` worktree, so this
  degrades rather than breaks. A conversation in a non-repository project gets checkpoints without
  file lists.
- **`agent-run-sandboxing`'s workspace boundary is now the project root** for these runs rather than
  a worktree beneath it. That is a wider boundary in absolute terms and the same boundary in
  intent — "your own workspace" is the directory the operator bound to the project.

## Migration Plan

None. No schema change, no data change, no configuration change. The behaviour change applies from
the next turn: a project that was blocked starts running, and a project that was working is
unaffected because it has a repository.

## Open Questions

- **Should project creation offer `git init`?** Out of scope here and unchanged by this change — but
  this change removes the urgency, because a project without a repository now works. Left for the
  operator to decide as a product question rather than a workaround.
