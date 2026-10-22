---
description: What AgentWeave writes in your project and on your machine, what to commit, and what moves between machines.
---

# Project files

## In your project

```text
my-project/
├── .agentweave/                 # the Hub's working files (kept out of git automatically)
│   ├── project.json             # binds this folder to its project id
│   ├── worktrees/<agent>/       # each writing agent's own checkout (branch agentweave/<agent>)
│   ├── tasks/<task-id>/         # each task's checkout (branch agentweave/task/<task-id>)
│   ├── reviews/<agent>/         # detached checkouts for review turns
│   ├── context/                 # the context rendered for each agent's turn
│   ├── calls/  reads/           # aw-tool arguments; large spec reads
│   └── logs/  evidence/
├── spec/                        # specification documents: commit these
│   ├── index.json               # the corpus map: home, and each document's place
│   ├── journey.json             # optional: this project's own spec steps
│   ├── changes/<name>/spec.json
│   └── capabilities/<name>/spec.json
└── knowledge/sources/           # vault sources stored "in the repository": commit these
```

### `.agentweave/`

The Hub's own working state for the project. It holds no secrets. The Hub adds its directories to
**`.git/info/exclude`**, not to your `.gitignore`, so they never show up in `git status` and the
Hub never needs to commit anything to hide them.

`project.json` holds a version and the project's id. It is what lets a renamed or moved folder keep
its identity, and what stops a copied folder from silently merging with the original. If you move
a project, use **Locate project** in its settings to rebind it.

### `spec/`

Ordinary project content. Commit it. Each document is a `spec.json` holding the structured content
plus a `hub` block (`phase`, `rigor`, `step`, `size`). It is written deterministically, so diffs
stay readable. The rendered page is produced on read and is never stored. The Hub writes these
files in your root checkout and does not commit them. You do, along with your other changes.

`index.json` is written only when you rebuild or arrange the index from the Spec tab. A document
created since the last rebuild is listed under *Missing* until you do.

Editing a `spec.json` by hand is detected: the document is flagged as *diverged* from what the Hub
last wrote, and the Hub does not silently pick either version.

### `knowledge/sources/`

Vault sources you chose to keep **in the repository**. Private sources live outside the project
(below), with only a stub here.

## On your machine

```text
~/.agentweave/hub/
├── .env                         # generated: the instance key and ticket secret
├── data/agentweave.db           # the default instance's database
├── profiles/<name>/             # each --profile instance's own database and state
├── vaults/<project>/            # private vault sources
├── tool-server/<digest>/        # the pinned tool server agents run
└── hub.pid                      # process identity while running (hub-<port>.pid on other ports)
```

`agentweave reset` deletes the database, and `--all` deletes the `.env` and the logs too. Neither
ever touches your projects.

## What moves between machines

| Travels with the folder (in git) | Stays in this machine's database |
|---|---|
| `spec/` documents and their index | Tasks and their history |
| Requirement identifiers (in each document) | Evidence, reviews and coverage |
| Tracked vault sources | Conversations, runs, traces and usage |
| `.agentweave/project.json` (if you copy the folder) | Agents, runners, charters, settings |

Another Hub opening the same repository rebuilds its requirement index from the documents. A spec
file it has no record of can be **adopted** from the Spec tab, and the file's phase is taken as
written.
