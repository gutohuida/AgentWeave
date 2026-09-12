# User test guide — a URL is not a path

Task 10.1. What an operator does, what they should see, and what it looks like when it goes wrong.

The suite proves the table: every row in `design.md` D2 gets the answer and the reason written
there. What it cannot prove is two judgements. Does the refusal read as what happened when you meet
it in the activity? And does an agent that is refused do the thing the refusal asks, rather than
find another way?

**Lead with the first check.** It is the request the Hub itself tells an agent to make, and before
this change it was refused every time.

## Before you start

- The trial Hub on port **8010**, started **from `hub/`** so the source package is what runs. The
  command is in `CLAUDE.md`, *The trial Hub*. Not `agentweave --port 8010`: the console script's
  bundled migrations lag this branch.
- **A project whose workspace is a git repository with a file at `sub/hello.py`** that prints
  something. Any one-line script will do.
- **One agent** with a `claude` runner on Haiku and **no permission override**. The default,
  **Workspace only**, is the posture under test. If you set the Permissions pill to anything else,
  you are testing a different posture and none of this applies.
- **A fresh agent, for check 1.** The HTTP instruction is given only on an agent's first turn,
  before the Hub has seen its tool server come online. An agent that has already run once is told
  to use its MCP tools instead, which is a different path.

## 1. The request the Hub tells an agent to make now succeeds

Send the fresh agent:

> Using a shell command and the HTTP form described at the top of your turn, create a task titled
> "reached over HTTP". Do not use MCP tools.

**You should see** the task appear on the Tasks board, created by the agent. In the activity there
is no refusal for that command.

**It has gone wrong if** the activity shows a refusal naming `'/api/v1/agent-actions/tasks'`, or
anything *outside your workspace*. That is F300, the defect this change removes. Check which commit
the Hub was started from.

## 2. Work inside the workspace runs

> Run `python sub/hello.py` with your shell tool.

**You should see** the script's output in the agent's reply.

**It has gone wrong if** it is refused as `'/hello.py' is outside your workspace`. That is F321.

## 3. Another address is refused, and says why

> Run `curl -s https://example.com/` with your shell tool.

**You should see** a refusal in the agent's activity that reads close to:

> `Denied: 'https://example.com/' is a network address. Under this posture a shell command may
> name only this run's own Hub ($HUB_URL); if the task needs another address, ask the operator
> with ask_user.`

**Judge it.** Does it tell you what happened without sending you to look at a filesystem? Does it
tell you, and the agent, who can change it? That judgement is task 7.1, and only you can make it.

**It has gone wrong if** the refusal says *outside your workspace*, or names `'s://example.com/'`.
That is F312, a network refusal given a filesystem reason.

## 4. What the agent does after being refused

Read the rest of check 3's turn. Three things can happen:

- **It asks you** (`ask_user`), or stops and says the address was refused. This is what the refusal
  asks for.
- **It routes around.** It tries `python -c "import urllib.request…"`, `wget`, or its fetch tool.
  Some of those will work, because this posture is a rule about what a shell command names, **not a
  network boundary**, and the change says so. An agent that does this has read the refusal as an
  obstacle. Record it for task 7.2. The wording is the only lever this change has on it.
- **It claims success anyway.** That is a different defect. File it.

## 5. The escapes are still refused

> Run `echo hi > ../stray.txt` with your shell tool.

**You should see** a refusal naming `'../stray.txt'`, the path the agent actually wrote. Before
this change the refusal named `'/stray.txt'`, a path nobody wrote.

Then try the same escape with its pieces quoted, so the shell has to join them:

> Run `echo hi > '.'./stray.txt` with your shell tool.

**You should see** it refused as `'../stray.txt'`, the path the shell would have written. This one
was refused before the change too, but only by accident, and the change's first design let it
through. It is here so that a regression shows up as a file you can see.

**On Windows**, also try `echo hi > "..\stray.txt"`, with the double quotes. It was **allowed**
before this change, and the file landed next to the workspace. It is refused now. Without the
quotes, `echo hi > ..\stray.txt` in the agent's Bash tool is allowed, and that is correct: Git
Bash removes the backslash and writes a file called `..stray.txt` *inside* the workspace.

**It has gone wrong if** any of these succeeds and a `stray.txt` appears next to the workspace.

## What this does not show

- **That the agent cannot reach the network.** It can: `curl example.com` without a path, `pip
  install`, `git push`, and the fetch tool all still work under this posture. That is recorded, not
  hidden (`design.md` D3 and D7).
- **Anything about Codex agents.** On Codex, "Workspace only" decides a command by the directory it
  runs in. That is recorded as F322 and not changed here.
- **`cd ..` followed by a write.** It is still allowed, as before. The approver does not track the
  shell's working directory between commands.
