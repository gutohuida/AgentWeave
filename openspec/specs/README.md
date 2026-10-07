# Frozen — the corpus moved to `spec/`

On 2026-10-07 the operator made `spec/` the source of truth for this project's specifications.
Every capability here was re-imported into `spec/capabilities/<capability>/spec.html` through the
Hub (`scripts/migrate_openspec_corpus.py`), and each one's requirement count was checked equal to
its `### Requirement:` count here (45 of 45).

These files are kept as the history they are. **Do not edit or re-sync them.** A behaviour change
goes into the `spec/` capability document, through the app or the Hub's document routes; the
changes still in `openspec/changes/` apply their deltas there when they are archived.
