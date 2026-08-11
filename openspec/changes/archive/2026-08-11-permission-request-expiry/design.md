# Design — A permission request never outlives the run that raised it

## Context

Two processes hold a view of one decision. The run, waiting inside `_ask_operator`, knows when it
stops waiting. The Hub, serving the card, knows what the operator clicked. Today only the second view
is ever written down, so when the first one changes the two silently disagree — and the operator is
shown the stale one as though it were live.

The constraint that produced the bug is real and does not go away: `mcp_server.py` is spawned
standalone and may import only stdlib plus fastmcp, so it has no database session. Everything it
knows reaches the Hub over HTTP or not at all. The Codex path has no such constraint, runs
in-process, and consequently got this right (`agent_trigger.py:1448-1452`).

There is a close precedent to follow and, importantly, to diverge from deliberately.
`2026-08-11-declining-a-question` faced the same shape — a request whose asker may no longer be
listening — and solved it by *deriving* `asker_waiting` from whether the asking run is still live,
defaulting to `True` when unknown, rather than storing it. D2 below says why the answer here is
different.

## Goals / Non-Goals

**Goals:**

- A permission request reaches a terminal status whenever the run stops waiting on it, by any route —
  timeout, kill, crash, or Hub restart.
- An operator is never shown a card for a decision that can no longer take effect.
- An operator who does hit the race is told, not silently ignored.
- The operator learns that an agent gave up waiting, rather than watching a card vanish.
- The route where the two views diverge is covered by a test that would have caught this.

**Non-Goals:**

- Changing the timeout, adding a re-ask path, altering the Codex path's behaviour, reworking the
  attention model, or adding a free-text reason. See the proposal.

## Decisions

### D1 — Two mechanisms, because either alone leaves the defect reachable

**The run reports** that its wait ended, and **the Hub sweeps** pending requests belonging to runs
that have ended. Both, not one.

Reporting alone is insufficient: a killed run, a crashed run, or a run whose Hub was briefly
unreachable never reports, and the row stays pending — the exact bug, in a narrower window. The
existing `_report_decision` docstring already establishes that reporting is best-effort and every
failure is swallowed, and that rule must hold here too: an unreachable Hub must never turn an
answered request into an unanswered one. A mechanism that is explicitly allowed to fail cannot be the
only mechanism.

Sweeping alone is sufficient for correctness but bad for the operator: the card would linger until
the run ended, which for a long turn could be many minutes after the agent moved on. The operator
would still be looking at a decision that no longer matters.

So: reporting makes it *prompt*, sweeping makes it *certain*. They are not redundant — they cover
different failure modes.

*Rejected: a periodic reaper over old pending rows.* Age is the wrong predicate. A request is not
stale because it is old; it is stale because nobody is waiting on it, and a long
`AW_DECISION_TIMEOUT` makes those two diverge. It also adds a background loop where the run lifecycle
already provides an exact event.

### D2 — Expiry is stored, unlike `asker_waiting`, which is derived

The declining-a-question change deliberately did *not* store whether the asker was still waiting,
because a stored flag goes stale at exactly the transition it describes. That reasoning is right
there and wrong here, and the difference is worth stating because a later reader will otherwise see
an inconsistency.

`asker_waiting` describes a *live, continuously changing* fact — is anyone listening right now —
used for **marking and sorting**. Deriving it per request is cheap and always current.

Expiry describes a **terminal event**: this wait ended, at this moment, and will never resume. That
is not a fact that goes stale; it is a fact that becomes true once. Storing it is what makes the
existing 409 guard work, what takes the row out of the pending filter, and what lets `decided_at`
distinguish an answer from a timeout — which `db/models.py:1157-1159` already says it should.

The model also already carries `"expired"` as a documented status value, so this stores nothing new.

**Where they agree:** both refuse to presume that silence means nobody is listening. The sweep keys
off a run having *definitely* ended, not off the absence of evidence that it is alive.

### D3 — A decision on a request nobody waits for is refused, not absorbed

The 409 guard already exists and already says the right thing. D1 and D2 make it reachable in the
timeout case; this decision extends it to the residual race — the operator clicking at t=119s while
the run gives up at t=120s.

The alternative is to accept the click and let it write `"allowed"`. That is what happens today, and
it is the worst option available: it produces a *false record that the operator authorised an action
that never occurred*. For a permission decision specifically, that record is the audit trail. A
denial that never happened and an approval that never took effect are not equivalent errors — the
second one misleads about authority.

This is the sharpest divergence from the question precedent. A stale question is **marked and sorted
out of the way**, because the cost of a stale question is wasted attention. A stale permission
request must be **refused**, because the cost of a stale approval is a false belief that an action
was authorised.

The race cannot be eliminated — two processes, one boundary — so the design goal is that whoever
loses it *finds out*.

### D4 — An expired card reads as expired before it goes away

A card that silently disappears is indistinguishable from a bug, and it withholds the one thing the
operator most needs: their agent stopped waiting and proceeded without them. That is actionable — it
is the signal to raise `AW_DECISION_TIMEOUT`, or to be at the screen next time.

An expired request therefore stays visible, marked, and no longer answerable, rather than being
filtered out the moment its status changes. This reuses the treatment the declining change built for
"no longer waiting" questions, which is the same operator-facing idea and should not look like a
second invention.

*Rejected: a toast.* The card is where the operator was already looking, and a toast is gone by the
time they come back from wherever they were during those two minutes — which is the whole reason the
request expired.

### D5 — The sweep runs at the run-end sites, not in the run's own teardown path

Both `agent_trigger.py:1270` and `:1656` already open a session, set `run.status` and `run.ended_at`,
and record usage. The sweep goes there, in the same transaction: a run whose status becomes terminal
has, by definition, stopped waiting on anything.

Doing it at both sites is a duplication risk, so it goes in one helper called from both rather than
being written twice — that is the shape that lets one site drift from the other, and the two sites
already differ enough (PTY versus appserver) to make that plausible.

`run_id` is already indexed on `permission_requests` and the model already carries a composite
`(project_id, status)` index, so this is a cheap targeted update, not a scan.

### D6 — The expiry endpoint is agent-facing and narrowly scoped

It lives beside the other `/agent-actions` routes and authenticates the same way, with run-bound
identity — never an agent name from a body or header. It may only move a row from `pending` to
`expired`, only for a request belonging to the calling run, and it is idempotent: expiring an already
terminal row succeeds without changing it, because the run may report after the sweep already ran.

It carries no reason and no operator-visible payload beyond the status change. The run is not
reporting a decision here — `_report_decision` already does that — it is reporting that it has
stopped listening.

## Risks / Trade-offs

- **The sweep expires a request the operator was about to answer** → that is the correct outcome, and
  D3 and D4 are what make it legible rather than silent. The run has ended; no answer can reach it.
- **Reporting and sweeping race each other** → both are idempotent guarded transitions from
  `pending`, so whichever lands first wins and the second is a no-op. D6 makes that explicit rather
  than incidental.
- **A best-effort report that fails leaves the card up until the run ends** → the accepted, designed
  gap between "prompt" and "certain". Bounded by the run's own lifetime rather than unbounded, which
  is the whole improvement.
- **An expired card that stays visible adds clutter** → it is one row per genuinely missed decision,
  and an operator missing decisions is something they should see accumulating, not something to hide.
- **Refusing a late click may read as the app being broken** → which is why D4 requires the card to
  say it expired *before* the operator can click it. The 409 is the backstop for the narrow race, not
  the primary way the operator learns.
- **The two run-end sites may not be the only places a run can end** → the tasks check this rather
  than assume it; if a third path exists, the helper is already the place to call from.
