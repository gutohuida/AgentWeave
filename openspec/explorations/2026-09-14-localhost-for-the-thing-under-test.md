# Localhost for the thing under test

**2026-09-14, day window, I-1 brief 11 of 11.** This is an improvement brief, not a proposal: there
is no change directory and no tasks. Source: `spec-queue/observations/2026-09-14-LoopEngine.md`,
`## Improvements` item 11 and `#### dev` item 6 (the refusal table).

## What we saw

**LoopEngine is a local server. The default posture would not let its agents call it.**
- **Three refusals, measured for this brief** (`event_logs`, `permission_denied`, `mode=ro`):
  - `dev`, twice at 16:58 (`run-1b9929e6d7a5`): a smoke test that started the project's server and
    called its health route on `127.0.0.1:57117`;
  - `tester`, at 18:58 (`run-d71648054489`): a probe of the served app on `127.0.0.1:57391`, a port
    it had chosen itself.
  - Each got *"… is a network address. Under this posture a shell command may name only this run's
    own Hub ($HUB_URL); if the task needs another address, ask the operator with ask_user"*.
- **The refusal was accurate, and it is the rule the operator chose.** F312's verdict (`DECISIONS.md`,
  `#### F312`, 2026-09-10) allows the run's own Hub and refuses every other URL with a reason that
  names network access. It was built by `a-url-is-not-a-path` and is required by
  `openspec/specs/agent-run-sandboxing` (*"A network address in a shell command is decided as a
  network address"*, `:516`).
- **Neither agent took the way out.** Neither called `ask_user`. Both dropped the live check:
  - `dev` cleaned up and reasoned that the in-process tests already covered the server;
  - `tester` moved on to reading the diff.

  Both concerned the server `task-b8e8b7f3beca` built: `dev` while building it, `tester` after it
  had merged (at `a212df9`, per `tester`'s own message that turn). `tester`'s rejection of its
  FR-60, for a DNS-rebinding hole, came at 18:56, two minutes before the refused probe. How
  `tester` found the hole, and whether a live probe would have found more, was not checked.
- **Codex would have answered differently.** On Codex, "Workspace only" decides a command by its
  working directory, not its text (F322, open). The same command would have run there.

## What would change

The operator can say, per project, that agents may call the project's own local server, and the
default posture then allows loopback addresses on the ports the operator named. The Hub's own
address stays allowed as today, and every other address is refused as today. The refusal, when it
fires on a loopback address, names the setting as well as `ask_user`. So the operator learns there
is a switch, and the agent learns why its probe failed.

## Why it matters

Agents building a server, a CLI with a local API, or a web app need to exercise what they built.
On LoopEngine the only evidence about the running server came from in-process tests, and two agents
quietly stopped at the boundary instead of asking. The refusal's advice to ask the operator is right
for the open internet. It is too heavy for the project's own port, which the operator set up and
would almost always allow. A per-project setting keeps the default closed for projects that never
need it.

## Rough cost — a code-read estimate

- **The rule:** `_is_own_hub` and `_judge_url` in `hub/hub/mcp_server.py` (`:1080-1123`) and the
  refusal text `_NETWORK` (`:1001-1004`), **which F354 keeps out today**. `mcp_server.py` may import
  only stdlib and fastmcp, so the allowed ports reach it as an environment variable, set beside
  `AW_PERMISSION_POSTURE` in `hub/hub/api/v1/agent_trigger.py:1136-1139`.
- **The setting:** a project column, so **a migration**. Also the project settings route, its schema,
  and a control in project settings, which is a UI bundle and falls under today's `:8000` rule.
- **Capabilities:** `agent-run-sandboxing` (the network requirement at `:516`, and *"The product
  states which postures confine a run and which do not"* at `:491`), and
  `project-environment-settings`.
- **Codex:** F322's repair would have to honour the same setting, or the two runners keep disagreeing.

## Risks and open questions

- **This widens the default posture, and that is the operator's decision.** F312's verdict rejected
  "allow all URLs" and said that real egress control would be a separate, larger decision. Loopback
  is not egress, but it does reach every local service, including a database admin port, another
  Hub instance, or a Docker API on a TCP port. So the setting should be a list of ports, not "any
  loopback", and it should be off by default. The operator may prefer to leave the rule as it is.
- **`localhost` and `127.0.0.1` are not equated** today (`_is_own_hub`'s docstring), and for a good
  reason: a DNS claim the approver cannot check. The setting would name `127.0.0.1` and `::1`
  literally.
- **A port the agent chooses** (`tester`'s 57391) would not be covered by a fixed list. Should the
  setting allow a range?
- **The other half of the gap is the ask.** Neither agent asked. If the operator keeps the rule, the
  refusal could still say more plainly that a request to the operator is expected and cheap. That
  is `a-url-is-not-a-path`'s open item 7.2 (*"Is the way out the one taken?"*), still undecided.
- **Order.** After F354, and after or with F322, so the two runners agree.

## The decision, in one line

Decide first whether the default posture may ever reach a loopback port. If yes, approve a spec
loop, on a day after F354, for *a per-project list of loopback ports agents may call*, taken
together with F322.
