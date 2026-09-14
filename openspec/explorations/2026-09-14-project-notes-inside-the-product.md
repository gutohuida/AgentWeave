# Project notes inside the product

**2026-09-14, day window, I-1 brief 8 of 11.** This is an improvement brief, not a proposal: there
is no change directory and no tasks. Source: `spec-queue/observations/2026-09-14-LoopEngine.md`,
`## Improvements` item 8, `### Architect` items 2, 8 and 9, and `#### tester` items 2 and 3.

## What we saw

**The four agents kept their shared knowledge where AgentWeave cannot see it.**
- **Where.** The harness's own memory directory for the project root holds 18 notes and an index,
  written between 09-13 20:11 and 09-14 07:56. The harness keeps 33 other directories for
  LoopEngine's checkouts: each agent's worktree, each review checkout, and each task worktree. None
  of them has a memory directory, so every agent wrote to the one under the root, from whichever
  checkout it ran in. The FR-70 note, for one, came from a session in `tester`'s worktree.
- **What they hold**, paraphrased:
  - *how AgentWeave behaves*: the guard's refusals and a long list of workarounds; that no agent can
    reassign a task; that a `completed` task cannot be sent back; not to complete a task you will
    review (`tester`, after the 20:45 refusal); route every evidence decision through `tester`;
    check `list_tasks` before fixing anything (`dev_2`, 19:13);
  - *decisions waiting on the operator*: two notes record evidence held undecided until an open
    operator question is answered, and name the question. One adds that `get_answer` answers 404 for
    it (brief 7, `a-peer-can-see-the-answer`);
  - *review state*: what to re-check on four tasks under review.
- **It worked, in a way.** The harness loads the index into every session in that project, so a
  lesson one agent learned reached the other three on their next turn. It is the only channel the
  agents had that carried a lesson forward, and they found it themselves.
- **It cost a warning per write.** Twelve of the Architect's 21 outside-workspace warnings were these
  writes, and the other agents' notes raised the same warning.
- **One of the notes is wrong.** It says the guard's boundary follows the shell's current directory.
  `_decide` resolves relative words against the workspace root and never sees a `cd`
  (`hub/hub/mcp_server.py:1308-1311`). Nobody who could correct it could see it.

## What would change

What an agent learns about the project, and about working in it, is kept by the Hub where the
operator can read it, correct it and delete it, and every agent on the project gets it at turn start
whichever harness it runs. The project already has one operator-owned text that reaches every turn:
the **Project Instructions**, rendered as `## Project Instructions` in the canonical context. The
improvement adds a second, agent-writable section beside it, **project notes**:
- an agent adds or replaces a short, named note through a tool;
- the operator sees the notes in the app, with who wrote each and when, and can edit, delete or
  promote one into the instructions;
- the notes are rendered into every turn's context after the instructions, capped, and marked as
  agents' notes rather than the operator's word.

## Why it matters

It helps the operator most. On LoopEngine the agents' shared understanding of the product lived in a
place the operator never looks, including one wrong rule about the guard and two
records of evidence held for the operator's answer. It helps agents on another harness: a Codex agent
on the same project would have seen none of the 18 notes. And it removes a warning per write. Several
notes are also findings about AgentWeave, written by its users. A notes surface the Hub owns is one
this repository can read.

## Rough cost — a code-read estimate

- **Storage:** a new project-scoped table, **a migration**. `ProjectInstructions` is one operator
  text per project (`openspec/specs/project-instructions`), so notes do not belong in it.
  `CheckpointNote` (`hub/hub/db/models.py:1725-1759`) is consumed by one checkpoint and is not a
  store.
- **Write:** an agent action route (`hub/hub/api/v1/agent_actions.py`) and a tool in
  `hub/hub/mcp_server.py`, **which F354 keeps out today**. Until then, the route alone is reachable
  over the HTTP form.
- **Read:** the context builder `_render_hub_agent_context` (`hub/hub/api/v1/agents.py:1495`), after
  the instructions section at `:1968-1972`.
- **UI:** a notes list on the Instructions page (`hub/ui/src/components/instructions/`), with delete
  and promote. The UI bundle is subject to today's `:8000` compatibility rule.
- **Capabilities:** `project-instructions`, `agent-capability-plane`, `agent-tool-surface`.

## Risks and open questions

- **The harness's own memory will still exist.** The Hub cannot stop an agent writing there, and it
  does not set Claude Code's memory location (no `CLAUDE_CONFIG_DIR` or settings flag in
  `hub/hub/runner_commands.py`). The briefing would have to point agents at the product's notes and
  say why. Whether to also switch the harness's memory off for spawned runs is a separate decision.
- **Notes are prompt text an agent wrote and every agent reads.** They are an injection channel from
  one agent into another's turn. The cap, the attribution, and the operator's delete are what bound
  it. Should a note need the operator's approval before it reaches other agents?
- **Notes go stale.** Two of LoopEngine's are about decisions since made. Should a note name the task
  or question it depends on, and lapse with it?
- **Overlap with checkpoints.** A checkpoint carries continuity for one conversation. Notes are
  project-wide and outlive conversations. The spec loop must keep the two from blurring.

## The decision, in one line

Approve a spec loop, on a day after F354, for *agents keep project notes in the Hub, visible to and
editable by the operator, rendered into every turn*, with the operator choosing whether a note needs
approval first.
