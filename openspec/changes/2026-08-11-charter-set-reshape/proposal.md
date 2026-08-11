# Charter set re-shape (B0)

## Why

A charter is injected into an agent's context verbatim. It is instruction, not documentation — and
`openspec/specs/agent-charter/spec.md:82-83` already says so: a seeded charter "MUST NOT instruct an
agent to read a file the system does not create, run a command that does not exist, or address a
participant the roster does not contain."

**The 21 seeded charters violate all three clauses.** Verified in the tree, 2026-08-11:

| Defect | Evidence | Charters affected |
|---|---|---|
| Addresses an absent participant | escalation to a "Tech Lead" that exists only if the operator happened to create one | **16 of 21** |
| " | defers to a "Coordinator" | 8 |
| " | defers to a "Project Manager" | 4 |
| Cites an absent command | six `aw-spec-*` skills; nothing installs them (below) | `spec.md` |
| Reads an uncreated file | `shared/design-*.md`, `.agentweave/shared/plan-[task-id].md` | `backend_dev`, `frontend_dev`, `tech_lead`, `coordinator` |
| Asserts absent behaviour | "the Hub discovers every safe `spec/**/*.html` … independently of `spec/index.json`" | `spec.md` |
| Self-enforces a shipped gate | "no implementation begins until … `aw-spec-status` flips to `approved`" | `spec.md` |

Three of these need saying precisely, because each is a mechanism that *used* to exist:

- **The skills do not install.** `src/agentweave/templates/skills/*.md` holds all six `aw-spec-*`
  templates, but **no Python reads that directory** — the reduction to five CLI commands removed
  whatever placed them. The only `.claude/skills/` reference left in the product is
  `hub/hub/workspace_paths.py:3`, the composer's `@path` filter, which surfaces skills the *operator*
  put there. An agent following `charters/spec.md:39-47` looks for six skills nobody shipped it.
- **The Hub does not discover spec files.** `hub/hub/api/v1/spec.py:71,213` stores an inventory a
  *client* supplies as `discovered_paths`. The rglob is in `src/agentweave/spec_manifest.py:90`, on
  the CLI side — reachable from the skills that no longer install. The charter promises the agent a
  discovery that nothing performs.
- **The approval gate moved into code.** `2026-08-10-task-transition-machine` (B1) shipped and is
  archived. A charter asking a model to enforce a gate the transition service now owns is asking for
  the gate to be enforced twice, inconsistently — and the model's copy is the one with no authority.

Why the defect survived a test written to catch exactly it: `hub/tests/test_agent_facing_text.py`
checks a fixed `REMOVED_SUBSYSTEMS` needle list covering *files and commands*. It has no assertion
for the third clause — the absent participant — which is the one 16 charters break.

Underneath the honesty defects is a structural one. Applying the accountability test from
`openspec/explorations/2026-08-10-charters-phases-and-the-spec-on-ramp.md` §1 — **a charter answers
"what am I accountable for", a phase answers "what am I doing right now"** — the starter set is the
deleted role subsystem under a new name: six flavours of developer that differ only by technology,
three charters asking a model in prose to do the coordination now being built in code, and several
that describe an activity rather than a responsibility. And not one of the 21 is non-software, which
undercuts the claim that AgentWeave serves domains with real separation of duties.

Now, because every additional seeded charter is another thing a new operator must read past to find
the one they want — and the organising constraint is ease of use.

## What Changes

- **BREAKING (new projects only): the seeded charter set goes from 21 to 9.** Seeding is
  once-per-project (`agent-charter` "Seeding does not repeat"), so existing projects — including the
  operator's Testbed — keep every charter they have. Nothing is deleted from a live database.
- **Six developer variants collapse into one `developer` charter carrying an explicit scope line.**
  `backend_dev`, `frontend_dev`, `fullstack_dev`, `devops_engineer`, `data_engineer`, `ml_engineer`
  are the same accountability — build the thing — differing only in subject matter, which is scope,
  not responsibility.
- **Three coordination-as-prose charters are removed**: `coordinator`, `model_router`,
  `project_manager`. Asking a model in prose to route work and pick models is the "guarantee is
  vibes" shape; that coordination is the transition machine and the model catalogue, in code.
- **Activity charters are removed and their content parked, not discarded**: `explorer`,
  `implementer`, `context_keeper`, and the procedural bulk of `spec`. These describe what an agent is
  *doing*, which is a phase's job. Phase guidance does not exist yet, so the text is parked inside
  this change for the change that builds it rather than left seeding or silently dropped.
- **`architect` folds into `tech_lead`, `qa_engineer` into `verifier`, `technical_writer` into
  `developer`'s scope** — in each pair the two names denote one accountability.
- **Two non-software charters are added**: `underwriter` and `underwriting_approver`. Underwriting is
  the exploration's decisive example precisely because underwriter and approver are not two
  activities one capable model can perform interchangeably — they are two accountabilities, and the
  separation between them is the point.
- **Every surviving charter is rewritten** to name no absent participant, file, command, or
  mechanism, and to stop restating procedure that belongs to a phase or is enforced in code.
- **The absent-participant clause gains a scenario and a test.** A charter naming a roster
  participant fails the suite, so this class of defect cannot return silently.

## Capabilities

### New Capabilities

None. This changes the content and composition of a shipped capability; it introduces no new
behaviour surface.

### Modified Capabilities

- `agent-charter`: the seeding requirement changes from "one charter per previously-bundled role
  guide" to a curated set defined by the accountability test; the "describe only what the runtime
  provides" requirement gains the missing absent-participant scenario and a requirement that the
  starter set demonstrate a non-software separation of duties.
- `aw-spec-workflow`: "The spec role routes instead of duplicating procedures"
  (`openspec/specs/aw-spec-workflow/spec.md:132`) mandates the skill routing that is now broken. It
  changes to require that the charter route only to mechanisms the project actually has, and that
  the approval gate is described as enforced by the transition service rather than by the agent.

## Impact

**Charter data** — `hub/hub/data/charters/`: 15 `.md` seeds removed, 3 added (`developer`,
`underwriter`, `underwriting_approver`), 6 rewritten, and `charters.json` re-keyed.

**Seeding paths** — both readers of the manifest are unaffected in mechanism and will simply seed
fewer records: `hub/hub/db/engine.py:149`, `hub/hub/project_lifecycle.py:198`.

**Tests that will break, and must** — `hub/tests/test_agents_self_registered.py:91` looks up
`"Backend Developer"` by name; `hub/tests/test_charters_api.py` derives expectations from the
manifest and so follows automatically. `hub/tests/test_agent_facing_text.py` gains the
absent-participant assertion and loses nothing.

**Not touched:** the charter API, the UI, the database schema, and any live project's charter rows.
No migration is required — this changes what a *fresh* project is given, not what any project holds.

## Non-Goals

- **Not building phase guidance.** The removed activity content is parked for it. Deciding what a
  phase is, and how its guidance reaches a turn, is later work.
- **Not migrating existing projects.** No backfill, no reconciliation, no prompt to adopt the new
  set. An operator's authored and edited charters are theirs.
- **Not adding a charter UI affordance** for browsing or re-seeding the starter set.
- **Not reinstating the `aw-spec-*` skills.** Whether that workflow returns, and in what form, is
  B2/B5's question. This change stops the charter from promising it today.
- **Not settling how many charters is right in general** — only what this starter set should be.
- **Not restoring the role subsystem** under any name.
