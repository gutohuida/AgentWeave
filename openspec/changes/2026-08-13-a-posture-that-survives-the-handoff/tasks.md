# Tasks — A posture that survives the handoff

Both defects were found by driving the product, not by reading it, and neither was visible to the
1693 tests that were passing at the time. They are recorded in
`openspec/explorations/2026-08-13-explore-to-development-end-to-end.md` as F2 and F3.

## 1. The default posture lets an agent verify its own work

- [x] 1.1 `DEFAULT_CLAUDE_PERMISSION_MODE` becomes the workspace posture.
- [x] 1.2 `DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER` — the fallback for a run with no Hub
      tool server, because `workspace` is `manual` plus an answerer and naming an absent approver
      refuses everything.
- [x] 1.3 `_build_claude_command` decides the fallback posture once, before assembling flags, so the
      approver flag and the mode flag cannot disagree about which posture is in force.
- [x] 1.4 The default emits `--permission-prompt-tool`, not only an operator-chosen posture.
- [x] 1.5 `workspace` is spelled `manual` to Claude; that translation stays in one place.
- [x] 1.6 Module docstring records both moves of this default and why each was wrong.

## 2. A chosen posture survives a new conversation

- [x] 2.1 `conversations.inherit_runtime_overrides(session, conversation)` — copies the agent's most
      recent overrides into a conversation that states none.
- [x] 2.2 `UNINHERITED_PERMISSION_MODE` — `bypassPermissions` is never carried forward.
- [x] 2.3 Values are copied, not shared, so the two conversations stay independent.
- [x] 2.4 Wired into the two paths where nobody was asked: peer messages (`messages.py`) and
      scheduled jobs (`scheduler.py`).
- [x] 2.6 **Not** wired into the operator's own new-thread branch. `agent-conversation-workspace`
      requires a conversation the operator starts to begin clean, and
      `test_agent_trigger_overrides.py` pins it. Found by that test failing — the first
      implementation was wrong and the requirement was right for the case it described.
- [x] 2.5 Not wired into `agents.py`'s agent-creation path — a brand-new agent has no earlier
      conversation, so it would be a no-op. `checkpoint_cutover` already inherits explicitly from
      its predecessor and is left alone.

## 3. Tests — agent-verifiable

- [x] 3.1 `test_permission_approver.py` — the default is the workspace posture, spells itself
      `manual`, and names its approver exactly once.
- [x] 3.2 `test_permission_approver.py` — a run with no tool server falls back to the posture that
      needs no answerer and names no approver.
- [x] 3.3 `test_agent_default_permission_mode.py` — an agent with no configured default now gets the
      workspace posture with an approver; a conversation that states its own posture still beats
      both defaults.
- [x] 3.4 `test_override_inheritance.py` — **new**, 8 tests: the posture is inherited; nothing is
      inherited without an earlier conversation; the most recent overrides win; `bypassPermissions`
      is dropped while other overrides survive beside it; stated overrides prevent inheritance;
      the two conversations do not become coupled; another agent's overrides are not taken.
- [x] 3.5 `pytest hub/tests/ -q` and `pytest tests/ -q`, run separately.
- [x] 3.6 `ruff check hub/ src/`, `black` on every file touched.
- [x] 3.7 `npx openspec validate --changes --strict`.

## 4. Human-only verification

Not assertable by a test — they need the running app and a person watching.

- [ ] 4.1 **Does a Claude agent now verify its own work unprompted?** Run a build turn with no
      permission choice at all and read the transcript: it should run its tests without the operator
      selecting anything, and without the "requires approval" refusal.
- [ ] 4.2 **Does the posture survive the hop?** Set a posture in the composer for agent A, then have
      a *peer or a job* — not the operator — open a new conversation for **that same agent A** (for
      example, have a different agent `send_message` to A) and confirm A's new conversation still
      carries the posture A last had. This is what `agent-conversation-workspace`'s "peer-opened
      conversation keeps what the operator chose" scenario and `test_another_agents_overrides_are_not_inherited`
      actually specify: inheritance is per-agent history, not propagation to a different recipient
      agent. Driven live 2026-08-15 (see judgement-evidence.md) — the wording here previously
      described testing it by messaging a *second, different* agent and expecting that agent's run
      to also ask the operator; that is **not** what the spec requires or the code does (confirmed:
      a fresh second agent's run, triggered by the first, runs under the plain default with no
      operator involvement at all), and following the old wording would make working, spec-correct
      behaviour look broken.
- [ ] 4.3 **Is the workspace boundary still felt?** Ask an agent to touch a file outside its
      worktree under the new default and confirm it is refused, and that the refusal is legible.
- [ ] 4.4 **Judge the wider execution surface.** The default now permits commands inside the
      worktree that it previously blocked. Watch one real build turn and decide whether what it runs
      is what you want agents running unattended.

## 5. User test guide

**Setup.** Hub restarted onto this change. A project with a Claude-runner agent bound.

1. **An agent can verify itself.** Trigger a turn asking the agent to write a small script *and run
   it*. Choose no permission posture.
   - *Expect:* it runs. Before this change it reported `This command requires approval` with nothing
     able to grant it, and could only offer a manual trace.
2. **The boundary still holds.** Ask it to read a file outside its own worktree.
   - *Expect:* refused, with a reason naming the workspace.
3. **The posture survives a handoff.** In the composer set Permissions to *Ask me* for agent A, send
   a turn, then have a *different* agent `send_message` to A so that A's next conversation is opened
   by a peer rather than by you.
   - *Expect:* **A's** new run also asks you — the same agent's own choice followed it across the
     hop. Before this change it silently reverted to the default. (The other agent's own run is
     unaffected either way — overrides are never propagated to a different recipient agent, by
     design; do not expect that agent to ask you too.)
4. **Full access does not spread.** Set Permissions to *Full access* for agent A, have a peer open a
   new conversation for A (as in step 3).
   - *Expect:* **A's** new conversation does **not** carry full access — it falls back to the
     default, because `bypassPermissions` is the one posture never inherited even across A's own
     history.
5. **A stated choice still wins.** Send a turn with an explicit posture into a thread that would
   otherwise inherit a different one.
   - *Expect:* the stated one is used.

**Where it would go wrong:** if step 1 still refuses, the run has no Hub tool server and took the
fallback — check the spawn command for `--permission-prompt-tool`.
