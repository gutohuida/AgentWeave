---
name: review-iteration
description: Review the work done in the last iteration — the commits and files changed since the previous handoff — against the project's specs and the handoff's own claims. Establishes the boundary from the last two handoffs or recent commits, loads only the changed files, and reports severity-ranked findings with evidence. Never fixes anything. Use when the user says "review the last iteration", "review what we just did", "review this work", "review the last handoff", "check the previous session's work", or before building on top of unreviewed work.
---

Review one iteration of work — not the whole repository, not a whole PR, but the bounded
chunk of change the last session produced — and report what is wrong with it.

**Core principle: no proof, no report.** A finding is a concrete failing scenario — specific
inputs or state, leading to a specific wrong result. Anything you cannot pin down that way is
noise, and noise is the failure mode that kills AI review: a reviewer with twenty maybes is
worse than useless, because the real bug is buried in it and the reader learns to skim.

**Second core principle: you fix nothing.** Not typos, not the obvious one-liner, not while
you're in there. The deliverable is findings. Mixing review with authorship destroys the
review — you stop looking once you start editing, and the user loses the chance to decide
what is worth changing. Offer to fix as an explicit separate step, after reporting.

Agent-agnostic: works in any CLI agent that can read files and run git. Best run in a **fresh
context**, and ideally by a **different model** than the one that wrote the code — a model
re-reading its own work in the same window mostly confirms itself.

## Step 1 — Establish the boundary (say it out loud before reviewing anything)

You are reviewing a range, and getting the range wrong makes everything after it wrong. Work
down this list and stop at the first one that yields a boundary:

1. **The user named it** — a range, a commit, a branch, "since yesterday". Use theirs.
2. **The last two handoffs.** List the chain and take the two highest numbers:

   ```bash
   ls .handoffs/handoff-*.md .claude/handoffs/handoff-*.md .agents/handoffs/handoff-*.md 2>/dev/null
   ```

   Read the latest. Its `**Iteration commits:**` field is the range. If it is absent or says
   the work was left uncommitted, use `<previous handoff's HEAD>..HEAD` — read the previous
   handoff for that sha. Include uncommitted work if the tree is dirty; say that you did.
3. **No handoffs** — fall back to git and state the assumption plainly:

   ```bash
   git log --oneline -10
   git log origin/HEAD..HEAD --oneline 2>/dev/null   # unpushed = probably this iteration
   git status --short
   ```

   Prefer the unpushed commits; otherwise ask the user how far back "the last iteration" goes
   rather than guessing at a number of commits.

Then gather the change itself:

```bash
git diff --stat <base>..<head>
git log <base>..<head> --format='%h %an %s'
git diff <base>..<head>
```

**Report the boundary before you start**: base sha, head sha, commit count, file count, and
whether uncommitted work is included. If the range is large enough that a careful review will
not fit (roughly >40 files or >2000 changed lines), say so and propose a split by area rather
than skimming everything — a shallow review of everything is worth less than a real review of
the risky half.

## Step 2 — Load the contract

You cannot judge whether code is *right* without knowing what it was supposed to do. Gather,
in this order, and keep it cheap — pointers and relevant sections, not whole documents:

| Source | What you take from it |
|---|---|
| **Latest handoff** | `## Goal`, `## Key decisions`, `## Constraints and user directives`, `## Verification`, `## Dead ends`, and the `Model:` field |
| **Previous handoff** | What was already true before this iteration, so you don't attribute old defects to it |
| **Specs** | The requirements this change was supposed to satisfy |
| **Project directives** | `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, contributing docs — the repo's own rules |

Search for specs the same way a spec-aware skill would; do not assume a location:

```
specs/   .specify/   .kiro/specs/   docs/specs/
spec.md  plan.md  tasks.md  requirements.md  design.md  constitution.md
```

**Load only the spec sections that cover the changed surface.** A spec directory is usually
far larger than the iteration; reading all of it is how the review runs out of context before
it reads the code. If requirements carry IDs, note the IDs in scope.

If there is no spec and no handoff, say so — the review is then against the repo's own
conventions and the commit messages' stated intent, which is a weaker contract. Name that
limitation in the output rather than pretending to a standard you don't have.

## Step 3 — Read the changed code, not just the diff

For every changed file, read **the file**, not only the hunks. Diffs hide the two things that
matter most: what the surrounding code already guarantees, and what else calls this.

For each non-trivial change:

1. Trace the complete call path — who calls this, what they pass, what they do with the result.
2. Search for **all** callers and uses of anything whose signature, contract, or behavior moved.
3. Read the tests that cover it, and the comments and docs that explain why it is the way it is.
4. Check whether an existing guard, validation, or caller-side check already handles the
   failure you are about to report. If it does, there is no finding.

Only read files outside the changed set when a specific question demands it (a caller, a
shared type, a base class). Do not tour the repository.

## Step 4 — Look for these, in this priority order

1. **Correctness** — logic errors, off-by-one, wrong branch, unhandled nil/empty/error,
   broken invariant, race, resource leak. Concrete inputs → wrong output.
2. **Security** — injection, authz/authn gaps, secrets in code or logs, unsafe deserialization,
   path traversal, missing validation on external input, permissive defaults. AI-generated code
   is materially more defect-prone here than human-written code; do not pass it on "looks done".
3. **Regressions and contract breaks** — changed public behavior, signature, schema, config
   key, or error shape with callers not updated. This is what tracing callers is for.
4. **Spec divergence** — a requirement in scope that is unimplemented, partially implemented,
   or implemented differently than specified. Cite the requirement ID or heading. Also flag the
   inverse: behavior shipped that no requirement asked for.
5. **Test integrity** — tests deleted, skipped, loosened, or rewritten to match new behavior
   instead of asserting intended behavior; a bug fix with no test that would have caught it;
   assertions that cannot fail.
6. **Handoff claims vs. reality** — the handoff's `## Verification` says what was run and what
   was not. Check the claims that are cheap to check. A verification claim that isn't true is a
   serious finding, because every later session will trust it.
7. **Scope creep** — changes outside the stated goal, especially unrelated refactors bundled in.
   Note them; they may be fine, but they need to be visible.
8. **Architecture violations** — breaks a rule the constitution/`AGENTS.md` actually states.
   Cite the rule. Your own architectural taste is not a finding.

### Do not report

- Style, formatting, naming, or import order — automation's job, or nobody's.
- Speculative future risk ("this won't scale") with no current failing scenario.
- Feature requests wearing a finding's clothes.
- Anything already suppressed deliberately (`// eslint-disable`, `# noqa`, `# type: ignore`)
  unless the suppression itself is the bug — and then say why.
- Anything you could not tie to evidence in this codebase. Discard it; don't hedge it.
- Pre-existing defects outside the iteration's changes, unless the change made them reachable.
  If you spot one anyway, put it in a separate "Outside this iteration" note.

## Step 5 — Prove each finding before writing it down

For every candidate, in order — drop it the moment one fails:

- [ ] The failing scenario is concrete: specific inputs or state → specific wrong behavior.
- [ ] The code path is actually reachable from a real caller or entry point.
- [ ] No existing guard, validation, or caller contract already prevents it.
- [ ] It is not intentional — no comment, test, or spec line says the behavior is by design.
- [ ] It was introduced or made reachable by *this* iteration.

Where a check is cheap and available, **run it**: execute the focused test, run the linter or
type checker, write a throwaway reproducer. A finding you demonstrated beats a finding you
reasoned toward, and running the existing suite also tells you whether the iteration left the
tree green. Record the exact commands and their real output. If you ran nothing, say so — an
unverified review is still useful, but only if it is labeled as one.

## Step 6 — Write the review

Write a file next to the handoff chain, in a `reviews/` subdirectory of whichever handoff
directory is in use: `reviews/review-NNNN-YYYY-MM-DD-HHMM.md`, where `NNNN` matches the
handoff number being reviewed. If there is no handoff chain, use `.reviews/` at the repo root
and number from `0001`. Reviews are append-only too — never overwrite an earlier one.

```markdown
# Review NNNN: <one-line description of the iteration>

**Date:** <ISO datetime> · **Range:** <base>..<head> (<n> commits, <n> files)
**Reviewing model:** <exact model id> · **Authoring model:** <from the handoff, or "unknown">
**Handoff reviewed:** <filename, or "none — boundary taken from git">
**Specs consulted:** <paths + requirement IDs in scope, or "none found">
**Verdict:** <Ship it | Ship with follow-ups | Fix before building on this | Needs rework>

## What this iteration did
2–4 sentences, in your own words from reading the code — not a restatement of the handoff.

## Findings
### [Critical|Major|Minor] <short title>
**Where:** `path/to/file.ext:LINE`
**What:** one sentence — the defect.
**Failing scenario:** the specific input/state → the specific wrong result.
**Evidence:** what you read or ran that proves it (command + real output, or the call path).
**Suggested direction:** one line. A direction, not a patch — you are not fixing it.

(Repeat. Most severe first. If there are none, write "No findings that meet the evidence bar."
and mean it — an empty review is a real and common result.)

## Verification status
Commands you ran and their actual output. Then, explicitly: what you did NOT check and why.

## Handoff claims checked
Each claim from the handoff's `## Verification` → confirmed / contradicted / not checked.

## Spec coverage
Requirement IDs in scope → implemented / partial / missing / not in this iteration.

## Outside this iteration
Pre-existing issues noticed but not caused by this work. Informational; do not act on them here.

## Open questions
Things needing a human decision — intent you could not infer from code, spec, or handoff.
```

Severity means:

| Severity | Bar |
|---|---|
| **Critical** | Data loss, security hole, or a broken primary path. Do not build on this. |
| **Major** | Wrong behavior on a real path, a broken contract, or a false verification claim. Fix before the next iteration. |
| **Minor** | Genuine defect, narrow blast radius. Worth a follow-up, not a blocker. |

## Step 7 — Report and stop

Print the review file path, the verdict, and the findings as a compact list — severity, title,
`file:line`, one line each. Then stop.

**Change nothing.** Not the code, not the tests, not the specs, not the handoff. If the user
wants fixes, that is the next task and it starts from the findings list: ask which findings to
act on, and treat that as new work with its own iteration and its own handoff. A review that
silently edits the thing it reviewed leaves nobody able to say what was wrong in the first
place.

See `../../ResearchClub/agent-operating-model/repo-skills-and-development-cycle.md` (§3.4,
`review-change`) for where this sits in the development cycle, and
`../../ResearchClub/ai-development-workflow/how-to-develop-with-ai.md` for the evidence on
why AI-authored code needs a verification loop stronger than "looks done".
