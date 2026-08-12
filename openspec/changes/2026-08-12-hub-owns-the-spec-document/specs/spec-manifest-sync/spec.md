# spec-manifest-sync

Every requirement of this capability is removed. The capability described a **push-fed content
cache** and a **multi-source reconciliation record**, both of which this change deletes: the Hub now
reads documents from the project working directory through `ProjectWorkspace`, and a project is bound
to one canonical directory, so there is no second source to reconcile with.

Four of these requirements describe a **document tree** rather than a sync, and are re-stated in
`spec-document-authority` rather than dropped — discovery, home-document selection, visible
degradation of an unreadable index, and subscriber refresh. Each is marked below.

## REMOVED Requirements

### Requirement: Spec discovery covers every safe HTML document

**Reason**: Carried forward into `spec-document-authority` as "Document discovery covers every safe
document". The behaviour is unchanged; its source is the working directory rather than a synced
inventory, so the requirement cannot remain in a capability whose subject is synchronisation.

### Requirement: The manifest has a versioned structural contract

**Reason**: The index is now written and read by the Hub alone. A structural contract negotiated with
an external writer has no counterparty; the constraint that survives is expressed as the payload
contract in `spec-document-authority` ("The payload contract is versioned and forward compatible").

### Requirement: HTML owns intrinsic metadata and the manifest owns relationships

**Reason**: Superseded by JSON in, HTML out. The document's markup is rendered by the Hub from a
validated payload, so markup no longer *owns* anything — it is output. Splitting ownership between a
document and an index described a division between two writers that no longer exists.

### Requirement: Invalid or absent manifests degrade visibly

**Reason**: Carried forward into `spec-document-authority` as "An unreadable or absent index degrades
visibly", including the rule that an entry which cannot be explained is retained rather than
discarded.

### Requirement: The Hub exposes manifest-aware spec state

**Reason**: The Hub still exposes document state, but it computes it from the working directory
rather than from a cache enriched with drift across sources. The drift vocabulary this requirement
defined — unfiled, missing, stale, conflicting — described disagreement between synchronising
machines, a condition that cannot arise once a project is bound to one canonical directory.

### Requirement: Home-document selection is explicit and resilient

**Reason**: Carried forward into `spec-document-authority` under the same name, including the rules
that an existing selection is preserved and an ambiguous one is asked about rather than guessed.

### Requirement: Users can trigger manifest repair from the Hub

**Reason**: Repair existed because an external writer could move files without telling the Hub. The
Hub now writes the documents and the index in the same operation, so the drift this repaired is not
produced. A hand-edit outside the Hub becomes the divergence case, which is reported and never
auto-resolved.

### Requirement: Spec synchronization remains backward compatible

**Reason**: Compatibility with a client that no longer exists. `HttpTransport.push_spec` and
`reconcile_specs` have no callers; the watchdog that called them is deleted and `agentweave spec
push` is among the removed CLI commands. Both endpoints are deleted by this change.

### Requirement: Spec state changes refresh subscribers

**Reason**: Carried forward into `spec-document-authority` as "Document state changes refresh
subscribers", extended to cover phase transitions as well as content.
