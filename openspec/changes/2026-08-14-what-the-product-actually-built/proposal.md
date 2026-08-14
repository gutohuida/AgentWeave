# What the product actually built

Everything here comes from one end-to-end run:
`openspec/explorations/2026-08-13-loop5-integration-reports-success-while-integrating-nothing.md`.
A project was driven from nothing — interview, 19-requirement specification, tasks, a builder that
wrote 38 passing tests — and four things were found that 1819 passing unit tests could not see,
because every one of them lives between two features rather than inside one.

## Why

**Approving a task merged `master` into `master`, recorded `outcome: merged`, and reported
`FR-7 → verified / integrated` — while every line of the product sat on `agentweave/builder` and
`master` contained only a README.**

```
task_integrations:  commit=6425180  source=master  target=master  outcome=merged
git ls-tree -r --name-only master   →   README.md
```

Evidence footprints are captured from the **project root's** git HEAD. Agents do not work there —
`worktrees.py` gives each agent `.agentweave/worktrees/<agent>` on `agentweave/<agent>`. So the
footprint names whatever the operator's checkout happens to be sitting on, `reachable_from_main`
compares `master` to itself and returns true, and `git merge <ancestor>` prints "Already up to date",
exits 0, and creates nothing — which `integrate()` records as a merge.

B3 built `verified, not integrated` precisely so `verified` could never describe code that never
ships. This is that guarantee inverted into the exact false positive it existed to prevent.

Three structural gaps came out of the same run:

- **No agent can read a specification.** The tool surface has `submit_spec_document` and
  `rename_spec_document` and no read. Both runners hit it independently; the builder implemented an
  approved document from a paraphrase the architect reconstructed from context.
- **Requirement links carry no statement text** — only an identifier and an anchor into a document
  the agent cannot open. B3's own user guide claims otherwise.
- **An approved document produces no work**, even though it already declares its own tasks.

## What Changes

- **A footprint names the work.** Agent-recorded evidence is footprinted from that agent's worktree.
  Operator-recorded evidence keeps the project root, which is genuinely the operator's own checkout.
- **A commit already in the target is `skipped`, never `merged`.** The guard that makes the failure
  visible, independent of everything else.
- **Reachability is re-answered after a merge**, because `reachable_from_main` is written once at
  capture and nothing has ever updated it.
- **Drift compares against the branch a footprint names**, not against a root — otherwise every
  accepted requirement becomes a candidate the moment footprints move.
- **An agent can read the document it is implementing**, through a real tool, in any phase.
- **A task carries its requirements' statements**, read from the document rather than stored.
- **Approval creates the tasks the document declares.** The convention already exists and nothing
  consumes it.
- Housekeeping: a seeded `.gitignore`, a title that survives a rename, and prose that stops being
  reported as an unresolved requirement.

## The convention that already existed

The approved document's payload declares tasks — `key`, `description`, and the requirement **keys**
each serves. `aw_identity.requirements` maps those keys to minted identifiers. `spec_payload`
validates that they resolve. `spec_completeness` reads them. **Nothing materialises them.**

In the run the architect wrote six tasks into the document and then hand-created three different ones
through `create_task`, because the document's own tasks are inert. This change consumes what is
already there rather than inventing a second format.

## Capabilities

### Modified Capabilities

- `task-lifecycle-governance`: integration SHALL NOT report a merge for a commit already in the
  target, and approval SHALL create the tasks its document declares.
- `spec-document-authority`: evidence SHALL be footprinted against the work it describes, drift SHALL
  be assessed against the line of work a footprint names, and a renamed document SHALL carry its new
  subject as its title.
- `agent-capability-plane`: an agent SHALL be able to read a specification document.
- `local-project-workspace`: a registered project SHALL be seeded with ignore rules for the artefacts
  the system itself creates.

## Impact

**Behaviour** — the demonstrable outcome: *a task approved on work an agent did in its own worktree
has that work on the main branch when the transition returns, and coverage says `integrated` because
it is.* Today that is unreachable, and the answer given instead is a false one.

**Schema** — `Task.spec_document_id` and `Task.spec_task_key`; migration `0071`.

**Risk** — coverage answers move for existing projects. Agent evidence flips from `integrated` to
`not_integrated` at capture, and back to `integrated` after a real merge. That is the fix working,
and it will look like a regression to anyone who does not know why. The reachability refresh exists
so the second half actually happens.

**What let this ship** — the tests written for the integration change used branch-switching inside a
single repository with no worktree at all, and the suite's autouse fixture resolves any project to
`tmp_path`. Both are shapes AgentWeave never produces. The new tests build the arrangement the
product actually creates.

## Non-Goals

- **Not the prose-interview backstop.** The operator's decision, verbatim: *"that's okay because this
  is an AI test. The AI should answer or not deliberately… The operator will answer those questions
  when he's working on it."*
- **Not narrowing footprint entries to changed paths.** `EvidenceFootprint.entries` stores the whole
  tree while the model documents "changed paths", so one unrelated commit drifts every requirement at
  once. Pre-existing, real, and a separate change — fixing it here would hide this one.
- **Not per-task branches**, not GitHub, not un-merging. Carried from the previous change.
- **Not assigning the tasks approval creates.** Who does the work is a roster decision, not something
  a specification should dictate.
