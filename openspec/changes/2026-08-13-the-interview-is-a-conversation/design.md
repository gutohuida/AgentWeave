# Design — The interview is a conversation, not a form

## Context

Three statements reach the agent about how to ask, and they do not agree.

| source | says | binding? |
|---|---|---|
| charter `spec.md` | *"Never run this as a questionnaire… Follow what they tell you."* | optional — a charter may not be bound |
| floor `SPEC_PHASE_DUTIES["exploring"]` | *"use `ask_user` for anything that changes scope"* | always |
| tool surface, `ask_user` | *"There is no way to ask without options."* | always |

The two that always ship point at a tool that can only produce a form. The one that asks for a
conversation is the one that may be absent. The observed behaviour follows the binding pair.

## Decisions

### D1 — Prose is the default medium; the tool is for a fork

The floor directs the agent to interview in its reply, and reserves `ask_user` for a decision with
genuine alternatives that it cannot proceed past.

The reason is not stylistic. A structured question tool can only collect answers to questions the
agent already thought of. The value of an exploration is disproportionately in what the operator
volunteers — the constraint nobody asked about, the workflow detail that changes the shape — and
that arrives only when there is somewhere to say it. The composer is that place; a radio group is
not.

It also restores the turn shape the skills had, which is what the operator is comparing against: ask
in the reply, end the turn, operator answers in the composer, next turn continues. Nothing new is
needed to support it — that is how every other conversation already works.

**Rejected: making `ask_user` options optional.** Put to the operator, who chose otherwise. A
question with no alternatives is one that belongs in prose, and loosening the tool would blur the
line rather than draw it. It would also keep every question blocking and modal, which is the half of
the problem that has nothing to do with options.

**Rejected: reinstating the skills per project.** Codex reads skills from `~/.codex/skills` only —
global, not per-project — so a project-folder install reaches Claude and never Codex. That is the
runner-specific delivery failure that removed them. Today demonstrated the converse too: globally
installed skills fire in every project whether they apply or not.

**Rejected: per-project `AGENTS.md` / `CLAUDE.md`.** Genuinely portable, unlike skills. But static:
it goes stale, while turn context is rebuilt every turn from live state. Worth revisiting only if
turn context proves insufficient, which this change is a test of.

### D2 — Sketching goes in the floor, not the charter

The charter's "When a sketch helps" section is good and stays. The floor gains the invitation because
the floor is what always ships.

This is the same reasoning as `12.2` in `2026-08-12-hub-owns-the-spec-document`: the charter carries
the *skill*, the floor carries the *obligation*, and anything load-bearing in an optional layer is
load-bearing only when someone remembers to bind it. A project with no charter should not get a wall
of prose where a four-line flow would do.

### D3 — Say what the tool costs, where the tool is described

`ask_user`'s entry gains that it blocks the turn and is for decisions. Left alone, *"There is no way
to ask without options"* reads as a statement about how asking works in general rather than about
what this particular tool is for — and an agent that has just been told to interview needs to know
which of the two mediums it is choosing between.

### D4 — The obligation to interview is untouched

Only the medium changes. "Interview before writing", "ground what you claim in the codebase", "do not
implement anything" all stay exactly as they are. This change would be a regression if it read as
permission to ask less.

## Risks / Trade-offs

- **Prose questions do not block, so an agent may ask and then answer itself.** The floor says
  interview before writing, but nothing enforces a pause the way `ask_user` does. Watch for an agent
  that asks three good questions and then proceeds on its own assumptions in the same turn — if that
  appears, the answer is a stronger stop in the floor, not a return to the form.
- **The operator loses the structured answer panel** for most questions, and with it the one-click
  answering. That is the trade: a click costs less than a conversation, and produces less.
- **This is prose guidance competing with an available mechanism**, which is the pattern that has
  lost twice today. The floor now points *away* from the tool rather than toward it, which is the
  strongest lever available short of changing the tool — and changing the tool was rejected. Whether
  it holds is 4.1, and only a live run answers it.

## Migration Plan

None. Generated context, rebuilt every turn.

## Open Questions

- **Does an agent interviewing in prose still stop and wait?** Unknown until observed. `ask_user`
  blocks; a reply does not. If agents start self-answering, the floor needs an explicit "end your
  turn after asking" and that is a wording change, not a mechanism change.
