# Background work ends with the turn

**2026-09-14, day window, I-1 brief 10 of 11.** This is an improvement brief, not a proposal: there
is no change directory and no tasks. Source: `spec-queue/observations/2026-09-14-LoopEngine.md`,
`## Improvements` item 10 and `#### dev` item 7.

## What we saw

**An agent started a test run in the background, said it would wait for it, and ended its turn.**
- **Twice, on `dev`.** Sessions `79131de2` (20:58) and `6623a907` (05:04) each ended with `dev`
  saying it would wait for a background test run's completion notice. The turn ending is the process
  ending. Neither session was resumed with the result.
- **Once, the notice came a run late.** In session `078560c0` the notice did arrive, but in the
  *next* run (`run-d479bd1e1710`, 00:45:27), after `run-539bd1d44ea1` had died on the Hub's own
  database lock (F359). It helped only because the next run resumed that session.
- **The model's assumption is reasonable.** In an interactive session a background command's result
  comes back into the conversation later. A Hub turn has no later: the Hub treats the turn as over
  when the `claude` process exits.
- **Unverified:** whether the harness kills the background process when it exits, or leaves it
  running with nobody to read its result. O-2 did not check, and this brief did not either.

## What would change

An agent knows, before it starts something long, that nothing outlives its turn except what it
records. The briefing says so in two sentences: *a turn ends when you stop, and anything you started
in the background will not report back to you; wait for it, or run it in the foreground, before you
end the turn.* If the work genuinely cannot finish in the turn, the agent says so in the task or the
evidence rather than promising to wait. As a second, separable part, the Hub notices a turn that
exits while a process it started is still running, records that on the run, and ends that process.
The operator then sees "this turn left a test run behind" instead of a turn that claims to be
waiting.

## Why it matters

It is cheap and it removes a failure that looks like progress. A turn that ends *"waiting for the
test results"* reads, to the operator and to the flow, like work in hand. On LoopEngine, two of
`dev`'s turns ended with no verdict on their own tests, and a third got its verdict only by the
accident of a resumed session. What `dev` did next in those sessions was not read. Every agent that
runs a slow suite meets this, which is every agent that tests.

## Rough cost — a code-read estimate

- **Part 1, the sentence:** the canonical context's tools section
  (`hub/hub/api/v1/agents.py:1450-1455`), under `agent-context-onboarding` (*"Canonical per-agent
  runtime context"*). A search of `hub/hub` for "background" and `run_in_background` finds no
  prompt string today. No migration, no API change, no UI.
- **Part 2, the leftover process:** the turn is decided at process exit
  (`hub/hub/api/v1/agent_trigger.py:2231`, then `:2272-2273`). The `result` event is read only for
  usage (`hub/hub/runner_parsing.py:306`). After a normal exit the `finally` block only drops the
  pty from `active_ptys` (`agent_trigger.py:2494-2495`). The only tree kills are an operator stop
  (`:1635`) and Hub shutdown (`:1680`), through `terminate_process_tree`
  (`hub/hub/pty_runner.py:202-213`, `taskkill /F /T` on Windows). Detecting survivors needs the
  run's descendants before the pty closes. Recording them is a run event, not a column. It touches
  `agent-conversation-workspace` and `turn-outcome-visibility`.
- **Not `mcp_server.py`.** Both parts can be built today.

## Risks and open questions

- **Part 2 could kill something wanted.** An agent may start a dev server the operator asked to
  keep running. Should the Hub end leftover processes, or only record them? Recording is the safe
  first step. Ending them is the operator's call.
- **The descendant walk is unreliable on Windows.** The pty's host process is not the `claude`
  process, and an earlier drive measured `OpenConsole.exe` as "the child" (FINDINGS, the orphan
  measurement near `:11700`). Part 2 must use the pid the Hub recorded (`runs.pid`).
- **A possible link, not confirmed:** four task-worktree releases on Windows failed with *"failed to
  delete … Permission denied"* (the observations file, *Not sorted*). A leftover test process
  holding files in the worktree would produce that. Nobody has checked which process held them.
  Part 2's record would answer it.
- **Codex** runs through a pipe session with its own process group (`pty_runner.py:353`). Whether it
  has the same shape was not read.

## The decision, in one line

Approve a spec loop for part 1, *the briefing says background work ends with the turn*, which is
small and buildable today. Take part 2, *record a turn's leftover processes*, into the same loop
only if R1 finds the Windows descendant walk solid.
