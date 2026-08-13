# Design — The Hub's specification procedure outranks whatever else is installed

## Context

`2026-08-12-hub-owns-the-spec-document` moved the authoring procedure out of runner-specific skills
and into turn context, on the grounds that turn context reaches every runner while `.claude/skills/`
reaches one. That reasoning was about **delivery** and it was right.

What it did not state is **precedence**. The block tells the agent how to write the document. It
does not tell it that its own workflow does not apply here. Those are different claims, and only the
first was made.

The gap is only visible when a competing procedure exists, which is why it survived the change's own
verification: nothing installed one until the operator's `~/.codex/skills` did.

## Decisions

### D1 — State precedence; do not detect, disable, or enumerate

The Hub says the Hub's procedure is the one that applies. It does not look for competitors.

Detection would mean reading `~/.codex/skills/`, `~/.claude/skills/`, project `AGENTS.md`, and
whatever the next runner uses — private layouts belonging to other tools, wrong the moment any of
them changes, and unable to cover a runner nobody has added yet. It would also produce a worse
sentence: naming OpenSpec specifically dates the instruction and does nothing about the second tool.

**Rejected:** passing a runner flag to suppress skills. Even where one exists, turning off a tool the
operator installed, without being asked, is not the Hub's decision — and it would suppress skills
that have nothing to do with specifications.

### D2 — Say what to do with the competing procedure, not only that it is wrong

The block tells the agent to mention the other workflow to the operator rather than follow it.

A prohibition alone leaves an agent holding a fact with nowhere to put it: it found a workflow that
matches the request, it has been told not to use it, and the natural resolution is to use it quietly
or to argue. Routing it to the operator makes the discovery useful — and the operator is exactly who
should decide, since the tool is theirs.

### D3 — This belongs in the code-owned floor, not the charter

The floor ships whether or not a charter is bound (12.2, and D9/12.3 deliberately left the spec
charter unbound by default). A project with no charter is the case most exposed here — the agent has
mechanism and no judgement — so putting precedence in the charter would omit it exactly where it is
most needed.

### D4 — Scoped to the block that only appears with a document open

The sentences sit inside `if open_spec_path is not None` and `if phase`, so a turn with no
specification document is unchanged. The claim being made is about *this document*, and asserting
procedural precedence on turns that have nothing to do with specifications would be both untrue and
noise on every unrelated turn.

### D5 — Written as precedence, not as a blocklist

"No other specification workflow applies to this document" rather than "do not use OpenSpec". Naming
a product makes the instruction stale the moment a different one is installed, and invites the
reading that unnamed ones are fine. The rule is about which authority governs the document, and that
is the thing that generalises.

## Risks / Trade-offs

- **This is an instruction, and instructions lose to well-matched triggers.** A skill description
  matching the operator's phrasing is evaluated against that phrasing at the moment of the request;
  a paragraph of standing context is not. This makes the right behaviour *stated* rather than
  *guaranteed*, and the change must not be reported as having solved the problem. Whether it holds
  is 4.1, and only a live run can answer it.
- **Prohibitions can misfire.** An agent told no other specification workflow applies might decline
  to *read* an existing `openspec/` directory that is legitimate context about the project. D2's
  "mention it" phrasing is meant to keep discovery allowed while making adoption the operator's
  call; the wording is worth checking against a project that genuinely has one.
- **The block grows.** Roughly 60 words on every turn with a document open. Small against a
  200-line context, and absent when no document is open.

## Migration Plan

None. Text in generated context, rebuilt every turn — the next turn carries it.

## Open Questions

- **Does stating precedence actually beat a matched skill trigger?** Unknown, and not knowable from
  tests: an assertion that the sentence is present proves delivery, not obedience. The honest test is
  restoring the moved skills and running the flow again. Until that is done this change should be
  described as "states precedence", never as "prevents".
