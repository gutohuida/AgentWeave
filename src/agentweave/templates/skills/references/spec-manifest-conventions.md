# The spec manifest (`spec/index.json`)

`spec/index.json` is the versioned, agent-maintained document forest for everything under
`spec/`. It is **not** itself a spec and is never rendered by the Hub. It exists so the Hub
can show one explicit home document, order documents into roadmap/change relationships, and
tell a deliberately-removed document apart from one an agent simply forgot to declare.

**The manifest is never a prerequisite for visibility.** The watchdog and Hub discover every
safe `spec/**/*.html` file independently of the manifest. An absent, unreadable, or invalid
manifest degrades to reported drift — never to a document silently disappearing from the Hub.

## Shape (version 1)

```json
{
  "version": 1,
  "home": "spec/agentweave-spec.html",
  "documents": [
    {
      "path": "spec/agentweave-spec.html",
      "title": "AgentWeave — Canonical Regeneration Specification",
      "kind": "baseline",
      "status": "living",
      "parent": null,
      "order": 10
    },
    {
      "path": "spec/changes/add-thing/spec.html",
      "title": "Add thing",
      "kind": "change-spec",
      "status": "draft",
      "parent": "spec/agentweave-spec.html",
      "order": 20
    }
  ]
}
```

| Field | Owner | Notes |
|---|---|---|
| `path` | intrinsic (HTML) | Safe, lowercase, POSIX path beneath `spec/`, ending in `.html` |
| `title` | intrinsic (HTML `<title>`) | Cached so a missing file is still identifiable |
| `kind` | intrinsic (HTML `aw-spec-kind`) | `baseline` \| `system-map` \| `roadmap` \| `change-spec` |
| `status` | intrinsic (HTML `aw-spec-status`) | `living` for baseline/system-map/roadmap; `draft`\|`approved` for `change-spec` |
| `parent` | semantic (manifest) | Another document's `path`, or `null`. No self-reference, no cycles. |
| `order` | semantic (manifest) | Integer; sibling presentation order, tie-broken by path |

**HTML owns intrinsic fields** (`title`, `kind`, `status`) because they travel with the
document — the manifest only caches them. **The manifest owns relationships** (`home`,
`parent`, `order`) because those are project semantics a filename cannot express reliably.

## Who writes it

- **`/aw-spec-propose`** adds or refreshes the entry for the change spec it creates, and sets
  `parent` to the relevant roadmap row (or `null` for a standalone change).
- **`/aw-spec-archive`** updates the entry's `path` and relationships when it moves a change
  into `spec/changes/archive/` — the manifest must never point at a path that no longer exists
  because of an archive move.
- **`/aw-spec-reindex`** is the mechanical repair skill: it scans the filesystem, refreshes
  intrinsic fields from HTML, adds unfiled documents, and flags entries it cannot safely
  resolve (e.g. a missing file with no evidence the removal was intentional). Run it whenever
  the Hub reports drift, or proactively after manual file moves.

**No skill invents semantic relationships.** `parent`/`order`/`home` reflect a real editorial
decision (which roadmap a change belongs to, what should open by default) — a skill that isn't
sure asks the user or leaves the ambiguity as reported drift rather than guessing.

## Maintaining an entry (propose / archive)

When creating or moving a document that should be Hub-visible:

1. Read `spec/index.json` if it exists (create a new `{"version": 1, "home": ..., "documents": []}`
   if it doesn't — do not treat its absence as an error).
2. Add or update the entry for the affected path: `title`/`kind`/`status` from the HTML you
   just wrote, `parent`/`order` from the editorial context (which roadmap row, or `null`).
3. If the document is new and no `home` is set yet, and the document is a `baseline`, set it
   as `home`.
4. Write the manifest back with `version: 1` preserved and every existing entry intact except
   the one you changed.

Never remove another document's entry as a side effect of your own change — a change spec's
skill only touches its own entry (and, on archive, the parent roadmap row's status/link,
per the archive skill's own rules).
