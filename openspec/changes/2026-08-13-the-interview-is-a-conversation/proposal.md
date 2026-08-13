# The interview is a conversation, not a form

## Why

**The exploration interview regressed to a quiz, and the charter that forbids exactly that could not
stop it.** From the operator, comparing it to the skill it replaced: *"I liked the aw-explore skill
better. Now it just ask hard questions with limited amount of answers and does not show the
architecture etc. Seems like less interactive. It just called ask user a bunch of times."*

The observation is exact. In `run-93ec79be` the agent made three `ask_user` calls — nine questions,
every one multiple-choice with two to four canned options — and asked the operator **no open
question at all**, showed no sketch, and laid out no alternatives in prose.

**The craft is not missing.** `hub/hub/data/charters/spec.md` carries 157 lines harvested from the
deleted skills, including:

> *"Never run this as a questionnaire. A fixed list of questions produces a fixed set of answers and
> misses the thing the operator would have volunteered. Follow what they tell you."*

and sections on open-threaded interviewing, on laying out options with what each makes easier and
harder, and on when a sketch earns its place.

**The mechanism overrides the craft.** Two things the charter cannot outrank:

1. The code-owned floor says *"use `ask_user` for anything that changes scope."* In an exploration,
   everything changes scope, so this reads as "ask through the tool, always".
2. `ask_user` **is** a questionnaire by construction: one to four questions, each requiring two to
   eight canned options, and its own description states *"There is no way to ask without options."*
   It also blocks the turn.

So the charter says do not run a questionnaire while the floor mandates the only sanctioned way to
ask, and that way can only be a questionnaire. This is the same failure shape as
`2026-08-13-the-hubs-procedure-outranks-an-installed-one`: a specific mechanism beats general prose
guidance, every time.

**The old skill was not better because it was a skill.** It was better because the agent asked *in
its reply* and the operator answered *in the composer*. That is a conversation, and the operator can
volunteer the thing nobody asked about. `ask_user` replaced it with a modal form that can only
collect answers to questions already thought of — which is precisely what the charter warns produces
"a fixed set of answers".

## What Changes

- **Prose is the default way to ask during exploration.** The floor directs the agent to interview in
  its reply: open questions, alternatives laid out with what each makes easier and harder, and what
  it found in the code.
- **`ask_user` is reserved for a real fork** — a decision with genuine alternatives where continuing
  without the answer would waste work. It blocks the turn, and that cost should buy something.
- **Sketching moves into the floor.** The charter already says when a diagram earns its place, but
  the charter is optional by decision and the floor is not. A project with no charter bound should
  still get a workflow sketch rather than a wall of prose.
- **`ask_user`'s description says what it is for and what it costs**, so "there is no way to ask
  without options" reads as a property of a decision tool rather than as the shape all asking takes.

## Capabilities

### Modified Capabilities

- `spec-document-authority`: the exploring phase's stated duty becomes conversational interviewing,
  with the blocking question tool reserved for decisions, and sketching named in the floor rather
  than left to an optional charter.

## Impact

**Behaviour** — the `exploring` entry of `SPEC_PHASE_DUTIES`, and the `ask_user` entry of the tool
surface. Both are generated context, rebuilt every turn.

**Not changed** — `ask_user` itself. Its schema, its blocking behaviour, its option requirement and
its batching are all untouched; what changes is when an agent is told to reach for it.

**No migration, no schema, no UI.**

## Non-Goals

- **Not making `ask_user` options optional.** The operator considered it and chose otherwise: a
  question with no alternatives is one the agent should be asking in prose, and loosening the tool
  would blur the line this change is drawing.
- **Not reinstating the skills.** Codex reads skills only from `~/.codex/skills`, which is global
  rather than per-project, so installing them into a project folder would reach Claude and never
  Codex — the exact runner-specific delivery failure that removed them. Today also showed the other
  edge: globally installed skills fire in every project whether or not they apply.
- **Not writing per-project `AGENTS.md` / `CLAUDE.md`.** Portable across both runners, unlike skills,
  but static — it goes stale while turn context is rebuilt every turn. Worth revisiting only if turn
  context proves insufficient.
- **Not changing the charter.** It already says all of this. The change is making the floor stop
  contradicting it.
- **Not weakening the obligation to interview.** Interviewing before writing stays a requirement.
  Only the medium changes.
