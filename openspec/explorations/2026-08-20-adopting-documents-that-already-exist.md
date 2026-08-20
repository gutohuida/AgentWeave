# Exploration — Adopting documents that already exist (2026-08-20)

**Status:** Stub. Opened at the operator's request as one of eight explore pages covering the open
backlog, to be explored properly before anything is designed or built. Nothing here is decided.

**Origin:** finding 17 of `2026-08-20-dogfooding-findings.md`, restated in handoff 0062 and 0063 as
the largest single blocker to using the product.

---

## What the problem is

`spec/capabilities/` holds **34 capability documents**, one per folder, tracked in git. Every one of
them is self-describing: all 34 carry an embedded `<script type="application/agentweave-spec+json"
id="aw-spec-payload">` block with title, kind, summary, requirements — verified 34/34 on
2026-08-20.

The Spec surface does not read the disk. It reads `spec_documents` rows. That table is **empty**.
So the corpus is invisible to the product built around it.

The only path that creates a row is `POST /documents` — and it destroys the file it is pointed at.
`hub/hub/api/v1/spec.py:1131-1153` creates the row, then immediately calls
`spec_service.save_document` with a **placeholder** payload (`"title": body.title or UNTITLED`),
which renders fresh HTML over the path. Point it at an existing document and you get a row plus an
empty stub where your document was.

So: the corpus cannot be brought into the Hub, and the one door into the Hub eats what you carry
through it.

## What already exists that a fix would use

- `hub/hub/spec_payload.py:297` — `extract_payload(document)` reads the embedded block back out.
  It is the exact reverse of the renderer that wrote these files, and it returns `None` rather than
  guessing when a document has no payload block.
- `spec/index.json` — lists 33 of the 34 documents in an authored order. The two it omits
  (`project-instructions`, `quiet-hours`) read `unfiled`.
- `spec/agentweave.html` — the authored system map, the corpus `home`.

The reading half is built. What is missing is a create-a-row-without-writing path.

## Open questions

1. **One document, or the directory?** Adopting `spec/capabilities/agent-charter/spec.html` by path,
   versus a single "adopt everything under `spec/`" sweep. The corpus case wants the sweep; the
   agent-authored case (see `2026-08-20-agents-starting-their-own-documents.md`) wants the single.
2. **A file with no payload block** — hand-written, or from a version predating the block. Refuse?
   Adopt with a minimal row derived from the `aw-spec-*` meta tags? `extract_payload` deliberately
   does not guess, so this is a real decision, not an implementation detail.
3. **Re-adopting a path that already has a row** — error, or refresh the row from the file? The
   second is close to "the file is the truth", which fights `content_digest`'s premise that a file
   edited outside the Hub is a conflict to report, never to silently resolve.
4. **What `phase` an adopted document lands in.** `create_document` sets `CURRENT` for
   `kind == "capability"` and `EXPLORING` otherwise (`spec_lifecycle.py:151`). Does an adopted
   document trust the `aw-spec-status` meta tag in the file instead? A file can claim any phase, and
   the row exists precisely because phase must not live where the gated party can write it.
5. **`content_digest` on adoption** — set it from the file as found, so a later external edit is
   still detectable? That seems right, but it means adoption asserts "this file is as the Hub would
   have written it", which for a converted corpus may not be byte-true.
6. **Is this a new endpoint or a flag on `POST /documents`?** A flag risks the destructive default
   staying one missing parameter away.

## Why it is worth doing first

Requirements, tasks, evidence and coverage all hang off a document row. Without rows none of that
machinery has a subject — so this blocks not only the Spec tab but items 5, 9 and 11 of the
operator's list, which all assume documents exist in the database.

## Size

Modest in code — one path reusing `extract_payload`. The cost is in the six questions above, which
are about what the Hub believes a file *is*, and are worth settling explicitly.
