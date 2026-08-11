# Handoff: four operator decisions settled, and the approval defect diagnosed to root cause

**Date:** 2026-08-11T14:23+01:00 · **Branch:** hub-native-experience · **HEAD:** `6b92101`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0033-2026-08-11-1240-declining-a-question-shipped.md`
**Status:** **chunk complete.** Working tree clean, nothing unpushed. Two changes shipped, two
proposed and ready to implement, one long-standing defect diagnosed to root cause.

## Goal

Handoff 0033 left three changes implemented-but-unarchived and a list of open operator questions.
This session the operator chose **"answer the open questions first"** over live testing. All four
were settled and acted on, then the operator picked **the permission defect** as the next work item,
which was diagnosed to root cause and specced.

The *why* that matters for judgement calls: every item here was blocked on a decision only the
operator could make, and the value was in converting each into either shipped code or a written
decision that a later session can build on. **"We never got round to it" and "we decided against it"
are different states, and only the second is safe to build on** — that framing drove how each was
recorded.

## Current state

**Nothing is half-done.** Four commits, all pushed, working tree clean.

### 1. Contrast bar — SHIPPED (`000a670`)

Operator chose **3.0 on every surface, keeping three text levels**, over AA 4.5 or a recorded
exemption. Applied in `hub/ui/src/index.css`:

| token | mode | was | now | worst surface (`--surface-3`) |
|---|---|---|---|---|
| `--text-3` | dark | `#5c5c66` | `#6f6f79` | 2.28 → **3.03** |
| `--text-3` | light | `#8e8e98` | `#85858f` | 2.68 → **3.01** |
| `--green` | light | `#16a06a` | `#0f9963` | 2.76 → **3.01** |
| `--amber` | light | `#c47f16` | `#bb760d` | 2.71 → **3.04** |

Ratios were **recomputed independently**, not copied from task 8.9's table. The deciding number: at
AA 4.5 the gap between `--text-2` and `--text-3` collapses to **1.03** (dark) / **1.20** (light); at
3.0 it is **1.53** / **1.81**. Dark `--green`/`--amber` already passed and are untouched; `--text`
and `--text-2` remain comfortably AA.

`hub/ui/src/__tests__/contrastRamp.test.ts` (**new, 8 tests**) parses `index.css` and computes every
level and status hue against all four surfaces. Deliberately computed rather than pinned to hex
literals — the contract is "whatever the colours are, they clear the bar". **Confirmed to fail on the
pre-change palette before being kept** (dark `--text-3` on `--bg`, 2.99).

Charcoal task **8.11 is now closed**. That change has 2 tasks left, both human-only (8.8 keyboard,
8.10 reduced-motion).

### 2. Declining a question — SETTLED AS SHIPPED (`000a670`)

Operator chose **neither a reason nor a reopen**. No code changed; `design.md` gained **D7** and
`tasks.md` 6.11 records the settlement. The load-bearing argument for D7: **reopening re-arms the
loop D4 exists to prevent** — a reopened question is once again an unanswered blocking question, so
the run boundary re-parks the task the decline just released.

### 3. B0 charter re-shape — PROPOSED, NOT IMPLEMENTED (`443cb91`)

`openspec/changes/2026-08-11-charter-set-reshape/` — proposal, design D1–D8, 2 delta specs, 33 tasks.
Operator chose **full re-shape** (not the narrow honesty repair) with **underwriting** as the single
non-software domain.

**The premise was verified in the tree, and the defect is larger than the exploration recorded.**
`openspec/specs/agent-charter/spec.md:83` already requires a seeded charter must not "address a
participant the roster does not contain" — and:

| Defect | Count |
|---|---|
| escalates to a "Tech Lead" that exists only if the operator made one | **16 of 21** |
| defers to a "Coordinator" | 8 |
| defers to a "Project Manager" | 4 |

It survived because `hub/tests/test_agent_facing_text.py` enforces the *file* and *command* clauses
against a fixed `REMOVED_SUBSYSTEMS` needle list and has **nothing for the participant clause**,
which is the open-ended one.

Also verified, not assumed: **nothing installs `src/agentweave/templates/skills/`** (no Python reads
it; the only `.claude/skills/` reference is `hub/hub/workspace_paths.py:3`, the composer's `@path`
filter), so `charters/spec.md`'s six `aw-spec-*` citations point at nothing. **The Hub does not
discover spec files** — `hub/hub/api/v1/spec.py:71,213` stores an inventory a *client* supplies as
`discovered_paths`; the rglob is CLI-side at `src/agentweave/spec_manifest.py:90`. And **B1 is
archived**, so the charter's self-enforced approval gate duplicates the transition service without
its authority. Two stale paths the exploration missed: `shared/design-*.md` and
`.agentweave/shared/plan-[task-id].md`.

**Plan: 21 → 9.** Keep 6 accountabilities (`tech_lead` absorbing `architect`, `code_reviewer`,
`verifier` absorbing `qa_engineer`, `guardian`, `security_engineer`, `spec`), add `developer`
(replacing the six `*_dev`/`*_engineer` variants, `technical_writer` folded into its scope), add
`underwriter` + `underwriting_approver`. Remove 15.

### 4. Permission defect — DIAGNOSED (`ac627ee`) AND PROPOSED (`6b92101`)

**Root cause found.** `mcp_server._ask_operator` times out at `AW_DECISION_TIMEOUT` (default 120s),
returns a **local** denial, and writes nothing back. The `PermissionRequest` row stays
`status="pending"` forever. Then:

1. `_report_decision` → `agent_actions.py:513-547` logs a `permission_denied` event and **never
   touches the row** — it is not given the request id, only `tool_name`/`tool_use_id`.
2. `list_permission_requests` filters `status == "pending"` (`permissions.py:57`) → **card still on
   screen**.
3. Operator clicks Allow. The guard is `row.status != "pending"` (`permissions.py:86`) — it *is*
   pending, so it does not fire. Row → `"allowed"`, API returns **200**.
4. Operator sees an approval succeed. Nothing runs. Nothing says why.

The guard's own message — *"this request was already {status}; the run has moved on"* — is the author
anticipating exactly this. It never fires because nothing sets a terminal status on this path.

**The contract is already written down.** `hub/hub/db/models.py:1157-1159` on `PermissionRequest`:
*"`decided_at` distinguishes an answer from a timeout, **which also writes a terminal status rather
than leaving the row pending forever**."* `"expired"` is already a documented status value. This is
an unimplemented contract, not a design gap. **No migration needed** — status already permits it and
`run_id` is already indexed.

**Why only Claude:** `agent_trigger.py:1451` is the **only line in the codebase that expires a row**,
and it is the Codex path, which runs in-process with a DB session. `mcp_server.py` is spawned
standalone (stdlib + fastmcp only), has no session, and silently went without the equivalent write.

**Second symptom, same cause:** `conversations.py:268-269` counts a pending permission request as a
reason a conversation is "waiting", so a stale row pins its conversation as waiting **permanently**.

## Files touched

Working tree **clean**, **0 unpushed**. Four commits this session, all pushed.

| path | what | done? |
|---|---|---|
| `hub/ui/src/index.css` | `--text-3` both modes; light `--green`/`--amber`; comments record the 8.11 decision | yes |
| `hub/ui/src/__tests__/contrastRamp.test.ts` | **new**, 8 tests, computed from the stylesheet | yes |
| `hub/hub/static/ui/**` | rebuilt, `diff -rq` identical | yes |
| `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/tasks.md` | 8.11 → `[x]` with the measured before/after table and the AA cost | yes |
| `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/specs/hub-workspace-shell/spec.md` | **new requirement**: three levels + stated bar + enforced by a check | yes |
| `openspec/changes/2026-08-11-declining-a-question/design.md` | **D7** — no reason, no reopen, and why | yes |
| `openspec/changes/2026-08-11-declining-a-question/tasks.md` | 6.11 records the settlement | yes |
| `openspec/changes/2026-08-11-charter-set-reshape/` | **new**: proposal, design D1–D8, 2 delta specs (`agent-charter`, `aw-spec-workflow`), 33 tasks | proposed only |
| `openspec/explorations/2026-08-10-operator-approval-not-honoured.md` | **rewritten**: diagnosis, 6 eliminations with evidence, live probe table, suggested fix | yes |
| `openspec/changes/2026-08-11-permission-request-expiry/` | **new**: proposal, design D1–D6, 1 delta spec (`agent-run-sandboxing`), ~45 tasks | proposed only |
| `testbed/scratch/stub_approver.py`, `run_probe.sh`, `probe_approver.py`, `permprobe/` | probe harness — **gitignored** (`testbed/.gitignore:3`), intentionally uncommitted | kept |

## Key decisions

1. **Contrast: 3.0, not AA 4.5.** Preserves three levels. Rejected AA because the measured
   `--text-2`↔`--text-3` gap falls to 1.03/1.20 — the ramp the charcoal refresh existed for.
   Rejected a recorded exemption because the failing token is not decorative.
2. **Enforce the contrast decision by computing from `index.css`, not by pinning hexes.** A hex list
   says nothing when someone edits it; the computed test says "whatever the colours are, they clear
   the bar", which is what was decided.
3. **D7 — declining carries no reason and cannot be reopened.** A reason turns a dismissal back into
   a reply, which is the friction the feature exists to remove. Reopening re-arms D4's loop.
4. **B0 D1 — the charter set is decided by one written test** (accountability, not activity), so a
   future addition has a criterion, not a precedent. *Rejected: cutting to the four pure
   accountabilities* — an operator's first agent would find nothing saying "build the thing".
   *Rejected: honesty-only repair* — it rewrites all 21 files in order to delete 15 later.
5. **B0 D4 — removed activity charters are parked** under
   `openspec/changes/2026-08-11-charter-set-reshape/parked-phase-guidance/`, not deleted. *Rejected:
   git history* — recoverable is not findable.
6. **B0 D8 — existing projects are left entirely alone.** Their charter rows are operator-owned data.
   Stated explicitly so a later session does not "finish the job".
7. **Approval fix D1 — two mechanisms, not one.** The run reports (prompt), the Hub sweeps at run end
   (certain). *Rejected: reporting alone* — best-effort by design, and a killed run never reports; a
   mechanism explicitly allowed to fail cannot be the only mechanism. *Rejected: a periodic age-based
   reaper* — age is the wrong predicate; staleness is "nobody is waiting", not "old".
8. **Approval fix D2 — expiry is STORED, though `declining-a-question` deliberately DERIVED
   `asker_waiting`.** `asker_waiting` is a live fact used for sorting, so storing it would go stale at
   the transition it describes; expiry is a terminal event that becomes true once. Recorded because a
   later reader will otherwise see an inconsistency.
9. **Approval fix D3 — a stale approval is REFUSED, where a stale question is merely marked.** The
   costs are not symmetric: a stale question wastes attention; a stale approval writes a false record
   that the operator authorised an action that never happened, and for a permission that record is
   the audit trail.

## Constraints and user directives (verbatim)

**From this session:**
- *"Answer the open questions first"* — chosen over live testing and over starting new work.
- *"The permission defect"* — chosen as the work item after the questions were settled.
- Settled by selection: contrast **3.0, keep three levels**; declining **neither reason nor reopen**;
  charters **full re-shape**; non-software domain **underwriting** only (legal, finance and editorial
  were offered and not chosen).
- Twice asked simply *"what's next?"* — read as wanting a short prioritised answer and forward
  motion, not another question modal.

**Carried and still binding:**
- **The `ci.yml` question is settled** — the operator chose "just push the branch", not a draft PR.
  **Do not raise it again.**
- **Handoff cadence:** only when asked, or when an openspec change is done.
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- *"Kind of lost"* / *"What is taking so long?"* — sensitive to volume and wall-clock.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; never mark a task complete
  on the strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**
- **`openspec validate --strict` only inspects a requirement's OPENING LINE for SHALL/MUST.** A
  requirement whose first sentence is non-normative fails with *"must contain SHALL or MUST"* even
  though SHALL appears two lines down. **Lead with the normative sentence.**
- **`npx openspec validate --change <name>` is not a flag** — it is `--changes` (plural, all), or
  `npx openspec validate <name> --strict` for one.
- **Claude Code silently ignores unknown flags.** `claude --definitely-not-a-real-flag xyz --version`
  exits 0. **"The CLI accepted it" proves nothing** — this invalidated a test before it misled.
- **`--permission-prompt-tool` is absent from `claude --help` but still works.** 16 occurrences in
  the binary; documented there as *"only works with `--print`"*. Do not conclude it was removed.
- **`--permission-mode manual` IS valid** in 2.1.221 (`acceptEdits, auto, bypassPermissions, manual,
  dontAsk, plan`).
- **`hub/hub/data/charters/` seeds are scanned by a glob** — a `.md` file there with no
  `charters.json` key seeds nothing but is still checked by `test_agent_facing_text.py`.
- **`mcp.get_tools()` does not exist on FastMCP 3.1.0** — it is `await mcp.get_tool("<name>")`.
- **`strings` is not available in this Git Bash.** Use `grep -ao` piped through
  `tr -c '[:print:]\n' '.'` to read a binary.
- **The Bash tool's cwd persists across calls** — an `ls hub/ui/src/...` failed because a previous
  call had left it in `hub/ui`. Bit again this session; use absolute paths or re-`cd`.

**Carried and still true:**
- **A background shell started with the Bash tool dies at session teardown.** Start the Hub via WMI:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
  Log at `%TEMP%\agentweave-hub.log`, **not** in the repo.
- **Nine UI test files mock `@/api/questions` explicitly**, so **any new export breaks 52 tests**.
- **Renaming an exported Python function breaks collection for the whole suite** — grep after any rename.
- **`hub/data/agentweave.db` is the live database.** Project `proj-cddb0827`, named **Testbed**.
- **`openspec` CLI rejects change names starting with a digit** — create letter-initial, then `mv`.
  **There is no `openspec sync`**; deltas are applied by hand.
- **`pytest hub/tests/ tests/` together fails collection** — run separately. Default `python` has no
  pytest; use `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`npm run lint` does not work**; `npx tsc --noEmit` is the check. **`npx tsc`/`npx vitest` fail
  outside `hub/ui`.**
- **The visual-language contract rejects raw hex** in `src/components/**`, except `SetupModal.tsx`
  and `SpecFrame.tsx`. `index.css` is where tokens are defined, so hex there is expected.
- **`preview_snapshot` is unreliable**; **`preview_press` and `preview_resize` do not work.**

## Verification

**Ran, with real output:**
- `npx vitest run` — **759 passed across 80 files** (751/79 at session start). `npx tsc --noEmit` clean.
- `npm run build` + `rm -rf` + copy + `diff -rq` — **identical**.
- `npx openspec validate --changes --strict` — **10 passed**; `--specs --strict` — **29 passed**.
- **Contrast maths recomputed independently** of task 8.9's table, via a standalone script; every
  new value clears 3.0 on all four surfaces in both modes.
- **Negative-control on the new test:** reverted dark `--text-3` to `#5c5c66`, ran, got
  `AssertionError: dark --text-3 (#5c5c66) on --bg is 2.99, below the 3.0 bar` — then restored.
- **Live Claude probe** (`testbed/scratch/run_probe.sh`), a stub approver with **no Hub in the loop**,
  driven by the exact argv `build_command` produces:

  | delay | approver called | allow returned | tool executed | elapsed |
  |---|---|---|---|---|
  | 0s | yes | yes | **yes** — `hello.txt` written | 10s |
  | 65s | yes | yes | **yes** — `hello.txt` written | 72s |

- **FastMCP serialization probe** on the real registered `approve_tool_call`: `output_schema` `None`,
  `structured_content` `None`, single `type="text"` block with
  `{"behavior": "allow", "updatedInput": {...}}`. The `CLAUDE.md` trap is genuinely avoided.
- **Live Hub** (`:8010`, PID **21272**, still up): `/openapi.json` confirms all five permission
  routes exist and match what `_hub_request` calls.

**NOT run, and deliberately:**
- **`pytest hub/tests/` and `pytest tests/` were NOT run this session.** No Python source changed —
  only markdown and one CSS file — but the baselines (1500 / 372) are therefore **carried, not
  re-measured**. Run them before trusting that number.
- **`ruff`/`black` not run** — no Python changed.
- **Nobody has looked at the new contrast values on screen.** The maths passes; the *look* is
  unverified, and it is a look-and-feel change.
- **No agent process has been spawned against any of the four unarchived changes.** Unchanged from
  handoff 0033.
- **The approval defect is diagnosed but NOT fixed and NOT reproduced against the real Hub.** The
  diagnosis is from code reading plus route inspection plus a Hub-less probe. The end-to-end
  reproduction is task 1.1 of the new change.
- **B0 and the approval fix are proposals only — zero implementation.**

## Git state

Branch `hub-native-experience`, HEAD **`6b92101`**, working tree **clean**, **0 unpushed**
(`origin/hub-native-experience` is at HEAD). **383 ahead of local `master`, 387 ahead of
`origin/master`.**

Hub running as PID **21272** on `:8010`, started via WMI on 2026-08-11 12:38, survived two session
teardowns.

## Next steps

1. **Implement `2026-08-11-permission-request-expiry`, starting with task 1.1**: write a failing test
   at the HTTP route level in `hub/tests/` that opens a request through
   `POST /api/v1/agent-actions/permission-requests`, lets the wait lapse with no decision, and
   asserts the row is not `pending` and that `POST /api/v1/projects/{id}/permission-requests/{rid}/decide`
   is refused. **It must fail on today's code for the stated reason** before anything is fixed.
   Then tasks 2–6 in order.
2. **Or implement `2026-08-11-charter-set-reshape`** (33 tasks) — no unknowns, fully specced.
3. **The six changes waiting on one operator sitting.** 20 open tasks, nearly all human-only,
   collapsing into four activities: reduced-motion toggle (closes charcoal 8.10, contextual-nav 7.7,
   conversation-first 7.5, one-chat 6.4 — and `2026-08-04-hub-contextual-navigation` has **only that
   one task left**); one keyboard pass (charcoal 8.8, conversation-first 7.4, one-chat 6.3); pane
   proportions (conversation-first 7.1–7.3, one-chat 6.1–6.2, 6.5); one live agent run (declining
   6.8–6.9, blocked 8.10–8.13, run-task-binding 8.15–8.16).
4. **Archive whatever passes**, via `openspec-archive-change`.
5. **Remaining roadmap:** A2 (shell conformance audit), then B2–B7.

## Open questions for the user

1. **Which of the two proposals to implement first** — the approval fix (live defect, diagnosis
   fresh) or B0. Asked at the end of the session; not answered.
2. Carried: should `.claude/handoffs/` stay tracked (**120 files, confirmed not gitignored**);
   `testbed/CHECKPOINT-TEST-GUIDE.md` names the old project.
3. **Resolved this session, do not re-ask:** the contrast bar, declining's reason/reopen, the charter
   count, and the non-software domain.

## Read on resume

- **This file's "Dead ends" first** — the openspec-validate opening-line rule and the
  "Claude Code silently ignores unknown flags" trap both cost real time this session.
- `openspec/explorations/2026-08-10-operator-approval-not-honoured.md` — the full diagnosis and the
  six eliminations. **Read before touching anything permission-related**, so the dead leads are not
  re-investigated.
- `openspec/changes/2026-08-11-permission-request-expiry/design.md` — D1–D6, and `tasks.md` §1, which
  is next-step 1.
- `openspec/changes/2026-08-11-charter-set-reshape/design.md` — D1–D8 if picking that instead.
- `hub/hub/mcp_server.py` `_ask_operator` (~line 680) and `approve_tool_call` (~line 724) — the
  timeout path that writes nothing back.
- `hub/hub/api/v1/agent_trigger.py:1448-1452` — the Codex expiry the Claude path needs an equivalent
  of, and `:1270` / `:1656`, the two run-end sites.
