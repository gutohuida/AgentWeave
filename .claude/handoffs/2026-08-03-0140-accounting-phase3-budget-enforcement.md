# Accounting and budgets — phase 3 complete

## Current objective

The user authorized completion of the whole active Hub-native umbrella. The current focused
`accounting-and-budgets` successor has phases 0–3 complete; phase 4 UI/integration remains. Continue
directly with OpenSpec, never initialize AgentWeave at this repository root, and commit/handoff at
verified boundaries.

## Phase 3 result

- Queue origins are now `operator | agent | job`. Migration 0019 safely replaces the old SQLite
  check constraints on existing deployments; additive Alembic startup without base project tables
  still advances cleanly.
- Scheduled jobs enqueue `origin_type="job"`, display as scheduled input in prompts, and produce
  `Run.initiator="autonomous"`; they no longer borrow operator classification.
- `schedule_agent` selects a conversation batch, determines initiator, checks measured project
  usage against `Project.token_budget`, and returns `token budget exhausted` before atomic delivery
  for autonomous work. Entries stay queued.
- Operator-containing batches bypass only the token-budget gate and persist
  `Run.initiator="operator"`.
- Queue status exposes token exhaustion. Raising/disabling a budget reschedules distinct agents
  with retained queue work; a now-permitted run starts without re-enqueueing.
- Timeline compatibility maps scheduled-job content to operator-style input presentation while its
  execution privilege remains autonomous.

## Verification

```text
focused accounting-budget, inbound-queue, scheduler, accounting-API, migration suites
all passed (migration-specific 0019 test also passed independently)

.venv\Scripts\python.exe -m pytest hub/tests -q
432 passed, 4 skipped

targeted Ruff + git diff --check
passed
```

## Next exact work — phase 4

Add the operator UI and finish the slice.

1. Inspect `OverviewPage.tsx`, `StatusBar.tsx`, `App.tsx`, and existing React Query API patterns.
2. Add `hub/ui/src/api/accounting.ts` with typed GET/PATCH hooks and stable query invalidation.
3. Add a compact project accounting component (prefer Overview for totals/configuration) covering:
   measured project total, per-agent rows, unavailable-turn count, optional budget progress/edit,
   allowance preferred display, and exact `API-equivalent estimate` label.
4. Put an exhausted-state warning where it remains visible in the active conversation shell
   (StatusBar or ConversationControls): “Autonomous turns are paused; operator messages can still
   run.” Do not disable the composer.
5. Tests first: tokens/unavailable, allowance precedence, API-equivalent wording, exhausted
   explanation, and positive/null budget mutation. Avoid brittle transient React Query status
   assertions.
6. Run targeted frontend tests, all frontend tests, production build, all Hub tests if backend
   changes, and strict OpenSpec validation.
7. Sync `openspec/specs/usage-accounting/spec.md`, archive `accounting-and-budgets`, annotate
   umbrella phase 9 as closed by the archived successor (leave superseded checkboxes unchanged),
   write final slice handoff, and commit each closeout boundary.

