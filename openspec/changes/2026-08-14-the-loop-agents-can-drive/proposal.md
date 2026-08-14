# The loop agents can drive

## Why

Driving the product from zero on 2026-08-14
(`openspec/explorations/2026-08-14-loop6-the-pipeline-agents-cannot-drive.md`) completed a full
loop — specification, tasks, a Claude builder, a Codex reviewer that found a real bug, a merge to
`master`. It completed only because the operator reached past the product twice, and one of those
reaches was minting a run credential directly in the database, which no operator can do.

The root problem: **the `verified → integrated` pipeline built across 2026-08-13 and 2026-08-14
cannot be driven by agents.** Both evidence routes exist on the agent plane and no tool reaches
either, so approval reports `skipped: no accepted evidence names a commit` and the loop stops one
step from done. The capability to accept evidence is gated on a column no surface can set.

Around that sit five smaller defects, each of which cost real time in the run.

## What changes

1. **The evidence loop reaches the agents.** Recording, listing and deciding evidence become tools;
   the acceptance capability becomes grantable; a granted agent is told it has the grant.
2. **A task-triggered agent can find the specification it implements.** The document a task
   implements is named in the turn context, in framing that says implement rather than author.
3. **A refusal by a Codex sandbox is recorded.** Today it is invisible to the event log, to SSE and
   to the timeline, so the operator cannot see that an agent was blocked.
4. **The main branch is choosable.** The integration note tells the operator to choose one in the
   project's settings; that control does not exist.
5. **The Hub stops committing build artefacts** it swept into an agent's snapshot.
6. **Declared tasks get usable titles** instead of a whole description clipped mid-word.

## Archive ordering

This change **modifies** a `local-project-workspace` requirement that
`2026-08-14-what-the-product-actually-built` **adds** and that has not reached the main spec yet.
Archive that change first; applied in the other order the modification has nothing to modify.

## Non-goals

- **The interview backstop (G5).** A question the operator never answers still leaves no trace. That
  is a standing operator decision — *"the AI should answer or not deliberately based on the test"* —
  and is not reopened here.
- **Peer-triggered posture inheritance.** The run's reviewer inherited no posture because it had no
  prior conversation; `conversations.inherit_runtime_overrides` behaves as designed and
  `Agent.default_permission_mode` already has an API and a UI control. What is broken is only that
  the refusal left no trace, which is item 3.
- **Untracking artefacts already committed.** Ignore rules apply to untracked paths. Repairing a
  repository the Hub already dirtied would mean the Hub rewriting the operator's index unasked.
