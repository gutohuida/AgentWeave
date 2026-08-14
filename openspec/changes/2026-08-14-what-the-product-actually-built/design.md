# Design — What the product actually built

## D1. The root a footprint is taken from is derived from the row, not passed in

`capture_footprint(session, evidence, workspace)` keeps its signature and reads `evidence.actor_kind`
and `evidence.actor`, which `record` has already set and flushed. A new
`footprint_root(workspace, actor_kind, actor)` returns the project root unless the actor is an agent
with a real worktree.

**Rejected: threading an `agent` argument through `record` and both routes.** The footprint hangs off
the evidence row; deriving it from that row means the two cannot come to disagree, and any later
caller — a backfill, a re-capture — gets the right root without knowing this rule exists.

Neither evidence route changes.

## D2. "Does this agent have a worktree" is a git question, not a filesystem one

`worktrees.existing_worktree(repo_root, agent)` must verify through `_registered_worktree_branch`
that git knows the path *and* that it carries `refs/heads/agentweave/<agent>`.

`worktree_path(...).exists()` is **not** an acceptable test. A git command run with `cwd` set to a
directory git does not know about **walks up to the parent repository** and answers about it — so an
empty or stale `.agentweave/worktrees/builder` would return the project root's HEAD on master,
silently reproducing the defect behind a check that appeared to pass. There is a test for exactly
this, because it is the mistake a reasonable implementation makes.

The function provisions nothing. `ensure_worktree` creates state and must never be reached from a
read path — also a test, because reaching for it is the other reasonable mistake.

## D3. The operator keeps the project root

That directory is the operator's own checkout, and an operator recording evidence while on some
feature branch records *that* branch, which is where they observed the thing.

It is also safe by construction rather than by convention: **git refuses to check out a branch that
is already checked out in a linked worktree**, so the main checkout can never be sitting on
`agentweave/<agent>`. The operator's footprint cannot accidentally *be* an agent's.

## D4. Reachability has to be re-answered, or the fix reads as a regression

`EvidenceFootprint.reachable_from_main` is written once, at capture, and **nothing in the repository
has ever updated it**. `requirement_coverage._integration` reads the stored column.

So the moment D1 lands, every agent footprint records `False`, the merge succeeds, and coverage says
`verified, not integrated` **forever**. Shipping D1 without this would replace a false positive with
a permanent false negative and look like the fix breaking coverage.

`refresh_reachability` re-answers footprints that did not already say yes: one git call per *distinct*
commit, bounded, writing only where the answer changed. It runs after a successful merge — project
wide, deliberately, because merging FR-1's commit genuinely makes FR-2's earlier commit on the same
branch reachable — and from the operator's explicit drift scan, which is what eventually notices a
merge done by hand in a terminal.

The configured `main_branch` wins over the `MAIN_BRANCH_NAMES` guess where both exist; they can
disagree, and the configured one is what integration actually targets.

**Known residual, stated rather than hidden:** a hand-merge with no subsequent scan leaves the answer
stale in the conservative direction. Closing it fully means a git call on the coverage read path,
which is polled. Not worth it yet.

## D5. Drift is assessed against the ref, not against a root

`detect_drift` compares a stored footprint's `entries` against `read_footprint(workspace.root)`. Once
footprints come from agent worktrees, those entries are the agent branch's tree: every file the agent
added is absent from master, so **every accepted requirement becomes a drift candidate on the first
scan**. That is not drift. "This is not on master" is `not_integrated`, which coverage already
reports — raising it again as drift asks the operator one question in two vocabularies, which
`detect_drift`'s own docstring already refuses for rewordings.

So drift reads the tree of the branch each footprint names, cached per distinct ref. A footprint with
no branch, a detached HEAD, or a branch that no longer resolves raises nothing: unknown is not drift.

This also fixes a latent bug — one `current` is applied to both footprint kinds today, so a `paths`
footprint in a project that later became a repository is compared against git blob ids.

**No new column.** `branch` already identifies the line of work, and it survives `release_worktree`,
which removes the directory and deliberately keeps the ref. A stored path would dangle there, and
would break again when a project is relocated. Worktrees share the object database *and* the refs, so
the branch is readable from the project root whether or not the checkout still exists.

**Accepted consequence:** after work merges, drift keeps watching the agent branch, so a later change
to the same files on main is not noticed. Answering that properly needs the *changed* paths rather
than the whole tree, which is a separate defect (see Non-Goals). Deliberately **not** solved by
switching the basis to main once reachable — that would make the basis depend on a column D4 mutates,
and drift would flip bases underneath an open candidate.

## D6. Already-there is `skipped`, and it is checked before the working tree

`git merge --no-ff <ancestor>` prints "Already up to date", exits 0, and creates nothing. That is why
a no-op was recorded as a merge.

The guard sits after `branch_exists` and **before** the dirty-checkout and current-branch checks:
whether a commit is already in the target is a fact about the commit and the target, independent of
the working tree. An operator with uncommitted changes should be told the true thing rather than
"commit or stash and the next approval will merge", which would be false.

`is True` specifically. `None` means the ref does not resolve and `False` means it is genuinely not
there; an unknown commit makes `merge-base` exit non-zero, falls through, and lets git fail with its
own message — which is the honest outcome.

## D7. A document is read as its payload, never as its rendering

The read tool returns the structured payload with minted identifiers joined on and acceptance
criteria **nested under the requirement they demonstrate**.

- **Not the HTML.** It is the rendering *of* the payload; returning it costs an agent its context
  window and buys it a parsing job.
- **Criteria nested, not sibling.** They arrive keyed by requirement key. An agent handed two flat
  lists has to perform a join the caller already knows how to do, and will get it wrong for a
  document whose criteria interleave.
- **Nothing is dropped.** A requirement with no row returns `identifier: null` plus a diagnostic; a
  document with no payload returns 200 with a `payload_missing` diagnostic. "Unknown" is not "empty",
  a distinction `spec_index` is already careful about.

**Any phase.** Reading is not writing, and every gate in this area is on writing or approving. A
reviewer needs a `proposed` document and a builder needs an `approved` one. A phase-based refusal
would be intermittent, and an agent that hits one concludes the capability does not exist and stops —
which is the failure this whole area already has on record.

The phase and rigor are *returned* instead, so the agent can calibrate rather than guess.

## D8. Statements are read, never stored

`SpecRequirement` holds no wording by explicit design — *"so this row cannot come to disagree with the
document about what a requirement says."* A statement column would violate that on purpose.

So statements come from the document, batched **one file read per distinct document per request**
rather than per task. A moved project directory degrades to "no statements" rather than failing a
task board, because `resolve_project_workspace` raises exactly there. A retired requirement whose key
is gone from the document yields `statement: null` — which is the honest answer, since a retired
requirement has no current wording by definition.

Because the agent routes reuse the operator handlers verbatim, this fixes the MCP `get_task` and
`list_tasks` payloads with no change to the tool surface.

## D9. Approval materialises the tasks the document declares

The payload already carries `tasks` — a `key`, a `description`, and the requirement **keys** each
serves — validated at save time, read by the completeness check, and materialised by nothing.

On the transition into `approved`, each declared task becomes a real row with real requirement links,
resolved through the identity block's key→identifier map and the same link path `create_task` uses.

**Idempotent by `(project_id, document_id, key)`**, so re-approving after a revision adds what is new
and never duplicates. A task the operator has since moved, renamed or reassigned is left exactly as
it is — the document declares that work *exists*, not what has happened to it since.

**Created unassigned and `pending`.** The document has no assignee field, and who does the work is a
roster decision. A document declaring no tasks creates none, silently — that is a document that has
not been decomposed yet, not an error.

## D10. What this deliberately does not do

- **Does not narrow footprint entries to changed paths.** Real, pre-existing, and separate: fixing it
  inside this change would hide what this change is for.
- **Does not touch the interview backstop**, by operator decision.
- **Does not add a footprint root column, per-task branches, GitHub, or un-merging.**
