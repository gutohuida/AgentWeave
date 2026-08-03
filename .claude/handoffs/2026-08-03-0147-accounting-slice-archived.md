# Accounting and budgets — complete and archived

## Outcome

The entire accounting-and-budgets successor is complete, verified, specified, and archived at
`openspec/changes/archive/2026-08-03-accounting-and-budgets/`. Its authoritative capability is
`openspec/specs/usage-accounting/spec.md`. Umbrella phase 9 is annotated as closed while its
superseded checkboxes remain intentionally unchanged.

Delivered behavior:

- immutable one-per-run measured/unavailable accounting;
- Claude final usage/model fallback/allowance, exact Codex rollout request deltas, OpenCode step
  normalization;
- project and agent aggregates with unavailable counts and honest display preference;
- optional project token budget, explicit operator/autonomous run initiator, scheduled `job`
  origin, pre-delivery autonomous pause, retained queue, and automatic resume after limit change;
- accounting API, Overview totals/configuration, and globally visible exhausted-state explanation
  without disabling operator input.

Verification: 432 Hub tests passed (4 skipped), 289 frontend tests passed, production build passed,
and post-archive strict OpenSpec validation passed for all 16 remaining items. `npm run lint` is an
existing unusable script because ESLint 9 has no `eslint.config.*`; TypeScript/build is green.

## Continue the umbrella

The terminal objective remains the whole active `2026-07-30-hub-native-experience` umbrella. Do
not stop here. Reconcile dependencies using the archived conversation-workspace slice table.

Known successor state after accounting:

- local multi-project workspace depends on conversation workspace + single runtime;
- specification program is ready for technical exploration, narrowed RQ-2;
- approval gates depend on conversation workspace + specification program;
- agent capability plane is independent and needs a proposal;
- single runtime depends on agent capability plane;
- retire the Hub name depends on single runtime;
- runner/agent/charter separation is independent and ready to propose.

The best next dependency-unblocking candidate is **agent capability plane**, because it unlocks
single runtime, which in turn unlocks local multi-project and retirement of the Hub name. Before
proposing, re-read umbrella phases 14–16 and the relevant design sections, then audit current Hub
MCP/runner capability code. Create a focused OpenSpec successor; do not implement directly from
the superseded umbrella checklist. Continue the same phase protocol: tests first, verification,
commit, handoff, authoritative spec, archive, umbrella annotation.

