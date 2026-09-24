# Test guide — a footprint names the line of work its commit is on

## Agent-verifiable

1. **No footprint carries detached-checkout text.** 1.1, 1.3, 1.4.
2. **F165's operator case now supersedes.** 1.2 flips a pinned non-guarantee on purpose.
3. **A later review of an older commit does not shrink the merge.** 1.5, with 1.6 as the rebase control.
3a. **Footprints that name no line of work are not one bucket.** 1.5d (unrelated unnamed commits are both merged; only a proper ancestor is dropped; an unknown probe keeps both), 1.5e through the approval route.
4. **F166's released-checkout case names the task branch.** 1.7; 1.8 keeps the task-less legacy case as it was.
5. **The migration** (1.9) rewrites only `HEAD`.
6. **The drive** (3.1).

## Human-only

1. After a conflict refusal, resolve on the task's branch, commit something else on top, and record
   evidence as the operator with the resolution's sha as the locator. Approve: it should merge, and
   the task drawer's integration row should name the resolution commit.
3. (Hard to stage by hand; 1.5e covers it.) If a task ever carries two accepted pieces of evidence
   whose branch reads empty, on unrelated commits, approval should merge both, and the drawer should
   show one integration row per commit.
2. Open a reviewer's evidence in the coverage view (once the F215 change ships): its branch should
   read as the task's branch, not `HEAD`.
