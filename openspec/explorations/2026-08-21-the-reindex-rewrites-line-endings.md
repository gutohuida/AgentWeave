# Exploration — The Hub writes corpus files with CRLF on Windows (2026-08-21)

**Status:** OPEN. Found by hitting it, 2026-08-21. Small, cause confirmed in source, one-line fix.

## The observation

`POST /api/v1/projects/{id}/project/spec/reindex` rewrites `spec/index.json`. On Windows it writes
**CRLF** where the checkout has LF. Measured immediately after a reindex that changed nothing:

```
reindex reported:  diagnostics: 0   rerendered: 0   skipped: 0
working copy:      334 CRLF          HEAD: 0 CRLF
identical after normalising:  True
```

So a reindex that genuinely changed no content still left a tracked file modified in `git status`,
with a 334-line diff that is pure line-ending churn, plus a warning on every later git command:

```
warning: in the working copy of 'spec/index.json', CRLF will be replaced by LF the next time Git touches it
```

## Cause — confirmed, not guessed

`hub/hub/spec_documents.py` writes both the index and the documents in text mode without pinning
the newline, so Python's universal-newline translation converts `\n` to `\r\n` on Windows:

- `write_index`, line 345 — `resolved.write_text(dump_manifest(manifest), encoding="utf-8")`
- `write_document`, line 164 — `resolved.write_text(content, encoding="utf-8")`

**Both paths are affected**, not just the index. Only `index.json` was dirtied in the run that
found this because `rerendered: 0` — no document was rewritten that time. Any reindex that does
re-render, and every `arrange`, `adopt` or document edit, will do the same to the HTML documents.

## What it does *not* do, in this repository

It does not corrupt anything committed. This repo carries a `.gitattributes` with `* text=auto
eol=lf`, and `core.autocrlf=true`, so git normalises on the way in — every corpus file at `HEAD`
is LF, checked across `index.json`, `agentweave.html`, an area document and two capability
documents. The damage here is confined to working-tree noise.

That is worth stating precisely, because it explains why this survived unnoticed for a corpus of
41 documents: the repository's own configuration has been quietly absorbing it.

## Why it still matters

1. **A user's project has no `.gitattributes`.** This repository is the exception, not the rule.
   AgentWeave writes a `spec/` corpus into whatever project it is pointed at, and in a project
   without that config the CRLF reaches the commit — so the corpus line endings depend on which
   operating system last ran a reindex. Two collaborators on different platforms would produce
   whole-file diffs against each other.
2. **`git status` stops being trustworthy.** A reindex is a routine maintenance step — the working
   order recorded in `2026-08-21-an-operator-cannot-rename-a-document.md` is
   "create → reindex → arrange → reindex", so the noise is guaranteed on the normal path.
3. **A real index change hides inside the noise.** 334 lines of churn is exactly the diff nobody
   reads before staging.

## Sketch of a fix

Pin the newline on both writers:

```python
resolved.write_text(content, encoding="utf-8", newline="\n")
```

Better still for the index: **do not write when the content is unchanged.** A reindex reporting
`rerendered: 0, diagnostics: 0` should touch no file at all, which kills the mtime churn as well
as the line endings.

## Open questions

1. Pin the newline, skip no-op writes, or both? Both is cheap and they solve different halves.
2. Are there other writers with the same shape? `write_text`/`open()` in text mode elsewhere in the
   Hub's filesystem paths should be swept, not just these two.
3. Docker mode runs Linux, where the bug is invisible. Any regression test has to run on Windows
   to mean anything — worth checking whether the existing suite could have caught this at all.
