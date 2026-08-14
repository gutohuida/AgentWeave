# Overnight autonomous work — 2026-08-15

**Branch:** `autonomous_work`, cut from `hub-native-experience` at `7cb7783`.
**Authorised by:** the operator, 2026-08-15 ~00:40, *"work on agentweave until 10 AM tomorrow …
open a branch of this branch called autonomous_work and work on whatever you feel is necessary …
I give you full autonomy on this branch."*
**Agent:** Claude Opus 5 (1M context) (Claude Code).

Read this file top-to-bottom in the morning. Newest entry is at the **bottom**, so it reads in the
order the work happened. Every entry states what was attempted, what actually happened, and what a
reviewer should distrust.

---

## What I am not allowed to do, self-imposed

The operator gave full autonomy on this branch. These are the limits I set anyway, because they are
the ones that would be expensive to get wrong while nobody is awake to stop me.

1. **Never leave `autonomous_work`.** No commits, merges, or rebases onto `hub-native-experience` or
   `master`. The morning's review decides what, if anything, comes across.
2. **Nothing outward-facing.** No PyPI publish, no GitHub release, no issue or PR creation, no
   force-push, no history rewriting. Pushing `autonomous_work` itself is allowed — it is what makes
   the work reviewable and durable.
3. **No destructive filesystem or database operations.** In particular `aw-loop6`, `aw-loop7` and
   `aw-loop8` stay: they are kept reproductions, and `aw-loop6` holds a hand-minted credential.
4. **Never mark an openspec task complete on the strength of a plan.** The standing rule; it matters
   more, not less, when nobody is checking.
5. **Every claim in this log is either measured or labelled as unverified.** If I could not run
   something, it says so.
6. **Stop and write it down rather than guess** where a decision is genuinely the operator's. Those
   collect under "Decisions waiting for you" at the bottom.

## Plan

Ordered by value, and each step's output feeds the next.

1. **Prove the data-loss fix live.** Changes A and B landed with agent-verifiable checks all green,
   but their human-only sections are unrun. `aw-loop8` (`proj-94f3f169`) exists for exactly this and
   has a `victim` codex agent. Kill a runtime mid-turn and watch whether the entry comes back, is
   retried without help, and abandons at three with the operator told.
2. **Drive the whole product with `/e2e-loop` (loop 9)** against the new code, from an empty
   directory. Loops 5–8 each found defects that live between features and that the 2028-test suite
   cannot see. This is the highest-signal activity available.
3. **Fix what it finds**, specced through openspec like everything else.
4. **Repeat 2–3** while the night lasts.

Anything the operator has already ruled out stays ruled out: G5 (the interview backstop), the narrow
requeue rule, and re-raising the settled `ci.yml` question.

---

## Log

### 00:45 — Branch cut, log opened

`autonomous_work` created from `7cb7783`. Nothing else done yet. Entry exists so the file is
committed before any work depends on it.
