# Permission postures

A **posture** is what a run may do without asking you. You pick one per turn from the composer's
Permissions pill, set an agent's default in its settings, or set the **project's default** for
every agent in the project's settings. The order is: the conversation's choice, then the agent's
default, then the project's, then the built-in default described below. An agent's default wins
over the project's in either direction, so one agent can be narrowed below a generous project or
widened above a careful one.

**The boundary is a guardrail against an agent's mistakes, not containment.** The Hub's judge reads
what a call *says* -- its path argument, its command text -- not what the process then does. It
stops an agent that reaches for the wrong directory; it does not stop a process that is trying to
get out. Choose the posture with that in mind.

This page states, **per posture**, whether a file write is checked against the run's own workspace.
It deliberately does not state it per execution mode — see [Why this is not stated by
mode](#why-this-is-not-stated-by-mode).

## A workspace is a working directory, not a wall

Every agent run is given a directory to work in — its own git worktree, a task checkout, or the
project itself — and the Hub records it as the run's workspace. That is where the run *starts*. It
is not a wall around it.

An agent that writes to a relative path stays there. An agent that writes to an **absolute** path
writes wherever that path points: another agent's worktree, your own checkout, anywhere on the
machine the agent process can reach. Whether anything stops it depends entirely on the posture, and
under two of the four postures below nothing does.

Where no posture is checking, **you are the boundary**. The Hub's answer to that is not a wall it
does not have: a write that leaves the workspace is **recorded rather than prevented**. The run row
keeps the destinations, shown beneath that run in the conversation, and you get one notice per
destination in the agent's activity — after the write, saying where it went. That holds under every
posture, Full access and granted roots included.

## What each posture checks

| Posture (composer label) | Id | A file write outside the run's workspace |
|---|---|---|
| **Workspace only** | `workspace` | **Checked by the Hub.** Each tool call is routed through the Hub's approval tool, which compares the path against the run's own workspace and refuses one that lands outside it. The refusal is recorded. |
| **Ask me** | `manual` | **Put to you.** The same routing, but you answer the card instead of the Hub. Approved, the write happens; it is recorded as an outside write, not as a refusal. |
| **Edit files** | `acceptEdits` | **Not checked.** Edits are accepted with no path comparison at all. |
| **Full access** | `bypassPermissions` | **Not checked.** No approval step exists to check anything. |

The built-in default for a Claude run that states no posture is **Workspace only** — so the posture
most operators run under *does* check, and the common claim that a natively-executed agent is
entirely unchecked is false. The one exception is a run with no Hub tool server configured: there is
no approver to answer, so it falls back to **Edit files**, which checks nothing.

**Full access means all of it**, for Claude and Copilot alike, and for a turn opened on a
specification document too: its requests other than file edits are allowed. A specification turn
still writes no file, under any posture -- that is the specification turn's role, not a reach limit.

### Granted reach: between Workspace only and Full access

Under **Workspace only** you can grant more without giving up the check. In the project's
settings (or an agent's, which then replaces the project's grants whole -- an empty list narrows
the agent back to its workspace) list:

- **Roots**, each **read** or **read/write**: an absolute path, `{temp}` (the machine's temporary
  directory) or `{project}` (the project's own directory, useful for an agent working in a
  worktree). A read root covers the read tools (`Read`, `Glob`, `Grep`, `LS`, Copilot's read); a
  shell command needs a read/write root, because a shell word cannot say whether it reads or writes.
- **Hosts** a shell command may name: `localhost:*`, `127.0.0.1:8000`, `registry.npmjs.org`,
  `*.pypi.org`. A bare host allows any port.

Everything not granted is refused exactly as before. Grants apply to Claude and Copilot runs;
Codex runs keep Codex's own sandbox.

**Docker mode confines at the mount, whatever the posture is.** A containerized Hub can only see
what is mounted beneath its configured workspace root, so a path outside it does not resolve to
anything the agent can write. That is containment by construction, and it is orthogonal to the table
above rather than a replacement for it.

### What the check does not cover

The check reads the *declared path argument* of a file-writing tool call, and the record of what
left the workspace is built from the same argument. Two consequences are worth knowing, both
recorded as findings rather than fixed:

- **A shell command declares no path.** `Bash` carries a command string, so nothing extracts a
  destination from it and **no shell write is ever recorded**, under any posture. Under **Workspace
  only** the approval tool reads the command text as the tool's shell (bash or PowerShell) will read
  it — quotes removed, joined words joined — and resolves each path it finds, relative or absolute,
  against the run's workspace; a word whose destination the shell decides only at run time (a
  variable, `~`, a command substitution) is refused rather than guessed. That is enough to refuse
  what the text spells, not enough to be a wall: a `cd` in an earlier call, or a path a program
  builds for itself, never appears in the text, and the tool describes itself accurately as *a
  boundary, not a sandbox*. It also lets a shell command name only one network address, the run's
  own Hub (`$HUB_URL`), and refuses `curl https://example.com/x` for naming another. That is a rule
  about what the command's text may say, not a network boundary: an address the text does not spell
  as a URL (`curl example.com`) is not recognised as one, and `WebFetch` is not checked at all.
  Under the postures that check nothing, a shell redirect leaves no trace at all.
- **A link is followed, but the path you are shown is the one the agent typed.** A symlink or
  junction inside the workspace pointing out of it is resolved before the comparison, so the write
  is correctly refused or correctly recorded as outside. What is reported alongside that verdict is
  the declared path, which reads as inside. The verdict is right; the path beside it is not the one
  the write landed on.

An empty record therefore means *no file-tool write left the workspace* — not *nothing left the
workspace*.

## Why this is not stated by mode

The tempting one-liner — that a natively executed agent is unchecked while a containerized one is
confined — is close enough to sound right, and is wrong in both directions.

It is wrong about native execution, because the default posture there **does** refuse a path outside
the run's workspace, per tool call. Telling an operator running the default that nothing is checking
would be false.

It is wrong about Docker, because the postures that check nothing exist under Docker too. The mount
is a real boundary and the workspace check is still absent — so telling an operator on **Full
access** that "Docker confines" answers a different question than the one they asked.

What a run's writes are checked against is a property of the **posture**. What a run's process can
reach at all is a property of the **deployment**. Stating either one in the other's terms produces a
sentence that is true of nobody.

## Related

- [Dashboard guide](../guides/dashboard.md) — where the Permissions pill and the agent default live
- [Environment variables](env-variables.md) — `AW_WORKSPACE_ROOT` and the Docker mount
