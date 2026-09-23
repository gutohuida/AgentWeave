## 0. Rounds and prerequisites — no task below may start until these are done

- [ ] 0.1 R2: re-derive the vocabulary from `hub/hub` (every `.broadcast(` call, multi-line ones included, by AST, not grep) and the allowlist from `hub/ui/src/hooks/useSSE.ts:21-68`, without reading R1's list first; re-check D4's table against each payload and each UI query key
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate every-event-the-hub-sends-reaches-the-app --strict` passes
- [ ] 0.3 The operator answers B9-Q1 (design D2); record it in `spec-queue/DECISIONS.md`
- [ ] 0.4 `an-event-is-announced-only-once-its-write-is-committed` is implemented and its test 1.1 passes on the tree this change starts from (or both land in one commit). **Do not start group 2 otherwise** — F335's false line would reach the feed

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 (D1) `hub/tests/test_sse_event_vocabulary.py::test_every_broadcast_kind_is_registered`: the AST walk of design D1.1-D1.2. FAILS today (no registry)
- [ ] 1.2 (D1) `::test_every_registered_kind_is_broadcast`: D1.3. Write it so it also fails when `job_deleted` is added to the registry (assert on a registry with that key injected, in the same test, as its own negative control)
- [ ] 1.3 (D3) `::test_the_generated_vocabulary_is_current`: regenerate in memory, compare with `hub/ui/src/lib/sseEventKinds.generated.ts`. FAILS today (no file)
- [ ] 1.4 (D1) `hub/tests/test_sse.py`: publishing an unregistered kind logs a warning (`caplog`) and still reaches a subscriber. FAILS today on the warning
- [ ] 1.5 (D2, F251) `hub/ui/src/__tests__/useSSE.test.tsx`: one test per admitted kind in D4's table, built from a chunk whose payload has the shape the Hub route sends, stamped with `project_id` as `SSEManager` stamps it. Each asserts a listener sees the kind **and** the D4 invalidations for that `pid` (spy on `queryClient.invalidateQueries`). FAILS today (each is dropped at `useSSE.ts:337`)
- [ ] 1.6 (D2) A frame named `some_future_kind` (not in the vocabulary) is dispatched to listeners and the buffer, and invalidates nothing. A frame named `connected` is **not** dispatched. FAILS today on the first assertion
- [ ] 1.7 (F251) `useCheckpoints`, mounted for conversation `c1` in project `p`: a `checkpoint_ready` chunk for `c1` invalidates `['project', p, 'checkpoints', 'c1']`. FAILS today — the subscription at `api/checkpoints.ts:45` never runs
- [ ] 1.8 (F251) `useProjectConversations(p)`: a `conversation_updated` chunk for `p` invalidates `['project', p, 'conversations']`; one for another project does not. FAILS today on the first assertion
- [ ] 1.9 Replace `useSSE.test.tsx:128`'s `job_deleted` with `job_archived` (the kind the Hub sends, `jobs.py:1290`) and assert the jobs invalidation. FAILS today on `job_archived`
- [ ] 1.10 (D2) Type check: after group 2, temporarily add `case 'job_deleted':` to the switch and confirm `npx tsc --noEmit` fails with TS2678; remove it. Record the output. (A one-off check, not a committed test: it is the build that carries this guard)
- [ ] 1.11 Control: every other test in `useSSE.test.tsx` and `useSSE-lifecycle.test.tsx` passes before and after; record the counts

## 2. The fix

- [ ] 2.1 (D1) `hub/hub/sse_events.py`: `EVENT_KINDS` (63 at R1, each with its one-line meaning) and `STREAM_FRAMES`
- [ ] 2.2 (D1) `hub/hub/sse.py`: a `logger.warning` for an unregistered kind in `publish` (or `broadcast`, if F335's funnel is not there), never a raise
- [ ] 2.3 (D3) `scripts/generate_sse_event_kinds.py`; run it; commit `hub/ui/src/lib/sseEventKinds.generated.ts`
- [ ] 2.4 (D2) `hub/ui/src/hooks/useSSE.ts`: delete `SSE_EVENT_TYPES`; skip `connected` beside the `message` skip; dispatch every other named frame; type `SSEEvent.type` as `SseEventKind` with the skew comment. Delete the now-obsolete comment at `:538-543` about kinds "absent from `SSE_EVENT_TYPES`"
- [ ] 2.5 (D4) The central switch: the cases in D4's table; `job_deleted` → `job_archived`
- [ ] 2.6 Fix any `tsc` fallout from 2.4 (each is either a dead handler to delete or a kind missing from the registry — never widen the type to `string` to silence it); list each in the round log
- [ ] 2.7 Run group 1; `py -3.11 -m pytest hub/tests -q`; `cd hub/ui && npm test && npm run lint && npm run build`; `ruff check hub/ scripts/ --select E9,F63,F7,F82,F401,F841`; `black --check --target-version py311 hub/hub hub/tests`
- [ ] 2.8 `python scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together

## 3. Drive and close out

- [ ] 3.1 On a trial Hub from source (never `:8000`), in Chromium on the served bundle: re-run `t_sweep_row16_logs_events_sse.py` legs 3 and 7 (archive a job; rename a conversation) and record that the job list and the rail update without reload. Drive a context-pressure checkpoint under `offered` and record that the offer banner appears without reload
- [ ] 3.2 Re-run F335's true-resolution leg with the Activity tab open: the feed shows *"1 open divergence on T resolved"* for the true resolution, and nothing for a refused one
- [ ] 3.3 Mark F251 fixed in `scripts/drive/FINDINGS.md`; reconcile the requirement into `openspec/specs/local-project-workspace/spec.md` on archive
