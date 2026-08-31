# Exploration — Authority is the missing leg (2026-08-23)

**Status:** Not explored with the operator. Written by an outside contributor reading the code cold,
offered as a starting point rather than a conclusion. Nothing here is **DECIDED**; every §
ends with the question the operator would have to answer for it to become a change.

Line references were checked against `2588126e`. Where a claim is a measurement, the measurement is
given so the next reader can re-run it rather than trust it.

**The finding in one line:** the codebase has a considered position on *who an agent is* and a
considered position on *how an agent behaves*, and almost none on *what an agent may do*.

**Two proposals do not survive this document**, and saying so first is the point:

| Withdrawn | Where | Why |
|---|---|---|
| Put a capability grant on the `Charter` | §2 | `models.py:250-266` already refuses it, correctly |
| Ship a capability check that refuses | §5 | `ROADMAP.md`'s barrier rule is right, and `contract` rigor already solves it |

---

## 1. What is already built, and should not be touched

Reading this codebase for holes turns up fewer than expected. Recording what is solid first, because
a contributor who proposes work already done wastes the operator's time:

- **Identity.** Run tokens are server-derived from the `Run` row, never accepted from a body or
  header, and instance-pinned (`agent_auth.py:40-80`). The spawn scrubs `HUB_API_KEY`,
  `HUB_PROJECT_ID`, `DATABASE_URL` and `AW_BOOTSTRAP_API_KEY` from the child environment
  (`agent_trigger.py:587-600`), with the comment *"AW_RUN_TOKEN is the run's complete authority."*
- **The operator/agent wall.** `auth.py:89-92` prefix-gates on `aw_live_`, so a run token cannot
  satisfy `get_project` or `get_operator`. No agent-plane route reaches a mutating operator route.
- **Self-approval and self-acceptance.** `task_transition_service.py:135-160` compares *agent name*,
  not run id — and the comment at `:113-121` records that the run-id version forbade nothing. The
  evidence twin is `requirement_evidence.py:395-404`. Both refuse at the service, not in tool prose.
- **Charter-as-authority, refused.** `models.py:250-266`, twice.
- **The task lifecycle.** One chokepoint, no forced-move override, entry statuses guarded,
  `blocked` deliberately withheld from the tool enum (`mcp_server.py:207-213`).

This document proposes nothing in any of those areas.

---

## 2. The three legs, and which one is short

The `Agent` row and the `Charter` row between them answer two of the three questions a contract has
to answer:

```
   MISSION          Charter.content, injected into turn context        built
   RESPONSIBILITY   TaskTransition.policy_digest, /permission-         built
                    decisions, the evidence trail
   AUTHORITY        can_read_checkpoints, can_recall,                  three booleans
                    can_accept_evidence
```

The Authority leg is not absent — it is *started*, and the reasoning around it is better than the
coverage. `models.py:245-252` explains why checkpoint access and recall are two flags and not one:

> *"An agent that may read what a peer concluded need not be able to read everything that peer's
> tools ever printed, and one flag would make the narrower grant inexpressible."*

That is a person reasoning carefully about grant granularity. The observation of this document is
just that the reasoning has been applied three times and there are more than three things to reason
about.

**The measurement.** Of the 22 agent-callable `@mcp.tool()` functions in `mcp_server.py`, **14
mutate state with no per-agent grant of any kind**:

| Tool | Mutates | Grant required |
|---|---|---|
| `send_message` | message + **queues a peer's turn** (`messages.py:307`) | none — hop budget only |
| `create_task` | task row | none |
| `update_task` | status | none per-agent; `apply_transition` guards the edge |
| `ask_user` | question rows | none |
| `submit_checkpoint_notes` | checkpoint | none |
| `create_job` / `create_loop` / `toggle_job` / `run_job` | scheduled compute | project-wide `allow_agent_jobs` |
| `create_spec_document` / `submit_spec_document` / `rename_spec_document` | spec rows | none at `sketch` |
| `record_evidence` | evidence row | none (deliberate, and right — `:376-380`) |
| `request_agent` | **an `Agent` row** | template pre-approval + budget |
| `recall` | — | **`can_recall`** |
| `decide_evidence` | acceptance | **`can_accept_evidence`** |

Exactly three of the 32 routes in `agent_actions.py` consult an agent capability.

So an operator can withhold *"read another agent's checkpoints"* from one agent, and cannot withhold
*"schedule unattended recurring compute"* from that same agent. `allow_agent_jobs` (`jobs.py:40`) is
one boolean for every agent in the project alike.

**Not a hole in the design — a hole in the coverage.** Which is why the fix below is not a new
model.

> **For the operator:** is the three-boolean vocabulary intended to grow one column at a time, or was
> it always a placeholder for something with structure? This document assumes the latter. If it is
> the former, everything below is unwanted.

---

## 3. `agent_actions.py` has an identity chokepoint and no authority chokepoint

All 32 routes take `actor: AgentActor = Depends(get_agent_actor)`. That is a genuine chokepoint, and
it is what makes the identity story above hold.

But `get_agent_actor` answers *who is calling*, and never *what they may do*. Each capability check
lives wherever its domain module happened to put it — `checkpoint_access.py:46`,
`requirement_evidence.py:366`, `spec_rigor.py:87`, `jobs.py:40`. There is no shared dependency or
decorator through which a capability question passes.

Compare `apply_transition` (`task_transition_service.py:189-286`), which concentrates five separate
guards and says why (`:236-241`):

> *"so every caller (operator route, agent HTTP, the tool surface, jobs and the run-binding runtime
> move) is covered without knowing this exists"*

That sentence is the argument of this document, applied to a different plane. Adding a capability to
the agent plane today means finding the handler that owns it and editing that one — which is the
scattering `apply_transition` exists to prevent.

**The proposal is not a new pattern. It is this one, on the plane that does not have it yet.**

```
   TASK PLANE                        AGENT PLANE
   ──────────                        ───────────
   who    → Actor                    who    → AgentActor        (built)
   what   → apply_transition         what   → require(...)      (missing)
            5 guards, 1 seam                  1 seam
```

> **For the operator:** is `agent_actions.py` the right place for that seam, or does it belong lower,
> beside the services that already refuse — so that the tool surface and any future surface inherit
> it the way `apply_transition`'s callers do?

---

## 4. The spec already tries to say who may act, and the field is dead

`spec_payload.py:136-140` defines, on a declared task:

> `reviewer` — *"Agent name this task's completion should be reviewed by, **resolved against the
> roster when the task is claimed for review**. Optional: an author writing a document has no way to
> know which agents exist on the machine that will run it, so an unresolvable name is kept rather
> than refused — resolution falls back to whatever the reviewing mechanism does when none is named or
> none resolves."*

That description specifies a resolution step, a claim-time trigger, and a fallback. **None of the
three exists.** Grepping `reviewer` across `hub/hub/` returns this definition, the unrelated
`author_is_not_reviewer` identifier, and prose in comments — nothing else. There is no column, no
materialisation write, and no read in `task_transition_service.py`.

Being fair to the field: it is not careless. The fallback clause shows the author thinking about the
case where the name does not resolve. What is missing is the mechanism that would do the resolving —
so the field is not a bad design, it is an unbuilt one, and the description reads as though it were
built.

This matters more than its size. An operator writing `reviewer: security-agent` into a **`gate`**-rigor
document has every reason to believe it binds — `gate` is the rigor whose whole meaning is that
declarations are enforced rather than reported (`requirement_gate.py:242-244`). It does not bind.

Note this is *not* a contradiction of `spec_tasks.py:46-47` (*"who performs it is a roster decision a
specification has no business making"*). That comment refuses the spec **assigning** work. A reviewer
constraint is the opposite shape: it does not say who does the work, it says who may not sign it off.
`_guard_author_is_not_reviewer` already enforces exactly that kind of rule — a *separation*
constraint, not a roster one. The field's shape is legitimate; only its enforcement is absent.

Two honest options, and the wrong one is leaving it as it is:

1. **Enforce it** — materialise onto the task, read in `_guard_author_is_not_reviewer`, refuse where
   the actor is not the named reviewer. Small, and it makes one true sentence out of a field that is
   currently a false one.
2. **Delete it** — if the operator's position is that a spec may not constrain actors at all, then
   the field contradicts that position and should go.

> **For the operator:** which? This is the only place in the spec model where authority is even
> expressible, so the answer also settles whether §5 is allowed to exist.

---

## 5. What a capability policy would look like — and why it must not refuse on arrival

`ROADMAP.md` is unambiguous: *"The organising constraint is ease of use. Where a capability and a
barrier conflict, the barrier loses."*

Taken at face value that kills this document. It should not, and the reason is already in the
codebase.

**`spec_rigor` is the mechanism that dissolves the conflict.** `sketch`/`contract`/`gate`
(`spec_rigor.py:39-44`) is one declaration with three enforcement strengths. At `contract`,
`requirement_gate.py:244` puts an unmet requirement into `GateRefusal.reported`, and `refuses`
(`:83-85`) never inspects that list — it is recorded and the transition proceeds. The pattern is
already reused once outside the gate, at `spec_service.py:179-180`, where `contract` rigor turns an
agent's document write into a proposal rather than refusing it.

A capability policy shipped at **`contract` is not a barrier.** It records every call an agent made
that it would not have been granted, refuses nothing, and produces exactly the evidence an operator
needs to decide whether the grant is worth having. Promotion to `gate` is then a decision made on
data rather than on fear.

Shape, deliberately thin:

- **A project floor** — the capability set every agent in the project has.
- **A per-agent set** that may only **narrow** the floor, never widen it. Narrowing-only is what
  makes "an agent cannot expand its own authority" structural rather than checked; it is also what
  the three booleans already get for free, since `False` is a floor nothing can rise above.
- Written **only** through the operator-authenticated `PATCH /agents/{name}` that already owns
  `GRANT_FIELDS` (`agents.py:1808-1813`). No agent-plane route touches it.
- The three booleans become entries in that set rather than a parallel mechanism.

**On the policy format.** Microsoft's Agent Governance Toolkit (MIT) ships a JSON policy document for
exactly this decision — `allowedTools` / `blockedTools` / `defaultEffect` with `allow`/`deny`/`review`
effects, a `reason` string on every rule, and `denyOnPolicyError: true`. Those three effects already
exist here as `{"allow": True}`, `{"allow": False, "reason": ...}` and `_ask_operator(...)`, and
`denyOnPolicyError` is `_decide`'s own *"Anything unrecognised denies rather than allows."*
Borrowing the schema costs nothing, needs no dependency — it is `json` plus `re` — and means this
project does not design a policy language. AGT's Python distribution is **not** proposed: it pulls
pydantic, cryptography, pynacl, httpx and a dozen more, and `mcp_server.py` may import only stdlib
and fastmcp.

> **For the operator:** does the capability set live as a column on the `Agent` row — keeping
> "authority is on the Agent row and nowhere else" true, which is the invariant `models.py:250-252`
> defends — or in its own table? And is the project floor a `Project` column or a project setting?

---

## 6. The refusal has to teach — and exactly one thing it must not teach

A capability that only refuses makes agents worse. A model that receives a bare refusal retries the
same call in three different phrasings, then works around it, then reports success it did not have.
So the grant has to be legible to the agent holding it, in three places.

**This is not a new idea in this codebase.** `api/v1/agents.py:1262` already injects a briefing block
into turn context when `can_accept_evidence` is set — the agent is told, in prose, that it may decide
evidence. The loop below is that behaviour generalised from one boolean to the set.

1. **Ambient.** The resolved set rendered into turn context at session start. This is the
   highest-value part and it is not about refusals at all: an agent that knows it does not hold
   `job.schedule` never plans around a loop it cannot create.
2. **Reactive.** The refusal names the capability, states that retrying will not help, and names
   `ask_user` as the way to ask for it. The first clause stops the retry loop; the second routes the
   agent into the escalation path that already exists rather than dead-ending.
3. **On demand.** A `my_capabilities` tool. Ungated, always — an agent that needed a capability to
   discover its capabilities could never understand its first refusal.

### The constraint this collides with

`checkpoint_access.py:119,145` deliberately makes a denied recall **indistinguishable from
not-found** — both return *"No recorded observation by that id is available to you."* That is a
considered property: a distinguishable refusal confirms the observation exists, which leaks another
agent's activity to an agent that may not read it.

A naive implementation of the loop above would flatten that and quietly undo it. So the rule:

> **An agent may learn what it may do. It may never learn what exists.**

Capability disclosure is about **verbs**, never **objects**. *"You do not hold
`observation.recall`"* is a fact about the agent and is disclosed. *"Observation `obs-4c1` exists but
is denied to you"* is a fact about the world and is not.

In practice: refusals are loud and named, **except** where the capability gates a lookup by
identifier — `observation.recall` and `checkpoint.read` — where the existing indistinguishable
refusal wins and the capability is disclosed only ambiently, never in the response to a specific id.

### The operator's loop is the same recording

At `contract` rigor the ungranted-but-allowed call is already being written (§5). That list is what
tells an operator *"`builder` called `job.schedule` 14 times this week — grant it, or promote to
`gate`?"* One record, two audiences: it is what makes promotion a decision on evidence rather than on
fear, which is the same argument `requirement_gate` makes for its own `reported` list.

> **For the operator:** should `my_capabilities` be a tool, or should the ambient briefing be
> considered sufficient? A tool is one more thing on a surface that has 23 already, and the
> reachability audit
> (`2026-08-21-audit-the-tool-surface-for-reachability.md`) is parked partly over that count.

---

## 7. What this does not solve

Being explicit, because the adjacent problem is the more interesting one and this document does not
reach it.

**`_decide` inspects paths, never commands.** `mcp_server.py:702-756` extracts absolute paths from a
`Bash` command string and checks them against the workspace root. It does not look at what the
command *does*. Inside the workspace, `rm -rf .`, `git push --force`, `curl … | sh` and `npm publish`
are all allowed unconditionally, because none of them contains an absolute path. The code says so
itself (`:729-732`): *"a boundary, not a sandbox."*

That is a real gap and a separate change — a different seam, a different rigor, and it needs no part
of §5. It is mentioned here only so that a reader of this document does not believe a capability
policy would have caught it.

**The 4c blocker is not resolved here either.** §9 of
`2026-08-20-what-the-spec-may-say-about-who-does-the-work.md` asks whether an agent may declare a
task's complexity, since *"an agent writing 'this needs Opus 5' is an agent committing the operator's
money"*. §5 gives that question a **place to be answered** — declaring complexity becomes a
capability an agent does or does not hold — but the operator still has to decide the answer. A seam
is not a decision.

(Two line references in that document have drifted since it was written: it cites
`mcp_server.py:1127` for `decide_evidence`, now `:1149`, and `spec_tasks.py:39-41` for the
roster-decision comment, now `:46-47`. Noted only because that document is cited often enough that
the next reader will follow them.)

---

## 8. If exactly one thing is taken from this

§4. The `reviewer` field is either a promise the runtime should keep or a field that should not
exist, it is decidable in an afternoon, and it does not depend on anything else in this document
being accepted.
