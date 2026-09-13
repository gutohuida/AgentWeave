# User test guide — an absent approver is not named

What an operator does, what they should see, and what it looks like when it goes wrong.

The suite proves the command. The first run names the approver, a run after an unreported test
does not, and nothing else in the argv moves. What it cannot prove is whether the operator, looking
at the conversation and the activity, understands what happened. **Lead with check 1.** It is F299's
own configuration.

## Before you start

- The trial Hub on port **8010**, started **from `hub/`** so the source package is what runs. The
  command is in `CLAUDE.md`, *The trial Hub*. Do not use `agentweave --port 8010`: the console
  script's bundled migrations lag this branch and stop at `0081`.
- Run `claude --version` and write it down. What the **first** run does depends on it (`design.md`,
  *"Which harness behaviour this is designed for"*). On 2.1.269 the first run works until its first
  write and dies there. On the build F299 was driven on, it carried on, refused.
- **One fresh agent** with a `claude` runner on Haiku, **no permission override**, and `hub_client`
  unset. A fresh agent matters: its first run is *untested* and is supposed to keep the approver.
- To simulate a policy that blocks MCP, add these two flags to that agent's runner:
  `--settings` and `{"deniedMcpServers":[{"serverName":"agentweave"}]}`. A real managed policy
  needs an administrator path. If your organisation already blocks MCP, skip this and use the real
  thing.

## 1. A harness that blocks the Hub's server

Send the agent: *"Create a file called hello.txt containing the single word ok."*

**First run. Expect it to behave as it did before this change.** On 2.1.269 the agent tries to
write the file, and the run fails at that moment. Its conversation shows, in order:
`Warning: MCP server blocked by enterprise policy: agentweave`, the agent's `Write` call,
`Error: MCP tool mcp__agentweave__approve_tool_call … not found`, and that error again as the
`Write`'s failed result. The run's usage reads as unavailable, although a model call was made.

Send the same message again.

**Second run. This is the change.** Expect:

- the run **completes** rather than failing, and takes a model turn, so it costs a little;
- no `hello.txt` in the agent's workspace;
- the conversation still shows the `Warning … blocked by enterprise policy` line, followed by the
  agent asking you to approve the write;
- **in the activity, a `permission_denied` line reading roughly *"`<agent>` refused Write: Refused
  by Claude Code: no approver was available to this run."*** Before this change there was none. The
  file's path is **not** on that line, because the activity never shows a refusal's detail, Codex's
  included. Use the entry's copy button: the path is in the copied JSON's `detail`.

**It has gone wrong if** the second run fails exactly like the first (the approver is still named),
if `hello.txt` exists (something widened the posture, which must never happen), or if the activity
shows no refusal.

The line's wording, *"`<agent>` refused Write"*, reads as if the agent did the refusing. Note
whether that misled you. It is the shipped wording for every refusal, not this change's.

## 2. A harness that allows it, for a fresh agent

Remove the two `--settings` flags, create a **second fresh agent** with the same runner, and send it
the same message.

**Expect the file to be written on the first run**, with no approval asked of you. That is the case
this change must not break: every new agent's first turn keeps its approver.

**It has gone wrong if** that first run is refused the write. That would mean the Hub has taken "no
evidence yet" for "evidence of absence".

## 2b. A typo is not evidence

Create a **third fresh agent** with the same runner, and add `--no-such-flag` to its runner's flags.
Send the message. **Expect the run to fail at once** with `error: unknown option`. Remove the flag,
and send it again.

**Expect the file to be written**, with no approval asked of you. The first run never got as far as
starting the Hub's server, so it says nothing about whether this machine allows it.

**It has gone wrong if** the second run is refused the write.

## 3. Lifting the policy

Go back to the agent from check 1, remove its `--settings` flags, and send the message twice.

**Expect the first of the two to be refused the write**, because the Hub still has only the old
evidence. **Expect the second to write the file**, because the server reported in during the first,
so the approver is back.

**It has gone wrong if** every run after lifting the policy stays refused.

## What to report

For each check, give the Claude Code version, the run ids, and whether the activity showed the
refusals. For check 1, say in a sentence whether you could tell from the screen **why** the run
could not write. The Hub adds no explanation of its own in this change (`design.md` D7). If the
answer is "only because I knew", that is a finding worth filing. It is not a failure of this change.
