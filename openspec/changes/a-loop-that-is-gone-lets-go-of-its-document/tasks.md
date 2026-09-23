## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: independently re-derive design's Context table: every writer and reader of `Task.loop_id` (`grep -rn "loop_id" hub/hub --include=*.py`), both archive doors, `materialise`'s owning-loop query, and `create_job`'s pre-write checks. Search `hub/tests` for any test that creates a plain job with `spec_document_id` and expects 201 (F157's entry cites `test_jobs_crud.py:537`; today only the docstring at `:602` mentions it). Record in design's round log
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate a-loop-that-is-gone-lets-go-of-its-document --strict` passes
- [ ] 0.3 The operator records the F53 and F157 decisions in `spec-queue/DECISIONS.md`, and design Open Question 1

## 1. Tests first — each must fail on today's code unless marked as a control

New `hub/tests/test_a_gone_loop_lets_go.py`.

- [ ] 1.1 (F53) A document with three materialised tasks: one `pending`, one `in_progress` assigned to agent A, one `approved`. Loop 1 claims it (adopts all three). Archive loop 1's job. Loop 2 claims the same document. The `pending` and `in_progress` tasks name loop 2; the `approved` one still names loop 1. Record that it FAILS today (none move)
- [ ] 1.2 (F53) Continuing 1.1: loop 2's queue (`GET /tasks?loop_id=<loop 2>`) lists exactly the two moved tasks
- [ ] 1.3 Control, PASSES before and after: a document whose tasks a **live** loop owns cannot be claimed (409), and its tasks keep their loop
- [ ] 1.4 (D3) Materialise with an archived loop and a live loop both naming the document: new tasks name the live loop. Seed the archived loop first **and** second in insertion order, so the test fails if the query still picks by row order. Record which order FAILS today
- [ ] 1.5 (D3) Materialise with only an archived loop naming the document: new tasks have `loop_id` NULL. Record that it FAILS today
- [ ] 1.6 (F157) `POST /jobs` with `spec_document_id` and no purpose or stop condition answers 400 with `spec_document_id describes a loop`, and `GET /jobs` does not list it. Record that it FAILS today (201)
- [ ] 1.7 Control: `POST /jobs` with `spec_document_id` **and** a purpose still creates a loop claiming the document; the MCP `create_flow` path still succeeds
- [ ] 1.8 Control: `test_f53_an_archived_loops_document_claim_does_not_block_a_new_loop` (`hub/tests/test_jobs.py`) passes before and after

## 2. The fix

- [ ] 2.1 `jobs.py` `_adopt_document_tasks`: design D1; update its docstring and the comment at `:155-163`
- [ ] 2.2 `spec_tasks.py:176-180`: design D3
- [ ] 2.3 `jobs.py` `create_job`: design D4 beside the `work_needs_evidence` refusal; rewrite the comment at `:614-619`; update `test_jobs_crud.py:600-604`'s docstring
- [ ] 2.4 Group 1, then `py -3.11 -m pytest hub/tests/ -q`; record counts inline or do not tick
- [ ] 2.5 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`

## 3. Drive it

- [ ] 3.1 On a trial Hub, reproduce F53's three calls (create a flow on an approved document, archive it before it fires, create a second flow on the same document), then list the second flow's queue: it holds the document's tasks. Disable every job before leaving
