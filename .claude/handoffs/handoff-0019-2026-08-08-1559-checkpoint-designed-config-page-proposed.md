# Handoff: handoff-rework exploration complete and fully specced; agent-config-page proposed

**Date:** 2026-08-08T15:59 · **Branch:** hub-native-experience · **HEAD:** 226f103
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0018-2026-08-08-1320-handoff-rework-picked-up.md
**Status:** chunk complete, working tree clean. **Nothing implemented this session — this was
exploration, design, and specification only.** Two changes are now ready to build.

## Goal

Take `2026-08-07-conversation-handoff-rework` from 0/24 with an untouched exploration gate to a
fully-specified, implementable change — and then give its agent-level settings somewhere to live.

The *why*, established by live observation rather than inherited from the proposal: **the Handoff
control does not work, and the reason changes the solution.** It tells the agent to invoke an
`aw-checkpoint` skill AgentWeave never installs, writing to `.agentweave/shared/checkpoints/`, a
path outside the agent's own sandbox. Both runtimes only appeared to work because this operator
happens to have a personal handoff skill installed. The competence was borrowed, not built.

## Current state

### Two changes, both validating strict, neither started

`npx openspec validate --changes --strict` → **6 passed, 1 failed**. The only failure is
`2026-08-07-spec-execution-coordinator`, the other gated skeleton, which fails by design.

| change | tasks | state |
|---|---|---|
| `2026-08-07-conversation-handoff-rework` | **11 done / 59 open** | both gates cleared; `design.md` + 4 spec deltas written |
| `2026-08-08-agent-configuration-page` | **0 done / 39 open** | new this session; no gates, no open questions |

### The exploration (tasks 1.1–1.8, all answered with live evidence)

Written up in `openspec/explorations/2026-08-08-handoff-behaviour.md`. Ran the *shipped*
`HANDOFF_PROMPT` — extracted by regex from `AgentOutputPanel.tsx`, never retyped — against live
agents on the Hub at `:8010`.

- **1.1 Claude (`haiku-1`)** — does not refuse and does not no-op. It finds the operator's own
  Claude Code `/handoff` skill, silently substitutes it, writes a genuinely good artifact to
  `<worktree>/.handoffs/`, and ignores three of the prompt's four instructions. **On a second press
  with that artifact in context it stops improvising**: `ToolSearch("aw-checkpoint")` → nothing,
  sandbox-blocked reading the shared path, then three clarifying questions and no artifact. Both
  runs lit up "Handoff ready".
- **1.2 Codex (`codex-1`)** — the proposal's premise was wrong. Codex has no *project*-level skill
  discovery but reads `~/.agents/skills/` and found the **same** handoff skill. It resolves
  `.agentweave/shared/checkpoints/` relative to its own worktree, creating a nested `.agentweave` —
  confirmed on disk at
  `…\worktrees\codex-1\.agentweave\shared\checkpoints\2026-08-08-1341-pre_handoff.md` (3222 bytes).
- **1.3 resume** — the successor receives *only* `RESUME_HANDOFF_PREFIX` + typed message in a brand
  new conversation. Both paths it names are wrong. Codex's round-trip closes **by coincidence**
  (it wrote to the same wrong place); Claude's took six failed lookups and a sandbox block before a
  bare `Glob("*")` rescued it.
- **1.4** — `handoff.md`'s sections split three ways: drop / Hub-stamps / model-authored.
- **1.5** — hybrid envelope. **1.6** — tasks aren't conversation-scoped; questions and overrides are.
- **1.7/1.8** — peer messages route by **recency**; three `codex-1 → haiku-1` messages sit in three
  unrelated `haiku-1` threads. There are no peer relationships in the data model to carry forward.

### The Hub

Running detached on **http://localhost:8010**, confirmed alive at handoff time. Started as in
handoff-0018:

```powershell
Start-Process -FilePath 'C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe' `
  -ArgumentList '-m','uvicorn','hub.main:app','--host','127.0.0.1','--port','8010' `
  -WorkingDirectory 'C:\Users\huida\Documents\projects\AgentWeave\hub' -WindowStyle Hidden
```

Project **`proj-84d218db` ("Testbed")**, key in `hub/.env` as `AW_BOOTSTRAP_API_KEY`. Serving
`assets/index-D0RqKR3V.js`. **No Python or UI code changed this session, so no restart or rebuild
is owed.**

### Live defects found and specced but NOT fixed

1. **Peer delivery routes by recency** — `messages.py:133`. One routing site; both operator and
   agent routes funnel into `create_message_for_actor`.
2. **Claude agents have never reported a context percentage** — 329 samples, **zero** usable.
   `runner_parsing._claude_usage_sample:199` emits token counts with `model: null`; the `modelUsage`
   branch at `:290` emits model + window with no tokens. A catalog keyed by model cannot answer for
   a sample that doesn't say which model ran. **This is a conformance failure against a correct
   spec**, not a spec gap — `agent-context-usage` already requires provider → catalog → unknown.
3. **`role` and `yolo` are dead fields.** `agents` table has neither column, but
   `schemas/agents.py:44-47` declares both and `AgentInfoTab.tsx:110-153` renders them. `yolo` is
   `bool = False`, so its badge can only ever read **Disabled**.
4. **Two more dead `/aw-checkpoint` references** at `agents.py:1444` and `:1474` — found this
   session, were missing from section 0's original list.

## Files touched

`git status --short` is **empty** — working tree clean, everything committed.

### Created

- `openspec/explorations/2026-08-08-handoff-behaviour.md` — the full exploration writeup.
- `openspec/changes/2026-08-07-conversation-handoff-rework/design.md` — 13 decisions.
- `openspec/changes/2026-08-07-conversation-handoff-rework/specs/conversation-checkpoint/spec.md`
  — ADDED, the new capability.
- `…/specs/agent-conversation-handoff/spec.md` — MODIFIED ×3.
- `…/specs/agent-conversation-workspace/spec.md` — ADDED, the queue-routing contract.
- `…/specs/agent-context-usage/spec.md` — ADDED, sample identifies its model.
- `openspec/changes/2026-08-08-agent-configuration-page/` — `proposal.md`, `design.md`, `tasks.md`,
  `specs/agent-configuration/spec.md`, `specs/operator-agent-creation/spec.md`.

### Modified

- `openspec/changes/2026-08-07-conversation-handoff-rework/tasks.md` — sections 2–9 replace the
  placeholders; 1.1–1.11 answered inline; section 0 gains 0.5.
- `openspec/changes/2026-08-07-conversation-handoff-rework/proposal.md` — header rewritten (it said
  SKELETON / DO NOT IMPLEMENT and assumed the agent authors the artifact).

### Outside the repo (deliberately — they read the API key from `hub/.env`)

- `C:\Users\huida\Documents\aw-probe\observe_handoff.py` and `observe_resume.py` — the probes.
  **Never commit these.** They still work; re-run to observe further behaviour.
- Memory: `project_checkpoint_trigger_prompts_provisional.md` + a line in `MEMORY.md`.

## Key decisions

1. **The reframe.** `/handoff` is a file in a terminal because `/clear` destroys the only copy.
   Nothing is destroyed here — a conversation is 1:1 with a provider session
   (`agent_trigger.py:289`, `runner_commands.py:206`), so a new conversation starts the CLI blind
   while the DB keeps everything, including `thinking` entries. **A checkpoint is compression across
   a session boundary, not preservation** — so it is solvable Hub-side.
2. **Hub-side generation via a reusable Worker.** `conversation_titles.py` is already a proto-worker
   (`build_title_command:59`, `_run_titler:93`). Generalised: operator-chosen Runner + model,
   Hub-owned versioned prompt, schema-validated output.
3. **Computed vs written split.** Never ask the model for what the Hub knows. Factory.ai found
   artifact tracking is the weakest dimension of *every* compression method (2.19–2.45/5) — and
   `worktrees.py:243-258` auto-commits every turn, so files-changed is a diff.
4. **A checkpoint that disagrees with the DB is FAILED**, not merely one that is absent. Stronger
   than task 1.11 asked, and deterministic.
5. **ARC-style recall.** `agent_outputs` is already an append-only observation store with stable ids
   and is thrown away at a handoff. Checkpoint carries citations + a `recall(id)` tool.
6. **Two independent grants**, closed by default, on the **Agent** record not the charter (charters
   are editable prose; letting them widen access is a trap). Summary access ≠ transcript access.
7. **Lineage stored, participation derived** — `Task.created_by_run_id → Run → (agent, conversation)`.
8. **Rename to Checkpoint.** Reclaims vocabulary the product already used. `aw-checkpoint.md` is
   **deleted**, answering task 0.4.
9. **Both prerequisites folded in** (peer routing §2, context measurement §3) rather than split out
   — 1.8 recommended narrowing, the **operator overturned it**: cross-agent reading is v1.
10. **Peer binding is per sender-conversation (option a)**, not a pair thread. Rejected: pair thread
    (loses conversation-level precision), requiring `conversation_id` (pushes bookkeeping onto the
    agent), routing by task (only works for task-bearing messages).
11. **Threshold is mode + value**, tokens in thousands. Absolute tokens needs no context window at
    all, routing around the measurement defect. Override replaces the **whole** threshold.
12. **One prompt per trigger in v1 — PROVISIONAL.** Recorded in `design.md`, task 6.7, and a memory
    that survives archival. Delegation is the likeliest first candidate to need its own variant.
13. **Agent config is an agent-scoped destination**, not an `ENVIRONMENT_SECTIONS` entry — those
    carry no subject. **Back is FIXED** to the agent's conversation (an earlier draft had it return
    to origin; that departed from `App.tsx:207`'s shipped pattern). **No link-through on bindings.**
14. **Agents are archived, never deleted.** Decision, not deferral. No `DELETE` route exists today,
    so it is additive plus a test asserting none appears.

## Constraints and user directives (verbatim)

**From this session:**
- *"Yeah that's the path. For the future I want control pages over this data that we're generating
  so a human can track as well what's happening."*
- *"we can always ask the agent in turn. For example when running a handoff sending a last message
  to the agent to get a structured response on a endpoint very brief very concise"*
- *"Good point. Maybe handoff is not the name. We can change it for checkpoint."*
- *"okay let's ok with i for v1 but we need to take a hard note on this because I'm for sure going
  to forget this in the future."* — done: memory `project_checkpoint_trigger_prompts_provisional`.
- *"Can we transform this into a configuration? If the user wants auto checkpoints and what are the
  threshold that he wants them (also double check the context filling logic it might not be working
  correctly, the agents are showing either no context or Context unavailable)"*
- *"I think the agent configuration is starting to become bigger we need to rework the config page
  instead of a pop up to be a page on it's own just like the project config."*
- *"we need to add a allow auto checkpoint with a box allowing to chose the percentage or the amount
  of tokens (because the context windows for different models can change some people might want to
  compact with 150K tokens rather then 50%) the count should be in K tokens so the user just sets
  150, 200, 300"*
- *"B. fixed back to the agent's conversation. Yes, no agent deletion. Just archive."*
- *"Wait. Are you already implementing? Should we dive in first to see what to do or at least give
  me the plan on what are you doing so I can make a more informed decision."* — **they want the plan
  before implementation. Do not start building without laying out what and why.**

**Carried and still binding:**
- *"no need for backups everything is test env"*
- *"handoff need a explicit place to sit. Where we know it's there. Users might not know of forget
  about the handoff."*
- *"I don't want it to be colorful it should be like the chat box but maybe a little lighter"*
- *"What is taking so long?"* — **the operator is sensitive to wall-clock.** `pytest hub/tests/` is
  ~3:00 for 1073 tests; `npx vitest run` ~11s. Targeted files during dev, one full sweep before
  committing.
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root; stage
  paths explicitly; openspec never aw-spec skills; `Icon` is the only icon system;
  `approve_tool_call` keeps **no return annotation**; `hub/hub/static/ui` is a committed artefact
  refreshed after `npm run build` and confirmed with `diff -rq`; never mark a task complete on the
  strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify prior claimed work on
  resume (**done at session start** — see Verification; **repeat next session**).

## Dead ends

- **`openspec new change` cannot manage a date-prefixed change**, which is this repo's convention.
  Hand-author `openspec/changes/<date>-<name>/` instead. (Confirmed again this session.)
- **`openspec validate` reads only a requirement's FIRST LINE for `SHALL`/`MUST`.** Every
  `### Requirement:` must state its obligation in the opening sentence.
- **The Bash tool is Git Bash, not PowerShell.** A PowerShell here-string (`@'…'@`) as a commit
  message leaks a literal `@` into the subject line. Use a bash heredoc: `git commit -F - <<'EOF'`.
- **A conversation's persisted `runtime_overrides` silently applies to a probe trigger.**
  `conv-ee0b0582` carried `{"permission_mode": "manual"}`; five approvals expired unanswered and the
  run **failed** after 11m36s (`run-9058966b`). **Always force `permission_mode` explicitly.**
- **`curl … -o /tmp/x.json` does not work from the Bash tool here** — write to a real directory.
  `json.load(open(...))` also dies on cp1252; use `io.open(..., encoding='utf-8')`.
- **The `event_logs` table is plural.** `event_log` does not exist.
- **Codex runs are slow** — 2m43s to 11m+ versus Claude's 22–55s. Budget for it; use
  `run_in_background` and do not pipe to `tail`, which buffers until the pipe closes.
- **Do not claim charter should be required at creation.** `operator-agent-creation` states a
  charter *"MAY be selected but MUST NOT be required"* with a defined no-charter contract. Caught
  mid-draft; the creation rule now governs what is **offered**, not what is required.
- Carried and still true: `ORDER BY EventLog.id` does not order by recency; `extra: "forbid"`
  rejects a forbidden **key** regardless of value; the `app` fixture in `hub/tests/conftest.py` is
  an httpx client with no `.routes`; **the default `python` on PATH has no pytest — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`**.

## Verification

**Ran, with real output:**
- **Live verification of handoff-0018's claims at session start** (standing directive): Hub serving
  `index-D0RqKR3V.js` as claimed; `conversation_id` present in `agent_actions.py`;
  `pytest hub/tests/test_mcp_body_contract.py test_agent_message_routing.py -q` → **13 passed**.
- **Five live agent runs** against `:8010`, all captured verbatim: `run-4a8a2305` (haiku, completed
  52s), `run-b5acd592` (haiku, completed 22s), `run-9058966b` (codex, **failed**, approval-expiry
  confound), `run-b4f1c688` (codex, completed 2m43s), `run-a9451359` + a codex resume run.
- `npx openspec validate --changes --strict` → **6 passed, 1 failed** (the expected skeleton).
- Direct SQLite inspection of `hub/data/agentweave.db` for context samples, peer routing, runs,
  permission requests, and conversation overrides.

**Explicitly NOT run — do not assume:**
- **No implementation was done and no product code was changed.** Zero lines of `src/` or `hub/hub/`
  or `hub/ui/src/` were modified. Every commit is markdown under `openspec/`.
- **The full test suite was NOT run this session** — no code changed, so nothing to regress, but do
  not report it as green.
- `npx vitest run`, `npx tsc --noEmit`, `ruff`, `npm run build` — **none run**. Not needed; nothing
  changed.
- **Nothing driven in a browser.** Still the standing gap; the operator has found defects by using
  surfaces that passed their tests.
- The four live defects listed under *Current state* are **specced, not fixed.**

## Git state

Branch `hub-native-experience`, HEAD `226f103`, **working tree clean**. **No upstream — nothing has
ever been pushed on this branch. 275 commits ahead of `master`.**

Eight commits this session, all openspec markdown:
`3406910`, `51ba3c2`, `9e947c3`, `ad66106`, `d068df6`, `b4166e4`, `44aa774`, `226f103`.

**openspec in flight (7):**

| change | tasks | note |
|---|---|---|
| `2026-08-08-agent-configuration-page` | **0/39** | **no gates, no open questions — ready** |
| `2026-08-07-conversation-handoff-rework` | **11/70** | gates cleared; §2 and §3 are prerequisites |
| `2026-08-07-conversation-navigation` | 81/81 | **still unsynced and unarchived** |
| `2026-08-07-spec-execution-coordinator` | 0/29 | gated skeleton — do not start |
| `2026-08-04-hub-charcoal-visual-refresh` | 39/42 | remaining are manual checks |
| `2026-08-04-hub-contextual-navigation` | 43/45 | 4.7 is real code; 7.7 is a manual check |
| `2026-07-30-hub-native-experience` | 119/188 | §14 spec traceability (19), §13 charters (15), … |

## Next steps

1. **Start `2026-08-08-agent-configuration-page` section 1 — remove `role` and `yolo`.** Concretely:
   grep the whole repo for `role` and `yolo` as agent fields (task 1.1 — **establish there are no
   consumers rather than assuming it**), then delete `role: Optional[str]` and `yolo: bool = False`
   from `hub/hub/schemas/agents.py:44-47`, remove the *Collaboration Role* block and *YOLO Mode*
   badge from `hub/ui/src/components/agents/AgentInfoTab.tsx:110-153` along with `ROLE_CONFIG` if it
   has no other caller, and correct the stale runner-enum comment at `schemas/agents.py:48-50`. Add
   a test asserting the agent response carries neither field. **This is small, self-contained, and
   independent of everything else** — the recommended low-risk start.
2. Then section 2 of the same change — the `{ kind: 'agent-settings', … }` destination in
   `hub/ui/src/lib/navigation.ts`, following `Sidebar.tsx:173-191`.
3. **Or** start the checkpoint change at section 2 (peer delivery binding), which is the other
   unblocked front. One routing site: `messages.py:133`.
4. Still open from handoff-0017/0018: **sync + archive `2026-08-07-conversation-navigation`** (81/81,
   operator has used it); the operator's visual pass on light mode and `⋯` visibility.

**Before building anything, lay out the plan first** — the operator asked for this explicitly this
session and it applies to both changes.

## Open questions for the user

1. **Which change first** — agent-config-page (no dependencies, unblocks the checkpoint change's
   §8) or checkpoint §2? My recommendation is the config page, section 1.
2. **Should `2026-08-07-conversation-navigation` be synced and archived now?** Carried unanswered
   across three handoffs. It is 81/81 and in use.
3. **Peer-thread presentation** was deferred by the operator this session. Binding per
   sender-conversation will make the tree busier; `origin: peer` exists to group them. Raise as its
   own change when the tree gets noisy.
4. Carried: should this branch be pushed — **275** commits, no upstream? Should `AgentCard.tsx` be
   deleted now it is unreachable? Should `pytest-xdist` be added? Should `.claude/handoffs/` stay
   tracked (104 files)? Is the 120-character title cap too long?

## Read on resume

- `openspec/changes/2026-08-08-agent-configuration-page/tasks.md` — **start here.** Section 1 is
  next-step 1 and is executable as written.
- `openspec/changes/2026-08-08-agent-configuration-page/design.md` — why the destination is
  agent-scoped, why back is fixed, why archive replaces deletion.
- `openspec/changes/2026-08-07-conversation-handoff-rework/design.md` — the 13 decisions, if picking
  up the checkpoint change instead.
- `openspec/explorations/2026-08-08-handoff-behaviour.md` — the captured evidence behind all of it;
  read before questioning any decision.
- `hub/ui/src/components/agents/AgentInfoTab.tsx` lines **110-153** — the dead `role`/`yolo` render,
  the literal subject of next-step 1.
- `hub/ui/src/lib/navigation.ts` lines **22-43** — `ENVIRONMENT_SECTIONS` and `WorkspaceDestination`,
  the shape section 2 extends.
