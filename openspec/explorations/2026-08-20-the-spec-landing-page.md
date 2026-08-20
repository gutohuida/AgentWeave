# Exploration — The spec landing page (2026-08-20)

**Status:** Stub. One of eight explore pages opened 2026-08-20 covering the open backlog. Nothing
decided.

**Origin:** item 5 of the operator's twelve:

> *"The spec main page is weak; wants an overview of the project, navigation, features, with detail
> in the other folders."*

---

## What exists today

- `spec/agentweave.html` — an authored system map, the corpus `home`. It exists and is committed.
- `spec/index.json` — an ordered list of 33 documents, authored order, writable since `8a8f0aa`.
- `spec/capabilities/` — 34 documents, one folder each.

The raw material for a good landing page is therefore already on disk. What the Spec tab renders
from it is the open question — and note that **right now it renders nothing at all**, because
`spec_documents` is empty (see `2026-08-20-adopting-documents-that-already-exist.md`). This item is
partly blocked behind that one: it is hard to judge a landing page for a corpus the app cannot see.

## What "weak" might mean — to be established with the operator

The complaint names three wants: **overview of the project**, **navigation**, **features**. Those
are three different pages in most products, and the exploration should find out whether the operator
means one page doing all three or a structure:

1. **Overview** — what this project *is*. Prose, authored, changes rarely. `spec/agentweave.html`
   is already an attempt at this; the question is whether it is being surfaced, or is weak.
2. **Navigation** — getting to the 34 documents without scrolling a flat list. The authored order in
   `index.json` is a first answer; grouping, search, or a tree is a different answer.
3. **Features** — a view *derived* from the corpus: what capabilities exist, what phase each is in,
   what has coverage. This one cannot be authored, only computed, and it is the one that most needs
   document rows to exist.

## Open questions

1. **One page or three?** See above. This is the first thing to settle, because it determines whether
   this is a design task or an information-architecture task.
2. **Authored versus derived.** `spec/agentweave.html` is hand-written; a features list is computed
   from rows. Mixing them on one page means part of it goes stale silently and part cannot.
3. **Is `spec/agentweave.html` the landing page, or a document that happens to be first?** The corpus
   calls it `home`. Whether the Spec tab treats it specially is worth checking.
4. **What does a landing page look like for a project with no documents yet?** Every fresh project
   starts there, and the empty state is most of the first impression.
5. **Does this wait for adoption?** Probably yes for the derived parts. The authored overview could
   ship first.
6. **How much of this is really the T3 reference?** `reference_t3_code_source_reference` is the
   operator's endorsed UI reference; worth looking at how it handles a document corpus before
   designing from scratch.

## Size

Unbounded until question 1 is answered — "the main page is weak" can mean a stylesheet or an
information architecture. Likely the largest of the eight in design effort, and it is the one most
worth prototyping in front of the operator rather than specifying.
