## Before you start

**Tier 1** (operator, 2026-10-05). One grounded review round, then the build. The acceptance drive
(group 1) is written, and seen to fail on today's code, **before** anything in groups 2–6 is built.
The sibling change `a-task-may-serve-a-whole-slice` (rejected evidence gate, ceiling, card) is
independent; either may land first.

Run tests with `py -3.11`. Drives go on `:8010` only, never `:8000`. Real agent turns bind Haiku.

## 0. Review

- [x] 0.1 One grounded review round. Every claim in `design.md` gets a `file:line` or a command run;
  ungrounded findings are dropped. Answer the open question (which real runner on `:8010` holds the
  spec tools for drive B). Side findings go to `scripts/drive/FINDINGS.md`, not into this change.
  Done at `a10b32d`: design.md "Review round" (D4 binds the roadmap as the drafting turn's spec
  document, D6 adds an approved-roadmap duty, R1 = Copilot `cp5` on a Haiku override).

## 1. Acceptance drive (written first, fails before the build)

- [x] 1.1 Drive A, the mechanics, deterministic: `testbed/drive-slices/` with a stub-provider
  Copilot agent `planner` (pattern: `testbed/drive1005-f495/stub_provider.py`) scripted across tool
  results. On `:8010`, the drive does the following, and must fail at step (a) on today's code
  (record the failure):
  - (a) `planner` creates a document of kind `roadmap`;
  - (b) it submits two slices, S1 and S2;
  - (c) the operator proposes and approves the roadmap (no task is created);
  - (d) `planner` creates a change document naming roadmap slice S1, submits it, and it is proposed;
  - (e) the operator approves it with `draft_next_slice: true`. The response reports `queued`,
    S2 and `planner`, and exactly one `operator`-origin queue entry to `planner` exists, in the
    conversation from step (a)'s run, naming S2.
  Written: `testbed/drive-slices/drive_a.py` + `stub_provider.py` (port 18496, runner
  `slices-stub-provider`). Seen failing at `9fb9de9`: FAIL (a), run `run-0db7e65ddfa5` got
  `create_spec_document` "kind: Unexpected keyword argument" and created nothing.
- [ ] 1.2 Drive B, a real model and the guidance (needs 0.1's runner): one real authoring turn on
  Haiku, given a LoopEngine-sized request, ends with a roadmap and a slice-1 change document of
  ≤ ~12 requirements and ≤ 4 tasks. Record the counts. A miss is a finding about the guidance, not a
  failed build (design, Risks).

## 2. Payload and validation (D1, D2)

- [x] 2.1 Tests first (`hub/tests/test_spec_roadmaps.py`), one per scenario of *A roadmap carries
  ordered slices…*:
  - slices refused off a roadmap;
  - requirements or tasks refused on a roadmap;
  - duplicate slice keys;
  - an unresolved or self builds-after;
  - the `roadmap` link shape on a change-spec.
- [x] 2.2 `Slice` model, `slices`, and the `roadmap` link on `SpecPayload`; per-kind rules in
  `validate_payload`.

## 3. Completeness (D3)

- [x] 3.1 Tests first:
  - `roadmap_without_slices`;
  - no `no_requirements` on a roadmap that has slices;
  - `roadmap_not_approved` (missing and exploring);
  - `roadmap_slice_unknown`;
  - both link findings block at proposed and at approved;
  - approving a roadmap materialises nothing.
- [x] 3.2 The roadmap branch and the link findings in `spec_completeness.check`, plus the lookup of
  the named roadmap.

## 4. Agent creation and guidance (D5, D6)

- [x] 4.1 Tests first:
  - an agent creates a roadmap;
  - with no kind, the agent gets a change-spec;
  - a capability is refused, and the refusal names both kinds;
  - the tool docstrings and `SPEC_PHASE_DUTIES` name the roadmap-plus-slice shape and the slice
    size;
  - `test_mcp_tool_schemas.py` agrees;
  - an approved roadmap's turn context carries the roadmap duty, not "Implement against it".
- [x] 4.2 `kind` on `create_spec_document` (MCP and `agent_actions.py`), `slices` and `roadmap` on
  `submit_spec_document`, both returned by the agent read view; the docstrings, `SPEC_PHASE_DUTIES`,
  and the charter bullet reworded.

## 5. Drafting the next slice on approval (D4)

- [x] 5.1 Tests first, against the route (`set_phase`), one per scenario of *Approving a slice can
  start the drafting…*:
  - queued, in the creating conversation, origin `operator`;
  - last slice;
  - no author (operator-created);
  - not asked;
  - not a slice.
  - the queued entry's `spec_document` is the roadmap path.
  Also ask what the route returns when queueing raises. The approval must already be committed and
  must stand; the response reports the failure.
- [x] 5.2 `draft_next_slice` on the phase request; next-slice and author resolution; the entry and
  `schedule_agent` after the commit; `next_slice` on the response.

## 6. Rendering and UI (D7)

- [x] 6.1 Tests first: a roadmap renders its slices in order; a linked change document renders
  "Slice S1 of <roadmap title>".
- [x] 6.2 `spec_render.py` sections.
- [x] 6.3 The approval control shows "Draft the next slice", on by default, only for a document that
  names a roadmap slice, and sends `draft_next_slice`. `npm run lint`; refresh the bundle
  (`scripts/refresh_ui_bundle.py`); commit `hub/ui/src` and `hub/hub/static/ui` together.

## 7. Close

- [ ] 7.1 Full suites: `pytest hub/tests/ -q` and `pytest tests/ -q`, with counts and a sha on this
  line.
- [ ] 7.2 Drive A passes; drive B is recorded (counts) on `:8010`.
- [ ] 7.3 A `spec-queue/METRICS.md` row: tier, times, and which stage caught each defect.
