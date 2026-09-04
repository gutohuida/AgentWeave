---
name: handoff
description: Compact the session by committing the iteration and writing a new, numbered handoff file to disk before clearing or compacting. Never overwrites a previous handoff — each one is a new version in a chain. Use when context is filling up, when finishing a work chunk, before clearing/compacting the session, or when the user says "handoff", "save context", "compact", "wrap up this session", or "I'm going to start a fresh session". Pairs with /resume and /review-iteration.
---

Write a durable handoff artifact so this session's state survives a context reset.

**Core principle:** the handoff file on disk is the real memory — the context window is
scratch space. In-place summarization is lossy and compounds (a summary of a summary of a
summary); a structured file re-derived from the *live* session each time does not.

**Handoffs are append-only.** Never edit or overwrite an existing handoff. Each run writes
a **new numbered file**, so the chain is a readable history of the work: who did what, when,
and against which commits. `/resume` reads the highest number; anything earlier stays as
evidence.

Agent-agnostic: works in any CLI agent that can read and write files. Where this file says
"reset the context", use whatever your CLI calls it — `/clear`, `/compact`, `/new`; the
names vary by agent.

## Step 0 — Pick the right move

Choose one, state which you chose and why in one line, then proceed:

| Situation | Move |
|---|---|
| Finished a chunk of work; next step is a different task | **Full handoff → then clear.** Best quality: fresh window, zero rot. |
| Mid-task, deep in one thread, lots of stale debugging noise | **Full handoff → then compact with steering.** Keeps conversational flow. |
| Context is fine (<50%) and everything loaded is still relevant | **Do nothing.** Say so and stop. Compaction is not free. |
| User explicitly asked for a handoff | **Full handoff**, regardless of the above. |

Do this **early** — around 50–70% context used, not at 95%. The model writing the summary
is at its least capable exactly when the window is fullest, which is the single most common
cause of a bad compaction. If the user invoked this late, still do it, but be extra careful
with Step 5's checklist.

## Step 1 — Gather hard state (deterministic, cheap, no guessing)

Run these and use the real output. Do not recall git state from memory:

```bash
git branch --show-current
git status --short
git log --oneline -8
git diff --stat HEAD
git log origin/$(git branch --show-current)..HEAD --oneline 2>/dev/null || echo "no upstream"
```

Also find the existing handoff chain — check every location, since a previous session may
have run under a different agent:

```bash
ls .handoffs/handoff-*.md .claude/handoffs/handoff-*.md .agents/handoffs/handoff-*.md 2>/dev/null
```

If prior handoffs exist, **read the newest one** (highest number) and carry forward anything
still true. Never let a fact survive only as your own recollection of a previous summary.

## Step 2 — Close the iteration with a commit

A handoff that points at a pile of uncommitted edits is fragile: the next session cannot
tell your work from anyone else's, and `/review-iteration` has no boundary to review. Commit
first, then record the commit in the handoff.

**Repository policy wins over the defaults below.** If the repo's own instructions
(`CLAUDE.md`, `AGENTS.md`, a scoped rules file, or a standing directive the user has given
and the handoff chain has been carrying) state a different commit-or-push policy, follow that
and **say in one line which policy you are applying and where it comes from**. A repo that has
decided "commit each checkpoint without asking" or "push, do not open PRs" has decided; do not
re-litigate it every session. The defaults exist for repos that have not decided.

1. Show the user `git status --short` and `git diff --stat HEAD`, state the branch, and
   propose the commit message you intend to use.
2. **Default: ask before committing, and wait for a yes.** The user may be mid-thought about
   what belongs in this commit, may want the work split, or may not want it committed at all.
   Call out anything that makes the commit riskier than usual: the branch is `main`/`master`
   or otherwise protected, the tree contains changes you did not make, or the diff touches
   secrets, credentials, or large binaries. Skip the asking only under an explicit repo policy
   as above.
3. One commit for the iteration is usually right. Split it only if the work contains two
   genuinely unrelated changes.
4. Write a message that states what changed and why, and name the agent that did the work:

   ```
   <summary line>

   <what changed and why, 2-5 lines>

   Handoff: <the filename you are about to write>
   Agent: <model-id · CLI>
   ```

5. **Default: never push.** Pushing is outward-facing and stays a user decision, unless repo
   policy says otherwise. Never use `--no-verify`; if a hook fails, fix the cause or report it
   in `## Verification`.
6. If the user declines the commit, that is fine — continue, and record the uncommitted paths
   in `## Git state` and the fact that the iteration has no commit boundary.

## Step 3 — Record what you learned the hard way

Before writing the handoff, append anything that cost you a second attempt this session to
the durable ledger at **`<handoff-dir>/DEAD-ENDS.md`** — create it if absent.

This is separate from the handoff on purpose. A dead end copied forward handoff-to-handoff
survives only if every future session chooses to re-copy it, which makes survival a coin
flip. Measured across one 108-handoff chain: individual facts were dropped and re-learned
between three and seven times each, with gaps of up to 46 handoffs between a fact being
written down and being painfully rediscovered. A ledger is written once.

- **Append, never rewrite.** When an entry stops being true, mark it `RESOLVED` with the date
  and what changed rather than deleting it — "we used to believe this" is worth knowing, and
  an entry that quietly disappears is indistinguishable from one that was forgotten.
- **Date every entry** with when you last confirmed it. An inherited stale fact is worse than
  no fact, because it is believed.
- Keep this file tracked in version control even when the handoffs themselves are not — it
  holds tool and environment facts, not session narrative.

In the handoff itself, `## Dead ends` then records only what *this session* hit, and points at
the ledger for the rest.

## Step 4 — Write the new handoff file

**Directory:** if any of `.handoffs/`, `.claude/handoffs/`, or `.agents/handoffs/` already
contains handoffs, keep using that one — splitting the chain across directories is how a
resumed session silently loads the wrong history. If none exists, create `.handoffs/`.

**Filename:** `handoff-NNNN-YYYY-MM-DD-HHMM-<short-slug>.md`

- `NNNN` is a zero-padded sequence number, **one higher than the highest existing number in
  that directory** — `0001` if the directory is empty, or if unnumbered handoffs are present
  see "Adopting an existing chain" below. It is the single source of truth for which handoff
  is newest — file mtimes do not survive a clone, a copy, or a checkout, and a `LATEST.md`
  pointer is one more thing that can go stale.
- `YYYY-MM-DD-HHMM` is the real current date/time, for humans reading the directory.
- The slug names the work, not the session ("auth-token-refresh", not "session-3").

```bash
# highest existing number in the chosen directory
ls <dir>/handoff-*.md 2>/dev/null | sed 's/.*handoff-\([0-9]\{4\}\).*/\1/' | sort -n | tail -1
```

**Never write to an existing handoff file.** If you believe an earlier handoff is wrong, say
so in the new one under `## Corrections to the previous handoff` — the chain is a record.

### Version control: track all of them or none of them

Handoffs are session notes, so ignoring them is usually right — but the choice must be
uniform across the whole directory, and `LATEST.md`, if one exists, must share it.

A **partially tracked chain is the one genuinely broken option**: a clone gets the tracked
handoffs only, `/resume` picks the newest one it can see, and works from month-old state that
looks entirely legitimate. Seen in the wild — a 108-handoff chain tracked through 0073 and
ignored from 0074, with a tracked `LATEST.md` naming a file no clone contained.

Check on the first run in a repo, fix a split if you find one, and mention it once. Note also
that handoffs quote the user verbatim and record environment detail: in a **public** repo,
look at what the chain is actually publishing before choosing to track it.

### Adopting an existing chain (one-time, first run in a repo)

If the directory contains handoffs but **none of them are numbered**, this repo predates the
convention. Do not start a fresh sequence beside them — that leaves two parallel chains and
`/resume` has to guess. Adopt the existing history instead:

1. **Identify the newest existing handoff** — by the date in its filename, or by `LATEST.md`
   if one exists and agrees. If the dates are ambiguous, say so and ask which one is current
   rather than picking.
2. **Rename it to `handoff-0001-<its own original date>-<slug>.md`.** Keep its original date
   in the name — it records when that work happened, not when you migrated it. Use `git mv`
   if the file is tracked, so the history follows.
3. **Fill in the header fields it lacks** (`Agent:`, `Previous handoff:`, and a
   `# Handoff 0001:` title). Write `unknown — predates this convention` for anything you
   cannot establish from the file itself or from `git log`. **Do not infer the agent or
   model.** This is the only time you may edit an existing handoff, and only to add missing
   headers — never touch its body.
4. **Leave the older handoffs where they are, unrenamed.** They are pre-chain history, and
   renumbering a pile of old files invents a sequence that never existed. `handoff-0001` names
   its predecessor as `<filename> (pre-chain, unnumbered)` so the trail is still followable.
5. **Delete `LATEST.md`** and say you did — two competing "which is newest" mechanisms is
   worse than either alone.
6. **The handoff you are writing now is `handoff-0002`**, and its `**Previous handoff:**` is
   `handoff-0001-…`.

Report every rename you made, explicitly, in Step 6. A silent file rename in a directory the
user relies on is the kind of thing that gets discovered three sessions later.

If the user names a different location, use theirs.

### Template — every section is required; write "None." rather than deleting a heading

```markdown
# Handoff NNNN: <one-line task title>

**Date:** <ISO datetime> · **Branch:** <branch> · **HEAD:** <short sha>
**Agent:** <model-id> · <CLI> · <posture>
**Previous handoff:** <filename, or "none — first handoff in this chain">
**Status:** <in progress | blocked | chunk complete>

## Goal
What we are ultimately trying to achieve, in 1–3 sentences. Include the *why*, not just
the *what* — the why is what lets the next session make judgment calls.

## Current state
Where things actually stand right now. What works. What is half-done and in what way.
Be concrete: "the parser handles nested blocks but not escapes" beats "parser mostly done".

## Files touched
One line per file: full path — what changed in it and whether it is finished.
This is the #1 thing summaries silently lose. Never write "various files" or "several
components". List every path. Cross-check against `git status` / `git diff --stat` output.

## Key decisions
Each: the decision, the reason, and — critically — the alternatives rejected and why.
A rejected alternative with no recorded reason will be re-proposed and re-tried.

## Constraints and user directives (verbatim)
Quote the user's explicit instructions, preferences, and prohibitions **word for word**.
Includes things stated early in the session that feel "settled" — those are precisely
what compaction erases. E.g. "no new dependencies", "don't touch the migration files".
If a directive is durable rather than session-scoped, say where it now lives permanently
(repo instructions, memory) so the next session stops re-deriving it from the chain.

## Dead ends
What *this session* hit, and the symptom. Anything durable also goes in
`<handoff-dir>/DEAD-ENDS.md` (Step 3) — name that file here so the next session reads it
instead of relying on this list. Include near-misses that looked correct but weren't.

## Environment left running
Long-lived processes, servers, containers, schedulers, background jobs, watchers or tunnels
this session started and did not stop — with the port or PID, how to check each is alive, and
how to stop it. "None." if the session started nothing.
This exists because a resumed session that does not know a server is already up will start a
second one, and because an unattended job left enabled keeps firing after everyone has
stopped watching.

## Verification
What was actually run (exact commands) and the actual result. Then, separately and
explicitly: **what was NOT tested.** Never imply verification that did not happen.

## Git state
Branch, HEAD sha, clean/dirty, uncommitted paths, unpushed commits. From Step 1's output.
Plus the iteration commit(s) from Step 2 with their subjects, and the range
`<base-sha>..<head-sha>` for the next reviewer — or "none — work left uncommitted".

## Corrections to the previous handoff
Anything the previous handoff got wrong or that has since become false. "None." if it
still holds. Never edit the old file — correct it here.

## Next steps
Numbered. Step 1 must be immediately executable with no further decisions — a specific
file and a specific change, not "continue the refactor".

## Open questions for the user
Anything genuinely blocked on a human decision. Empty is a fine and common answer.
If a question has been carried unanswered across several handoffs, say how many — a
question nobody has answered in five sessions is not reaching anyone, and should be raised
directly rather than copied forward again.

## Read on resume
3–6 file paths worth reloading, each with a reason. Paths only — do not paste contents.
Pointers are cheap and always current; pasted excerpts are expensive and go stale.
```

### On the `Agent` field

One field, three facts, `·`-separated: the **exact model identifier** (`claude-opus-5`, not
"Claude"), the **CLI** that ran it (`Claude Code`, `Codex`, `Kimi`, `OpenCode`), and the
**posture** — `interactive`, `unattended`, `scheduled driver`, or whatever describes how this
session was invoked.

It was two fields once, `Model:` and `Agent:`, and the split did not survive contact: across a
108-handoff chain `Model:` was filled 7 times out of 108 while `Agent:` was filled 108 times,
because writers state them together naturally. The posture half was invented spontaneously by
the sessions that needed it and is now required — a repo where scheduled jobs write into the
same tree cannot interpret its own chain without it.

Take the model id from what the harness reports; if you genuinely cannot determine it, write
`unknown — <CLI> did not report it` rather than guessing. It matters for three concrete
reasons: a mid-chain model swap explains sudden shifts in style or judgment that would
otherwise look like drift; `/review-iteration` uses it to avoid having a model review its own
work unexamined; and when a chain produces bad output, the field is what makes the pattern
visible across handoffs instead of invisible.

## Step 5 — Validate before you finish

Re-read what you wrote and fix any of these:

- [ ] The filename's `NNNN` is exactly one higher than the previous highest, and no existing
      handoff file was modified or deleted — except a one-time chain adoption, where exactly
      one file was renamed to `handoff-0001-…` and only its headers were added.
- [ ] If handoffs existed but none were numbered, the newest was adopted as `handoff-0001`
      and this one is `handoff-0002` — not a second chain starting at `0001`.
- [ ] `Agent:` holds a real model identifier, a CLI, and a posture — not a family name.
- [ ] `## Git state` names the iteration commit range and matches what `git log` shows.
- [ ] Every file path mentioned actually exists (or is explicitly marked "to be created").
- [ ] `## Files touched` accounts for everything in `git status --short` and `git diff --stat`.
- [ ] `## Corrections to the previous handoff` is present and was actually considered — if you
      corrected, contradicted or superseded anything the previous handoff asserted, it belongs
      here and not buried in another section. "None." is a real answer; a missing heading is
      not. (Observed failure: a chain where this section survived in 5 handoffs out of 108
      while corrections were being recorded under `## Files touched` instead.)
- [ ] `## Environment left running` accounts for every process this session started.
- [ ] Durable dead ends were appended to `DEAD-ENDS.md`, not only listed in this handoff.
- [ ] No dangling references: no "the fix we discussed", "that approach", "the bug" without
      the content stated inline. The next session cannot see this conversation.
- [ ] Constraints are quoted, not paraphrased.
- [ ] Verification section distinguishes ran-and-passed from not-run. No implied testing.
- [ ] Next step 1 is executable as written by someone with zero prior context — including
      a different agent, which may not share this one's tools or conventions.
- [ ] Nothing important lives *only* in the conversation. If it does, it is now lost.

Bias to **recall over brevity** on the first pass: it is far cheaper to include a fact that
turns out irrelevant than to lose one that mattered. Trim only obvious redundancy.

## Step 6 — Report and hand back control

Print:
1. The handoff file path and its number.
2. Any chain adoption you performed: the file renamed to `handoff-0001-…`, what it was called
   before, which headers you added, and whether `LATEST.md` was deleted.
3. The commit sha(s) and subject(s) from Step 2, or that nothing was committed and why —
   and which commit/push policy you followed, if it was not the default.
4. What you appended to `DEAD-ENDS.md`, if anything.
5. A 3–5 bullet digest of what the handoff captured.
6. The recommended next move, exactly one of:
   - **Clear the context, then run `/resume`** — for a task boundary (preferred; cleanest
     window).
   - **Compact with explicit steering** — for staying mid-thread. Always supply the
     steering text, e.g. "keep the auth refactor, drop the test debugging". An unsteered
     compact guesses at where the work is heading and guesses badly.
7. If the iteration was substantial, security-sensitive, or is about to be built on:
   mention that `/review-iteration` in a **fresh context** will review exactly this
   commit range against the specs. Do not run it yourself from this window — a full
   context is the wrong place to review from, and a model reviewing its own work in the
   same session mostly confirms itself.

Name the actual command for the CLI you are running in if you know it; otherwise describe
the move and let the user pick the command.

**Do not reset the context yourself** — the user decides when the window resets. State the
recommendation and stop.
