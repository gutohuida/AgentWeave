# Tasks — The interview is a conversation, not a form

Wording in two generated strings. The work was the diagnosis; the risk is that prose guidance is
what already lost twice today, so section 5 is the only place this is settled.

## 1. Establish the cause before rewording anything

- [x] 1.1 Confirm the craft is present rather than missing, so this is not a case for restoring the
      skills' content. `hub/hub/data/charters/spec.md` is 157 lines and carries *"Never run this as
      a questionnaire… Follow what they tell you"*, open-threaded interviewing, laying out options
      with what each makes easier and harder, and a section on when a sketch earns its place.
- [x] 1.2 Confirm the floor contradicts it. `SPEC_PHASE_DUTIES["exploring"]` said *"use `ask_user`
      for anything that changes scope"* — and in an exploration everything changes scope.
- [x] 1.3 Confirm the tool cannot produce a conversation. Its own description: 1–4 questions, each
      requiring 2–8 options, *"There is no way to ask without options"*, and it blocks the turn.
- [x] 1.4 Confirm the observed behaviour matches. `run-93ec79be`: three `ask_user` calls, nine
      questions, every one multiple-choice, **zero** open questions in prose, no sketch.
- [x] 1.5 Establish why per-project skills do not solve it. Codex reads skills from `~/.codex/skills`
      only — global, not per-project — so a project-folder install reaches Claude and never Codex,
      which is the delivery failure that removed them. Confirmed today from the other side too: the
      global OpenSpec skills fired in a project that had nothing to do with them.

## 2. The floor (D1, D2, D4)

- [x] 2.1 Replace *"use `ask_user` for anything that changes scope"* with a direction to interview in
      the reply: questions written out, directions side by side with what each makes easier and
      harder, what reading the code established, then end the turn.
- [x] 2.2 Reserve `ask_user` for a genuine fork, and say that it blocks the turn — so the cost is
      visible where the choice is made.
- [x] 2.3 Invite a sketch in the floor, so it survives a project with no charter bound (D2).
- [x] 2.4 Leave the obligation untouched: interview before writing, ground claims in the codebase,
      implement nothing. Only the medium changes (D4).

## 3. The tool description (D3)

- [x] 3.1 Rewrite the `ask_user` entry as a decision tool: what it is for, that it blocks, and that
      an open question belongs in the reply. *"There is no way to ask without options"* otherwise
      reads as a fact about asking rather than about this tool.
- [x] 3.2 **Found while checking 3.1 and not in the original plan.** The entry's continuation still
      said *"if the decision feels open, offer the answers you consider most likely"* — an explicit
      instruction to manufacture options for a question that has none, which is the mechanism that
      turns an interview into a quiz. Rewritten: the options requirement is now framed as the signal
      that such a question does not belong in this tool. The batching guidance in the same paragraph
      (*"Ask everything you need in one call"*) is unchanged and was verified still present.

## 4. Tests — agent-verifiable

**What these can show is that the guidance is delivered and no longer self-contradictory.** Whether
an agent interviews conversationally because of it is 5.1.

All in `hub/tests/test_exploring_interview_medium.py`.

- [x] 4.1 The exploring floor directs asking in the reply, and no longer tells the agent to route
      everything through `ask_user`. Pinned as an **absence** of *"anything that changes scope"* —
      the failure was not a missing instruction but a binding one pointing the wrong way, so the
      test has to assert the wrong instruction is gone rather than that a right one exists.
- [x] 4.2 The floor reserves `ask_user` for a fork and says it blocks.
- [x] 4.3 The floor invites a sketch, with no charter bound.
- [x] 4.4 The obligation to interview, to ground claims, and not to implement is still present.
      This change would be a regression if it read as permission to ask less.
- [x] 4.5 The tool surface's `ask_user` entry describes it as a decision tool. The existing
      constrained-values and coverage tests must keep passing unchanged. They did.
- [x] 4.6 `pytest hub/tests/ -q` and `pytest tests/ -q` run separately.
- [x] 4.7 `ruff check hub/ src/`, `black` on every file touched.
- [x] 4.8 `npx openspec validate --changes --strict` and `--specs --strict`.

## 5. Verification — human-only

- [x] 5.1 **Run an exploration and compare it to what the skill used to do.** Does the agent ask in
      prose, lay out alternatives, and show a sketch? Does it feel like a conversation? This is the
      whole change and no test reaches it.
      **Accepted by the operator, 2026-08-16**, on the live evidence recorded in `.claude/autonomous/2026-08-15-judgement-evidence.md` — run id, tool-call order and cost for each.
- [x] 5.2 **Does it still stop?** A prose question does not block the way `ask_user` does. Watch for
      an agent that asks three good questions and then answers them itself in the same turn. If that
      happens the floor needs an explicit stop, not a return to the form (design Risks).
      **Accepted by the operator, 2026-08-16**, on the live evidence recorded in `.claude/autonomous/2026-08-15-judgement-evidence.md` — run id, tool-call order and cost for each.
- [x] 5.3 Does `ask_user` still get used where it should — a real fork — rather than disappearing
      entirely? Losing it would be its own regression.
      **Accepted by the operator, 2026-08-16**, on the live evidence recorded in `.claude/autonomous/2026-08-15-judgement-evidence.md` — run id, tool-call order and cost for each.
- [x] 5.4 With no charter bound, is the interview still recognisable? That is what the floor is for.
      **Accepted by the operator, 2026-08-16**, on the live evidence recorded in `.claude/autonomous/2026-08-15-judgement-evidence.md` — run id, tool-call order and cost for each.
- [ ] 5.5 Compare against `aw-spec-explore` directly if you still have it, since that is the bar you
      named.
      **WAIVED for archiving, 2026-08-17 (autonomous N6).**
      `.claude/autonomous/2026-08-15-judgement-evidence.md` § this change, 5.5: answerable only
      indirectly — the skill was deleted along with the rest of the CLI messaging/local-role
      subsystem, so a literal side-by-side is no longer possible. The nearest comparison (old
      skill-driven run vs. new charter+floor run) is already written up there and in this change's
      own task 1.4. No further evidence can be gathered unattended; a literal `aw-spec-explore`
      re-run cannot happen because the artefact being compared against no longer exists.

## 6. User test guide

1. **Start an exploration and describe something half-formed.** The agent should reply with
   questions in prose, several directions with trade-offs, and what it found in the code — not a
   multiple-choice panel.
2. **Answer in the composer, in your own words.** Say something it did not ask about. That is the
   thing the form could not have collected, and the reason for this change.
3. **Expect a sketch** where a flow or a boundary is involved — a few lines of text, not a diagram
   for its own sake.
4. **Watch for a real fork.** When there genuinely are two ways and it cannot continue, it should
   still use the structured panel. If it never does, it has over-corrected.
5. **Watch that it waits.** If it asks and then answers itself in the same turn, tell me — the fix
   is a stronger stop, not going back to the form.
