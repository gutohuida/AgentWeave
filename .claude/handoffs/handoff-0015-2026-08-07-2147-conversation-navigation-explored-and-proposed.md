# Handoff: conversation navigation explored and proposed, handoff rework gated on exploration

**Date:** 2026-08-07T21:47 · **Branch:** hub-native-experience · **HEAD:** 59216c9
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0014-2026-08-07-2011-backstop-batching-settings-and-housekeeping.md
**Status:** chunk complete. One commit, working tree clean. **No implementation was done this
session** — this was exploration and specification only. Nothing in either new change is built.

## Goal

Answer handoff-0014's next step 1 — *"Ask the operator for their navigation idea before designing
anything"* — then turn their idea into an openspec change.

The *why*: the operator's complaint was that agent settings are *"kind of confusing and hard to
find"* and *"those 3 buttons showing all the conversations is not good"*. Tracing that surfaced a
larger problem — a conversation is the unit of work in AgentWeave and is the one object with no
place in the shell: no name, no home in the rail, no way to remove one. It also surfaced that the
Handoff feature does not do what it claims, which became a second, gated change.

## Current state

### Shipped this session

**Nothing was implemented.** Two openspec changes were written and committed. Both are proposals.

**1. `openspec/changes/2026-08-07-conversation-navigation/` — complete, validates.**
`proposal.md`, `design.md`, `tasks.md`, and three spec deltas. `npx openspec validate --changes
--strict` passes; `npx openspec change show <id> --json --deltas-only` reports `deltaCount: 17`,
confirming every requirement parsed rather than silently dropping.

**2. `openspec/changes/2026-08-07-conversation-handoff-rework/` — deliberate skeleton.**
`proposal.md` and `tasks.md` only. **No `design.md`, no `specs/`** — that absence is the gate.

### Known-broken / not done

1. **`openspec validate --changes` now fails on the handoff skeleton**, reporting *"Change must
   have at least one delta. No deltas found."* **This is intentional and documented in that
   change's `proposal.md`.** Do NOT silence it by writing placeholder requirements. It clears when
   its task 1.10 writes the real specs. Totals are now "4 passed, 1 failed (5 items)".
2. **The `openspec` CLI cannot manage any date-prefixed change.** `openspec new change
   "2026-08-07-foo"` and `openspec status --change "2026-08-07-foo"` both fail with *"Change name
   must start with a letter"* — but `openspec list`, `openspec validate --changes` and `openspec
   change show` all work fine. CLAUDE.md mandates `openspec/changes/<date>-<name>/`, so the two new
   changes were scaffolded under a temporary letter-first name and renamed. **This is why the three
   other in-flight date-prefixed changes cannot be driven by the CLI either.**
3. **Everything from handoff-0014's "Known-broken" list is still true** — Codex per-file paths
   (follow-up #4) not started, `AgentsPage`/`AgentDetailPanel` still unreachable (now scheduled for
   deletion by the navigation change, task 9.4), three older openspec changes still in flight.

## Files touched

`git show --stat 59216c9` — 10 files, +1188, all new. Working tree clean; nothing uncommitted.

**`openspec/changes/2026-08-07-conversation-navigation/`** (complete)
- `.openspec.yaml` — `schema: spec-driven`, `created: 2026-08-07`. Complete.
- `proposal.md` (132 lines) — Why / What Changes / Capabilities / Impact. Complete.
- `design.md` (206 lines) — Context, Goals/Non-Goals, 8 Decisions each with rejected alternatives,
  6 Risks, a 5-step Migration Plan, 3 Open Questions. Complete.
- `tasks.md` (109 lines) — 11 sections, 86 checkboxes, dependency-ordered. Complete.
- `specs/conversation-lifecycle/spec.md` (186 lines) — **new capability**, 7 ADDED requirements:
  title, origin, rename, title-generation policy, archive/unarchive, archive refusal,
  archived-send recovery. Complete.
- `specs/agent-conversation-workspace/spec.md` (302 lines) — 6 ADDED + 3 MODIFIED. The MODIFIED
  three are *Navigation lists the project and its agents as a tree*, *Only high-frequency controls
  remain visible*, *Conversation identity is readable without exposing provider identity*, each
  copied whole from `openspec/specs/agent-conversation-workspace/spec.md` and edited. Complete.
- `specs/agent-capability-plane/spec.md` (42 lines) — 1 ADDED requirement, the `send_message`
  refusal contract for an archived recipient conversation. Complete.

**`openspec/changes/2026-08-07-conversation-handoff-rework/`** (skeleton, by design)
- `.openspec.yaml` — hand-written, matching the other. Complete.
- `proposal.md` (109 lines) — opens with a STATUS: SKELETON / DO NOT IMPLEMENT block stating both
  gates and the expected validation failure. *What Changes* is explicitly marked provisional.
  *Capabilities* and *Impact* both say "Not yet determined" on purpose. Complete **as a skeleton**.
- `tasks.md` (98 lines) — Section 0 (ungated, the live stale-reference defects), Section 1 (11
  exploration tasks), Sections 2–5 marked **PLACEHOLDER — not to be started**. Complete **as a
  skeleton**.

**Files read but NOT modified** (for grounding; listed so the next session need not re-derive):
`hub/ui/src/components/layout/Sidebar.tsx`, `hub/ui/src/lib/navigation.ts`,
`hub/ui/src/api/agentChat.ts`, `hub/ui/src/components/agents/ConversationControls.tsx`,
`hub/ui/src/components/agents/AgentOutputPanel.tsx`, `hub/hub/conversations.py`,
`hub/hub/db/models.py`, `hub/hub/api/v1/agent_chat.py`, `hub/hub/api/v1/messages.py`,
`hub/hub/api/v1/agents.py`, `hub/hub/api/v1/agent_trigger.py`, `src/agentweave/templates/__init__.py`,
`scripts/sync_skills.py`, `openspec/explorations/2026-08-02-product-direction.md`.

## Key decisions

### About the product (agreed with the operator during exploration)

1. **The rail becomes three levels — project → agent → conversation — with a toggle to a flat
   recency list across agents.** Tree is the default. Rejected: flat-list-only (loses the agent
   roster, which is AgentWeave's differentiator); tree-only (loses the global recency scan that
   T3's two-level sidebar gets for free). Operator: *"A hybrid with the default being agent tree."*
2. **No hover colour tint.** Agent identity colour appears as a **persistent 2px leading edge** on
   recency rows only. Rejected hover-only tint on two grounds: it defeats scanning (you decode one
   row at a time), and it contradicts the operator's own standing directive that the UI not be
   colourful. In the tree the parent already carries the colour, so children need only an indent
   guide.
3. **Archive, not delete.** Governance is a stated product pillar and runs carry cost/usage data.
   `Conversation.lifecycle` already accepts `archived` and `latest_open_conversation` already
   filters on `open` — nothing has ever written the value.
4. **Archiving refuses rather than resolves.** A live run: refusing costs a click, stopping a run
   from a row menu destroys work with no undo. Undelivered `InboundQueueEntry` rows: this one is
   **not a preference** — `latest_open_conversation` filters on `lifecycle == 'open'`, so archiving
   strands the entry permanently; the next peer message creates a fresh conversation
   (`messages.py:93-99`) and nothing will ever deliver the old one. Rejected re-homing entries on
   archive as scope creep (invents delivery semantics to serve housekeeping).
5. **An agent sending to an archived conversation gets a failure carrying three parts**: the cause,
   the instruction to start a new conversation, and **its own submitted content restated verbatim**
   so the retry is mechanical rather than requiring reconstruction.
6. **`⋯` hover menus on rows, not right-click-only.** Operator: *"using right click is nice but not
   everyone will think about it. So your instinct to show three dots is good."* Right-click as an
   additional accelerator on the same menu was left undecided and unbuilt.
7. **Handoff gets a persistent labelled control on the conversation header**, never a menu item,
   never a row action. Operator pushed back on putting it in a menu: *"handoff need a explicit
   place to sit. Where we know it's there."*
8. **The conversation-actions overflow menu is deleted entirely.** With conversations, settings and
   handoff rehoused it holds nothing. This closes the operator's original complaint.
9. **Titles: truncate by default, model-generated as a project-level opt-in.** Truncation is the
   floor, never absent, so the tree never shows an identifier and a generation failure changes
   nothing structural. Operator: *"We start with truncate as default and the user can then toggle
   it making it his choice to spend the tokens on this."*
10. **A titling run is a one-shot throwaway spawn bound to no conversation.** `Run.conversation_id`
    is nullable, so the schema already permits it. Rejected: titling through the agent's live
    session (spends the agent's own context window on titles, in a product that warns on context
    usage, and pollutes the timeline unless suppressed); a direct provider API call (needs a
    credential surface the product doesn't have, and the operator said *"no new registry"*).
11. **`title` AND `origin`, not title alone.** `origin ∈ {operator, peer, handoff, spec, job}`,
    immutable. Peer-created conversations are real rows today and would otherwise be
    indistinguishable from operator-started ones in the tree. `handoff` and `spec` are accepted
    with no producer yet — deliberately, so retrofitting doesn't leave every existing row unknown.
12. **Conversations are created by the first message, not by the "new" action.** Preserved from
    today's behaviour (`hub/hub/conversations.py:15` is called server-side from the trigger path;
    there is no `POST /conversations`; the UI carries a `__new__` sentinel). Rejected materialising
    a row on click: buys pre-configuration at the cost of abandoned empty rows in a tree whose
    purpose is scanning. This is also what lets the title requirement be unconditional.
13. **Attention state is denormalised onto three tables.** `Question` (keyed `from_agent`) and
    `PermissionRequest` (keyed `agent`) reach a conversation only via `Run`
    (`created_by_run_id`/`run_id` → `Run.conversation_id`). Navigation reads this for every
    conversation on every SSE re-render; a two-hop join per row is the wrong shape. Mirrors the
    `batch_size` denormalisation decision from `2026-08-07-batched-operator-questions`.
14. **Selection lifts out of `AgentOutputPanel` into the destination.** Today two sources of truth
    are kept in sync by effects. The destination already carries `conversationId`
    (`lib/navigation.ts:30, 83`). The auto-select-first effect must **move up, not be deleted** —
    it is what makes "click an agent" open something — and must not fire when the destination is
    deliberately the new-conversation surface.

### About the handoff change

15. **It is a skeleton with no specs, and that is the point.** The design is not known; writing it
    now would encode assumptions instead of findings. Two hard gates recorded in its proposal: the
    navigation change ships first (it consumes `archive`/`origin`/`title`), then section 1's
    exploration completes, then design and specs are written.
16. **The one mechanism that WAS verified: delivery via `InboundQueueEntry`, not the context
    renderer.** I initially asserted the handoff summary would ride in on "turn-start injection, the
    same channel that already carries the roster, charter and queued input." That was wrong.
    `_render_hub_agent_context` (`hub/hub/api/v1/agents.py:820`) takes **no `conversation_id`** and
    writes one file **per agent** (`agent_trigger.py:339` → `.agentweave/context/<agent>.md`), so it
    structurally cannot carry something belonging to one successor conversation. The inbound queue
    is conversation-scoped by construction, delivered at turn start by existing machinery, and
    renders in the timeline.

## Constraints and user directives (verbatim)

**From this session:**
- *"So my idea is to move the conversations to the navigations on the left side as a new level to
  the agents. Like the agents as a folder so to speak."*
- *"Also new conversations should take the same shape as all the other tools. The box in the center
  just like the print."* (Referring to a T3 Code screenshot: breadcrumb `AgentWeave / New thread`,
  a large centered composer, no sidebar row for the unsent thread.)
- *"I don't know if we can make use of right clicks in the webpage but we shoujld be able also to
  delete a conversations. Change the name (Also the name should be something more user friendly).
  I believe t3 send the name to a AI. We can maybe do something similar."*
- *"Now looking into the future a new conversation spawned by a spec should carry the spec name but
  this is for later."*
- *"1: A hybrid with the default being agent tree."*
- *"2: Archive then. Governance is important."*
- *"3: Both. If the composer is being created from the tree navigation then we already know the
  agent. If it's being created from the recency view then we need an agent picker as well."*
- *"4: It should show in the tree as well."* (Peer-initiated conversations.)
- *"using right click is nice but no everyone will think about it. So your instinct to show three
  dots is good. I think we should go with that."*
- *"The hover color would be just and extra touch but I think we don't need it."*
- *"I would push a little bit against the handoff living in the right click. I'm all for getting rid
  of the barely used menu but handoff need a explicit place to sit. Where we know it's there. Users
  might not know of forget about the handoff."*
- *"We can block the run. Refuse to archive with pending messages. If an agent tried to send a
  message to a archived conversation it fails and returns saying to the agent to send to a new one
  with context about the message. Show archived is good. Unarchivable."*
- *"The naming could be a config in the project. The user can chose the operator and model or
  truncate… so only claude and codex with the existing connections so no new registry… We start
  with truncate as default and the user can then toggle it making it his choice to spend the tokens
  on this."*
- *"Let's use title and origin. Yeah let's show up to a cap with the possibility to expand if the
  user wants to."*
- *"Yeah I mean a throwaway spawn. Yeah the handoff can be it's successor."*
- *"Write the navigation proposal and the skeleton for the handoff with the directive that we should
  explore more first."*

**Carried from handoff-0013/0014 and still binding:**
- *"I don't want it to be colorful it should be like the chat box but maybe a little lighter with
  highlight on the cards just like T3. It should feel as a extension of the chat box"*
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root;
  stage paths explicitly, never `git add -A`; openspec, never aw-spec skills; `Icon` is the only
  icon system; `approve_tool_call` keeps **no return annotation**; never mark a task complete on the
  strength of a plan existing.
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking. The one commit this session was unprompted.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. **Done at
  session start** — see Verification. **Repeat next session.**

## Dead ends

- **`openspec new change` and `openspec status --change` reject any name starting with a digit**
  (*"Change name must start with a letter"*), so the repo's mandated `<date>-<name>` convention is
  unreachable through those two commands. Workaround used: scaffold under a letter-first name, then
  `mv` the directory. `openspec list`, `openspec validate --changes` and `openspec change show` all
  accept date-prefixed names fine. Do not "fix" this by renaming changes to letter-first — CLAUDE.md
  mandates the date prefix.
- **`openspec instructions <artifact> --change <name> --json` does not emit JSON** — it prints a
  banner line first, so `json.load` fails on char 0. Read it as text and `sed` out the
  `<instruction>`/`<template>` blocks instead. Same for `openspec status --json`, which prints
  `- Generating…`/warning lines before the payload in some invocations.
- **`openspec instructions` also warns `Unknown artifact ID in rules: "spec"`** on every call. Noise
  from the project's own schema config; it does not stop the command.
- **The default `python` on PATH is `C:\Users\huida\AppData\Local\hermes\hermes-agent\venv\` and has
  no pytest.** The working interpreter is
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`. `python -m pytest` at the
  repo root fails with *"No module named pytest"* and is not evidence of a broken suite.
- **My own first sketch of the handoff mechanism was wrong** — see Key decision 16. I claimed the
  summary would ride the same turn-start channel as the roster and charter. `_render_hub_agent_context`
  is agent-scoped and takes no `conversation_id`. Verifying it before writing the proposal is what
  changed the design from "thread conversation identity through the renderer" to "deliver as an
  inbound queue entry".
- **Related latent risk found while checking that:** the canonical context file path is
  `.agentweave/context/<agent>.md` — per agent, not per run — so two concurrent runs of one agent
  would race on it. Probably unreachable today; putting conversations in the rail makes "run two
  threads of one agent at once" an obvious thing to try. Recorded in the navigation `design.md`.
- Carried and still true from handoff-0014: **`pytest tests/` recreates `.agentweave/` at the repo
  root** (`setup_logging()` builds its path from the process cwd) — do not delete it as a stray, fix
  the tests; **`openspec validate` reads only a requirement's FIRST LINE for `SHALL`/`MUST`** (every
  requirement written this session puts it on line one deliberately); **`preview_click` returns a
  schema error but the click lands**; **Radix menus do not open from a synthetic `.click()`**.

## Verification

**Ran, with real output:**
- **Live verification of handoff-0014's claims, at session start** (the standing directive):
  - `pytest hub/tests/ -q` → **983 passed, 10 skipped** — matches handoff-0014's claim exactly.
  - `cd hub/ui && npx vitest run` → **528 passed, 60 files** — matches exactly.
  - Migration head `0034_add_agent_waiting_settings.py` present; all new backend/frontend modules
    from that session confirmed on disk; three openspec changes in flight as recorded.
- `npx openspec validate --specs --strict` → **24 passed, 0 failed**.
- `npx openspec validate --changes --strict` → **4 passed, 1 failed** — the 1 failure is the handoff
  skeleton, intentionally (no `specs/`).
- `npx openspec change show 2026-08-07-conversation-navigation --json --deltas-only` →
  **`deltaCount: 17`**, confirming 7 + 1 + 9 requirements all parsed rather than silently dropping.
- `git show --stat 59216c9` → 10 files, +1188, all additions.

**Explicitly NOT run/tested — do not assume:**
- **No code was written or changed this session.** No migration, endpoint, component or test exists
  for either change. Nothing in `tasks.md` is done.
- **The test suites were not re-run after the commit** — the commit adds only markdown under
  `openspec/`, so it cannot affect them, but they were not re-run.
- **`mkdocs build` not run.** **`ruff`/`tsc` not run** (nothing to check).
- No live Hub was started this session; nothing was exercised in a browser.
- The claims about the handoff feature being inert are from **static tracing only** — reading the
  prompt, the constants, and every caller of `get_skill_template`. **No agent was actually triggered
  with the handoff prompt to observe what it does.** That observation is exactly task 1.1 of the
  skeleton, and it is the reason that change is gated.

## Git state

Branch `hub-native-experience`, HEAD `59216c9`, **working tree clean**. **No upstream — nothing has
ever been pushed on this branch.** **245 commits ahead of `master`.**

One commit this session: `59216c9` *"Two proposals: conversations get a home, handoff gets a gate"*
(10 files, +1188). `4739f15` was handoff-0014's final HEAD.

**openspec in flight (5, up from 3):** `2026-07-30-hub-native-experience` (119/188),
`2026-08-04-hub-charcoal-visual-refresh` (39/42), `2026-08-04-hub-contextual-navigation` (43/45),
**`2026-08-07-conversation-navigation` (0/86, ready to implement)**,
**`2026-08-07-conversation-handoff-rework` (0/~20, gated — do not start)**.

## Next steps

1. **Start `2026-08-07-conversation-navigation` at task 1.1** — add `title` (nullable) and `origin`
   (non-null, default `operator`, check-constrained to `operator|peer|handoff|spec|job`) to the
   `Conversation` class in `hub/hub/db/models.py:224`. Then 1.2, migration
   `0035_add_conversation_title_and_origin.py`, guarding for a missing `conversations` table the way
   `0033`/`0034` do. Use the `openspec-apply-change` skill.
2. **Alternatively, do section 0 of the handoff skeleton first** — it is explicitly ungated and
   fixes live defects: `AgentOutputPanel.tsx:37-41` (`HANDOFF_PROMPT`) instructs agents to invoke an
   `aw-checkpoint` skill that is never installed (`:39`) and write to
   `.agentweave/shared/checkpoints/` which is never created (`:41`); `:43-49`
   (`RESUME_HANDOFF_PREFIX`) tells the successor to read `.agentweave/shared/context.md` at `:46`,
   which nothing writes;
   `src/agentweave/diagnostics.py:477` tells the operator to run `agentweave sync-context`, a
   command deleted in the 56→5 CLI cut. Four tasks, no dependencies.
3. **Do NOT start sections 2–5 of the handoff skeleton.** They are placeholders. Its task 1.9
   replaces them after the exploration.
4. **Decide the fate of the 3 older openspec changes** — carried unresolved from handoff-0014.
   Archiving them requires creating ten capability spec files that do not exist. Note that
   `2026-08-04-hub-contextual-navigation` (43/45) overlaps the new navigation change and should be
   reconciled with it rather than archived blindly.
5. **Follow-up #4 from handoff-0013 — Codex per-file approval paths** — still unstarted. Read
   `map_item_to_events` in `hub/hub/codex_appserver.py`; exploration only.
6. **Stop `pytest tests/` writing `.agentweave/` into the repo root** — carried from handoff-0014.
7. **The specification program remains the stated differentiator and is unstarted** — carried since
   2026-08-02. Note that `origin: spec` now exists as an accepted value with no producer, which is
   the attachment point when that work starts.

## Open questions for the user

1. **The conversation display cap** — `tasks.md` 5.4 says "a fixed number" with an expander. The
   number is a judgement to make against a real project. (Recorded as an Open Question in
   `design.md` too.)
2. **Should the recency view show archived conversations?** Currently specified as no. If the
   operator archives aggressively it may feel like data loss.
3. **Should `origin: peer` be visually distinct in the tree, or only in the conversation header?**
   The spec requires it be distinguishable; it does not say where.
4. Should `hub-native-experience` be pushed? Still no upstream, now **245** commits ahead of
   `master`. Carried unresolved since handoff-0012.
5. Should the Hub gain project/agent deletion? (Carried from handoff-0012.)
6. `npm run lint` in `hub/ui` does not start (ESLint 9, no flat config). Pre-existing.
7. Should the database backup at `C:\Users\huida\Documents\aw-db-backup-2026-08-06\` be kept?
8. Should `.claude/handoffs/` stay tracked? It is (100 files). Carried from handoff-0014; the
   operator has used them to trace development, which argues for keeping them.

## Read on resume

- `openspec/changes/2026-08-07-conversation-navigation/proposal.md` — the change to implement.
  Start here; `design.md` and `tasks.md` only make sense after it.
- `openspec/changes/2026-08-07-conversation-navigation/design.md` — the 8 decisions with their
  rejected alternatives, and the migration ordering. Read before deviating from any of them.
- `openspec/changes/2026-08-07-conversation-navigation/tasks.md` — the 86 tasks, dependency-ordered.
- `openspec/changes/2026-08-07-conversation-handoff-rework/proposal.md` — read only to understand
  why it must not be implemented, and to pick up section 0's ungated defects.
- `hub/ui/src/components/layout/Sidebar.tsx` — the rail that gains a level. The project row's
  split of expander-button and name-button (lines 158–179) is the precedent the agent row copies.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — where `selectedConversationId` lives today
  (line ~145 for the auto-select-first effect) and where the handoff prompt constants sit:
  `HANDOFF_PROMPT` at 37–41, `RESUME_HANDOFF_PREFIX` at 43–49.
