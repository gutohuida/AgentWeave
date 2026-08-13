# The Hub's specification procedure outranks whatever else is installed

## Why

**An agent given the Hub's specification procedure announced it was using a different one, and did.**
Observed on a live run (`run-3bf5d318`, 2026-08-13): the operator typed *"I would like to create a
budget web app for my home and my usage"* and the agent's first words were *"I'm going to use the
OpenSpec proposal workflow to turn this into a concrete, build-ready feature set."* It then shelled
around the project looking for an OpenSpec change to extend.

**Everything the Hub controls was correct.** The queue entry carried
`spec_document = spec/changes/i-would-like-to-create-a-budget-web-app.../spec.html`, so the document
was attached to the first message. The delivered context file carried the phase block — `Phase:
**exploring**`, the duty to interview, `submit_spec_document`, and the statement that the agent
cannot propose or approve. The agent had read it: an earlier run in the same project said *"this
workspace is a specification interview, not an implementation workspace… I won't invent product
scope"* and called `ask_user`.

**The cause was a competing procedure installed on the machine.** `~/.codex/skills/` held five
OpenSpec skills, `openspec-propose` among them, whose description reads *"Use when the user wants to
quickly describe what they want to build and get a complete proposal…"* — a near-exact match for
what the operator typed. A skill whose trigger matches the user's own phrasing is evaluated against
that phrasing; the Hub's block is a paragraph of standing context. The skill won.

This is not a contaminated-machine story to be waved away. OpenSpec is a widely installed tool, its
skills install globally per runner, and **AgentWeave has no reach into `~/.codex/` or
`~/.claude/`.** The one lever the Hub has is what it says in the turn context — and what it says
today is only what to *do*:

> Write the document with `submit_spec_document`. Never write specification HTML yourself.

There is no sentence saying that another specification workflow does not apply here. The block
answers "how do I write it?" and never answers "should I be using my own workflow instead?", which
is the question a matching skill description has already answered by the time the agent reads it.

The premise of `2026-08-12-hub-owns-the-spec-document` was that a procedure delivered in turn context
reaches every runner, which is why the `aw-spec-*` skills could be deleted. That premise holds for
*delivery*. It does not hold for *precedence*, and precedence was never stated.

## What Changes

- **The phase block states the negative.** The specification is authored through
  `submit_spec_document` and no other specification workflow, skill, command, or CLI applies to this
  document — including one installed on the machine and including one the agent has used before.
- **It says what to do with the competing thing rather than only forbidding it**: mention it to the
  operator instead of silently obeying it. An agent told only "do not" has nowhere to put the fact
  that it found something.
- **Nothing is scanned for, detected, or disabled.** The Hub does not look in `~/.codex/` or
  `~/.claude/`, does not enumerate skills, and does not pass a flag to suppress them. It states
  precedence in the one place it owns.

## Capabilities

### Modified Capabilities

- `spec-document-authority`: the procedure floor delivered in turn context gains precedence over any
  other specification procedure available to the agent, stated rather than assumed.

## Impact

**Behaviour** — three sentences of the `### Open specification document` block in
`_render_hub_agent_context`. No API, schema, or UI change.

**Cost** — the block grows by roughly 60 words on turns where a document is open. It is absent
entirely when none is.

**No migration.** No stored state.

## Non-Goals

- **Not detecting installed skills.** Reading `~/.codex/skills` or `~/.claude/skills` would make the
  Hub depend on the private layout of two other tools, and would be wrong the moment either changes.
  It also could not cover a third runner.
- **Not disabling the runner's skills.** Even where a flag exists, suppressing a tool the operator
  installed, without being asked, is not the Hub's call.
- **Not claiming this makes it impossible.** A stated precedence is an instruction, and instructions
  can lose to a well-matched trigger. This raises the odds and gives the agent the sentence it needs;
  it is not a guarantee, and the change should not be read as one.
- **Not touching the charter.** The charter carries interviewing craft and is optional by decision
  (`2026-08-12-hub-owns-the-spec-document`, D9/12.3). Precedence is load-bearing and belongs in the
  code-owned floor, which ships whether or not a charter is bound.
- **Not addressing the operator's own machine.** The five OpenSpec skills were moved aside by hand,
  which is the operator's to undo. This change is about the next user, who will not know to look.
