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

### Run — clean re-run

*In progress at time of writing; see the addendum below.*

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
