# Exploration — Architecture proposals for AgentWeave (2026-08-17)

**Status:** Thinking, not a decision. Written at the operator's request this session: "start
proposing ideas base on the market research and start thinking of architectures for improving
agentweave." No code in this document.

**Starting point.** `2026-08-15-where-agentweave-fits.md` (corrected today — see its 2026-08-17
addendum in §2) narrowed AgentWeave's claim to three infrastructure properties Claude Code's
in-session orchestration and the small self-hosted peer group do not have: **durability across
sessions**, **addressable, bound identity**, and **an operator-facing UI**. This document does not
re-survey the market. It takes that narrowed claim as given and asks what to build next to make it
truer, in a world where two of tonight's own changes have already moved it forward:

- `2026-08-16-the-corpus-keeps-what-shipped` (N2) — a spec document now has somewhere to end up other
  than `approved` forever: `archived` for a finished change, `current` (kind `capability`, no
  transitions) for a living record of what a capability actually does today, filled in by an explicit
  operator-authored merge.
- `2026-08-16-many-named-loops` (N3) — `Loop` wraps an `AIJob` with a purpose, a stop condition, and a
  queue that is literally the `Task` board scoped by `loop_id`. Several loops can run at once, each
  addressable, each legible after the fact through its own conversations and firings.

Both are model + API + UI only — nothing spawns or re-enters a loop yet, and nothing yet reads a
capability document to check the product still matches it. That gap between "the record now exists"
and "something acts on the record" is where the three proposals below live.

## Proposal A — Loops as a fourth roster citizen, not just infrastructure

**The gap.** An `Agent` today is a roster identity — named, bound to a runner and a charter,
addressable across runs, visible on the Agents page. A `Loop` (N3) is also named, also bound to
recurring execution, also produces a queue and a history — but it has no charter, is not on any
roster page, and nothing about its design gives it the second-class-citizen treatment a reason to
stay second-class. `Loop.purpose` (`design.md` D1) is a free-text field with nowhere to be read except
by opening the loop directly; there is no "what is this loop for and what is it allowed to touch" the
way a charter states that for an agent.

**The proposal.** Give a `Loop` the same three-part shape an `Agent` has: bind it to a charter (what
it's for, what it should and shouldn't do — reusing the exact charter mechanism that already injects
into canonical turn context) and let it show up alongside agents in whatever roster surface the
operator watches, distinguished by a badge ("recurring" vs "on demand") rather than by living on a
separate page. Concretely: `Loop.charter_id`, nullable FK, same undroppable-column reasoning N3 and
N2b already established applies (index, no table-level CHECK naming it). The Agents page becomes a
roster page; a `Loop` row renders with its cadence and last-fired time where an `Agent` row renders
idle/active.

**Why now, not before N2/N3.** Before tonight, there was one `AIJob` model with a message string and
a cron — nothing charter-shaped to bind. N3 gave loops a `purpose`; this proposal is the next half-step
of the same idea, not a new one. It also directly answers the operator's second N3 note ("we can have
loops for multiple things... shorter dev loops... longer loops that will do security scans") — a
roster the operator actually looks at, where a security-scan loop sits next to the agents it might file
tasks for, makes "many named loops" legible as a fleet rather than as rows in a jobs table nobody
opens.

**Cost.** One migration column, one FK, one UI badge and roster-page filter. No new concept —
`Charter` and its binding UI already exist and are reused verbatim. Genuinely small; the risk is
scope creep into "loops should also get their own charter *editing* affordances distinct from an
agent's," which this proposal explicitly does not ask for — reuse the existing charter CRUD, do not
fork it.

## Proposal B — A spec-drift loop: capability documents become a thing something checks, not just a
thing something writes

**The gap.** N2 gives the corpus a `current` document per capability — content an operator explicitly
merged in. Nothing re-reads it. A capability document can go stale the same day it is merged if the
next change to that capability lands through a different, unrelated proposal that nobody thinks to
merge back. This is exactly the risk `2026-08-16-a-corpus-at-scale.md` (N1) named for navigability —
except staleness is worse than bad navigation, because a stale capability document is not merely hard
to find, it is actively wrong, and "the spec should still be useful" (the operator's own acceptance
criterion for the corpus, recorded in N1) fails outright if the corpus lies.

**The proposal.** A **named loop whose purpose is verification, not authorship**: its queue (Task
board scoped to `loop_id`) is one task per capability document, each task asking "does this
document's requirements still match the shipped behaviour," and its charter (Proposal A) states the
check discipline — read the capability document, read the code paths its scenarios name, record
evidence for divergence via `record_evidence` (already wired to tasks), and stop short of editing the
document itself, because content changes to a `kind='capability'` document stay an operator-authored
merge (N2's own rule) — the loop's job is to *surface* drift, not silently resolve it. This is the
same operator-in-the-loop shape the product already applies to permissions and questions, pointed at
the corpus instead of at a running agent.

**Why this is the governance-shaped opportunity, not a detour into it.**
`2026-08-15-where-agentweave-fits.md` §1 found governance demand described as *"demonstrable human
oversight that is trained, measurable, and provable"* and *"who authorized this / what context did the
agent have / what did it decide"* — aimed at enterprise buyers AgentWeave doesn't target today. A
spec-drift loop does not chase that buyer. It is the same audit shape turned inward: every firing is a
`Conversation` with output logs and cost accounting (N3's `JobRun.conversation_id`), every finding is
`Evidence` against a `Task` that names the capability document it checked, and the corpus's own
`archived` changes (N2) give a "what shipped and when" trail to check divergence against. If governance
demand grows into AgentWeave's actual market later, this is infrastructure that was worth having
anyway, for the same reason a test suite is worth having even if nobody outside the team ever asks to
see it pass.

**Cost and risk.** No schema changes beyond Proposal A's — this composes entirely from N2 + N3 + the
existing evidence/task machinery. The real risk is a verification loop that hallucinates drift
findings on capability documents that are actually fine, spending operator attention on noise; the
charter must be conservative (record evidence only on a concrete, named divergence, not "this seems
possibly related"), and the loop should start on a small number of capabilities, not all 30 at once.

## Proposal C — Retire `STATE.json`: run the autonomous session itself as a Loop

**The gap, stated plainly.** `2026-08-15-where-agentweave-fits.md`'s honest-read section already
named this: *"the loop that runs this very session is not in the product."* Tonight's own queue
(`.claude/autonomous/STATE.json`) is an ordered list with per-item status, a `current` pointer, a
narrative log, `decisions_for_user`, a heartbeat, and a stop condition — and N3's `design.md` D1
literally lists these as the four things a `Loop` adds to a plain `AIJob`, because `STATE.json` was
its explicit model. The gap N3 closed is that the *Hub* can now represent that shape. The gap this
proposal closes is that the *autonomous session infrastructure* (this very run) still doesn't use it.

**Why this belongs in the "next architecture" conversation and not just "go implement N3's own
backlog."** It is the sharpest possible test of the durability claim `where-agentweave-fits.md`
identifies as the actual remaining moat. Right now the claim is asserted from the Hub's schema; a
`STATE.json`-driven session, including this one, is proof by counterexample that the tool best
positioned to demonstrate durable, addressable, cross-session state does not yet trust its own
product to hold that state. Closing it is the difference between "AgentWeave models durable
multi-session work" as a database capability and as a *demonstrated* one, dogfooded on the very
process writing this document.

**Shape, at the level this exploration should commit to (implementation is a future change, not
this one).** A `Loop` whose `Task` queue holds this run's actual queue items (N1 through N6, right
now), whose `Loop.purpose` is the paragraph currently living at `STATE.json.purpose`, whose
`stop_at`/`stop_when_queue_empties` are literally the same two fields already in both places by name,
and whose narrative log is the loop's own conversations/output rather than a hand-appended markdown
file. Two things this proposal explicitly does NOT claim to solve, because CLAUDE.md and tonight's own
`limits` already ruled them out of scope: the Hub does not spawn or re-enter a coding-agent iteration
today (N3's scope ceiling was model+API+visibility only, and this proposal inherits that ceiling — it
describes what the *state* would look like inside the Hub, not a new execution path that drives Claude
Code from inside a `Loop` firing), and this repository's own governance rule stands — the Hub the
autonomous session would use must stay the **trial** Hub, never the one being edited, for exactly the
reason CLAUDE.md gives: editing the Hub restarts the process orchestrating the work.

**What actually blocks this today, so a future session doesn't have to rediscover it.** The
autonomous session's real unit of work is "drive Claude Code through an openspec round or an
implementation slice," which has no equivalent to `AIJob`'s "fire an agent through the Hub's own
execution path" — the Hub fires *Hub-registered agents* against *Hub-managed runners*, and this
autonomous session is neither; it is a Claude Code process started outside the Hub entirely, with the
Hub only ever a thing it happens to also be developing. Representing the *queue and narrative* in a
`Loop`/`Task` is straightforward reuse of N3. Representing the *firing* — this process's own turns —
is not, and forcing it in prematurely would be the "build the thing that would drive it" N3's scope
ceiling explicitly withheld. The honest scope for a first cut: mirror the queue and log into a `Loop`
that a human (or a future session) updates the same way `STATE.json` is updated now, gaining the UI and
durability without yet gaining automatic firing. That is a smaller, safer slice than it sounds, and it
is the one that proves the moat rather than just asserting it.

## What NOT to build now

- **Do not give loops their own execution path independent of `AIJob`.** N3 deliberately left
  `AIJob`'s existing scheduler-fire path untouched and added `Loop` beside it. Nothing above needs a
  second execution mechanism; Proposal C's firing gap is a reason to *wait*, not a reason to build
  around N3's ceiling.
- **Do not let Proposal B's verification loop write capability documents directly**, even under an
  "if confidence is high" exception. N2's authored-merge rule exists precisely so an agent doesn't
  become the sole author of the corpus's current-behaviour record; a verification loop that could edit
  around that rule would be the same category of mistake N3's own design memo warned against
  ("re-implements questions, runs, and tasks under new names").
- **Do not scope Proposal A to "loops get a full second charter-editing UI."** Reuse what exists.

## Recommendation and sequencing

Proposal A is the cheapest and most self-contained — one column, one roster-page change — and it
makes Proposal B legible immediately (a security-scan loop sitting on the same page as the agents it
might hand work to, distinguished at a glance). Do A first if any of these three get picked up.
Proposal B is the one that turns tonight's N2 from "the corpus has somewhere to put current behaviour"
into "the corpus stays true," which is the actual promise `current` phase implies but does not by
itself keep — it is the highest-leverage next spec change. Proposal C is the most consequential
long-term but the least ready to spec tonight; its value is proving the durability claim on the
product's own development process, and its risk is scope creep into execution the operator has
twice now (N3's ceiling, this document's own "what not to build") kept out of tonight's build. Treat
it as the next exploration to deepen, not the next change to propose.

None of these are proposed as tonight's next queue item — this document is thinking, per the
operator's framing, not a build order. If the operator picks one to spec next, Proposal A is small
enough to fold into a single change; B and C each warrant their own exploration-before-proposal pass,
the same discipline N1 modeled for N2/N2b.
