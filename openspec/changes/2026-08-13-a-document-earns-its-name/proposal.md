# A document earns its name

## Why

**A specification document is named before anyone knows what it is.**

The path is minted in the browser, from whatever text the operator happened to type first.
`hub/ui/src/components/agents/NewConversationSurface.tsx:75` slugifies the operator's *entire
opening message*; `hub/ui/src/components/agents/ConversationView.tsx:165` slugifies the conversation
title, falling back to the literal `exploration`. So the first live run of the flow produced a
document whose subject turned out to be a houseplant watering tracker, at a path derived from a
sentence written before the interview had asked a single question.

This is backwards in three separate ways:

1. **The name is decided at the worst possible moment.** The whole point of the exploring phase is
   that the subject is not yet known. Deriving a permanent identifier from the first sentence
   guarantees the identifier records the operator's opening guess rather than the finding.
2. **It reads as meaning when it has none.** `spec/changes/i-want-to-track-my-plants/spec.html`
   looks like a considered name. `spec/changes/exploration/spec.html` — the fallback — collides with
   the next exploration and is refused as `document_exists`.
3. **Two call sites derive it differently.** One uses the raw first message, the other the
   conversation title, which may itself have been rewritten by a model. The same operator action
   through two doors produces two different names.

Meanwhile the agent *does* learn what the document is, usually within one turn, and has no way to
say so. It mints a real `title` in the payload — `Personal Houseplant Watering Tracker` — and that
title lands in the database beside a path that still says something else.

## What Changes

- **New documents get a deliberately meaningless placeholder**, minted by the Hub: a colour and a
  mythic animal, `spec/changes/amber-griffin/spec.html`, drawn fresh each time. A name that
  obviously carries no meaning cannot be mistaken for one that does, and it is memorable enough to
  say out loud while it lasts.
- **Path minting moves out of the browser.** `POST /project/documents` accepts a request with no
  path and returns the one it minted. Both UI call sites stop deriving names, and the divergence
  between them disappears with the code.
- **The agent renames the document as soon as the interview establishes what it is.** A new
  `rename_spec_document(path, subject)` tool takes a *subject* — prose, not a slug — and the Hub
  slugifies it. The exploring turn notice tells the agent to call it once it knows.
- **A rename moves the file, the `path` column, and any not-yet-delivered queue entry pointing at
  it.** Nothing else refers to a document by path in a way that survives the request.
- **Two readability defects found reading the first agent-authored document** (task 6.1 of
  `2026-08-13-the-spec-tool-reaches-the-agent`): acceptance criteria render in payload order, so a
  reader scanning by requirement hits `FR-8, FR-8, FR-7`; and an empty open-questions list renders
  as nothing at all, so "asked and resolved" is indistinguishable from "never asked".

## Capabilities

### Modified Capabilities

- `spec-document-authority`: a document's path SHALL be minted by the Hub as a meaningless
  placeholder and SHALL be renameable, by subject, until it is approved.
- `agent-tool-surface`: the agent SHALL be able to rename the document it is exploring.

## Impact

**Behaviour** — a new document is `spec/changes/amber-griffin/spec.html` until the agent knows
better, then `spec/changes/houseplant-watering-tracker/spec.html`. An operator who names nothing
gets a working document instead of a collision with the last one.

**API** — `DocumentCreate.path` becomes optional; the response already carries the path. One new
agent route, one new MCP tool.

**UI** — `documentPathFor` is deleted along with both its call sites' use of it; the create response
becomes the source of the path. The open-document reference follows a rename.

**No migration.** `SpecDocument.path` already exists and is already mutable; the rename event reuses
`spec_document_events`, whose `kind` has no CHECK constraint.

## Non-Goals

- **Not renaming documents that already exist.** Settled with the operator. The two documents on
  disk today keep their paths; this governs documents created from here.
- **Not renaming after approval.** An approved document's path is part of what was approved, for the
  same reason `save_document` refuses to rewrite approved content.
- **Not letting the agent choose the slug.** It supplies a subject; the Hub slugifies. A tool that
  accepted a path would let an agent write to an arbitrary location under `spec/`, and the
  validation that stops that is worth keeping as the only door.
- **Not rewriting `spec/index.json`.** The Hub reads that file and has never written it. A manifest
  entry naming a renamed document becomes a `missing` entry, which existing diagnostics already
  report — that is a truthful result, and editing a file the operator owns to hide it is not.
- **Not making the placeholder stable or derivable.** It is random on purpose. Anything reproducible
  invites being treated as identity, and identity is `SpecDocument.id`.
