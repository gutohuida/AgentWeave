# The Hub owns the specification document

## Why

**A user cannot author a specification today, and the reason is structural rather than a missing
feature.** Three independent breaks, each verified in code:

**1. The storage the specification surface reads from can no longer be filled.**
`hub/hub/api/v1/spec.py` stores documents in `project_specs`, a push-fed content cache whose own
docstring states its purpose — *"synced to the Hub so the UI can display them without filesystem
access."* Its only writers are `HttpTransport.push_spec` and `reconcile_specs`
(`src/agentweave/transport/http.py:555,576`), and **those two methods have no callers at all**. Their
docstrings say "called at watchdog startup… plus manually via `agentweave spec push`" — the watchdog
is deleted and that command is among the 51 removed from the CLI. The live database holds 3 stale
`project_specs` rows and **0** `project_spec_snapshots`. The Spec tab reads a cache nothing can
write.

**2. The authoring procedure was delivered through skills that no longer install.**
`src/agentweave/templates/skills/aw-spec-*.md` ships 1,306 lines of procedure plus 796 lines of
reference, and **no code anywhere writes `.claude/skills/`**. Even when it did, the channel was
runner-specific: `.claude/skills/` is read by Claude Code, so *a Codex agent could never invoke
`aw-spec-propose` under any circumstances* — while the seeded charter instructed every agent to use
it.

**3. The premise the cache was built on is gone.** `project_spec_snapshots` exists to reconcile
"possibly multiple machines syncing the same project." A local Hub owns projects bound to one
canonical directory each, by `canonical_path_key` plus the `.agentweave/project.json` marker. And the
blindness that justified a cache no longer exists in **either** deployment mode: native leaves
`AW_WORKSPACE_ROOT` unset with no containment restriction (`project_workspace.py:89`), Docker mounts
a real root, and `ProjectWorkspace.resolve_relative` (`project_workspace.py:62-71`) gives
containment-checked, traversal-free reads in both.

So the specification program is not blocked on a design question. It is blocked on the fact that its
storage, its delivery channel, and its architectural premise were each removed by changes that had
other subjects.

The design this change implements is `openspec/explorations/2026-08-12-spec-hub-integration.md`.
**Read §7 before starting** — this is change 1 of five, and five of its requirements exist only to
keep changes 2–5 possible.

## What Changes

- **Documents live in the project working directory.** The Hub reads and writes them through
  `ProjectWorkspace`. The push apparatus is deleted: both endpoints, both tables, the drift and TTL
  machinery, and the two unreachable transport methods.
- **The agent submits JSON; the Hub renders HTML.** A new `submit_spec_document` tool takes a
  structured payload validated against a versioned schema. An agent never writes specification HTML
  again, which retires 713 lines of format conventions from every model's context permanently.
- **The Hub mints requirement identifiers**, and they survive rewording and schema changes. An agent
  that invents its own reintroduces exactly the drift stable identifiers exist to remove.
- **A document has a phase, and the Hub owns the transitions.** `exploring → proposed → approved`,
  with entry conditions checked by code. **The agent cannot approve.** This is the property no skill
  could ever have: today `aw-spec-apply.md:33-51` enforces the approval gate by having the agent grep
  its own permission slip.
- **The self-checks become validators.** `aw-spec-propose.md:230-259` asks the model to verify its
  own document and report the result — the `unverifiable_claim` failure mode by construction. Orphan
  requirements, orphan tasks, missing modal verbs, empty non-goals and unresolved clarification
  markers become blocking checks the Hub runs.
- **Every write records an attributed event and a content digest**, from the first document, even
  though nothing in this change consumes either. Neither can be backfilled.
- **A minimum procedural floor ships in the per-turn context**, so a project with no charter still
  produces a valid document. The *obligation* to interview is code; the *skill* at interviewing is the
  charter, harvested in commit `2909137`.

## Capabilities

### New Capabilities

- `spec-document-authority`: where a specification document lives, who may write it, how it is
  identified, what phase it is in, and who may move it between phases. Four requirements are carried
  forward verbatim in intent from `spec-manifest-sync` — discovery, home selection, visible
  degradation, subscriber refresh — because they describe a document tree rather than a sync.

### Modified Capabilities

- `spec-chat-session`: the operator gains an entry point that creates an empty document in
  `exploring`, and the per-turn context that already names the open document also names its phase.

### Removed Capabilities

- `aw-spec-workflow` (10 requirements): describes authoring through the `aw-spec-*` skills, which
  nothing installs and which one of the two supported runners can never invoke. Two of its
  requirements describe technical exploration, dropped by operator decision.
- `spec-manifest-sync` (9 requirements): built on the push model. One of them — *"Spec
  synchronization remains backward compatible"* — is compatibility with a client that no longer
  exists.

## Impact

**Removed** — `hub/hub/api/v1/spec.py` loses `POST /project/specs/sync` and
`POST /project/specs/reconcile`; `ProjectSpec` and `ProjectSpecSnapshot` are dropped by migration;
`HttpTransport.push_spec` and `reconcile_specs` are deleted. `src/agentweave/spec_manifest.py` and
its Hub counterpart lose the snapshot/drift half and keep path validation and manifest parsing.

**Added** — a document store reading through `ProjectWorkspace`; a payload schema and validator; a
renderer; an identifier minter; a phase machine with an append-only transition log; one MCP tool.

**Migration** — one guarded migration dropping two tables, with head assertions bumped in both
`hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`.

**Skills** — `src/agentweave/templates/skills/aw-spec-*.md` and `references/` are deleted against the
disposition table in §6 of the exploration. Their judgment landed in
`hub/hub/data/charters/spec.md` in commit `2909137`, ahead of this change.

## Non-Goals

- **Not creating tasks from the specification.** That is change 2, and it needs the requirement
  identifiers this change mints.
- **Not building evidence links, relevance judgement, rigor levels, or the independence check** —
  §2.3, §2.4, §2.5. Change 3.
- **Not building rejection categories or reviewer telemetry** — change 4.
- **Not building the hand-edit resolution interface.** The digest ships here; what the operator does
  about a conflict is change 5. Until then a divergence is reported and nothing is overwritten.
- **Not freezing the payload contract.** §3.5 of the exploration is binding: gates and traceability
  have not stated their requirements on it. The contract is versioned rather than final, and unknown
  fields survive a round trip so a later change can extend it without migrating documents.
- **Not changing how a conversation works.** `spec-chat-session` shipped the composer, the
  conversation reuse and the document-beside-chat layout; this change adds a phase to what it already
  reports.
