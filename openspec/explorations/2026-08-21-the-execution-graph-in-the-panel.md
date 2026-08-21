# Exploration — The execution graph belongs in the panel (2026-08-21)

**Status:** OPEN. Operator asked for this to be specced. Carries `task-dependencies` 11.1, waived
as **not passing** when that change was archived.

## What the operator asked for

> "The execution graph (the task view as graph I don't know.) should be on the right panel with the
> spec and the others. To access the lineage fast."

So: the dependency board becomes a tenant of `PanelShell`, beside the spec document, files and
loops tabs — reachable while a conversation is open, rather than only from the Tasks tab.

## And it needs to look like something first

> "The edges are kind of broken. They're static on the page. If I expand the 2 done they just don't
> make sense anymore. We can see which are done but the UI looks bad. […] The UI is just kind of
> ugly. The links should not be static."

Two separable problems, and only the first is understood.

### 1. The edges go stale — cause located

`DependencyBoard.tsx:157`:

```js
const layoutKey = layers.map((l) => `${l.depth}:${l.tasks.map((t) => t.id).join(',')}`).join('|')
```

It encodes which tasks sit in which layer, and **not which layers are collapsed** — so it is
identical before and after a folded layer expands: same tasks, same layers, only more of them
mounted. `useEdgeLines` keys its layout effect on it, so the effect never re-runs, the newly
mounted cards never join its `ResizeObserver`, and every line keeps the geometry it had while the
layer was folded.

**This part is one line** (fold the collapsed set into `layoutKey`). It was deliberately not
applied: the surface is being replaced and 11.1 should be re-judged against the replacement, not
against a patch.

### 2. "Ugly" — not yet diagnosed

No cause recorded, because none was investigated. This needs the operator's eye on specifics before
it can become requirements. Known ingredients: straight point-to-point lines with no crossing
minimisation (task 8.12 deferred that as "unbounded polish"), and collapsed layers rendering as a
bare "2 done" row.

## Open questions

1. Which tab does it become, and is it per-document or per-project?
2. Does it stay read-only? (`task-dependencies` 11.7 established that structure is edited through
   the document's `depends_on`, and that the refusal explains itself.)
3. Is the layer-collapse behaviour worth keeping at all once the board is narrower in a panel?
4. What does "lineage fast" mean concretely — from a task to its blockers, or from a conversation
   to the task it is working?
