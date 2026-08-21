# Tasks — corpus-aware documents

Groups 1–3 are useful shipped alone: a flat corpus where every document links home already beats
thirty-five islands. Groups 4–6 add the arrangement.

## 1. Corpus context, and a renderer that ignores it

- [x] 1.1 Define the corpus-context value passed to rendering: the home path, the parent entry (path and title) or `None`, and the ordered children (path, title, kind, phase, summary). Plain data, assembled by the caller — `spec_render.py` must not reach the database or the filesystem, and does neither today. Landed as `CorpusChild`/`CorpusContext` frozen dataclasses in `spec_render.py`, next to `render_document` since they describe its own contract; no new import beyond `dataclasses`/`typing`.
- [x] 1.2 Add the parameter to `render_document` with a default of `None`. Added as a keyword-only `corpus: Optional[CorpusContext] = None`, documented in the docstring as unused until §2–3 land.
- [x] 1.3 Assert byte-identical output for every existing caller when no context is supplied. This is the test that lets groups 2–6 land without re-reviewing every rendered document. Landed as two tests in `test_spec_render.py`: one pins a sha256 digest of a rich document's rendered output captured before `corpus` existed (so a future change to the `corpus is None` branch that alters output fails loudly), the other asserts omitting `corpus` and passing `corpus=None` produce identical strings.
- [x] 1.4 Build corpus context from a `Manifest` in `spec_documents.py`: children resolved by `parent`, ordered by `order`, summaries read from each child's own file payload. Landed as `spec_documents.build_corpus_context(manifest, path, summaries)` — pure over a manifest and a precomputed summaries map, no filesystem access itself. Not yet called from any route; §4 (reindex) is where it gets wired in.
- [x] 1.5 Decide and record how a child's summary is obtained without reading 33 files on every render — a single pass over the corpus per rebuild, not a read per child. **Decision:** `spec_documents.corpus_summaries(workspace, manifest)` walks `manifest.documents` once, reading each document's file and extracting its payload's `summary` field into a `{path: summary}` map (omitting empty/missing ones — the renderer, not this function, decides what an absent summary looks like, per §3.4). A rebuild calls this once and passes the same map into every `build_corpus_context` call for the documents it re-renders, so N re-rendered documents cost the O(corpus) pass once, not once per document times its child count.

## 2. The navigation region

- [x] 2.1 Render the home link on every document; suppress it on the home document itself. Landed in `spec_render._navigation`: suppressed when `corpus.path == corpus.home`. `CorpusContext` gained a `path` field (the document's own path) so the renderer can tell — `build_corpus_context`'s existing `path` argument is threaded through, no new caller-side plumbing.
- [x] 2.2 Render the parent link where a parent is recorded; render nothing where it is not. `_navigation` renders it only when `corpus.parent is not None`; home link and parent link are independent, so a document can have neither, either, or both.
- [x] 2.3 Compute links as relative paths that resolve from the document's own location on disk, not from a URL the Hub serves. `spec/capabilities/x/spec.html` reaching `spec/agentweave.html` is `../../agentweave.html`. Landed as `spec_render._relative_link`, `posixpath.relpath` unconditionally (not `os.path`, since corpus paths are always `/`-separated regardless of the Hub's own OS) — verified this exact example in `test_relative_links_climb_out_of_nested_directories`.
- [x] 2.4 Style the region within the existing inline stylesheet — no new external resource, per `render_document`'s standing rule. `.aw-nav` added to `_STYLE`. This is unconditional, like every other rule already in `_STYLE` (`.aw-chip-rigor-contract` is present even in documents whose rigor isn't `contract`) — so it appears in every document's `<style>` block whether or not that document has a `corpus`, which is why the §1.3 baseline digest moved and was recaptured, documented inline where it lives.
- [x] 2.5 Test that a rendered file opened from disk with no Hub running resolves both links. `test_a_rendered_file_opened_from_disk_resolves_both_links_with_no_hub_running` writes a rendered document and its home to real nested directories under `tmp_path` and resolves the emitted `href` with plain `Path` arithmetic — no HTTP server anywhere in the test.

## 3. The generated map

- [ ] 3.1 Render a map section on any document with children; render none where there are none.
- [ ] 3.2 List each child with title, kind chip, phase chip and summary, linked relatively.
- [ ] 3.3 Order children by recorded `order`, not alphabetically.
- [ ] 3.4 Render "no summary yet" in the existing `aw-empty` style where a child's summary is empty or is placeholder text (design D8). Decide and record what counts as placeholder — two documents currently begin `TBD - created by syncing change`.
- [ ] 3.5 Label the region visibly as generated, so an operator hand-editing the file knows what will be overwritten.
- [ ] 3.6 Decide the open question in design: recursive on the home, direct children elsewhere. **Ask the operator before implementing** — it changes what the home document is.

## 4. Regeneration on reindex

- [ ] 4.1 In `POST /project/spec/reindex`, after `write_index`, compute the set of documents whose navigation or map the rebuild changed. Compare against the previous manifest — the route already reads it as `existing`.
- [ ] 4.2 Re-render exactly that set: read file, `extract_payload`, render with fresh context, write.
- [ ] 4.3 Skip and report a document whose file carries no readable payload. Never render from guessed structure.
- [ ] 4.4 Record a `rerendered` event, distinct from `content` (design D6), so history separates regeneration from authorship.
- [ ] 4.5 Update `content_digest` for re-rendered documents that have a row (design D7).
- [ ] 4.6 Re-render documents with no row too — they have no digest, and skipping them would leave adopted-later documents permanently without navigation.
- [ ] 4.7 Return the re-rendered and skipped sets in the reindex response.
- [ ] 4.8 Test the bound directly: adding one document under an existing parent re-renders that parent **and nothing else**. Assert the exact set of touched files, not just that the map is correct.
- [ ] 4.9 Test that a rebuild changing nothing writes no file.
- [ ] 4.10 Test that an approved document regenerates rather than being refused.
- [ ] 4.11 Test that drift is not reported after a regeneration, and *is* reported after a subsequent outside edit.

## 5. Setting a document's place

- [ ] 5.1 Add `POST /project/spec/documents/arrange` — path plus parent path or `null`. Operator-only; the agent capability plane gets no equivalent.
- [ ] 5.2 Validate through the manifest's existing rules: unknown parent, self-parent, cycle. Do not reimplement them — `spec_manifest.py:236-274` already has all three.
- [ ] 5.3 Rewrite the index and re-render the affected set (the moved document, its former parent, its new parent).
- [ ] 5.4 Broadcast `spec_updated` so the rail and any open document refresh.
- [ ] 5.5 Schema for request and response, including what re-rendered.
- [ ] 5.6 Tests for each refusal, and for the placement surviving a subsequent rebuild.

## 6. The arrangement itself

- [ ] 6.1 Create the six area documents through `POST /project/documents` — the correct route, since these are genuinely new. Kind `system-map` (design, open question 3).
- [ ] 6.2 Author a short narrative for each: what this area of the product is, in a paragraph. The map beneath it is generated.
- [ ] 6.3 Set each area's parent to `spec/agentweave.html`.
- [ ] 6.4 Set each of the 32 filed capability documents' parent to its area, per design D4.
- [ ] 6.5 Reindex and confirm the home and all six area maps regenerated, and nothing else did.
- [ ] 6.6 Enrich the home document's authored narrative — the "thin" complaint is about this prose, and the generated map does not replace it.
- [ ] 6.7 **Content backlog, tracked separately:** the eight documents with no usable summary (design D8). They will render as gaps until written. Do not treat writing them as part of this change's completion.

## 7. Verification an agent can do

- [ ] 7.1 `py -3.11 -m pytest hub/tests/ -q --ignore=hub/tests/browser` passes.
- [ ] 7.2 `py -3.11 -m pytest tests/ -q` passes.
- [ ] 7.3 `ruff check hub/`, `black --check hub/`, `mypy hub/hub/` clean on touched files.
- [ ] 7.4 Task 1.3's byte-identity assertion still passes after all six groups.
- [ ] 7.5 Confirm `SpecTree`'s path-prefix rendering was not changed — it is a stated non-goal, and it is the kind of thing that gets "improved" while nearby.
- [ ] 7.6 Confirm neither `spec_manifest.py` twin diverged; if either was touched, synchronise both and run `hub/tests/test_spec_manifest_roundtrip.py`.
- [ ] 7.7 Confirm no external resource was introduced into a rendered document — grep the rendered output for `http://`, `https://`, `<link` and `<script src`.

## 8. Verification only a human can do

These need the operator, a browser, and a real corpus.

- [ ] 8.1 **The home stops being thin.** Open the Spec tab with nothing selected. The home opens and shows the narrative followed by six areas, each with a real one-line description.
- [ ] 8.2 **The map is navigable.** Click through home → area → capability → back up. Every hop works and lands where expected.
- [ ] 8.3 **The corpus reads outside the app.** Open `spec/agentweave.html` directly in a browser with the Hub stopped. The map renders, and every link resolves.
- [ ] 8.4 **The first reindex diff is reviewable.** Run reindex after group 4 lands and read `git diff --stat spec/`. Every file changed once, gaining a navigation strip. Confirm no document's authored content changed.
- [ ] 8.5 **The bound holds in practice.** Add one document, reindex, and confirm `git status` shows exactly two changed files: the new one and its parent.
- [ ] 8.6 **The generated region is obviously generated.** Look at the map on the home document and confirm a reader would not mistake it for prose someone wrote.
- [ ] 8.7 **Nothing regressed in the rail.** The `SpecTree` still shows the file tree as before; the hierarchy did not leak into it.

## 9. User test guide

- [ ] 9.1 Write the operator-facing test guide: what to run, in what order, what a correct result looks like, and what a wrong one looks like. Lead with 8.4 and 8.5 — the two checks on *which files were written*. The failure mode this change most plausibly ships with is not a wrong map but a rebuild that quietly rewrites the corpus, and that is invisible unless someone looks at the diff.
