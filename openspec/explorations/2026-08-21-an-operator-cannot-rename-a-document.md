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
