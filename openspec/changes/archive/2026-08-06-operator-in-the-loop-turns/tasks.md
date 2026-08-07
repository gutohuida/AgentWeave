# Tasks — operator-in-the-loop turns

**DEFERRED 2026-08-06 by operator decision — do not start.** Finish
`2026-08-06-agent-messaging-delivery` and `2026-08-06-hub-composer-and-chrome-refinement` first.

**Blocked on** `2026-08-06-agent-messaging-delivery` sections 2 and 3. Sections 1-3 below need only
the Hub; sections 4-6 need the app-server client from that change.

## 1. Blocking questions — Hub side

- [ ] 1.1 Add a bounded wait for an answer, resolving as answered / declined / expired. Do not hold
      a database session for the wait's duration.
- [ ] 1.2 Add "declined" as a real operator action, distinct from leaving a question unanswered.
- [ ] 1.3 Make the waiting period configurable with a sane default; record how it was chosen.
- [ ] 1.4 Ensure an expired question stays visible as unanswered, and that answering it afterwards is
      not delivered into a turn that has continued.
- [ ] 1.5 Cap concurrent waits so many waiting agents cannot exhaust the Hub.
- [ ] 1.6 Unit tests: answered, declined, expired, answered-after-expiry, cap reached.

## 2. Blocking questions — tool surface

- [ ] 2.1 Make `ask_user` with `blocking` wait and return the answer, declination, or expiry as its
      result.
- [ ] 2.2 Keep non-blocking `ask_user` behaviour byte-for-byte as it is today.
- [ ] 2.3 Ensure the MCP request timeout exceeds the Hub's waiting period, so an expiry surfaces as
      an expiry rather than a transport error. Verify against a real provider, not in theory.
- [ ] 2.4 `get_answer` keeps working for agents that poll.
- [ ] 2.5 Unit tests: blocking returns the answer; declination is distinguishable; expiry is
      distinguishable; non-blocking is unchanged.
- [ ] 2.6 **Live:** a real codex agent calls blocking `ask_user`, the operator answers in the UI, and
      the agent continues in the same turn using the answer.

## 3. Questions in the conversation

- [ ] 3.1 Render a pending question in its conversation, in turn sequence, answerable in place.
- [ ] 3.2 Show the agent as waiting on the operator, not working — in the conversation and in the
      rail.
- [ ] 3.3 Settle Decision 4: new status value vs flag alongside `running`. Check every existing
      status consumer before choosing. Record the decision.
- [ ] 3.4 Keep the question and its answer in the conversation record after resolution.
- [ ] 3.5 Leave the existing questions pages working and reachable.
- [ ] 3.6 Unit tests: pending renders in-conversation; answering in place resolves it; waiting state
      is distinct from running; resolved requests persist; existing pages unaffected.

## 4. Escalating a refused action

- [ ] 4.1 In the app-server approval handler, add the path where a would-be refusal is put to the
      operator instead, carrying the action and the provider's stated reason.
- [ ] 4.2 Never escalate something that would be granted anyway.
- [ ] 4.3 Bounded wait; expiry refuses.
- [ ] 4.4 An allowance authorises exactly one action — no standing grant, no change to the run's
      protections, next request asked again.
- [ ] 4.5 Do not use the protocol's decision-persistence (`_meta.persist`).
- [ ] 4.6 Guarantee that any failure in this path refuses and answers, never leaves the request
      unanswered — an unanswered request hangs the turn (see the depended-on change's implications
      §2).
- [ ] 4.7 Unit tests: escalation offered; allow proceeds once; second request asked again; expiry
      refuses; handler exception still refuses and answers; grantable action not escalated.

## 5. Escalation in the UI

- [ ] 5.1 Render a pending escalation in the conversation with the action and the reason, allow and
      refuse both available. Reference: t3code `ComposerPendingApprovalPanel.tsx`,
      `ComposerPendingApprovalActions.tsx`.
- [ ] 5.2 Make an escalation visibly different from a durable question — one expires into refusal and
      cannot be answered late; the other persists.
- [ ] 5.3 Show it as expired and unanswerable once the wait has passed.
- [ ] 5.4 Unit tests: renders with action and reason; allow and refuse; expired state; not confusable
      with a question.

## 6. Steering and interrupting

- [ ] 6.1 Report per-runner whether redirection is supported, following the launchability pattern.
- [ ] 6.2 Wire `turn/steer` and `turn/interrupt` for runners that support it.
- [ ] 6.3 Offer the controls only where supported.
- [ ] 6.4 Preserve prior work on both redirect and stop.
- [ ] 6.5 Record both as operator actions on the run timeline.
- [ ] 6.6 Unit tests: supported/unsupported reporting; steer preserves work; interrupt preserves
      work; both recorded.
- [ ] 6.7 **Live:** steer a running codex agent mid-turn and confirm it changes course without
      losing what it had done.

## 7. Attribution

- [ ] 7.1 Record every question and answer against its run and agent, with both timestamps.
- [ ] 7.2 Record an allowed escalation as an operator allowance naming the action — never as
      something the run's own protections permitted.
- [ ] 7.3 Unit tests for both records.

## 8. Verification

- [ ] 8.1 `pytest hub/tests -q` — full pass, count recorded.
- [ ] 8.2 `npm test -- --run` and `npx tsc --noEmit` in `hub/ui` — clean.
- [ ] 8.3 `npm run build`, refresh `hub/hub/static/ui`, `test_ui_staleness.py` passes.
- [ ] 8.4 **Live:** blocking question answered from inside the conversation; agent continues in the
      same turn.
- [ ] 8.5 **Live:** a sandboxed agent attempts a write outside its workspace, the operator is asked,
      allows it once, and the *next* attempt is asked again.
- [ ] 8.6 **Live:** the same attempt, left unanswered, is refused.
- [ ] 8.7 **Live:** a claude agent degrades correctly — no escalation offered, no broken prompt, and
      messaging still works.
- [ ] 8.8 `openspec validate 2026-08-06-operator-in-the-loop-turns --strict` — clean.
