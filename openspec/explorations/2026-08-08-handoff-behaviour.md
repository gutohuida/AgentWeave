# Exploration — what the Handoff control actually does

**Change:** `2026-08-07-conversation-handoff-rework`, section 1
**Date:** 2026-08-08
**Method:** the *shipped* `HANDOFF_PROMPT` was extracted from
`hub/ui/src/components/agents/AgentOutputPanel.tsx` by regex (never retyped) and posted to
`POST /api/v1/projects/proj-84d218db/agent/trigger` against live agents in live conversations on
the Hub at `:8010`. Every quotation below is copied out of the conversation timeline
(`GET /agent/{agent}/chat/{conversation_id}`), not reconstructed.

The prompt under observation, verbatim:

```
Prepare a durable AgentWeave handoff before ending this session.

Invoke your aw-checkpoint skill with reason pre_handoff. Save the current intent, files modified,
decisions and rationale, blockers, exact next steps, and verification commands under
.agentweave/shared/checkpoints/. Stop after confirming the checkpoint path.
```

---

## 1.1 — Claude agent (`haiku-1`), observed

Two runs exist, and they answer different questions. The **first** is the uncontaminated one.

### Run `run-4a8a2305` — first press, no prior handoff in context

Conversation `conv-e41cc24e` (*"Count slowly from 1 to 30…"*), 52s, `status=completed`.

**The agent neither refuses nor no-ops. It improvises, and it improvises well — by silently
substituting a different skill.** From its reasoning, verbatim:

> I need to check if I have such a skill available. Looking at the system reminders, I see several
> skills listed, but I don't see "aw-checkpoint" among them. The skills I see are: handoff,
> harness-audit, harness-refresh, resume, dataviz, update-config, keybindings-help, simplify,
> fewer-permission-prompts, loop, schedule, claude-api, run, init, review, security-review
>
> There's a "handoff" skill which is described as "Compact the session by writing a durable,
> structured handoff file to disk…". This seems to be what the operator is asking for.

It then called `Skill(skill="handoff")` and executed **the operator's own Claude Code `/handoff`
skill**, inherited from `~/.claude/skills/`. It gathered git state, searched for prior handoffs,
and wrote two files:

- `…/.agentweave/worktrees/haiku-1/.handoffs/2026-08-08-session-end.md` (1366 bytes)
- `…/.agentweave/worktrees/haiku-1/.handoffs/LATEST.md`

Both exist on disk today. The artifact is genuinely good — it carries Goal, Current state, Files
touched, Key decisions, Constraints verbatim, Dead ends, Verification, Git state, Next steps, Open
questions, Read on resume — and it is honest that the session contained no work.

**What it ignored, completely and without comment to the operator:** the skill name
(`aw-checkpoint`), the reason argument (`pre_handoff`), and the destination
(`.agentweave/shared/checkpoints/`). Three of the prompt's four concrete instructions.

### Run `run-b5acd592` — second press, artifact already in context

Same conversation, 22s, `status=completed`, cost $0.0492.

With a handoff already made, the improvisation **does not repeat**. The agent instead:

1. called `ToolSearch(query="aw-checkpoint")` → `No matching deferred tools found`;
2. tried to list `.agentweave/shared/` and **was blocked by its own sandbox**:

   > `ls … was blocked. For security, Claude Code may only list files in the allowed working
   > directories for this session: 'C:\Users\huida\Documents\agentweave-testbed\.agentweave\worktrees\haiku-1'.`

3. gave up and put three clarifying questions to the operator, producing no new artifact:

   > I've checked the available tools and skills, but I don't find an "aw-checkpoint" skill or tool
   > in my current environment. Additionally, the shared `.agentweave/shared/checkpoints/`
   > directory is outside my allowed working scope […] To proceed, I need clarification: […]

Both runs ended, so both set **"Handoff ready"** on the header control. The second produced
nothing at all.

### Findings

1. **The destination is structurally unreachable, not merely absent.**
   `.agentweave/shared/checkpoints/` sits outside the agent's allowed working directory, which is
   its worktree. Installing `aw-checkpoint` would not fix task 0.1 — a writing agent confined to
   `.agentweave/worktrees/<agent>/` cannot write to the project-level shared tree at all. **The
   path is wrong, independently of the skill being missing.**
2. **The behaviour is not stable across presses.** First press: a good artifact in the wrong place.
   Second press: a question back to the operator and no artifact. Same prompt, same agent, same
   conversation — the difference is what was already in context. Anything the rework builds on
   "what the agent does" must survive that.
3. **A working handoff skill already exists in the agent's environment**, inherited from the
   operator's user-level Claude Code config. The agent found it unprompted and preferred it. This
   is the strongest argument for task 0.1 resolving toward *"produce the summary inline / use the
   handoff skill you have"* rather than toward shipping an `aw-checkpoint`.
4. **The Hub cannot see any of it.** The artifact landed at a worktree path no Hub record
   references. "Handoff ready" is set by the run stopping — confirmed against both runs, including
   the one that wrote nothing.
5. **A model-authored markdown artifact carries unverifiable fields.** The handoff's own header
   reads `**Date:** 2026-08-08T00:00Z` — wrong. `powershell -Command "Get-Date …"` came back
   `This command requires approval`, and rather than block, the agent invented a timestamp. Direct
   input to **1.5**: fields the Hub already knows (date, agent, branch, HEAD, conversation) should
   be stamped by the Hub, not authored by the model.

---

## 1.2 — Codex agent (`codex-1`), observed

### Run `run-9058966b` — voided by an unattended approval queue, but still informative

Conversation `conv-ee0b0582`. **The run failed**: `status=failed`, `error="turn timed out with no
turn/completed notification"`, 11m36s. The cause was a confound in my own probe, recorded here so
it is not repeated: that conversation carries persisted
`runtime_overrides={"permission_mode": "manual"}` from an earlier operator session, and the probe
did not override it. **Five permission requests expired unanswered** (`perm-d289ad46`,
`perm-a12d95cf`, `perm-7c319ce4`, `perm-560ae6bd`, `perm-dcc51a0b` — all `status=expired`,
`decided_at=NULL`). The timeline ends mid-tool-call with no completion entry.

Even voided, three behaviours are legible and differ from Claude's:

1. **Codex never looks for `aw-checkpoint` and never reports it missing.** It went straight to
   authoring a checkpoint document itself. It did guess at a skill path —
   `C:\Users\huida\.codex\skills\.system\handoff\SKILL.md` — which does not exist.
2. **Codex reads `.agentweave/context/codex-1.md`**, its injected runtime context file, and quotes
   its own working directory back. That file is the only project-level orientation it has.
3. **Codex resolves the destination literally and relative to its own worktree**, producing a
   *nested* AgentWeave tree:

   > `C:\Users\huida\…\worktrees\codex-1\.agentweave\shared\checkpoints\pre_handoff-codex-1-2026-08-08.md`

   Note the `.agentweave` inside `worktrees\codex-1\`. Where Claude recognised the shared path as
   out of scope and said so, Codex would have silently created a second, agent-local
   `.agentweave/shared/` that nothing reads. **Same broken instruction, two different wrong
   outcomes.**

Nothing was written — both `apply_patch` calls hit the expired approvals, and
`worktrees/codex-1/.agentweave/shared/` does not exist on disk.

### Run `run-b4f1c688` — clean, and it corrects the proposal's premise

Conversation `conv-a6b2e314` (*"Send a message to haiku-1 asking it to reply 'ack'"*), forced
`permission_mode=acceptEdits`. `status=completed`, 2m43s, **zero permission requests**.

**The proposal's stated premise is wrong, and this is the session's most consequential finding.**
The change says *"Codex has no project-level skill discovery at all"*, and infers its behaviour
will therefore differ. Project-level is correct; the inference is not. Codex read:

> `Get-Content C:\Users\huida\.agents\skills\handoff\SKILL.md`

`~/.agents/skills/` exists on this machine and contains `handoff` and `resume` — the
**agent-agnostic** skill location. Codex found the *same* handoff skill Claude used, from a
different directory, and followed it step for step: branch, status, `log --oneline -8`,
`diff --stat HEAD`, the `origin/…` upstream probe, the three-location prior-handoff search, then
the full section template and a `LATEST.md` pointer.

So **both runtimes silently substitute the operator's personal handoff skill.** Claude announced
it (*"There's a 'handoff' skill […] This seems to be what the operator is asking for"*); Codex
never mentioned `aw-checkpoint` at all, in either run. Neither has ever executed the thing the
prompt names.

**The artifact was written, and it is good.** Verified on disk, 3222 bytes:

```
…\worktrees\codex-1\.agentweave\shared\checkpoints\2026-08-08-1341-pre_handoff.md
…\worktrees\codex-1\.agentweave\shared\checkpoints\LATEST.md
```

Note the nesting again — `.agentweave\` *inside* `worktrees\codex-1\`. Codex resolved the prompt's
relative path against its own cwd and created a second AgentWeave tree that nothing reads. This is
now confirmed on disk, not merely inferred from the voided run.

Two further observations from the clean run:

- **`apply_patch` was rejected twice under `acceptEdits`, and a PowerShell heredoc write to the
  same path succeeded.** The agent worked around it by itself (*"`apply_patch` is being rejected in
  this workspace, so I'm using a direct file write fallback"*). Two tools, same destination,
  different verdicts — worth a look independently of this change.
- **With approvals not blocking, `Get-Date` worked and the timestamp is correct**
  (`2026-08-08T13:41+01:00`). Compare Claude's invented `2026-08-08T00:00Z` under an
  approval-blocked clock. The failure mode from 1.1 finding 5 is real but posture-dependent.

### The caveat that constrains section 0

Both agents rescued the broken prompt **only because this operator happens to have a personal
handoff skill installed** — `~/.claude/skills/` for Claude, `~/.agents/skills/` for Codex. Neither
is shipped by AgentWeave, and `get_skill_template` still installs nothing.

A user without those directories gets the *un-rescued* behaviour, which 1.1's second run already
shows: search, find nothing, hit the sandbox, ask the operator a question, produce no artifact.
**The observed competence is borrowed, not a property of the product.** Task 0.1 cannot be
resolved by assuming it.

---

## 1.3 — What the successor conversation actually receives

### The mechanism, traced

`AgentOutputPanel.tsx:371` sets `startingFresh` once the handoff trigger returns. That makes
`currentConversationId` `undefined` (`:222`), which makes `startsFresh` true (`:225`), which is the
condition at `:439` for prefixing. The submission is then
`postTrigger(RESUME_HANDOFF_PREFIX + "\n\n" + typed, undefined, …)` — **conversation_id null, so a
brand-new conversation**.

The successor therefore receives **exactly one thing**: the prefix plus the operator's typed
message. No history, no peer messages, no tasks, no runtime overrides, and no reference to any
artifact. Confirmed live — the successor conversations opened with a single `operator_input` entry.

### Both paths the prefix names are wrong

Verified on disk: `.agentweave/shared/` exists **nowhere** — not at the project root
(`project.json` + `worktrees/` only) and not in any worktree. `context.md` exists nowhere in the
testbed at all. The real file is `.agentweave/context/<agent>.md`, so the prefix is wrong by one
directory *and* a filename.

### Codex — `run` in `conv-…`, the two bugs cancel

Codex found its checkpoint immediately:

> I found the latest checkpoint at `.agentweave/shared/checkpoints/2026-08-08-1341-pre_handoff.md`

Because it had earlier resolved the *handoff* path against its own worktree, and now resolved the
*resume* path the same way, the two errors compose into a working round-trip. It confirmed branch,
HEAD, clean tree, empty task ledger, and flagged the one path that genuinely does not exist:

> Note: I could not find `.agentweave/shared/context.md` at the path you gave

**This works only by coincidence, and only for a runtime that resolves relatively.** Nothing about
it is a design.

### Claude — six failed lookups, then brute force

`run-a9451359`, 55s, `status=completed`, $0.0723. Claude had written to `.handoffs/`, not to the
path the prefix names, so the round-trip does not close. In order:

1. `Glob(".agentweave/shared/checkpoints/haiku-1*")` → `No files found`
2. `Read(".agentweave/shared/context.md")` → not permitted
3. `Bash(ls …\.agentweave\shared\)` → rejected, `Contains backslash-escaped whitespace`
4. `PowerShell(Get-ChildItem …\shared\)` → **sandbox-blocked**, *"may only access files in the
   allowed working directories for this session"*
5. `Glob(".agentweave/**/*")` → only `context\haiku-1.md`, which it correctly identified as *"just
   the runtime context file that was injected into the prompt — it's not the handoff checkpoint"*
6. `Glob("**/handoff*")` and `Glob("**/*.handoff")` → `No files found` (the directory is
   `.handoffs`, so neither pattern matches)

Only a bare `Glob("*")` surfaced `.handoffs\LATEST.md`, which it then followed to the real
artifact and summarised correctly. **It recovered — by ignoring the instruction and searching its
whole worktree.**

### Findings

1. **The successor gets no state at all beyond a prompt.** Everything the rework's sections 2–4
   propose to deliver — artifact, lineage, peer context, task ownership — is absent today. There is
   no current behaviour here worth preserving, which is what 1.3 was asked to determine.
2. **The round-trip closes for Codex and not for Claude, for reasons neither runtime controls.**
   Any fix must make the location a property of the *product*, not of how a given CLI resolves a
   relative path.
3. **Recovery costs a turn and is not guaranteed.** Six failed lookups here; the same agent in
   1.1's second run gave up and asked a question instead.
4. **`.agentweave/context/<agent>.md` is already injected into the prompt**, so the prefix telling
   the agent to go read a context file is redundant even in the version where the path is right.

---

## 1.4 — Which of `handoff.md`'s sections survive the move to a conversation

Source: `src/agentweave/templates/skills/handoff.md`, 106 lines. It is written for a single agent
in a terminal, driving one repository, deciding for itself when to compact. An AgentWeave
conversation breaks three of those assumptions, and the sections split cleanly along the break.

### Drop — the terminal's job, not the conversation's

- **§1 "Choose the move."** The operator already chose by pressing a button. Observed waste: in
  `run-4a8a2305` the agent reasoned through all four branches to arrive at *"The user explicitly
  asked for a handoff → Full handoff"*, which was known before the run started.
- **§2's git gathering.** This is not merely redundant in AgentWeave, it is **actively
  uninformative**. `hub/hub/worktrees.py:243-258` runs `git add -A` and commits
  `"Auto-snapshot: <agent>'s turn"` at the end of every turn. So by the time any handoff runs, the
  tree is *always* clean and the log is *always* a wall of identical messages. Observed exactly
  that: `git status --short` empty, `git diff --stat HEAD` empty, and eight consecutive
  `Auto-snapshot: haiku-1's turn` lines — from which the agent concluded "Worktree clean, all
  changes committed / No pending work", which is true of a worktree that did a week of work.
- **§2's `git log origin/…` and "unpushed commits."** Agent branches have no upstream. Observed
  output: *"Unpushed commits: none visible from local state"* — a non-answer.
- **§2's search for a previous handoff.** The Hub knows the conversation's predecessor; making the
  agent `find` for it wastes a turn and found nothing.
- **§3's `.handoffs/` + `LATEST.md` filesystem chain.** Replaced by conversation lineage
  (tasks 4.2/4.3). The observed artifact landed in a worktree the Hub cannot see.
- **§4's closing instruction** — *"exactly one recommendation: start fresh and run `/resume`"*.
  The successor is created by the Hub, not by the operator running a slash command.

### Stamp, don't ask — the Hub already knows these, and the model gets them wrong

The whole header block: `Date`, `Branch`, `HEAD`, `Agent`, `Previous handoff`, `Status`.

The date is the proof. §3 says *"using the real current time"*; the agent's attempt
(`powershell -Command "Get-Date …"`) came back `This command requires approval`, and it wrote
`**Date:** 2026-08-08T00:00Z` — invented rather than blocked on. Every one of those fields is a
column the Hub holds already.

**Files touched** belongs here too, in a modified form: the Hub can diff the conversation's
auto-snapshot commits and produce the real list, instead of trusting the model to recall it.

**Constraints and user directives (verbatim)** is the interesting case. It is the section most
worth having and the one a model is least reliable at — but the Hub holds every `operator_input`
entry for the conversation verbatim, so the quotes can be sourced rather than recalled.

### Keep, model-authored — nothing else can produce these

`Goal`, `Current state`, `Key decisions` (with rejected alternatives), `Dead ends`,
`Verification` (tested vs untested), `Next steps` (step 1 executable with no hidden decision),
`Open questions`, `Read on resume`.

These are judgement, and they are the entire value of a handoff. The observed artifact did them
adequately even on an empty session.

### What this hands to 1.5 and 1.11

The split above is not a stylistic preference, it is a **verifiability** boundary, and it answers
1.5 without needing a separate investigation:

- Hub-stamped fields are checkable, so a handoff that omits or fudges them can be *failed*.
- Model-authored prose is not checkable, so requiring it to be structured buys nothing.

That argues for a **hybrid**: a structured envelope the Hub fills and validates, carrying one
markdown body the model writes. It also makes 1.11's rule testable — "did this run produce a
handoff record attached to this conversation?" is a row lookup, which the current
run-ended-therefore-ready check cannot express.

---

## 1.5 — Structured or markdown

**Decision: hybrid — a structured envelope the Hub fills and validates, carrying one markdown
body the model writes.**

This follows from 1.4's split rather than from taste. The line between the two groups is
*verifiability*:

- The Hub-known fields (date, agent, branch, HEAD, predecessor, files touched, overrides) are
  checkable, so structuring them buys a real thing: a handoff that omits or fudges one can be
  **failed**. Both failure modes were observed — an invented `2026-08-08T00:00Z`, and "no pending
  work" concluded from an always-clean worktree.
- The judgement fields (Goal, Current state, Key decisions, Dead ends, Verification, Next steps,
  Open questions, Read on resume) cannot be validated by any schema. Forcing them into JSON adds
  ceremony and removes nothing from the failure surface.

Fully-structured is therefore over-engineering and one-markdown-blob is unverifiable. The
envelope is what makes 1.11 expressible.

## 1.6 — What a handoff must carry that a single-agent session never had

Checked against the live schema. Four candidates, and they are not equally carryable:

| Candidate | Where it lives | Conversation-scoped? |
|---|---|---|
| Outstanding questions | `questions.conversation_id`, `unasked_questions.conversation_id` | **Yes** — carry exactly |
| Runtime overrides | `Conversation.runtime_overrides` | **Yes** — carry exactly |
| Peer messages | `Message.conversation_id` (outbound) / `InboundQueueEntry.conversation_id` (inbound) | **Per-side only** — see 1.7 |
| Tasks the agent owns | `tasks.assignee` | **No** — no `conversation_id` column at all |

Two consequences the design has to absorb:

- **Tasks cannot be scoped to a conversation.** `tasks` is project-scoped with an `assignee`. A
  handoff can carry "tasks assigned to this agent", which is identical for every concurrent
  conversation that agent owns. Either that imprecision is accepted and stated, or `tasks` gains a
  conversation binding — which is a larger change than this one.
- **Runtime overrides are not cosmetic.** `conv-ee0b0582` carried
  `{"permission_mode": "manual"}` from an earlier operator session; inheriting it silently is what
  expired five approvals and failed `run-9058966b` after 11m36s. A successor that silently
  inherits, or silently drops, a posture will produce exactly that class of confusion.

## 1.7 — Does the peer need to be told? The premise is too generous

The task supposes routing "will resolve to the successor — establish by test whether that is
correct or merely convenient." It is **neither. It is already wrong today, before handoffs enter
the picture.**

`messages.py:133` — when a peer omits `conversation_id` (the normal case, since a sender rarely
knows the recipient's thread ids), delivery goes to `latest_open_conversation(recipient)`:
`lifecycle='open'` ordered by `updated_at DESC`. **Whatever thread the recipient touched most
recently**, with no reference to the sender, to prior traffic between the pair, or to the sender's
own conversation.

Observed in the live database — three messages from `codex-1` to `haiku-1`, one ongoing peer
exchange by any human reading, delivered into three unrelated `haiku-1` conversations:

| Message | Landed in | That thread is about |
|---|---|---|
| `pong` / `Please send a reply.` / `Received.` | `conv-b275cb8d` | *"Send a message to codex-1 asking it to reply…"* |
| `Please reply with the single word 'ack'.` | `conv-dbaf9847` | *"Create a file called notes.md…"* |
| `Please respond with the exact phrase: ok 1.` | `conv-f22fb84f` | *"Renamed live from the row menu"* |

Note also that `Message.conversation_id` **is** recorded — but it holds the *sender's* thread
(`conv-a6b2e314`, a `codex-1` conversation) and is never consulted for delivery. The data to do
better is already being written and then ignored.

**Answer to the question as asked:** after a handoff the successor is the most-recently-updated
open conversation, so peer traffic does follow it — by the same accident that scattered it above,
and only until the agent touches any other thread. Telling `haiku-1` about the handoff would not
help, because `haiku-1` has no binding to the predecessor to update.

## 1.8 — Should a handoff carry peer relationships forward?

**The question dissolves: there are no peer relationships in the data model to carry.**

There is a per-message `sender`/`recipient` pair and a `conversation_id` pointing at the sender's
thread. There is no representation of "these two agents are working the same thread", so a
successor starting peer-blank is not a *default* — it is the only state that exists. Every
conversation is already peer-blank; peer messages arrive by recency.

This is the finding that most reshapes the slice, and it reshapes it by **narrowing** it. Carrying
peer context across a handoff is not implementable on top of recency routing; it would be building
the visible half of a feature whose foundation is missing. Two honest options for 1.9:

1. **Scope the rework to the single-agent case** — artifact, verification, lineage, delivery to
   the successor — and record peer carry-forward as blocked on conversation-bound peer routing.
2. **Fix the routing first**, in its own change: bind delivery to the sender's conversation (the
   column is already populated) or to a durable pair thread, then revisit carry-forward.

Recommend (1) for this change and a separate proposal for the routing defect, which is a live bug
affecting every peer message today and is not caused by handoffs.

---

## Method notes for whoever repeats this

- The probe lives outside the repository (`C:\Users\huida\Documents\aw-probe\observe_handoff.py`)
  because it reads the Hub API key out of `hub/.env`. It must never be committed.
- **Force `permission_mode` explicitly on the trigger.** A conversation's persisted
  `runtime_overrides` silently applies otherwise, and `"manual"` with nobody watching expires every
  approval and fails the run after ~11 minutes.
- Codex runs are slow — 11m+ against Claude's 22–52s. Budget for it.
- Extract `HANDOFF_PROMPT` with
  `re.search(r"const HANDOFF_PROMPT = \`(.*?)\`", source, re.DOTALL)`. Observing a retyped
  approximation would prove nothing about what ships.

---

## Open — not yet observed

- **1.3** — what a successor conversation actually receives after a handoff.
- **1.4–1.8** — content, artifact shape, multi-agent carry-forward.
