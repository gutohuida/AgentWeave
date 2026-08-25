# Design

Decided with the operator on 2026-08-23, after driving the product end to end and watching a
reviewer report its own blindness. Every decision below has a rejected alternative and the reason,
because the rejected ones are individually defensible and will otherwise be re-proposed.

## D1 — The reviewer gets a worktree, not a diff and not a mount

Three shapes were on the table. The criterion that separated them is **can the reviewer run the
tests**, and only one survives it.

| | reads the change | reads surrounding code | runs the suite | boundary intact |
|---|---|---|---|---|
| diff tool | yes | no | **no** | yes |
| read the author's worktree | yes | yes | risky | **no** |
| **own worktree at the commit** | yes | yes | **yes** | yes |

The product's whole thesis is evidence: an agent records "5 passed" and cites a commit. A reviewer
that cannot execute is reviewing a *claim*. Being able to re-run the suite against exactly the code
the evidence names is what turns a recorded claim into a verified one, and it is the only reason to
have a second agent look at all.

## D2 — Detached HEAD, no branch

The review checkout is created detached at the evidence commit.

A branch invites a commit, and the reviewer is not an author — if it wants a change made, the
product already has `revision_needed` and the author makes it. Detached also means git itself states
the role: `git status` in that directory says *"HEAD detached at cad5d74"*, so the environment tells
the agent what it is doing without depending on the prompt to say it. That is the same instinct as
the boundary: enforce it rather than ask for it. And an accidental commit is orphaned and harmless
rather than accumulating on a branch nobody prunes.

Rejected: `agentweave/review/<agent>` as a real branch, for inspectability. The gain is small and
the invitation to commit is the cost.

## D3 — Keyed by the reviewing agent, not by the commit, task or evidence

Path: `.agentweave/reviews/<agent>`, mirroring `worktree_path(repo_root, agent)`.

Keyed by reviewer because it is **bounded**: one per agent, forever, re-pointed with
`git checkout --detach <sha>` at each review. Only one run per agent can be live at a time, so one
review checkout per agent is provably sufficient.

Rejected: keying by commit, task or evidence id. Each grows without limit and reintroduces a
cleanup problem — a directory per review, accumulating for the life of the project.

## D4 — Exactly one workspace per review turn

During a review turn the reviewer's workspace **is** the review checkout. Its own working worktree
is not part of that turn.

This is what eliminates rather than mitigates the "two directories" hazard. The agent is never told
there are two places and asked to keep them straight; there is one place, the Hub put it there, and
the other is outside its boundary. A predictable path alone would not achieve this — it would only
stop the agent *constructing* a path, not stop it reasoning about the wrong one.

Corollary, and worth stating because it is the thing most likely to go wrong: **the boundary
enforces *where*, the turn context must still state *what*.** A reviewer that is not told it is
reviewing will helpfully fix the bug itself and report the work as verified. Both halves are
required.

## D5 — The commit is the one the most recent evidence names

Evidence carries `footprint: {branch, commit_sha, reachable_from_main}`, already populated and
already re-stamped at run end to point at the commit that actually holds the work.

A task can carry several evidence rows naming different commits — observed live, `ev-42cad5d2` and
`ev-5d0273ad` on the same task. So a rule is required rather than an assumption: **the most recent
evidence wins, and where earlier evidence names a different commit the reviewer is told so.** Told,
not silently given the newest: a reviewer that knows the work moved can ask why, and one that does
not cannot.

Rejected: the task's latest run snapshot. It is the same commit in the ordinary case and a
different one whenever a run ended without recording evidence — and in that case there is nothing
to review.

## D6 — Shared dependencies are symlinked, or this change does nothing

`_symlink_shared_dependencies` already runs for a working worktree. It must run for a review
checkout too. A reviewer with no `node_modules` cannot run the suite, and D1's entire justification
is that it can.

## D7 — Scope: visibility only

This change makes a reviewer *able* to review. It deliberately does not decide:

- **who dispatches the reviewer** — `loop-becomes-a-flow` already specifies that `completed`
  becomes claimable by an agent that did not complete it, and resolves `Task.reviewer`;
- **who may approve** — whether an agent may take `under_review -> approved` and therefore write to
  the main branch;
- **per-task review policy** — declaring in the specification document which tasks require a human
  approver and which an agent may approve, which the operator raised on 2026-08-23 and which is a
  later change of its own.

Kept apart because the mechanism is useful alone and the policy is worthless without it, so the
ordering is forced. Bundling them would also make this change unlandable until the policy question
is settled, while `loop-becomes-a-flow` waits on it.

## Note on a rule that could be read as forbidding this

`CLAUDE.md` records that a backstop which detected whether a run's trailing prose *read like* a
question was deliberately retired, and must not be reintroduced. That decision is about **inferring
intent from prose**. Nothing here infers anything: a review turn is identified by a task's status
and a stored `reviewer` field. Observation, not inference. Stated so the retired decision is not
later cited against this one.
