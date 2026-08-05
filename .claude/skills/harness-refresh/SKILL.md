---
name: harness-refresh
description: Re-derive the agent-harness configuration knowledge from upstream documentation and report what changed since the last pass. Updates the reference files that /harness-audit reads and appends a dated entry to the verification log. Use when the user says "refresh the harness research", "is this still accurate", "check for new claude code features", "update the audit references", or before running /harness-audit on something important after a gap of weeks. Does not touch any repository's configuration.
---

Re-derive what `/harness-audit` knows, from primary sources, and report what moved.

**This skill writes documentation, never configuration.** It updates reference files and the
verification log. It does not audit a repository, does not edit `.claude/`, and does not touch
settings, hooks, or instruction files. If the user wants a repo changed, that is
`/harness-audit`.

**Primary sources only.** Official documentation is authoritative. Vendor blog and support
content is second tier — useful for how the tool's own team works, but its numbers are usually
unmethodical. Community writing is third tier and is used only to *generate questions* to check
against the docs, never as a citation. Label every tier explicitly in the log; the value of this
skill is that a future reader knows how much to trust each line.

Run this in a forked or fresh context when possible. It is a research fan-out, and its output is
a small diff — exactly the shape that should not consume a working session's window.

## Step 1 — Establish the baseline

Read `ResearchClub/agent-harness-configuration/verification-log.md` and note the date, the CLI
version, and the "known gaps" list from the most recent entry. Determine the *current* CLI
version (`claude --version` or equivalent). State the delta out loud: "last verified at X on
DATE, now on Y" — that span is what you are looking for changes within.

## Step 2 — Re-derive from the docs

Fetch the pages that back the reference files. The current set:

```
features-overview · memory · skills · sub-agents · hooks
permissions · settings · context-window · costs · agent-teams · commands
```

Start from the documentation index (`llms.txt` where the vendor publishes one) rather than
assuming the URL list is still complete — new pages are how new features arrive.

For each, compare against `ResearchClub/agent-harness-configuration/claude-code-reference.md`
and the audit skill's `references/`. You are looking for four things:

1. **Contradictions** — something stated that the reference now gets wrong. Highest priority.
2. **Version gates** — behaviour that changed in a version between the baseline and now, and
   whether the user's current version is on the new or old side of it.
3. **New surface** — commands, hook events, frontmatter fields, settings keys that did not
   exist.
4. **Closed gaps** — items from the previous entry's "known gaps" that are now documented.

## Step 3 — Chase the open gaps

Work the previous entry's "known gaps" list explicitly. Carrying a gap forward unexamined for
several passes is how a research file quietly stops being research. If a gap is still
undocumented after being checked, say so and keep it — that is a finding about the vendor's
docs, not a failure.

## Step 4 — Update, conservatively

- Correct anything contradicted. **Note the correction in the log**, do not just overwrite it —
  what was wrong, and what it should have been, is the most useful thing in the file.
- Add new surface only where it changes a recommendation. A new command that nobody would act
  on is noise; a new hook event that makes a previously unenforceable rule enforceable is not.
- Keep the reference files at reference length. If one is growing past usefulness, split it or
  cut what has stopped earning its place — these files are read into a working context, so the
  same economics being documented apply to them.
- Preserve version annotations. `(v2.1.218+)` on a claim is what lets the next reader decide
  whether it applies to them.

## Step 5 — Append to the verification log

Never edit a previous entry. Append a new dated block containing:

- date, CLI version, platform, method
- sources used, grouped by confidence tier
- **corrections this pass produced** — the section that matters most
- new surface worth acting on
- overlap discovered with shipped built-ins, if any — a feature that now does something the
  audit skill hand-rolls should be delegated to, and the skill trimmed
- known gaps carried forward or newly opened

## Step 6 — Report the diff, not the research

The deliverable is short: what changed, what it means for `/harness-audit`, and whether anything
previously recommended is now wrong. Do not restate what stayed the same.

If a correction invalidates advice the user has already applied somewhere, say so plainly and
name the fix. That is the single most valuable output this skill produces.

## Files this skill owns

```
ResearchClub/agent-harness-configuration/claude-code-reference.md
ResearchClub/agent-harness-configuration/cross-agent-portability.md
ResearchClub/agent-harness-configuration/verification-log.md      (append-only)
skills/harness-audit/references/claude-code.md
skills/harness-audit/references/cross-agent.md
```

`extension-model.md` and `heuristics.md` are reasoning, not mechanics — change them only when a
source contradicts the reasoning itself, not merely when a version bumps.

After updating the source copies, re-run `skills/install.sh` so the installed copies match, and
say that you did.
