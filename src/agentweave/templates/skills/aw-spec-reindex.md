---
name: aw-spec-reindex
description: Repair spec/index.json — the deterministic mechanical half of manifest maintenance. Scans every safe HTML file beneath spec/, refreshes intrinsic fields (title/kind/status) from each document's own <head>, adds unfiled documents, and flags anything it cannot safely resolve on its own (a missing file, an ambiguous parent) instead of guessing.
---

Repair `spec/index.json`, the manifest that gives the Hub an explicit home document and a
document forest (parent/order relationships) for everything under `spec/`. Run this whenever
the Hub's Spec tab reports drift, or after moving/renaming spec files by hand.

**Project:** {project_name}
**Principal:** {principal}
**Agents:** {agents_list}

**Manifest schema and field ownership:** `spec-manifest-conventions.md` (bundled beside this
skill) — read it first. **HTML metadata conventions:** `html-spec-conventions.md` (also
bundled) — the source of `aw-spec-kind`/`aw-spec-status`/`<title>`.

This skill is split deliberately: the **mechanical merge** below is deterministic and safe to
run unattended. **Semantic decisions** (which roadmap a change belongs to, what should be
`home`, whether a missing file was actually deleted on purpose) are not — this skill asks
rather than guesses whenever a step calls for one.

---

## Steps

### 1. Inventory the filesystem

```bash
find spec -name "*.html" | sort
test -f spec/index.json && cat spec/index.json
```

Every `.html` file beneath `spec/` is a candidate document — nested archives, roadmaps, and
system maps included, not just `spec/changes/*/spec.html`.

### 2. Read intrinsic metadata from each document

For every discovered file, read its `<head>`:
```html
<title>...</title>
<meta name="aw-spec-kind" content="baseline|system-map|roadmap|change-spec">
<meta name="aw-spec-status" content="living|draft|approved">
```

A file missing `aw-spec-kind` or `aw-spec-status` is itself a drift item — report it; do not
invent a kind/status for a document that doesn't declare one.

### 3. Merge deterministically

For each discovered file:
- **Already in the manifest:** refresh `title`/`kind`/`status` from the live HTML. Leave
  `parent`/`order` untouched — those are semantic and this step never overwrites them.
- **Not in the manifest (unfiled):** add a new entry with `title`/`kind`/`status` from the
  HTML. Set `parent: null` and pick an `order` after the highest existing sibling at the same
  level — do not guess a parent relationship; that is step 5.

For each manifest entry with no matching discovered file (missing):
- Do **not** delete the entry automatically. See step 4.

This step never touches `home` unless step 6 applies.

### 4. Investigate missing documents before removing an entry

A manifest entry with no file on disk is ambiguous — it could be a genuine deletion, a rename
the manifest wasn't updated for, or a document that hasn't synced from another machine yet.

- Check `git log --diff-filter=D -- <path>` (if this is a git repo) for a deletion commit.
- Check whether a similarly-named file exists elsewhere under `spec/` (a probable rename).
- If evidence clearly shows deletion, remove the entry and say so in the summary.
- If a rename is likely, ask the user to confirm before updating `path`.
- Otherwise, leave the entry in place and report it as unresolved drift — **never** silently
  discard a manifest entry you can't explain.

### 5. Resolve ambiguous or missing parent relationships

If a newly-added (unfiled) document's likely parent roadmap is genuinely ambiguous, or an
existing entry's `parent` now points at a path that no longer exists, do not guess:

- Prefer inference from context that's actually there — the document's own content, an
  `spec/roadmaps/*.html` row that already names it, or its directory (`spec/changes/<name>/`
  matching a roadmap's declared child-spec path).
- If nothing resolves it confidently, ask the user with **AskUserQuestion**, or leave `parent:
  null` and report the ambiguity — a flat, correct manifest beats a wrongly-nested one.

### 6. Home document

If `spec/index.json` doesn't exist yet, create it (`{"version": 1, "home": ..., "documents":
[]}`) and set `home` to the discovered `baseline` document if there is exactly one. If there
are zero or multiple baseline candidates, ask the user which document should be `home`.

If `home` already points at a document that still exists, leave it — reindex never changes an
existing editorial decision without being asked.

### 7. Write the manifest

Write the complete `spec/index.json`, `version: 1`, pretty-printed. Validate it yourself before
finishing:
- Every `path` is safe (lowercase, POSIX, beneath `spec/`, ends `.html`) and unique.
- `home` references an existing document.
- Every `parent` is `null` or another document's `path`; no self-reference, no cycles.
- `kind` is one of the four valid values; `status` matches kind (`living` for
  baseline/system-map/roadmap, `draft`/`approved` for `change-spec`).

### 8. Show the repair summary

```
## Spec Manifest Repaired

**Added:** N unfiled document(s)
- spec/roadmaps/epic.html (roadmap)

**Refreshed:** M document(s) with drifted title/kind/status
- spec/agentweave-spec.html — status: draft → living

**Missing (unresolved):** K entr(y/ies) — evidence inconclusive, left in place
- spec/changes/old-thing/spec.html — no deletion commit found; confirm before removing

**Home:** spec/agentweave-spec.html (unchanged | set for the first time)

Run `agentweave spec push` to sync the repaired manifest to the Hub.
```

---

## Guardrails

- Mechanical only: title/kind/status refresh and unfiled-document addition never need
  confirmation. Anything semantic (parent, home, a missing-file removal) is confirmed with the
  user or reported unresolved — never guessed.
- Never remove a manifest entry without positive evidence of deletion (or explicit user
  confirmation).
- Never invent `kind`/`status` for a document whose HTML doesn't declare it — report the gap.
- Validate the manifest (unique safe paths, valid home, acyclic parents, kind/status
  compatibility) before writing it — an invalid manifest you just produced is worse than the
  drift you were asked to fix.
- This skill repairs `spec/index.json` only. It does not edit spec HTML content, and it does
  not push to the Hub — that's `agentweave spec push`.
