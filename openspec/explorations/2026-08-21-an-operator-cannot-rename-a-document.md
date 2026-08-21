# Exploration — An operator cannot rename or delete a specification document (2026-08-21)

**Status:** OPEN. Found by hitting it, 2026-08-21.

## The gap

There is **no operator route to rename a document, and no route to delete one at all.**

- Rename exists only as `POST /api/v1/agent-actions/spec/documents/rename`, which requires a run
  token. An operator credential cannot reach it.
- Delete does not exist in any form. Checked the OpenAPI surface: no `DELETE` on any document
  route, and no retire/archive equivalent for documents.

Clearing a document created by accident meant editing `spec_documents` by hand and moving the file
on disk.

## Why it matters more than it sounds

A document is created **before** anyone knows its subject, under a deliberately meaningless
placeholder — a colour and a mythic animal. That is by design (`create_spec_document`). The rename
is what makes the placeholder temporary. If the rename never happens — an agent that stops early, a
document an operator started themselves — the placeholder is permanent and only an agent can fix
it.

**Measured cost, same session:** a leftover `scarlet-yeti/` folder led the operator to report
`agent-created-documents` check 6.3 as failing. It had not failed; the agent's own rename was
clean. The operator was looking at a placeholder nobody could clear. A leftover placeholder name is
indistinguishable, to a reader, from that check failing.

## A second, smaller thing worth folding in

`POST /project/spec/documents/arrange` refuses a document that is not yet in the on-disk index, and
creating a document does not index it. The working order is **create → reindex → arrange →
reindex**. The refusal says only:

```
spec/capabilities/<name>.html is not in the index
```

which does not say that reindexing is what fixes it.

## Open questions

1. Should an operator rename, or only re-target the placeholder? Renaming moves a file that may
   already be linked from other documents' maps.
2. Delete, or archive? The corpus already has an archive concept for documents that shipped;
   a never-completed placeholder is a different case.
3. What happens to requirements, tasks and evidence attached to a deleted document? The fixture
   removed by hand had four `spec_document_events` rows and would have had tasks.
4. Should an unrenamed placeholder expire, or be surfaced as drift rather than needing a delete?

## Measured again, 2026-08-22, at a larger scale

The operator asked for the trial's scaffolding to be cleared: two `spec/changes/` documents, the
six-task fixture board, the two agents (`speccer`, `builder`), and — added mid-cleanup — the whole
`aw-loop10` project. **None of it was reachable through the product.** The Hub offers
`POST /agents/{name}/archive` (reversible), plus archive for jobs, loops and conversations, and
`DELETE /api/v1/projects/{project_id}` for a whole project. For a document or a task it offers
nothing.

### How it was actually resolved — and why that matters to the design

The first attempt was SQL surgery: 61 hand-written statements across 34 tables, 1,589 rows. It
worked and the Hub started clean afterwards. **It was also the wrong answer, and the operator said
so:** for a trial database the cheap move is to delete the file and let the next startup rebuild
it. That took minutes, ran all 84 migrations green, and produced a provably clean instance.

That contrast is the useful finding, not the row count:

- **Recreating is only cheap because the corpus does not live in the database.** `spec/` and
  `spec/index.json` are on disk and in git. A fresh instance re-adopted all 41 documents and
  regenerated all 452 requirements with `POST /project/spec/adopt` followed by a reindex, landing
  on exactly the counts the surgical route had produced. The database is a projection; the
  documents are the source.
- **So the delete question is narrower than it looks.** An operator who wants one document gone
  cannot recreate the instance to get it — they would lose agents, conversations, evidence and
  task history, none of which is reconstructible from disk. That asymmetry is the argument for the
  feature: recreating is fine for a trial, useless for real use.
- **The project marker survived, which is what made recreation safe.** `.agentweave/project.json`
  still named `proj-5e960453`, and `POST /projects/open` honoured it, so the fresh instance came
  back with the same project id. Every doc, handoff and CLAUDE.md reference stayed accurate.

### What a product delete would still have to own

The SQL pass is worth keeping as a measurement of the blast radius. Two documents and six tasks
reached into `spec_requirements`, `spec_requirement_revisions`, `spec_document_events`,
`task_dependencies`, `task_integrations`, `task_requirement_links`, `task_transitions`, and —
through the runs that produced them — `agent_outputs`, `messages`, `questions`, `turn_usage`,
`inbound_queue_entries` and `event_logs`. A document is not a row; it is a subtree. That is a
strong argument for **archive over delete**: a phase change touches one row and leaves the subtree
addressable.

Two traps any such feature has to avoid, both hit during the SQL pass:

1. **Agent names are unique per project, not globally.** `aw-loop10` had its own `speccer` and
   `builder`. A delete keyed on the agent *name* without a project scope would have destroyed 8
   conversations and 8 runs in a project nobody asked to touch. Caught before applying, only
   because the row counts did not match the project-scoped counts.
2. **Deleting by `run_id` can sweep history off documents you are keeping.** Rows in
   `spec_document_events` and `spec_requirement_revisions` are keyed to the run that wrote them, so
   "delete everything these runs did" silently rewrites the history of unrelated documents. It was
   safe here only because the overlap happened to be zero — which had to be checked, not assumed.

And it manufactures debris: the deletions orphaned 44 further rows — conversations whose agent no
longer existed, `apscheduler_jobs` rows pointing at absent `ai_jobs`, and an `agents` row for
`proj-21cfa499`, a project not in the `projects` table at all. That last one **predates this
session**, which is evidence that partial deletion has happened before and left debris nobody
noticed. Whatever ships should be transactional over the closure.
