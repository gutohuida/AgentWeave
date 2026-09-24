# Decisions waiting for the operator

The backlog of questions the unattended windows could not answer for themselves. Written by the
windows, cleared by the operator, and **durable** — before 2026-09-01 these lived only in
`STATE-night.json`, which each window rewrites, so the list survived by being copied forward by
hand and had drifted into duplicates.

Contract, matching `APPROVALS.md`: **the status token is the authority.** One row per decision.

```
- OPEN      <id>  the question
- DECIDED   <id>  what was decided, and when
- DEFERRED  <id>  why, and what would reopen it
```

A window may **add** rows and may sharpen an OPEN row's evidence. A window may never mark one
DECIDED. Absence is not consent.

---

## Open

### The MISREPORT ratchet measures a decayed table -- 2026-09-21 night, OPEN

- OPEN      F396-rekey  **How should `RENDERS` be re-anchored, and who triages the 18 sites that
  now carry no classification at all?** Measured tonight (F396 in `scripts/drive/FINDINGS.md`):
  `n11_query_error_surface.RENDERS` is keyed by `(file, line)`, **8** of its 57 `MISREPORT`
  classifications match no live call site, and the ceiling `MISREPORT_CEILING = 52` was **already
  holding 5 dead keys on the day it was measured** (`6484de4`, 2026-09-10) -- so the current count
  of 49 is decay, not repair, and zero surfaces were actually fixed. The window did not change
  anything, because the repair is a change and the night window does not write proposals.

  **Three parts; only the operator should answer the second and third:** (1) re-anchor the key to
  something a line shift cannot move -- `(file, hook)` is the obvious candidate and is already in
  every site record; (2) whether to re-measure the ceiling from the re-anchored table, which will
  jump back up toward 57 and must not be read as a regression; (3) whether the **18** currently
  `UNCLASSIFIED` live sites get hand-triaged in the same change or a later one -- six are
  recoverable from the dead keys' recorded `why` strings, twelve have never been classified at all.

  **What must not happen meanwhile:** lowering `MISREPORT_CEILING` to 49. `_ratchet`'s warning text
  asks for exactly that on every run, and this window's own iteration 8 wrote it down as a chore.

**One row is open, immediately above. The two rows below it are discharged, and both were
verified so on 2026-09-19.**
They are kept in place, not deleted, because each carries the reasoning and the measurements behind
a decision the corpus still relies on — and a decision log that is silently rewritten stops being
evidence. **Read them as history. Neither is work waiting on the operator.**

- **`a-quote-can-spell-a-slash` / F332-rule — fully discharged.** The row reads *"REVISING — take the
  night's candidate correction through one more verification round, then build"*. That happened:
  **F332's status is `fixed 0e52ad4`**, and the change is archived at
  `openspec/changes/archive/2026-09-15-a-quote-can-spell-a-slash`. The blocked night-queue items it
  names (`f332-s4`…`s7`) survive only inside `.agentweave/tasks/`, which is gitignored scratch, not
  the corpus.
- **F352-free — decided, and the decision shipped.** *"Reject (d), go with (f), already shipped"*,
  2026-09-15; `4b59ee0` (`a-task-nothing-will-move-holds-nobody`) is archived. **What is still live
  is a finding, not a decision:** F352 reads *"open for the visibility half; the definition half is
  fixed `4b59ee0`"*. The visibility half belongs in `FINDINGS.md`, where it is, and needs no
  decision from the operator to be queued.

**If a future row is genuinely open, put it above this banner**, so this section keeps meaning what
its name says.

### a-quote-can-spell-a-slash stopped at §2 — 2026-09-13 night, DECIDED 2026-09-15

- DECIDED    F332-rule  **REVISING — take the night's candidate correction (below) through one
  more verification round, then build.** Decided 2026-09-15, by the operator, in an interactive
  session. *Rejected:* the blunter "refuse every codepoint escape above 0xFF on Windows" option —
  it needs a new `_UNCHECKED` reason string, which §2.3 forbids, so it is not actually cheaper, it
  just moves the cost onto a different rule.

**What was found.** The rule was built exactly as tasks §2.2 states (not committed), then measured
through `_decide` and real Git Bash. It **allows two writes outside the workspace that today's lexer
refuses**, on Windows only. The cause is in design D1's invariant, "safe iff it never emits *fewer*
separators than bash". That is half of it. A backslash the decoder keeps but bash does not is a
phantom directory level on Windows, and a later `..` climbs out of it:
`mkdir A; echo hi > $'A\Uffffffff/../../x'` writes outside in every locale (bash emits nothing for
`\U` ≥ 0x80000000), and `$'A\u0100/../../x'` does the same under a UTF-8 `LANG`. Evidence, the
measured rendering table and the reproductions are under F332's *Night note* in
`scripts/drive/FINDINGS.md` and at the top of the change's tasks §2.

**The night's candidate correction, for the day window to re-derive, not to adopt as written.**
The invariant becomes *reproduce bash's separator structure exactly, and judge every reading
where it depends on the locale*:
- `\u`/`\U` from 0x100 to 0x7FFFFFFF: two readings, the C-locale literal (backslash kept) and the
  UTF-8 one (a non-separator character). Refuse if either refuses. One way to build it is a flag on
  `_lex` and one `_read_command` pass per reading, the way `_decide` already reads an unknown tool
  in both dialects.
- `\U` ≥ 0x80000000: nothing, which is what bash emits in every locale. This moves **N3**
  (`$'\Uffffffffx'`) to *allow* on Windows, since bash writes `x` inside, and D2's N3 row with it.
- `\cX`: the control character of X's first UTF-8 byte (`\c` + é is `03 a9`), per tasks §2.2's "any
  real body character". The night briefly restricted it to ASCII X, which re-created the phantom
  level. Measured, then dropped.
- New D2 rows pinning both escapes above (Windows deny *outside*), plus a mutation that keeps the
  backslash for `\U` ≥ 0x80000000 and one that renders only the C reading.
- `$$'…'`: bash reads `$$` as a pair (the PID), so what follows is an ordinary `'` quote, not
  ANSI-C, but the lexer as built opens ANSI-C at the second `$`. Worked by hand and **not
  measured**: it can only over-refuse, because the extra `$` already sends any such word that
  holds a separator to rule 3, *cannot be checked*. The revision should say which way it goes
  and pin a row for it.

The other option is to refuse every word holding a codepoint escape above 0xFF on Windows as
*cannot be checked*. It is simpler, but the `_UNCHECKED` wording names variables, `~` and
substitutions, so it would need a new reason string, which §2.3 forbids.

**What stays.** `1ebff15` (§1, tests only, green: 182 passed, 1 skipped, 16 xfailed on Windows)
stays on the branch. Its N3 *after* answer on Windows is wrong under the correction; the revision
changes that row. The night queue's f332-s4…s7 are blocked on this row. Its CI XFAIL half of 7.1
is collected: run `34786122094`, `hub-test` job `103801807485`, green with 11 xfailed. The 11 are
G1–G10 and D1, the same set WSL measured.

### F352-free — what "free" means for review staffing, raised 2026-09-14 by REV, DECIDED 2026-09-15

- DECIDED    F352-free  **Reject (d). Go with (f), already shipped.** Decided 2026-09-15, by the
  operator, in an interactive session, after the Opus validation below. **The five-option frame
  (a)-(e) put to the operator was stale.** The
  2026-09-15 night shipped `4b59ee0` (`a-task-nothing-will-move-holds-nobody`, archived), which
  replaces D4's blanket "any active task holds" rule with **option (f), reachability**:
  `hub/hub/scheduler.py:1138`, `loop_id in live or (task_id, assignee) in queued` — a holding counts
  only if a live loop still walks it or a queued turn names it. (f) was not one of the five options
  put to the operator; it answers a different, narrower question (unreachable phantom holdings) than
  D4's "should review use a looser rule than new work" — but it resolves the LoopEngine snapshot
  that motivated the question: the eight NULL-`loop_id` holdings on `dev`/`dev_2` are now reachable-
  free, proven by `hub/tests/test_a_task_nothing_will_move_holds_nobody.py:307`
  (`test_the_loopengine_shape_staffs_its_review`). Architect and tester correctly stay held — their
  tasks are in-loop, real queued work.
  An independent Opus adversarial review (2026-09-15), asked to validate (d) against this corrected
  premise, **rejects (d) in favour of (f)**: (d)'s "not already reviewing another `under_review`
  task" throttles concurrency, not sequence, so an agent with five in-loop `pending` tasks stays
  permanently review-eligible under (d) — D4's pile-up recreated under (f) wouldn't arise, since a
  real in-loop holding still counts. (d) also offers reviews into an unresolved worktree-collision
  gap (`hub/tests/test_task_worktrees.py:434`,
  `test_two_tasks_held_by_one_agent_conflict_as_two_workspaces`) that (f) cannot reach, because (f)
  still holds an agent with a real in-progress in-loop task. Verdict text and citations verified
  directly against the code and commit by this session, not taken on the subagent's word alone.
  **Decided:** REJECT (d); build the F353 half (`F352-split`, already approved above) now;
  re-derive the rung-3 naming half against **(f)**, not the stale (e) the change was written
  against (`proposal.md:187`, *"the rung-3 half is written against (e) today, and the answer
  re-derives it"*). This closes `F352-free`.

---

## Re-triage of 2026-09-01, evening — eight rows to three

The morning triage folded 32 raw entries into 8 rows. An evening pass compared all eight **against
the code** rather than against each other, and six of them turned out not to be decisions.

Two structural faults caused most of it.

**One token cannot answer ten questions.** D-7 absorbed ten entries and D-8 seven. The contract at
the top of this file says one row per decision and the status token is the authority — so there was
no answer the operator could give that made either token true. Answer two of D-7's ten and it stays
`OPEN`, and the answered parts get re-asked. Both were unclosable by construction, which is why
both sat. **D-1 is the only row that ever closed, and it is the only one that was a single
question.** Grouping is good for reading and fatal for tokens: from here, group in prose, tokenise
per question.

**A label can block work it does not describe.** D-7 was named "response-shape and API-surface calls"
and justified as "each changes a contract an existing caller depends on". Measured against the code,
**one of its ten entries** actually does. Three are purely additive — `GET /tasks/{id}/transitions`
is a new route with nothing to break (verified: no route and no MCP tool exists, the thirteen code
references are all writes), and `F212` adds a `document_id` the same response already carries. Those
sat parked behind a rationale that was never true of them.

### Where every earlier row went

| Was | Now | Why |
|---|---|---|
| **D-1** fastmcp ceiling | **stays, DECIDED** | Ratified in session 2026-09-01. Kept below as history. |
| **D-2** pin fastapi | **→ R-1** | The path that actually bit is already closed; what remains is an instance of the unwritten ceiling rule. |
| **D-3** refusals with no surface | **→ R-1** | "One convention or eleven fixes?" is R-1's question, and this is its best-evidenced instance. |
| **D-4** standing rules vs instances | **→ R-1**, three rows dropped | Measured: three of its four sweeps are 2-9 sites. Only the fourth needs deciding. |
| **D-5** sweep vs repair | **→ queue** | Overtaken: two of its three severity-A items now have approved changes. |
| **D-6(a)** archive collision | **→ R-2** | A genuine tooling call, unrelated to (b). |
| **D-6(b)** corpus ahead of code | **→ R-1** | "May a task tick on backend evidence alone?" is a rule question. |
| **D-7** API-surface calls | **→ R-3 + queue + R-1** | Splits three ways; see below. |
| **D-8** stale rows | **→ queue** | A bring-forward list, not a decision — and it rests on a figure this file already disproved. |

Nothing is lost: every original entry number is still named by whichever row now carries it.

---

### R-1 — Does this repo enforce conventions, or repair instances?

**DECIDED 2026-09-08 00:30 — ENFORCE, AS A RATCHET. By the operator, in session.** Absorbs D-2,
D-3, D-4, D-6(b), and behind them entries 3, 5, 8, 10, 11, 13, 15, 16, 20, 27, plus F169, F173,
F178, F179, F180, F187, F190, F195, F197, F201.

**The decision.** When this repo learns a rule it **writes a check** — and the check freezes today's
count as a ceiling that may shrink and may never grow. It does **not** repair every existing
instance before the check may go green.

**Why the question sat a week: both readings of it cost about twenty nights.** Repairing 35 routes
and 51 misreports one at a time is more than twenty. Enforcing *as a sweep* — write the check, then
fix everything it flags before it can pass — is the same cost arriving all at once. Neither fits a
one-person, nights-only operation, so neither got taken.

**The reframe that resolved it: the repo already does all three things, and the third is a ratchet.**

- It already **enforces**, thirteen times: `test_tool_surface_matches_server.py`,
  `test_fastmcp_api_contract.py`, `test_mcp_server_stdio_surface.py`, `test_mcp_body_contract.py`,
  `test_ui_build_stamp.py`, `test_ui_staleness.py`, `test_requirement_drift.py`,
  `test_conversation_contract.py`, `test_briefing_names_its_contract.py`,
  `test_timestamp_serialization.py`, `test_evidence_restamp.py`,
  `test_agent_tool_surface_phase7.py`, `test_session_sync.py`. So "does this repo enforce?" was
  never the open question — it enforces, and has for weeks.
- It already **ratchets**: `.claude/autonomous/mypy-baseline.txt` is 172 lines of frozen known
  failures that must not grow, and `test_ui_build_stamp.py` gates its stricter
  bundle-matches-source assertion behind `AW_CHECK_UI_BUNDLE=1` for the same reason.

A ratchet is therefore this codebase's convention rather than this decision's taste — the same
argument round 3 used to approve `2026-09-06-an-unread-editor-cannot-overwrite`.

**What this buys.** ~20 findings stop being backlog and become *bounded and non-growing*. You do not
finish 51 misreports; you stop the 52nd and pay the rest down as you touch the files.

**What it costs, stated plainly.** The 35 client-less routes and the 51 operator-reachable
misreports **stay wrong, indefinitely, with a passing test blessing them.** That is the trade and it
was taken knowingly. Any single one of them that is a real operator-facing defect comes *out* of the
allowlist and gets fixed on its own merits — that is a per-instance call and R-1 does not pre-empt
it.

**The three checks this authorises**, sized against the tree at `a6f67af` and re-measured
2026-09-08 00:20 (both scripts reproduce their 2026-09-02 figures exactly):

| Check | Promote from | Frozen ceiling | Covers |
|---|---|---|---|
| route reachability | `scripts/drive/n10_route_reachability.py` | **35** routes with no client (33 distinct paths); 6 more whose hook nothing renders | F169, F187, F260 |
| query error surface | `scripts/drive/n11_query_error_surface.py` | **51** MISREPORT sites an operator can reach, of 107 call sites, 7 of which bind the error | F173, F178, F179, F180, F195, F197, F201 |
| dependency ceilings agree | new, small | the three `fastmcp>=2.0,<4` declarations in `pyproject.toml`, and `starlette<2.0` | old D-2, entry 31 |

**Both measurement scripts already exist and both ran clean.** The work is promoting them from
`scripts/drive/` into `hub/tests/` with a frozen baseline, which is why this is one window and not
twenty. **It is Stage 6 of `ROADMAP.md`, not the next thing built** — the four approved changes and
the F292 instrument repair come first.

**Consequences elsewhere, settled by this and needing no further decision:** the old **D-2**
(FastAPI's own major) is an instance of the ceiling rule and is covered by check 3. **D-6(b)** —
may a task tick on backend evidence alone? — is answered *no*: a rule that cannot be checked is not
enforced, so a requirement with an unbuilt UI half does not tick. Three of D-4's four sweeps were
already measured at 2–9 sites and drop into the queue as ordinary instances.

**Not settled by this:** F190's payload-ordering rule. CLAUDE.md records that only the instance it
was learned from is checked and no sweep has been run over the other payload-shaped consumers.
Whether that rule gets a fourth ratchet is a separate, later call — it needs a way to enumerate
payload-shaped consumers first, and nothing does that today.

---

#### The evidence this was decided on, retained in full

Everything from here to `### R-2` is the case as it stood while R-1 was OPEN. It is kept because it
is the justification for the ceilings above, and because the two scripts it names are the ones being
promoted to tests. **Read it as the basis for a decision already taken, not as an open question.**

The question in one line: **when the repo learns a rule, does it write a check that enforces it, or
does it fix the instance and rely on remembering?**

**The repo already answers this two ways at once, which is the tell.** `fastmcp>=2.0,<4` and
`starlette<2.0` are the *same move* — a defensive ceiling so a major needs a conscious bump — taken
twice, months apart, each with the reasoning written into a comment beside it. That is a standing
rule in practice that no file states and no check enforces. Meanwhile the same defect class gets
re-filed: *the Hub computes a sentence for an operator and no file under `hub/ui/src` reads it* has
been filed **six times across two nights**.

**The evidence, verified against the tree 2026-09-01:**

- `ChartersPage.tsx:191` is `createCharter.mutate(values, { onSuccess: … })` — **no `onError`**. The
  refusal is a plain 422 the mutation already holds. Nothing needed computing, wiring or designing,
  which is what makes this a missing convention rather than a refactor.
- `GET /documents/{path}/rigor-history` exists (`hub/hub/api/v1/spec.py:535`) and returns **zero
  hits** across `hub/ui/src`. Ten more operator-only routes are 0-hit in both the source and the
  served bundle. `spec_rigor.py`'s own docstring justifies allowing demotion *on the grounds that
  the audit trail exists* — and no screen shows it.
- The old D-2 is closed at the point it actually bit: `starlette<2.0` is pinned nineteen lines below
  `fastapi>=0.110`, and its comment names the exact incident — *"an unbounded fastapi>=0.110 once
  let pip silently resolve starlette 1.6.0 in CI while dev ran 0.52.1."* Both CI failures were
  Starlette crossings. What is left is FastAPI's own major: real, unrealised, and a *third* instance
  of the same unwritten rule.
- `runner-registry/spec.md:72-73` is a shipped requirement whose UI half was never built — ticked on
  backend evidence alone and archived. The approved `runner-model-is-chosen-from-the-catalog`
  repairs that instance; whether a task may tick on backend evidence alone is the rule question.
  *(Pointer corrected 2026-09-02, night window: that requirement now starts at
  `openspec/specs/runner-registry/spec.md:67`, because the change's delta was synced into it on
  2026-09-02, and it is **no longer unbuilt** — the picker shipped and was driven against the
  served bundle. The instance is closed; the rule question the bullet raises is not, which is why
  the bullet stays.)*

**The "ten more", enumerated — measured 2026-09-02 by the night window.**

The second bullet above has asserted *"ten more operator-only routes are 0-hit in both the source
and the served bundle"* since 2026-08-31 without the list ever being written down. Here it is, and
**the figure is not eleven — it is 35.**

Reproduce with `py -3.11 scripts/drive/n10_route_reachability.py`. Routes are read from
`hub.main:app`'s own route table rather than from decorators, so an include-time prefix cannot be
mis-transcribed; UI call sites are the `/api/v1…` literals `client.ts`'s helpers require, with the
HTTP verb taken from which helper carries each one.

| | |
|---|---|
| declared `/api/v1` route+method pairs | **187** |
| under `/api/v1/agent-actions` (the agent API, operator-invisible by construction) | 32 |
| everything else | **155** |
| reached from `hub/ui/src` with a matching verb | 110 |
| not reached from the UI | **45** |
| — of those, called by the CLI's `HttpTransport` instead | 10 |
| — **of those, called by no client anywhere in this repo** | **35** (33 distinct paths) |

**Verb matters and path-only sweeps get this wrong.** `GET /projects/{id}/charters/{charter_id}`,
`DELETE /projects/{id}/jobs/{job_id}` and `POST /projects/{id}/agents/{name}/output` all sit on
paths the UI *does* call — with a different verb. A sweep that compares paths reports 40 unreached
and calls those three reached; comparing (verb, path) reports 45 and is right.

**The CLI is a second client, and its ten are not operator gaps.** `HttpTransport._request` takes a
path *relative* to one of three prefixes (`transport/http.py:145-149`), so its calls never contain
the string `/api/v1` and any repo-wide grep for the literal misses every one: `POST …/agents/{name}/
heartbeat`, `/output`, `/context-usage`, `POST …/logs`, `POST …/messages`, `POST …/questions`,
`GET …/questions/{id}`, `POST …/session/sync`, `POST …/tasks`, `DELETE …/jobs/{job_id}`.

**The 35 with no client at all**, grouped by the file that declares them:

| Area | Routes |
|---|---|
| `spec.py` — 17 | `GET …/project/documents/{path}/rigor-history` · `PUT …/project/documents/{path}/content` · `POST …/project/documents/{path}/merge` · `POST …/project/documents/adopt` · `POST …/project/spec/adopt` · `POST …/project/spec/documents/arrange` · `POST …/project/spec/reindex` · `GET …/project/spec/requirements` · `GET …/project/spec/requirements/{identifier}` · `GET …/project/spec/drift` · `POST …/project/spec/drift/detect` · `POST …/project/spec/drift/{drift_id}/resolve` · `GET …/project/spec/evidence` · `POST …/project/spec/evidence` · `POST …/project/spec/evidence/{evidence_id}/decision` · `GET …/project/spec/evidence/{evidence_id}/reviews` · `PUT …/project/spec/evidence-retention` |
| `agents.py` — 5 | `GET …/agents/agent-context` · `GET …/agents/configured` · `GET …/agents/context` · `POST …/agents/register` · `POST …/agents/request` |
| `events.py` — 3 | `GET /api/v1/events/ticket` · `GET …/events` · `GET …/events/ticket` |
| `tasks.py` — 2 | `POST …/tasks/{task_id}/dependencies` · `DELETE …/tasks/{task_id}/dependencies/{depends_on}` |
| `inbound_queue.py` — 2 | `GET …/queue/settings` · `PATCH …/queue/settings` |
| `loops.py` — 2 | `POST …/loops/{loop_id}/archive` · `POST …/loops/{loop_id}/control` |
| four singletons | `GET …/projects/{project_id}` · `GET …/charters/{charter_id}` · `GET …/checkpoints/{checkpoint_id}/rendered` · `GET …/worktrees/conflicts` |

Each is 0 in the served bundle too, probed by string literal rather than by symbol name — Vite
renames every local, so an absent hook name proves nothing, while template literals survive intact
(``/api/v1/projects/${n}/loops/${e}`` is in `index-x3nWU-L2.js` verbatim). Five fragments that
*must* be present are probed alongside as controls; all five are.

**The second class the bullet did not separate: a client exists, and nothing renders it.** Six more
routes have a working hook in `hub/ui/src/api/` that no component outside its own file imports —
`requestCompact` (`POST …/agents/{name}/compact`), `requestNewSession` (`…/new-session`), `useJob`
(`GET …/jobs/{job_id}`), `useRunnerLaunchability` (`GET …/runners/launchability`),
`useAgentLaunchability` (`GET …/agents/launchability`) and `useDivergences`
(`GET …/tasks/divergences/recent`). This is F260's shape, and it is worse than it reads: **the
bundler tree-shakes them, so all six paths are 0 in the shipped bundle** — measured with the
terminating backtick, because `runners/launchability` *is* in there as the prefix of
`runners/launchability-by-provider`, which is the variant that ships. The client code exists,
passes its unit tests (`useAgentLaunchability` is named by nine test files) and is not in the
product. `useUpdateJob` is orphaned the same way but its route is not, because `usePauseJob` and
`useResumeJob` `PATCH` the same path.

**What the eleven was probably counting: unknown, and no subset of the measurement lands on it.**
The nearest natural groupings are both 17 — the `spec.py` routes, and the `GET`s among the 35. The
figure looks like an estimate that was never enumerated, which is the whole reason this item
existed.

**110 is an upper bound, not a count of what an operator can reach.** The unrendered-hook pass is
depth-1: it asks whether any *file* outside the hook's own names it, so a hook imported by a
component that is itself imported by nothing reads as consumed. F260 is exactly that — `useMessages`,
`useMessageHistory` and `useMarkRead` are all imported, by `MessagesFeed`, which nothing imports and
which is absent from the bundle. So `GET …/messages` and `PATCH …/messages/{id}/read` are counted
in the 110 here and are unreachable in the shipped app. Sizing that class properly needs a reachability
walk from `App.tsx`, not a symbol grep; this measurement does not attempt one, and the 35 and the 6
are both floors.

**Limits, stated rather than left implied.** A static sweep can show that no caller *in this repo*
names a route; it cannot show the route is dead, and an external client is out of scope. The bundle
probe is path-level, so a bundle hit does not distinguish verbs — it is used here only to confirm
absences. Nine matches were ambiguous because the UI computes a segment (``/projects/${action}``
could be `create`, `open` or `{project_id}`); each was resolved by reading the line and is recorded
with its line number in the script's `HAND_RESOLVED`. Two more are composed by
`agentChat.ts:213`'s `conversationPath()` helper rather than written at the call site, which the
literal scan cannot see; both are in fact called. The unrendered-hook pass names exported symbols,
which would miscount a hook re-exported through a barrel — `hub/ui/src/api/` has no barrel and no
`export *`, checked.

**This block adds evidence only.** R-1's two halves, (a) and (b) below, are untouched and remain
the operator's to answer.

**What the old D-4 got wrong, measured.** It presented four findings as symmetric, each naming "a
grep that would say how big it is". The greps were never run. They are:

| From | Measured sweep |
|---|---|
| **F190** | **2** functions — and both are deleted by the change approved 2026-09-01 |
| **F195** | 21 `subprocess.run`/`Popen` sites, **13 already pass `cwd`** → ~8 |
| **F201** | **9** `model_validator`s under `hub/hub/schemas/` |
| **F197** | **133** `useQuery` declarations; 62 of 97 component files never mention `error` |

At 2, 8 and 9 sites the rule-or-instance question is academic — do both, in an afternoon. Those
three rows are **queue work, not decisions**, and are moved below. Only **F197** is large enough to
need an answer, and its real question is not the one D-4 asked: it is whether an unrendered query
error is a defect *at all* in every case, since a background poll's failure may be correctly
invisible. (133 is an order-of-magnitude grep, not a defect count.)

**One of R-1's instances has now answered "enforce", and the answer is half-done on purpose
(2026-09-02 night window, task 5.3 of `a-turn-says-how-it-ended`).** The rule F190 taught —
*a test for code that consumes an API payload uses the ordering that route actually returns, and
some test fails if the route's order is reversed* — is now **written down in two places a reviewer
meets**: as a requirement, *Payload-shaped model functions are tested against real route ordering*
(`agent-stream-events`), and as a line in `CLAUDE.md`'s Critical Rules.

**Stating it is not enforcing it, and this row should not be read as if it were.** What exists is
the rule plus a check on the single instance it was learned from: `test_a_turn_says_how_it_ended.py`
asserts the timeline route returns newest-first and that its truncation keeps the newest fifty —
both mutation-checked by actually reversing `agents.py`'s sort — and `timelineRunFacts.test.tsx`
asserts the client's read of the run-facts map survives a shuffled input. **No sweep has been run
over the repo's other payload-shaped consumers, and no automated check prevents the next one.**

So R-1's question is untouched: this is one convention written by hand, in the middle of the change
that needed it, with the general case still open. It is offered as evidence of what "enforce" costs
when taken seriously — a spec requirement, a `CLAUDE.md` line, two mutation-checked test sites — not
as a decision the operator has been spared.

**Pointer note.** Task 5.3 names this file's *D-4*. D-4 was dissolved by the 2026-09-01 evening
re-triage; its F190 sweep row is the table above and its queue entry is under *Not decisions* below.
This block is where the note belongs now, and `tasks.md` records the correction.

**F197 sized, 2026-09-02 (night window, N-11).** The row above is now superseded by a count.
Harness: `scripts/drive/n11_query_error_surface.py`, one command, no product code touched. The
write-up with the quotes is in `scripts/drive/FINDINGS.md` under *"F197 sized, 2026-09-02"*.

**133 was the wrong unit and does not reconstruct.** There are **57** `useQuery` declarations in
`hub/ui/src/api/`, in 56 exported hooks. `useQuery` appears on 138 lines and 114 outside imports;
no natural grep of this tree lands on 133. The `62 of 97` half does reconstruct — 97 `.tsx` files
under `components/`, 61 with no `error` in them today — but a file is not a defect count either: a
hook called by three components is three chances to render an error, and a file that never says
`error` is one missing chance, not one per query it runs.

**The unit that is a defect is a call site.** There are **107** outside `api/`, in 48 files. **6**
bind the query's `error`/`isError` and render it. **101** do not — and 3 of those could not have,
because two hooks (`useAgentOutput`, `useLogs`) destructure `useQuery` internally and return a
narrower object with no error field, so no component fix reaches them.

| What the 101 render when the fetch fails | |
|---|---|
| **MISREPORT** — a false statement reaches the screen | **60** |
| — on a surface an operator can reach | **57** (3 sit in `MessagesFeed`, F260's dead component) |
| — of those 57, an empty picker rather than a sentence | 13 |
| — a sentence, a number, or a terminal skeleton | **44** |
| **SUPPRESSED** — an alert or affordance silently does not render | 16 |
| **BLANK** — a decoration or lookup is missing; nothing is claimed | 24 |
| **NAMED** — says the data is unavailable without binding `error` | 1 |

The rule was written before it was applied and is at the top of the script; every one of the 101
is classified individually in `CLASSIFIED`, each naming the line it was read off. The mechanical
part is the 107/6/101 split and the poll flags — which of the four labels a site earns is a
reading, and disputable per row rather than in aggregate.

**The rule gained two labels while it was applied, which the brief asked it not to.** `SUPPRESSED` was split out of `BLANK` (a blocked run's approval card not rendering is not a missing avatar colour) and `NAMED` did not exist at all until `RunnersPage.tsx:198` turned up. Both narrow `MISREPORT` rather than widen it, so neither inflates the headline; both are recorded in the script's docstring.

**The question this row existed to answer — how many are background polls whose errors are
correctly invisible — has a hard answer: at most four, and none of them misreports.** Exactly two
of the 56 hooks poll (`usePendingPermissionRequests` and `useQuestions`, 3s), reaching 4 of the 101
sites; three are `SUPPRESSED` and one `BLANK`. The Hub pushes SSE rather than polling (8 of 22 api
files invalidate on an event), and an SSE-invalidated query that fails its **first** load does not
retry until the next event arrives. Even the four are pardoned only after a first success — a poll
that fails cold renders the same false empty as any other query. So the "much of this is correctly
invisible" reading of the 133 does not survive: on this tree it accounts for 4 sites, not a
fraction of the whole.

**What is on the screen, from the 44.** *"No agents connected. Run `agentweave start` to connect
agents"* (`OverviewPage.tsx:79` — it also instructs the operator to do the wrong thing);
*"Everything here is archived"* (`SpecPage.tsx:35`); *"No quality governance configured"* and
*"All reviewed tasks clear"* (`QualityHealthPanel.tsx:25-26`); *"This agent is no longer in the
roster"* (`AgentSettingsPage.tsx:42`); four `?? 0` counts in the status bar. The sharpest is not a
display defect at all: `InstructionsPage.tsx:9` seeds its editor from `if (data) setContent(...)`,
so a failed load leaves an **empty textarea with Save enabled**, and a save writes `''` over the
stored instructions. Static read, not driven.

**Two facts that bear directly on (b), stated as evidence and not as an answer.** First, the repo
already contains the worked pattern *and* its rationale: `QuestionsPanel.tsx:86` renders its error
only `if (isError && unanswered === undefined)` — *"A failed fetch used to fall through to 'No
pending questions' — an error rendered as reassurance, on the one screen where 'nothing is waiting
on you' is the most expensive thing to say wrongly"* — and deliberately does **not** replace a
screen of real questions when its 3s poll blips. Second, a check phrased as *"the site binds
`error`"* would misfire in both directions: it would call `RunnersPage.tsx:198` a defect, which
renders *"The model catalog is unavailable — this runner will use the provider's default"* from
`!!catalog` and binds nothing, and it would pass any site that binds `error` and drops it.
`JobCard.tsx:146` shows the near-miss the other way: a comment that reasons the claim must not be
made before the answer arrives, guarded on `isLoading`, which is false after an error.

**Falsified rather than asserted: none of the 60 has an error branch elsewhere in its file.** Every
`MISREPORT` site's file was re-read for any `error`/`isError` token outside the call site. 34 of the
60 have one — and all 34 are a *mutation's* error, a local `useState` error, a severity enum, a
`console.error`, or a **different** query's (`TasksBoard.tsx:57` handles `useTasks` and not
`useAllowedTransitions` one line below). Not one is a branch that would cover the query in question.
`ProjectSettingsPanel.tsx:84` is the original F197 sentence restated by the pass: `const error =
update.error ?? relocate.error` — two mutations, never the query.

**Which is the asymmetry worth carrying into (b).** The UI renders mutation failures routinely — 18
`readableApiError(...)` call sites across 13 component files, every one of them fed by a mutation or
a handler's `err` — and query failures 6 times in 107. It is not that this codebase does not handle
errors. It handles the ones it caused and not the ones it merely observed.

**Blind spot, N-10's again.** Sites are found by symbol, one level deep, so a site in a component
nothing imports counts as live; 3 of the 60 are exactly that, and were caught only because F260
had already named `MessagesFeed`. 57 and 101 are therefore upper bounds on what an operator can
reach.

**Blind spot closed, 2026-09-02 (day window, D-5).** Harness:
`scripts/drive/d5_reachability_walk.py`, which imports the two night scripts rather than
reimplementing them, so its numbers differ from theirs by the module filter and by nothing else.
The write-up is in `scripts/drive/FINDINGS.md` under *"What D-5 measured, 2026-09-02"*.

Of 170 source files under `hub/ui/src`, **157 are reachable from `main.tsx` and 13 are not** —
and 12 of the 13 have every literal that occurs nowhere else in `src/` absent from the shipped
bundle, with a dozen reachable files probed as controls and every one of their literals present.
The thirteenth, `badgeVariants.ts`, is reached only by an `import type`, which the compiler erases.
The choice of entry point does not matter: `App.tsx` alone reaches 155, the two extra being
`main.tsx` and `ErrorBoundary.tsx`.

| Figure | Depth-1 | Reachable only | What moved |
|---|---|---|---|
| routes reached from the UI | 110 | **106** | 4 pairs are reached only from dead code |
| operator routes with no live client | 45 | **49** | 35 no client + 10 CLI-only + these 4 |
| query call sites outside `api/` | 107 | **99** | 8 in dead code, of which N-11 knew 3 |
| unhandled sites | 101 | **93** | |
| MISREPORT | 60 | **54** | N-11's "57 an operator can reach" is **54** |
| SUPPRESSED | 16 | **14** | |

**The four routes are a category (a) did not have.** `GET /messages`,
`PATCH /messages/{id}/read`, `POST …/compact` and `POST …/new-session` are not *"no client was ever
written"* — a client exists, in `api/context.ts` and `api/messages.ts`, and its screens were
removed. When (a) asks whether the operator-only routes are en route to a screen, deliberately
API-only, or dead, this is a fourth answer: **the screen was there and went away**, leaving the
route and its client behind. Whatever standing rule (a) settles on has to say what happens to these.

**One line of the evidence above is wrong and is corrected here.** *"What is on the screen, from
the 44"* lists *"four `?? 0` counts in the status bar"* (`StatusBar.tsx:15`). `StatusBar.tsx` is
imported by nothing and is not in the bundle, so those four counts are on no screen —
`Sidebar.tsx:112` says as much in passing. F259, whose headline is built on the same chip, is
amended in `FINDINGS.md` for the same reason; its substance (nothing marks a message read; the
scheduler depends on the flag) is untouched.

**And the count was never the interesting number.** F271 — filed the same day, severity A — is one
of these unhandled sites, and dozens of the others are cosmetic. What separates them is whether a
failed load can be **written back**: does the query's data seed component state, does the file
write, and is there an early return that stops the write rendering while the fetch is failing. Of
the 54 MISREPORT sites, **2** seed state and write it back with no guard (`InstructionsPage.tsx:9`,
which is F271, and `AgentOutputPanel.tsx:207`), 2 do so behind a guard, 23 write without seeding,
and 27 do not write at all. If (b) becomes a repo check, that ordering — not the total — is what it
should be built on: a check that fires on all 54 equally will be turned off.

**Still evidence only.** Nothing here answers (a) or (b), nothing is marked `DECIDED`, and no
recommendation is offered.

**The decision has two halves, unchanged from D-3 and still the right two:**

**(a)** Are the eleven operator-only routes en route to a screen, deliberately API-only, or dead? A
standing answer settles the sweep's remaining rows too.
**(b)** Should a repo check assert that a server-side refusal string is grep-able somewhere in the
UI, and that a mutation whose failure an operator must see carries an `onError`?

**Why this one first.** Answering it settles the old D-2 and D-6(b) for free, empties three of
D-4's rows into the queue, and supplies the missing axis for what an unattended window may take —
see *The axis that actually predicts it* below.

---

### R-2 — Should `openspec archive` refuse a colliding delta?

**DECIDED 2026-09-08 — a repo script. By the operator, in session.** The full verdict, its rejected
alternatives and its stated weakness are under `## Decided` below (*"R-2 — a repo script"*). This
copy is kept for the question it states; **it is not the authority and no longer says OPEN.** Was
D-6(a). Absorbs entry 18. A tooling call, unrelated to R-1.

Applying a delta against the current corpus warns about nothing when two changes both carry a
`## MODIFIED` block for the same requirement. Archiving the second **reverted the first**, dropping
a qualification that had just landed. Caught only because the diff was read before committing;
repaired, and the other six were swept — exactly one collision in a batch of seven. **Two changes in
flight against one requirement is not rare here.**

Should archiving be gated on a collision check, and does that belong in a repo script, in the
`openspec-archive-change` skill, or upstream?

---

### R-3 — Four small product calls

**DECIDED 2026-09-08 — all four answered. By the operator, in session.** The verdicts are under
`## Decided` below (*"R-3 — the four small product calls, all four answered"*): thread F209's
`reason` through; **remove** `PATCH /queue/settings`; a bare `uvicorn hub.main:app` from `hub/` must
**refuse to start**; check the model catalog with a `scripts/` tool, not a CI-skipped test. This copy
is kept for the four questions it states; **it is not the authority and no longer says OPEN.**

Each was one question with two defensible answers and closable in a sentence. These are
what is left of D-7 once the additive work and the already-answered rows are removed. Absorbs
entries 1, 6, 19, 21.

- **F209** — `accept` declares a 2000-character `reason` and **stores nothing**; `reject`, three
  functions away, keeps it. Thread it through, or delete the field. The current state promises
  something it discards.
- **F196 + F198** — should `PATCH /queue/settings` exist at all? It writes four columns
  `PUT /projects/{id}/settings` already owns, with a weaker contract on both ends, and the UI never
  calls it.
- **Entry 19** — should a bare `uvicorn hub.main:app` from `hub/` **refuse to start** on the
  relative default rather than silently opening a second database beside the one everything else
  uses? This has cost time twice.
- **Entry 21** — `model_catalog.py` names `~/.codex/models_cache.json` as its source of truth and
  nothing re-checks it; it has drifted. Per-machine and absent in CI, so it can only be a
  skip-if-missing check or a `scripts/` tool. *Doing nothing is defensible; doing nothing silently
  is what let a phantom default model sit in the catalog for four weeks.*

---

## The axis that actually predicts what a window may take alone

D-7 asked *which kinds of change need the operator*, and answered "response-shape ones". Measured,
that answer was wrong about nine of its own ten entries. The property that actually separates them
is not the kind of change:

```
        is the right answer already written down?
                    │
        ┌───────────┴────────────┐
       YES                      NO
        │                        │
     REPAIR                  DECISION
   a window takes it        needs the operator
        │
        └── ...but wide or irreversible?
                    │
              REPAIR + GATE
        observe first, verify after
```

The gate arm is not theoretical: `a-turn-says-how-it-ended` was approved 2026-09-01 as a **BREAKING**
response-shape envelope — precisely D-7's blocked class — and what made it safe was not a signature
but a condition. Its phase 0 stops any builder until the defect has been observed live, and its
phase 7 puts verification in a different sitting than implementation. Authorization queues on a
person; evidence queues on a check.

**R-1 is this axis restated.** Deciding whether the repo enforces conventions is deciding whether
answers get written down — which is what moves work from the right branch to the left.

---

## Not decisions — moved to the queue

These were carried as decisions and are not. Each is work with a known answer, or a scheduling call
already made.

**From D-7 — additive, nothing to break, window-takeable:**

- **F203** — `task_transitions` is append-only, carries actor/run/policy, has a reader, and no route
  or MCP tool exposes it; drives have had to open sqlite. Verified 2026-09-01: **no GET route and no
  MCP tool exist** — the thirteen code references are all writes. `GET /tasks/{id}/transitions` is a
  new route with no existing caller to break.
- **F212** — `GET /spec/coverage` projects `unserved` to bare identifiers, which are minted per
  document, so 34 entries all read `FR-1` and feeding one back answers **422**. The same response's
  `requirements` array already carries `document_id`. Additive.
- **F202** — `GET /projects/{id}/tasks` defaults to `limit=100` with no `total`/`has_more`/`next`,
  so at 241 tasks the Overview says "100 tasks". Part two is independently fixable: `list_tasks` in
  `mcp_server.py` has no limit or offset at all. Both additive.

**From D-7 — already answered by something already written down:**

- **F185 + F181** — agent queries with no lifecycle filter. D-7 itself named clearing the bindings
  on archive as "cleanest, closes both at source", and the operator's standing directive is that the
  cleanest solution wins and "more work" is never the objection. Apply it; note that `unarchive`
  must then say the bindings are gone.
- **F193** — what archiving an agent means for its open threads. **The product already made that
  three-way choice explicitly** for archiving a conversation with a live run. Follow the precedent
  unless it is wrong.

**From D-4 — sweeps small enough that the meta-question is moot:** F190 (2 sites, already in an
approved change), F195 (~8), F201 (9). Do the narrow fix and the sweep together.

**From D-5 — overtaken by events.** Its recommendation was to spend a window on F173, F188 and F190
rather than on coverage row 9c. Since it was written, **F173** has an approved change
(`runner-model-is-chosen-from-the-catalog`) and **F190** has one approved conditionally
(`a-turn-says-how-it-ended`). Verified 2026-09-01: **F188 has no change and no design** — nothing
under `openspec/changes/` references it. What is left is not a prioritisation decision but one queue
entry: *F188 is the last unspecced severity-A.* Its cited ledger size of 219 headings is now 289.

**From D-8 — a bring-forward list.** Absorbs entries 22-26, 28, 29. Re-queue or close, per row; none
needs a decision from the operator except by being scheduled. ~~One correction: the row claims the
Hub suite runs "~25 minutes". **This file already disproves that** — `hub/tests/` was measured at
**14:39** on 2026-09-01.~~ **Withdrawn 2026-09-03: the correction was wrong, and this is a better
example of the failure it was trying to name than the thing it corrected.** One measurement does not
disprove a range. Re-measured 2026-09-03 in a DECIDE session: **3850 passed, 84 skipped, 1 xpassed
in 24:50** — with the UI suite and the CI lint set running alongside it, where the 14:39 run had the
machine to itself. Both are real; the suite is **15–25 minutes and load-dependent**, which is what
both playbooks now say. The "~25 minutes" figure was never disproven, and two days were spent with
this file asserting it had been.

**Widened again 2026-09-08 by the night window's baseline green check: 3972 passed, 86 skipped in
46:41** (`py -3.11 -m pytest hub/tests/ -q`, started 23:00:59, exit 0). That is **1.9x the stated
ceiling**, and it is the third distinct figure from three runs, so the honest statement is
**15–47 minutes and load-dependent** — which is what both playbooks now say. Two stray `python`
processes from earlier windows (started 2026-09-07 20:15 and 21:55) were resident throughout and are
the most likely contention, but that is inferred, not measured. The point the 2026-09-03 entry makes
survives intact and is reinforced: no single run is *the* figure, and a window that sizes a firing
against one of them loses the iteration. Also still live there: F47/F120's
categorical third-actor prohibition, F77 (an agent has no way to address the operator), F53/F65
never queued, five findings queued 2026-08-29 and dropped from three runs, and the 8010 trial Hub
serving four-day-old code.

---

## Decided

### 2026-09-24 — two decisions already made, now written down

**DECIDED by the operator; recorded 2026-09-24 in an interactive session** ("Record both"). Both
were decided earlier and were missing from this file. The B3 and B1 bundle rounds found the gaps
(`spec-queue/tracks/B3.md`, `B1.md`).

- DECIDED   D3-self-registration  **Agents no longer register themselves.** Self-registration is
  deleted along with `contact_mode` and its sibling columns. The operator decided this on 2026-08-29
  (handoff-0099, decision 2: *"No it does not belong in the product … I think it's a legacy thing"*;
  FINDINGS F111 *"The decision, 2026-08-29"*; `openspec/explorations/2026-08-30-release-roadmap.md:78`).
  It is carried out by the parked change `agents-no-longer-register-themselves` (B3), which is not
  yet approved.
- DECIDED   F327-scope-b  **Option (b): the dispatch, not the flow, stages `under_review`.** The
  operator chose this on 2026-09-23 (`ROUNDS.md` S13), and it **supersedes `F327-scope` option (a)
  of 2026-09-12** below. It is carried out by the parked change `a-flow-stages-its-review-in-the-dispatch`
  (B1), which is not yet approved.

### 2026-09-24 — the daily review of the twelve bundles

**DECIDED 2026-09-24, by the operator, in an interactive session** (DECIDE). Each bundle's
recommended answers were taken as recommended unless noted below. The per-change record is in
`APPROVALS.md` `## 2026-09-24`, and each change's `design.md` opens with `## Operator review,
2026-09-24`. Only the rows that are decisions rather than approvals are listed here.

- DECIDED   F42-by-design  **F42 is closed as by design** (B2 D11). A run bound to a task at
  `-> in_progress` may reach `completed` without completion evidence. Requiring evidence there
  deadlocks the ordinary path, and the residue is one attributable task per run, reviewed by someone
  else. Do not re-file.
- DECIDED   B2-follow-ups  **The 2026-08-21 decision ("failed at once, no new vocabulary") stands for
  now.** Revisiting it, together with the reaper's no-runner case, is queued as `REQUESTS.md` R7 for
  its own spec loop. History rows naming their agent is R8.
- DECIDED   B8-D6-final-warning  **A reopened, handed-over conversation keeps its free final
  compaction warning.** Only the billed steps decline (amends B8's D6).
- DECIDED   B10-stale-stop  **A stop on a loop that has already ended is refused (409)** and its
  record is left as it was. `end_loop` is write-once.
- DECIDED   B12-F278-revise  **F278's change goes back for a round** (REVISING): base64 key segments
  and short tokens inside paths.

### 2026-09-22 afternoon — F119: `doctor`'s secret filter stays broad; R9-5 reconfirmed

**DECIDED 2026-09-22, by the operator, in an interactive session.**

- DECIDED   f119-doctor-redaction  **The CLI's `doctor` keeps its broad catch-all** (`[A-Za-z0-9_=-]{32,}`,
  `src/agentweave/diagnostics.py`); it is not narrowed to the Hub's post-F31 rule. `doctor` prints env and
  config values, where a long unbroken string is far more likely a real key than an identifier. Over-redacting
  there costs a few blanked words, while under-redacting leaks a credential into a pasted report. F31's
  measurement was of transcripts and does not transfer. This closes F119, the only question it ended on.
- DECIDED   unstaffed-r9-5-reconfirmed  **R9-5 "dropped" meant accepted as is**, as recorded above; the
  operator confirmed it when asked, before tonight's arm. No APPROVALS change.

### 2026-09-22 — `an-unstaffed-review-names-its-holders` groups 2, 5, 6 approved; R9-5 dropped

**DECIDED 2026-09-22, by the operator, in an interactive session** ("Great, approve.", then "yes
dropp it"). This follows the Round 9 that the 2026-09-21 late-night `unstaffed-r8-review` decision
asked for. It ran in the 2026-09-22 day window (`design.md` `## Round 9`): R8-1..R8-5 hold, three
LOW text fixes were applied, and F407 was filed and fixed the same day.

- DECIDED   unstaffed-approve  **Groups 2, 5 and 6 are approved** (group 1 is already built). They are
  queued for the night of 2026-09-22, after F388's change. The `unstaffed-bundle` rule stands: group
  5's bundle is committed only if 5.3's served-bundle drive passed.
- DECIDED   unstaffed-r9-5  **R9-5 is dropped: accepted as is**, with neither cure (a) nor (b)
  applied. A sentence over 500 characters may end with the REJECT remedy even when no booked clause
  survived the fit. The remedy is still true, and the delta's SHALLs are met. Round 9 recommended (b),
  but each cure changes the fit's arithmetic, and three earlier rounds shipped fixes to that
  arithmetic that a later round found broken. Revisit only if it is seen live.

### 2026-09-21 late night — `an-unstaffed-review`'s three questions answered; `examples/` deleted

**DECIDED 2026-09-21 ~21:40, by the operator, in an interactive session** ("delete. yes"). The
three questions had been carried since handoff 0135.

- DECIDED   unstaffed-booked  **`an-unstaffed-review-names-its-holders`: the holdings clause reads
  `is booked for`** (R8-2), and R8's clause order stands: excluded, no runner, held, booked, running.
- DECIDED   unstaffed-bundle  **A night window may commit group 5's UI bundle.** The rule is still
  task 5.4's: commit only if 5.3's served-bundle drive passed. The operator accepts that a committed
  bundle reaches `:8000`'s live app on its next reload.
- DECIDED   unstaffed-r8-review  **Before anything is built, a short review of Round 8 only runs in
  the day window of 2026-09-22** (`DIRECTION.md` `## 2026-09-22`). It checks R8-1 to R8-5's fixes
  against the tree, not the whole change. **This decision is not an approval**: groups 2, 5 and 6
  still carry no token. If the review returns clean, that day's DECIDE session may add the row.
- DECIDED   examples-delete  **`examples/` is deleted whole**, and `CONTRIBUTING.md`'s tree line
  with it. Without `cli_session.sh`/`.bat`, whose commands no longer exist, only a README saying
  nothing there works would have been left (F405).

### 2026-09-21 night — F388's change approved after R4 and a second Opus pass

**DECIDED 2026-09-21 ~21:30, by the operator, in an interactive session** ("yes approve"). This came
after R4 on `a-hub-that-was-not-told-which-database-refuses-to-open-one` (`da19eb5`), which answered
the 2026-09-20 Opus DO NOT APPROVE. The standing adversarial Opus pass then ran over R4 and returned
APPROVE WITH FIXES, with one blocking item (the `agentweave-hub` console script and
`docs/reference/env-variables.md`). All of its items were applied in `b14342b`.

- DECIDED   f388-approve  **The change is approved, all groups (1-6).** It is queued for the night of
  2026-09-22 in `APPROVALS.md` `## 2026-09-22`, not tonight: tonight's ORDER was already full.
- DECIDED   f388-8000  **The `:8000` effect is accepted as measured.** `:8000` is a CLI-started, told
  launch (R4, corrected by the Opus pass), so (a) does not refuse it. On the operator's next restart
  it runs the new `config.py`/`main.py` with no migration and no UI bundle. Group 2's startup line
  goes to `DEVNULL` there, and that is a known limit, not a defect.
- DECIDED   f388-unreviewed  **The Opus pass's fixes are not re-reviewed**, the same call as F375. The
  build's own tests and the group 6 drive are the check. If a task disagrees with the code, the task
  is the more likely thing to be wrong.

### 2026-09-21 late evening — F375's change approved after three rounds

**DECIDED 2026-09-21 ~19:50, by the operator, in an interactive session** ("approve"), after the
spec loop on `a-word-without-a-separator-can-still-leave` (R1 `38c243a`, R2 `55ae8e7`, R3 `4f87390`)
and a summary of its five open questions with a recommendation on each. Approved as recommended:

- DECIDED   f375-tilde  **R3's narrowed `~` check** (design Open Question 5): refuse only the shapes a
  shell substitutes (`~`, `~+`, `~-`, `~name`); `~N` and `~30%` stand.
- DECIDED   f375-d7  **Option-joined values stay in scope** (Open Question 3), with R3's widening of
  the colon form to both dialects and `--name:`.
- DECIDED   f375-d9  **Archived `a-url-is-not-a-path` D9 is superseded** (Open Question 4) for R8
  (`cd ..`), R9 (`git -C ..`) and its two PowerShell residuals.
- DECIDED   f375-findings  **File D5, D6 and brace expansion as findings** (Open Question 1): F401,
  F402, F403, all (B).
- DECIDED   f375-8000  **Task 0.4 is satisfied by this approval**: the operator was told, before
  approving, that editing `mcp_server.py` changes `:8000`'s next run, committed or not.
- Noted, not waived by name: the standing Opus review before approval was offered (R3's fixes are
  unreviewed) and the operator approved without it. The build's own tests (tasks 1.x, 2.3) are the
  check on R3's text.

### 2026-09-21 evening — the week's scorecard asks for decisions, and four are made

**DECIDED 2026-09-21 ~17:30, by the operator, in an interactive session** reviewing the week
scorecard (O4: severity A 8 → 2; O5: ≤ 2 open changes / ≤ 40 tasks). The day window had finished
its whole queue by 10:08 because every open change was gated on spec work or on the operator, and
the drain rule stopped it doing the spec work.

- DECIDED   f299-f301  **Triage: won't build now.** F299 + F301, with F339 and F340 grouped in
  (the 2026-09-13 afternoon shapes (i)/(ii)/(iii) stay parked). Both creatable runners take MCP
  (`RUNNER_CLIS = ("claude", "codex")`, both in `MCP_INJECTABLE_RUNNERS`), `hub_client` has no UI
  control, and shape (ii) buys editing only. **Reopen when a runner that cannot take MCP — GHCP —
  is implemented.** Each finding's Status line now carries this; they stay counted as open.
- DECIDED   f325  **Keep open.** The operator declined to retire it, although Codex is cancelled as
  undrivable (2026-08-29). It remains an open severity A nobody can currently drive.
- DECIDED   loop-staffs-s5  **Move §5 out of `a-loop-staffs-the-agent-it-names` as a finding (F400),
  drive §7 and archive the rest.** §5 was never approved (its `:1471` requirement was rewritten in R4
  and never re-rounded). The change's delta is trimmed to what the built groups do before archive,
  so archiving syncs nothing the code does not meet.
- DECIDED   unstaffed-review  **One verification round now, then build if it comes back clean.**
  First put to the operator on a false premise — a stale "STOPPED 2026-09-14" banner in `tasks.md`
  was read as the change's state — and corrected before acting: `proposal.md` records R5/R6
  re-derived it against (f) on 2026-09-19, group 1 is built (`f663898`), and groups 2/5/6 are
  F352's visibility half, the only proposal for that severity A. The operator's first answer
  ("reject") was given on the false premise and is **void**.
- DECIDED   tonight-order  **Tonight's `ORDER:`** — archive `a-first-turn-is-not-told-it-has-nothing`;
  F380 as a no-spec repair; F292 fix-or-quarantine; `a-loop-staffs-the-agent-it-names` §7 then
  archive. Written into `APPROVALS.md`'s `## 2026-09-21`.

### 2026-09-20 evening — F302 reaches R2, and its one dissent is answered with a measurement

**DECIDED 2026-09-20 evening, by the operator, in the same interactive session.** F302's 2026-09-09
verdict was found decided-but-unbuilt; the operator directed it into openspec under the **full**
R1/R2/R3 discipline rather than a single verification round. R1 and R2 have run, R2 as a fresh
process with no access to R1's reasoning. R3 is still owed.

- DECIDED   f302-d2-dissent  **Ship the decided shape, then measure — the conditional text is
  neither adopted nor closed.** R2 dissented from design D2: it argued the declined one-text
  alternative (*"the `agentweave` tools are available if they appear in your tool list; otherwise
  the same operations are HTTP requests"*) is the better change, because the Architect kept to
  `curl` for **ten runs after the notice healed**, so what persisted was the positive HTTP steer
  this change keeps rather than the falsehood it removes. **What decided it: that evidence is
  confounded and the confound cannot be resolved from the observation it rests on.** By the time
  the notice healed the Architect had already learned a working method — payload shapes derived
  from two 422s, a file-plus-`curl` routine that worked. "The steer keeps pointing it at `curl`"
  and "it kept a method it had already paid for" both fit that record, and one agent that had
  already invested cannot separate them. **Only a fresh agent's first turn can**, and that turn
  cannot be observed until the falsehood — a competing cause — is gone. So: land the change, then
  measure, then decide. Recorded as **tasks group 7**, with the change barred from archive until
  7.4 carries counts, because a "decide after measuring" that never measures is **F392** in a new
  coat. *Rejected:* **keeping the decided shape and closing the question**, which would bank an
  unproven claim that the behaviour is fixed; **switching to the conditional text now**, which
  would overturn the 2026-09-09 verdict on confounded evidence and rework a delta that has passed
  two rounds.
- DECIDED   f302-home  **openspec, not the trial Hub, and the full three rounds.** The change edits
  a shipped requirement in `agent-capability-plane`, and the corpus is openspec's. *Rejected:*
  authoring it in the trial Hub, which would have needed hand reconciliation back into
  `openspec/specs/`; and the single verification round CLAUDE.md allows an already-proposed change,
  because the verdict predated both the approver fix and F393's correction of the runner registries.

**What R2 found, recorded here because it is the argument for not collapsing the rounds.** R1's
premise, its independent `_decide` measurement and its spec fidelity all survived. But
`_tool_surface_lines` (`hub/hub/api/v1/agents.py`) renders the *same* false denial from the *same*
`described_path`, reaching the model as `--append-system-prompt-file`, and R1's Impact had
explicitly excluded that file — so the change would have shipped **violating its own new scenario**.
`hub/tests/test_launchability.py::test_a_run_without_mcp_is_not_told_it_cannot_act` exists to stop
exactly this class of sentence and checks only three *older* wordings, which the live clause walks
past. R1 had also silently narrowed a MODIFIED SHALL, dropping the HTTP-form obligation in the one
world where HTTP is the run's only path, and had described the 2026-09-09 verdict as conditional
when it is flat.

### 2026-09-21 — F302 group 7 measured: 3 of 3 fresh first turns reached for MCP

**MEASURED 2026-09-21**, tasks 7.1-7.5c of `a-first-turn-is-not-told-it-has-nothing`. Throwaway Hub
(`:8091`, scratch profile `testbed/scratch/f302_measure/`), three brand-new agents, Haiku
(`claude-haiku-4-5-20251001`), one capability-plane instruction each ("create a task..."), one turn,
no charter, peers present in the roster. Preconditions confirmed against the scratch db before
triggering: no session-wide or per-agent `hub_client` override, runner `cli=claude` (MCP-injectable),
zero prior runs with `mcp_adapter_online_at` set for all three agents.

- DECIDED   f302-d2-measurement  **All three sampled first turns called `mcp__agentweave__create_task`
  directly, with no HTTP shellout anywhere in any transcript** (run-3e7497554e98, run-63c923499c5d,
  run-9ddb13b6dfeb; full transcripts quoted in `scripts/drive/FINDINGS.md` F302). Per tasks.md 7.5c's
  first branch: **the positive HTTP steer does not dominate a fresh turn**, which weakens R2's
  f302-d2-dissent substantially. **This does not close D2** — n=3, one model (Haiku only), one
  instruction shape, one throwaway project, and the confounds in 7.5b (model, task shape, surrounding
  text) are unaddressed by this sample. F302 is marked **fixed, measured** in `scripts/drive/FINDINGS.md`
  — not fixed without qualification. *Not decided here:* whether the conditional text R2 preferred is
  still worth building; this measurement answers only whether the shipped shape's own first turn
  reaches for MCP, and on this sample it does.

### 2026-09-20 — archival's blast radius, and an approval taken without the adversarial pass

**DECIDED 2026-09-20 afternoon, by the operator, in the interactive session that resumed handoff
0132.** The day window had already hit the weekly usage limit, so this did not come from a window.

- DECIDED   archived-agent-blast-radius  **API plus a persisted, broadcast archival event — the
  middle of the three shapes offered.** The change `an-archived-agent-holds-nothing-and-is-offered-nowhere`
  carried exactly one question through three rounds: how far past the API does it go. Chosen because
  `persist_event` and `sse_manager.broadcast` are both server-side, so the rider's *recording* half
  is discharged with nothing under `hub/ui/src` and nothing reaching the live `:8000` app on reload —
  the cost that made the third option expensive. *Rejected:* **API only as R3 left it**, which leaves
  the released charter's identity existing solely in a response body that `useArchiveAgent`'s
  argument-less `onSuccess` discards, so the fact dies with the request. *Rejected:* **accepting the
  bundle refresh**, which would close the display gap properly but commits `hub/ui/src` and
  `hub/hub/static/ui` together and reaches the operator's live app. Carried as **group 2b**;
  `design.md` D10 holds the full reasoning. **Not decided, and still open: the display half.**
  `useSSE.ts:31`/`:460` do not know the new kinds, so an operator still sees nothing.
- DECIDED   archived-agent-group-5  **Build it.** The trim to `DIRECTION.md`'s three files was
  offered — R1 had marked group 5 (`runners.py`, F390) as the one part safe to cut — and declined.
- DECIDED   archived-agent-opus-pass  **Skip the standing adversarial Opus review for this one
  change.** The operator's own standing rule (`feedback_opus_review_before_approval`) asks for an
  adversarial pass before any `- APPROVED` row; they instructed otherwise here, on the grounds that
  R1, R2 and R3 ran as three independent processes and each corrected the last — unlike
  `a-loop-staffs-the-agent-it-names`, where two of three rounds shared a session and a later
  adversarial pass returned eight blocking findings. **Recorded because its absence is otherwise
  indistinguishable from an oversight**, and because the consequence is specific: D10 and group 2b
  are R3-and-later work that nothing has re-derived. *This decision is about one change, not about
  the rule.*

### 2026-09-19, second sitting — two severities rated, and tomorrow's second spec loop named

**DECIDED 2026-09-19 afternoon, by the operator, in the interactive session that resumed handoff
0131.** Two of these close a question carried in the handoff chain eight times.

**The question itself was wrong as carried.** It read *"five open findings with no severity (F77,
F130, F132, F165, F167) can never be reached by the night window's A-before-B-before-C queue"*.
Three of the five do declare a severity — F77 is C, F165 and F167 are both B — and
`backlog_page.py` simply could not read the spelling they used. Fixing the parser (`3918fa9`) also
found **F166 (C) and F168 (B), which had never appeared on the backlog page at all.** So the real
decision was over two findings, not five.

- DECIDED   F130-severity  **B.** Not A: it needs an operator action to trigger — pressing
  Checkpoint twice with no turn between — and nothing is lost or blocked when it fires. Not C: once
  tripped it is permanent and unbounded, because nothing ever re-establishes a non-NULL
  `covers_through`, and the observed damage was a checkpoint whose prose said the work was not done
  while its own file list named the file it had created. *Rejected:* **A**, argued on the grounds
  that it hands a worker a false record rather than merely a bill, and that worker tokens are now a
  real constraint under the weekly window — refused because severity measures what the product does,
  and here it keeps working, over-widely. *Rejected:* **C**, which would have left it unreachable in
  practice, since 89 C's are open and the queue has never reached that far.
- DECIDED   F132-severity  **C.** The trap cannot spring: the same missing UI that cannot clear a
  drift candidate cannot raise one, and no MCP tool or agent route reaches `/spec/drift` either, so
  nothing in the product can put a requirement into `DRIFTING`. A half-built feature, not a
  misbehaving one. *Rejected:* **B**, argued on consequence rather than probability — one call to
  `POST /spec/drift/detect` makes a `gate`-rigor requirement permanently un-approvable through the
  app, with no escape. **That argument was accepted as correct and deferred, not dismissed:** the
  finding now records that it becomes B the day any drift caller ships, and that whoever builds one
  owns raising it in the same change. *Rejected:* folding F132 into F129 and retiring it, which
  would have stopped tracking the gate's unactionable remedy anywhere.
- DECIDED   day-2026-09-20-loop-2  **`F388` (A) — a Hub started from source silently opens the
  operator's live database.** Named in `spec-queue/DIRECTION.md` so the window does not choose for
  itself. It is the only open severity-A that is already decided (a+b+d) and has no change
  directory, and it is a hazard on this machine specifically. Its blast radius shares no file with
  loop 1 (`charters.py`, `agent_lifecycle.py`, `agents.py`) or with either approved-and-unbuilt
  change. *Rejected:* **F299+F301** as one change, whose runner/transport blast radius would have
  cost R1 a round just to establish the boundary between them; **F347**, a first-run barrier but a B
  while eight A's are open; **F168**, which is a missing feature rather than a defect, so a round on
  it would be product design rather than repair.

### 2026-09-19 — six decisions in one sitting: the gate, the day's shape, and four findings

**DECIDED 2026-09-19 afternoon, by the operator, in an interactive DECIDE session**, after being
driven through each one with its consequences. Several had been carried unanswered for four to five
days. The operator's framing that governs two of them:

> *"The daily windows is for driving the app on a e2e process finding problems and doing spec round
> for me to just read and approve for the night run."*

- DECIDED   merge-gate-cadence  **The gate runs at window close, not iteration 1.** Move it to the
  window's final firing, after the last commit, and let it wait for CI to conclude at `HEAD`.
  Nothing commits behind it, so the ~13-minute clock finishes instead of being restarted by the
  next iteration's own commit. Costs the tail of the window; keeps the CI condition intact; needs
  no extra firing. *Rejected:* waiting at iteration 1 up to a budget (the next firing commits
  anyway, so it only works if the budget exceeds a full CI run); a firing whose only job is the
  gate (it still arrives after a committing firing); dropping condition 3 (`master` stops being
  CI-verified at merge time, and `master` is what `:8000` eventually runs). Closes a question
  carried on the 09-16, 09-17, 09-18 and 09-19 review pages.
- DECIDED   day-window-spec-gate  **Gate on undecided, not unbuilt.** The drain count that decides
  whether a spec loop runs counts only changes waiting on the **operator** — an `APPROVED` change
  waiting on a night no longer suppresses tomorrow's proposal. This is the real defect: all four
  starved days were gated by proposals awaiting an operator token, not by night capacity, so the
  window stopped producing the one thing the operator opens it for. *Rejected:* dropping the gate
  entirely (restores the 2026-09-08 pile-up it was added to stop: 129 tasks, 2 ticked); raising the
  threshold to 3 (arbitrary, and still counts the wrong thing); leaving it (the starvation was not
  self-releasing — it ran four days).
- DECIDED   F388-fix  **Refuse the implicit default, log the resolved path, fix the docstring**
  (options a + b + d). Direct `uvicorn hub.main:app` with no `DATABASE_URL` fails to boot with a
  message naming the two ways to set it; every startup logs the resolved absolute database path and
  whether the file pre-existed, at INFO, as its first line; `config.py:12-15`'s docstring stops
  claiming the default "never fires" for the exact invocation `CLAUDE.md` prescribes. (a) alone
  would have prevented the 2026-09-19 incident. *Rejected:* logging only (prevents nothing); the
  primary-profile sentinel (c) (strongest, but needs a migration installed **against the operator's
  live database**, which is the thing being protected).
- DECIDED   F387-fix  **The sort goes in `list_questions`' `order_by`**
  (`hub/hub/api/v1/questions.py:318`), not in the card. Blocking first, then newest, so every reader
  gets a correct floor at once — the Overview card, the conversation tray (`F381`), and any surface
  added later. *Rejected:* the card alone (narrower blast radius, but leaves every other reader on
  oldest-first); both (duplication without a named failure it prevents).
- DECIDED   F374-fix  **A gate-refused approval is not "no verdict", and no operator-only refusal
  re-staffs.** Any 409 naming a remedy only the operator can apply ends the review and surfaces the
  gate's own sentence to the operator, rather than re-staffing to a second reviewer who meets the
  identical refusal. Deliberately broader than F374 measured, so it covers `F352`'s and `F316`'s
  seams in the same repair. *Rejected:* keeping the re-staff and only correcting the false staffing
  message (still pays a second review turn on a refusal no reviewer can clear, in the week the
  rate-limit window counts); scoping it to the evidence gate alone.
- DECIDED   F128-fix  **The free list becomes loop-scoped.** A loop staffs only the agents it names;
  a flow staffs its roster, so design D12's width survives where D12 meant it. This restores the
  invariant `_agents_that_are_free`'s own docstring already claims. **F127's 500 must be fixed in
  the same change** — the busy-guard becomes reachable again, and that is exactly the corner where
  it answers 500. Accepted cost: a loop pinned to a busy agent now waits, including on `:8000`,
  where loops that currently keep moving by substituting will start idling. What decided it: an
  agent is not only a name — `charter_id` (`models.py:219`), `runner_id` (`:216`) and the three
  authority flags `can_read_checkpoints`/`can_recall`/`can_accept_evidence` (`:254-268`) all live on
  the `Agent` row, so a substitution silently swaps the behaviour text, the runner **and the
  permissions the operator selected that agent for**. *Rejected:* UI/API honesty alone (leaves the
  authority hole — a UI that correctly reports you have no control); a per-job opt-in width flag
  (a **flow** already is the width case, so the flag re-implements an existing concept at the cost
  of a migration and a control — struck under the standing "cleanest solution wins" preference).

**Correction, 2026-09-20 (night window, `alsn-closeout`).** The row above's sentence *"F127's 500
must be fixed in the same change"* was stale when written on 2026-09-19 afternoon: F127 was already
fixed five days earlier, by `c8e3bbd` on 2026-09-14 (`a-spent-allowance-holds-the-queue` design D11,
archived), not by this change. `a-loop-staffs-the-agent-it-names` made that existing fix's busy-guard
reachable again in the multi-agent shape F128 used to hide it in — driven live and confirmed in
`scripts/drive/FINDINGS.md`'s `D-4, 2026-09-20` — but it did not fix F127 itself. Appended per this
change's own task 8.4 instruction not to edit the row.

**Also settled, as queueing rather than deciding:** `F185` + `F181` share one root cause
(`agent_lifecycle.archive` leaves `charter_id` bound) and their remedy was already decided at
`DECISIONS.md:536` and `:586`. They become **one change, taken by the next day-window spec loop** —
which the `day-window-spec-gate` decision above now permits to run.

**Three carried questions closed as stale in the same sitting**, verified before closing: `F356` is
**fixed** (`d16a76a`, `a-late-answer-is-delivered`, 2026-09-15, driven live 22/22); `F188` was
**retired** 2026-09-04, so the night playbook's "last severity-A finding with no change" line points
at nothing; `F185`/`F181` needed a change directory, not a decision.


### 2026-09-15 — the windows are routed, metered, and trimmed rather than capped

**DECIDED 2026-09-15 ~09:20, by the operator, in an interactive session** (the day window was
disabled for the day at their request). The operator's words:

> *"With the promo I wans using everything right on the weekly window so it fit me perfectly but now
> it's not going to be enought at all. So we need to be more deliberate and find a better way to
> execute our autonomous windows. The windows are working perfectly so I want to keep using them."*

Measured first (09-14 transcripts, list-price weights): every window call ran on `claude-opus-5` at
effort `high` — day $222 incl. $32 of Opus subagents, night $92; LoopEngine's agents $153 that day;
~60% of cost is cache reads, so context size is the budget. The weekly bar read 49% on the Tuesday
morning of a week resetting Sunday. Three decisions, chosen from options put to the operator:

- DECIDED   window-model-routing  **Spec rounds on Opus, build on Sonnet.** R1–R3 and REV stay on
  Opus/high (the round discipline is untouched); `-impl` runs on Sonnet/high; drives, gates,
  archives, ledger, compose and read-and-sort items on Sonnet/medium; unrecognised ids default to
  Opus/high. Encoded in `.claude/loops/usage-policy.json`, read by `run-iteration.ps1` per firing
  from STATE's `current`; an item's own `model`/`effort` overrides. *Rejected:* only mechanical items
  on Sonnet (~15–20% saving); Sonnet everywhere but REV (weakens R2/R3).
- DECIDED   meter-before-cap  **Meter for a week, then set caps.** Every iteration writes one row
  to `.claude/autonomous/usage-ledger.jsonl` from its own `--output-format json` result; the
  statusline persists the plan's real 5-hour/weekly percentages to `~/.claude/usage-snapshot.json`
  and `usage-history.jsonl`; `.claude/loops/usage_report.py` joins them into $ per 1% of weekly.
  No window cap until then — only a per-iteration runaway guard (`--max-budget-usd 40`) and a
  60-minute pause after a usage-limit refusal. **Revisit ~2026-09-22** with a week of calibration.
  *Rejected:* a 50% or 70% share now, set blind.
- DECIDED   claude-md-slim  **Slim CLAUDE.md for every session.** 33 KB → 11 KB; runbooks moved to
  `.claude/reference/`, recipes to path-scoped `.claude/rules/` (verified to load only when a
  matching file is read). An independent review found three dropped constraints; all restored.

This closes `weekly-window-care` below: the throttle is routing + trimming now, and a cap after
calibration.

### 2026-09-15, later — the build queue: F332-rule and the review-staffing split

**DECIDED 2026-09-15, by the operator, in an interactive session**, with no daily window running
that day.

- DECIDED   F332-rule  See the row under `## Open` above, now flipped: revise, one more
  verification round, then build.
- DECIDED   split-unstaffed-review  **Approved REV's split of
  `an-unstaffed-review-names-its-holders`, and executed** (`cba4ae2`). The F353 half (task groups
  3 and 4, 2.5, 2.5b, 2.12 and 2.13 — the refusals' remedies, F334's wording, F365's once-per-task
  record, the `error_summary` fit F367 needs) now lives at
  `openspec/changes/a-refusal-names-a-remedy-that-works/`, renumbered, ready for its one
  verification round, and does not wait on `F352-free`. The rung-3 naming half (D1, D2, D3, D6,
  task 2.14) stays in `an-unstaffed-review-names-its-holders`, annotated stale against `F352-free`
  (below), and needs its own re-derivation round against (f) before it can build.

`F352-free` itself was decided the same day: see its own row below, **REJECT (d), go with (f)**.

### 2026-09-14 afternoon — LoopEngine stays parked, and the weekly rate-limit window needs care

**DECIDED 2026-09-14 ~14:50, by the operator, in an interactive session** (not the day window),
after the session reported LoopEngine stalled since 07:02 on the `review_unstaffed` staffing gate
(F352), with 498 consecutive no-staff ticks and nothing moved since 06:41. The operator's words:

> *"Let's leave it parked while we fix the issues and since anthropic ended the 50% promotion we
> have to be more carefully about our weekly window"*

- DECIDED   LoopEngine-parked  **LoopEngine is left exactly as found.** No manual intervention to
  restaff its stuck reviews, unstick its queue, or otherwise touch `:8000` outside today's existing
  `mode=ro` read. It stays parked until the fixes already in flight (f355, then the F352 operator
  question, then f356–f364) ship through the normal spec loop and, separately, the operator
  restarts it. This extends the day's existing "`:8000` is read, never touched" rule to cover
  LoopEngine's *product* state, not only its database.
- DECIDED   weekly-window-care  **The 50%-off promotion on the Anthropic account this repo's
  autonomous loops and LoopEngine's agents both run under has ended**, so the shared weekly
  rate-limit window is now a real cost/availability constraint rather than a cushioned one. The
  concrete throttling (which sessions moderate usage, and how) is **not yet decided** — asked back
  to the operator in the same session. **Answered 2026-09-15** (section above): routing, metering
  and trimming now; a cap after a week's calibration.

### 2026-09-14 — a day that reads LoopEngine and builds what it finds

**DECIDED 2026-09-13 ~23:05, by the operator, in session**, for the 2026-09-14 day window only. The
operator's words:

> *"I want to change the daily run for tomorrow. I have a project running in hub 8000. I want to
> push the window to 11:00 and from 9 to 11 we're doing a different run. We're going to read every
> conversation, interaction and log running on the project loopengine in the port 8000 in agentweave
> and pick up everything that happened. All the issues and improvements that we can find. The
> development life cicle, the interaction between agents propose the fixes and improvements. For
> each fix then the afternoon window will do a spec loop and implement it. For each imrpovement it
> will just generate a short specification so I can evaluate the improvement. The window will run
> until 19 then."*

- DECIDED   2026-09-14-hours  **09:00–11:00 is a read-only review of LoopEngine on `:8000`, and the
  building half runs 11:00–19:00.** It is delivered as **one** armed day window, 09:00–19:00, whose
  first phase is the review (`day-window.md`, `## O`) and which moves to the building half at 11:00.
  It is not delivered as two windows, because both would own the same tree and cycle branch, and
  the windows must never overlap (`.claude/loops/README.md`, State). Two windows would also need a
  second arming task, which someone has to remember to remove. The hours come from a `DAY WINDOW:`
  line in `DIRECTION.md`'s dated section, which `arm-cycle.ps1` reads and which expires with the
  day.
- DECIDED   2026-09-14-build  **A build day.** This is the first use of `day-window.md`'s
  `## A day that builds`.
  - **Each fix** the review finds is taken through R1, R2 and R3, an adversarial review (`REV`),
    implementation and a drive, then archived by the day window. That covers new findings and
    existing ones the review re-observes on LoopEngine. Higher severity goes first.
  - **Each improvement** gets a short brief the operator evaluates. It is not specced into
    `openspec/changes/`, and it is not built.
  - **A fix that does not finish** stays specced, with no `APPROVED` row. The night builds it only if
    the operator approves it that evening.
- DECIDED   2026-09-14-privacy  **Cite, don't quote.** This repository is public, and the window pushes
  every iteration. Findings and briefs cite run, entry, task and conversation ids, and paraphrase.
  Only AgentWeave's own output is quoted verbatim. LoopEngine's code, task and conversation text, and
  the operator's messages stay out of the repository. Credentials are always redacted. Rejected:
  **quote freely**, and **raw notes kept outside the repository**.
- DECIDED   2026-09-14-plan  **The LoopEngine work replaces the day's plan.** If its queue empties
  before the review page's slot, the window continues with F327's spec loop (R1–R3 only, with no
  build, since this row does not cover F327). Everything else in the plan it replaced is carried to
  2026-09-15 unchanged: the F332 drive, F215's loop, and the access-path exploration. Rejected:
  **replace with no fallback**, and **keep the F332 drive at 09:00**, which would push the review
  later.
- DECIDED   2026-09-14-ui  **A UI fix's bundle is committed only if it is compatible with what `:8000`
  is running.** The bundle must be driven in a browser, and it must need nothing from Python newer
  than the `:8000` process's start time. Otherwise the fix is specced and left for the night, pending
  approval. Rejected: **no UI fixes by day**, and **allow every UI fix**.
- DECIDED   2026-09-14-read  **`:8000` is read, never touched.** Its database is opened only through a
  `mode=ro` SQLite URI. The project's files and transcripts are read, never written, and the Hub's
  API is never called. `arm-cycle.ps1`'s `:8000` limit is narrowed from *"must never be touched"* to
  exactly this exception, and nothing else about `:8000` changes.

### F347, decided 2026-09-13 evening — and `:8000` running this checkout is intended

**DECIDED 2026-09-13 ~22:45, by the operator, in session**, on a RESUME session's recommendations.
Both questions had been raised that afternoon and left unanswered.

- DECIDED   F347  **Option (a): refuse the turn with a sentence that names the repair.** For
  example: *"<project> is a git repository with no commit yet. Make a first commit, and the turn
  will start."* The Hub creates no commit and provisions no orphan branch, which keeps
  `repo_hygiene.py`'s stance that the Hub does not write commits into the operator's repository.
  The sentence is written in `worktrees.py`, which that module's docstring names as the place
  operator-facing sentences are written, and it replaces git's `fatal: invalid reference: HEAD`.
  Rejected: **(b)**, an orphan worktree. The turn would run, but the Hub would then own a branch
  with no shared history with anything the operator later commits, and nothing says how that work
  lands. **Left to R1:** the finding's last sentence, that the refusing pass should not hold the
  operator's own message silently behind a condition only the operator can clear.
- DECIDED   port-8000  **The operator's `:8000` Hub runs this checkout's editable install on
  purpose.** `CLAUDE.md`'s paragraph is rewritten to say so, with the consequences: a committed UI
  bundle reaches the live app on reload, and a restart runs this checkout's migrations on the
  operator's database. Rejected: repointing the shortcut at `agentweave-live` (PyPI 1.1.0, head
  `0081`), which is far behind the database `:8000` now holds. **This does not widen what a window
  may do.** `:8000`'s process, database and credential stay out of bounds, as the 2026-09-08
  trial-key verdict below already says.
- DECIDED   chain  Two items carried for 3 and 6 handoffs are dropped: whether the ledger's *"shape
  of a fix"* lists are labelled as unverified sketches (new ones already are), and `continuity-kit`.

### 2026-09-13 afternoon — F299's 1b handed back, the roadmap widened, and the gate may re-run a flake

**DECIDED 2026-09-13 ~14:20, by the operator, in session.** Each was put with a recommendation, and
the operator took all four recommendations.

- DECIDED   F299-1b  **Option (b): 1b is handed back, and `an-absent-approver-is-not-named` is
  `REJECTED` and archived unbuilt.** This answers the OPERATOR QUESTION at the top of that change's
  `proposal.md`. On `claude` 2.1.269 the run already ends at its first approval-needing call, and
  what it shows is the harness's own true error naming the blocked server. As written, 1b swaps that
  for a turn that survives the refusal, and whose model asks the operator to approve a prompt no
  surface shows. Option (a) repairs the wording, but still leaves a run that cannot write, and pays a
  migration and 24 tasks for it. **The deciding input is F339.** 1b rejected `acceptEdits` on no
  grounds *"by removing the path check entirely"* (1b above, *"Rejected: also drop to
  `acceptEdits`"*). The 2026-09-13 day window reproduced that claim as false on 2.1.269: `acceptEdits`
  confines writes to the workspace, and the harness refuses the rest. A mechanism built on 1b would
  be built on a reason that no longer holds. Rejected: **(a)**, and **1b as written**. The rounds'
  measurements are kept in the archived change's `design.md` and `evidence/`, and they are inputs to
  the question below.
- DECIDED   roadmap  **The second daily spec loop takes release/usability work, and the first keeps
  draining.** Loop 1 drains decided A and B findings, in `DIRECTION.md`'s order. Loop 2 takes the
  work-lands arc of `openspec/explorations/2026-08-30-release-roadmap.md`: **F215 first** (the
  evidence screen, over an API that already works), **then F124** (a loop's work never reaches
  `main`). Neither has a verdict, so R1 for each writes the options into an OPERATOR QUESTION rather
  than choosing one. The operator also takes the recommendation to use AgentWeave day to day **on
  another project**, as the best source of usability findings. This widens `### The scope of the
  drain` below and does not replace it. The reasoning and the capability assessment are in
  `ROADMAP.md` `## 2026-09-13 — the objective widens`. *(An earlier version of this row said the
  `:8000` instance runs PyPI 1.1.0. That was wrong: it runs this checkout's editable install, per
  DEAD-ENDS 2026-09-13. Whether that is intended is the open question, not an update.)*
- DECIDED   gate-rerun  **The day window's merge gate may re-run a failed CI run once, when every
  failure is F292's or F314's signature and nothing else.** The exact rule is in
  `.claude/loops/day-window.md` step 1, condition 3, with the requirement to write nothing until
  `HEAD`'s run concludes. This answers the night's `decisions_for_user` item 4 and the day window's
  item 1 of 2026-09-13. Rejected: **raising F292/F314 into `DIRECTION.md`'s order now**, which is
  still open as a separate priority call; and **accepting about two mornings in five that do not
  land**.
- DONE   merge  `master` was fast-forwarded to `ab7cf72` by the DECIDE session, with the operator's
  agreement, 2026-09-13 14:25. All four gate conditions were re-measured immediately before the
  push. That landed the 2026-09-12 and 2026-09-13 cycles, 54 commits.

**OPEN, not decided: the access path on a harness that blocks MCP (F299, F301, F339, F340), as one
question.** What should a `claude` run do when its harness refuses the Hub's tool server? The four
findings are one mechanism seen from four sides:
- **F299** is a run killed at its first write.
- **F301** is the `cli` path with nothing to answer an approval (1c).
- **F339** is `acceptEdits` confined after all.
- **F340** is grounds that are positive-only and permanent, while `init` reports the server's state
  on every run.

Shapes already on the table, none chosen:
- **(i)** today's behaviour, plus a Hub-authored sentence in place of the harness's two raw lines
  (F340, research candidate 3);
- **(ii)** on refuted grounds, spawn with no approver under `acceptEdits`, so the run can edit inside
  its workspace, and record the harness's `permission_denials`;
- **(iii)** 1b's shape with option (a)'s flag.

(ii) trades the operator's approval of each command for the harness's own workspace check. That
trade is the operator's, per `agent-capability-plane`, and it is the question. It needs an
exploration that lays the shapes against the archived change's measurements before anyone proposes.
`DIRECTION.md` queues that exploration.

### F319 + F320, decided 2026-09-12 afternoon — a refused review leaves nothing behind

**DECIDED 2026-09-12 ~15:30, by the operator, in session.** The session recommended it and the
operator agreed. F319 became severity A that morning (day window D-1, driven live), and F320 was
filed beside it in the same drive. Neither had a verdict.

- DECIDED   F319  **A refused review dispatch leaves the task exactly as it was before the dispatch,
  and the operator is told.** No assignee, status change or transition row survives a refusal,
  whichever refusal it is and whichever path (the route, or the scheduler) reached it.
- DECIDED   F320  **A scheduling pass that abandons a refused queue head moves on to the next
  entry.** Abandonment exists *"so a permanently wrong entry stops wedging the whole queue"*, and
  the pass that abandons it is today the last pass anything makes (`agent_trigger.py:2433`,
  *"There is no tick"*).
- DECIDED   F319+F320  **One change, not two.** Both live in `turn_scheduler.py`'s refusal branch.
  The commit that persists the staging is at `:349`, and the `return` after abandonment is at
  `~:512`. Two proposals would edit the same lines.

**Left to R1, deliberately.** R1 chooses the mechanism: undo the staging on refusal, or ask the
repository-reading refusals (`review_turn.py` commit-present, git-repo, checkout-path) before
`enter_selected_task` stages anything. Neither is decided here. R1 also answers whether the
waiting-reason write at `:349` can keep recording the refusal's words without committing the
staged assignee.

**Why it goes first, ahead of F299.** It breaks the review path the loop and flows use every day,
while F299 needs a harness that blocks MCP servers, which this machine's is not. It is silent: the
board shows an ordinary `Under Review · Idle` card, and the next reviewer is refused by D9. And
the 2026-09-11 night's F306 fix widened it. As the session reads the code and the D-1 log, leg A's
refusal comes from the §3.4 entry-guard fallback added at `4929ea0`, and before that commit the
same sequence ended in a self-review. The fix is right, and it left a stall where the self-review
was.

- DECIDED   F327-scope  **[Superseded 2026-09-24 by `F327-scope-b`.] Option (a): `a-refused-review-leaves-nothing-behind` ships as scoped, and
  F327 stays open.** The operator decided it in session, 2026-09-12 ~19:20, answering R2's OPERATOR
  QUESTION. The change fixes the dispatch's own staging, on the route and the scheduler, and F320.
  A review a flow (or a divergence restaff) staffed *before* its dispatch, and which the dispatch
  then refuses, is **F327 (B)** and waits for its own spec loop. R3 measured that every row of
  F327's table is unchanged on the fixed tree, so the change makes no flow worse. R3 also scoped the
  delta's scenarios so they no longer reach flows. Rejected: **(b)**, moving the flow's staging
  into the dispatch, which is unexamined by any round and, per R3, larger than R2 estimated,
  because the divergence restaff collides with D9. **(c)**, a compensating `under_review ->
  completed` edge, because it leaves transition rows the verdict forbids. **(d)**, exempting flows
  in the main requirement, because it would define the verdict's intent away.

### F306 and F312, decided 2026-09-10 evening — and the scope verdict's mechanism, amended

**DECIDED 2026-09-10 ~18:50, by the operator, in session**, after a code exploration of both
findings. These were the last two open severity-A findings with no verdict.

#### F306 — an agent may not review work it recorded evidence for

**DECIDED: repair BOTH defences, and count EVERY evidence row regardless of `review_state`.**

`agents_that_may_have_authored` (`hub/hub/task_transition_service.py:253-283`) unions exactly three
records — transitions, `assignee`, runs bound to the task. A fourth exists and is not a source:
`requirement_evidence.actor`. In the measured run all three legitimate sources were empty, the
ladder got `exclude=set()`, and the agent approved its own work — `under_review → approved`,
`actor_kind='run'`, nothing refused it.

**The function's own docstring decides this**, which is why the verdict is not a close call: *"a
record associating an agent with a task is sufficient to exclude it, and a source's silence is not
evidence that the agent did not work it."* That principle was applied to three of four sources, and
by its own standard the missing one is the **strongest** — the other three are circumstantial
(moved it / holds it / ran about it), while an `implementation` evidence row is the agent asserting
*"this is my implementation of this task"*, carrying the commit the reviewer is handed.

**Both defences, not just the ladder.** `_guard_author_is_not_reviewer` (`:286-311`) compares
`agent_that_completed`, which is `NULL` on an operator completion, so it has nothing to compare and
permits. Repairing only the ladder leaves the **silent** failure standing: a ladder that cannot
staff reports *"no reviewer available"* and the operator sees it; a guard that permits a
self-approval is seen by nobody. The guard falls back to the evidence actors when there is no
completer.

**Every evidence row, not only `ACCEPTED`.** Rejected: filtering on `review_state == ACCEPTED`.
An agent whose evidence was rejected, or whose evidence is still awaiting review, still **authored
the work** — that is what the row records. Filtering by decision would reintroduce the gap one
status value further along, and it would make the exclusion depend on a review outcome that the
review being staffed is supposed to produce.

**The cost, accepted knowingly and already priced by the code:** *"the cost of excluding an agent
that did nothing is a review the flow reports it could not staff, which the operator sees and
resolves; the cost of including an agent that wrote the work is a self-approval nobody sees."* This
verdict buys more of the first to eliminate the second.

**Blast radius, measured before deciding:** two call sites (`scheduler.py:625`, `:1574`) and one
test file (`hub/tests/test_a_flow_names_what_it_cannot_staff.py`). `RequirementEvidence` already
carries `task_id`, `actor` and `actor_kind`, so the fourth source mirrors
`agents_of_runs_bound_to` exactly and needs no migration.

**Open and NOT decided here** — flagged so a round picks it up rather than assuming: **whether the
reviewer ladder picks deterministically** when several agents are eligible. In the measured run the
pool was two and it chose the author. That is unverified either way and is a question for R1.

#### F312 — the workspace posture and URLs

**DECIDED: allow the run's own Hub URL, and deny every other URL with a reason that names network
access rather than the filesystem.** This is option C of three, and it composes with — rather than
replaces — the F300 verdict above.

**What settled it is a measurement, not a preference.** `python -c` reading `os.environ` makes the
**identical** request to the **identical** address and is **allowed** today, because it puts no
absolute path in the command text for `_ABSOLUTE_PATH_RE` to find. So the current behaviour is **not
containment — it is a syntax filter.** It stops the agent that writes a URL plainly and no other,
and it reports that as `'p://127.0.0.1:9/…' is outside your workspace`, sending the model and the
operator to debug a filesystem.

Rejected: **allow all URLs** — honest about what is enforceable at this layer, but it grants shell
egress under the *default* posture, and a porous boundary is not a reason to open it deliberately;
that is a capability decision, and it is not forced by this defect. Rejected: **deny every URL with
a true reason** — zero widening and it does fix the message, but it leaves F300's mandatory-path
failure standing and keeps a filter any `python -c` walks past.

**Not claimed by this verdict:** that egress is now contained. `_decide`'s own docstring says it is
*"a boundary, not a sandbox"*. Actually containing network access needs a different layer entirely
and **is not authorised here**. If the operator later wants real egress control, that is a new
decision and a much larger one.

**F300 and F312 are one change.** Both are edits to the same regex-and-`_decide` path, they must
agree on what a URL is, and shipping either alone leaves the other's message or capability wrong.
Whoever writes R1 writes one proposal covering both.

#### The scope verdict's mechanism — amended

**The 2026-09-10 morning verdict *"drain A and B, ratchet C and D"* cites R-1's model, and R-1's
model cannot express what it was asked to.** A ratchet freezes *a count of one homogeneous,
countable population* — 35 clientless routes, 52 MISREPORT surfaces, 100 unhandled query sites, the
dependency ceilings. The 88 open C, D and unlabelled findings are heterogeneous: there is no single
number, and no check can assert them.

**DECIDED: the citation is dropped and the verdict says what it does — those findings are NOT
PROPOSED AGAINST.** They stay in `scripts/drive/FINDINGS.md` as recorded history. There is no check,
no ceiling, and nothing stopping the population growing, and **that is now stated rather than
implied by a citation that promised otherwise.**

Rejected: **freeze the open C/D count as a ceiling.** It is buildable, but it would go red whenever
a drive files a new low-severity finding — and filing them is behaviour worth keeping, not
suppressing. A gate that punishes honest reporting gets worked around. Rejected: **two named
mechanisms** (ratchet the countable classes, leave the rest unscheduled) — accurate, and rejected as
more structure than the distinction earns now that it is written down plainly.

**The cost is unchanged and stands:** **35 of the 75** low-severity findings read on 2026-09-09 are
named nowhere outside `FINDINGS.md`. Under this verdict *unscheduled* is very close to *forgotten*,
and that was accepted with the wording in front of the operator.

### The access path, re-decided 2026-09-10 — one verdict reached one of its three findings

**DECIDED 2026-09-10, by the operator, in session**, after the three findings were read together
against the spawn path and after a four-shape measurement run for this decision. It **narrows** the
2026-09-09 verdict rather than replacing it, and adds two verdicts that verdict could not reach.

**Why this was re-put.** The 2026-09-09 verdict is titled *"F299 / F300 / F301"* and its mechanism —
teach `_decide` about the run's own Hub address — **can only fire in F300's configuration.** `_decide`
lives behind `approve_tool_call` in `mcp_server.py`, a process spawned only when the Hub emits
`--mcp-config` *and* the harness honours it. F299 is a harness that ignores it; F301 sets
`hub_client: "cli"` so it is never emitted. This is the same class as entry 19 and as `F305`: a
verdict that reads as settled and cannot do what it says.

#### 1a. F300 — the verdict stands, narrowed to this finding

Unchanged and now better evidenced. On `workspace` there **is** an answerer, so `_decide` is the only
thing between the instructed command and the network — measured below, the harness does not refuse
that command shape statically. Teaching `_decide` the run's own Hub base URL makes the instructed
request execute. The 2026-09-09 constraint still binds: **not permissive about URLs in general**, the
run's *own* Hub base URL only.

#### 1b. F299 — no grounds, no approver flag

> **HANDED BACK 2026-09-13 by the operator.** See `### 2026-09-13 afternoon` under `## Decided`. The
> spec loop that took this verdict found that the installed harness no longer behaves as this
> section's drive recorded. Its *"Rejected: also drop to `acceptEdits`"* rests on a claim F339
> reproduced false. This section is kept as history, and is no longer an instruction.

**DECIDED: when there are no grounds that the harness honours MCP, do not emit
`--permission-prompt-tool`.**

The Hub already measures this and already trusts the measurement for a different purpose.
`harness_has_honoured_mcp` (`hub/hub/launchability.py:232`) is a per-agent, positive-only read of
`Run.mcp_adapter_online_at`, and `described_access_path` uses it to choose what a run is **told**. It
does not reach `_build_claude_command`, which decides what a run is **given**. This verdict connects
the two: same signal, same grain, same conservative direction.

**What it changes, exactly.** From the second run of an agent whose adapter has never come online,
the run is spawned without an approver flag naming a tool nothing serves. That is F299's own
**condition C**, which it drove: the model then says *"I need permission to write the file"* instead
of *"contact your system administrator to resolve this."* **The denials are identical.** Nothing is
widened — a flag is removed, not a permission granted.

**What it does not do, stated so nobody expects it.** It does **not** restore the run's ability to
work. On a harness that blocks MCP there may be no posture that gives both containment and
capability, and this verdict does not pretend otherwise; it stops the run lying about whose fault it
is. The remaining trade is `hub_client: "cli"`, and **nothing in the UI says what that costs.**

**Corrects the 2026-09-09 verdict's closing note**, which told whoever specs it that *"the Hub cannot
today detect that a harness blocks MCP."* It cannot detect it **before the first spawn**. From the
second run it demonstrably can, by the mechanism above — which shipped in the same change that filed
these three findings.

**Rejected: also drop to `acceptEdits` on no grounds.** That restores capability by removing the path
check entirely, reversing the 2026-09-09 rejection of the same option. Rejected again for the same
reason: `agent-capability-plane` reserves containment to the operator.

#### 1c. F301 — the `cli` path has no answerer, and that is the whole finding

**DECIDED after measurement, 2026-09-10.** F301 records fifteen attempts and five refusal classes and
attributes four of them to the harness's *static* command analyser, concluding that the notice
instructs a shape the harness refuses outright. **The measurement says otherwise.** Four shapes were
run twice, once under `acceptEdits` headless and once with the approval gate removed
(`testbed/scratch/f301shapes/`, Haiku, every request aimed at `127.0.0.1:9` where nothing listens, so
a connection error proves execution):

| shape | `acceptEdits` headless | approval gate removed | `_decide` |
|---|---|---|---|
| `python -c` reading `os.environ` | denied | **executed** | **allow** |
| PowerShell `curl.exe "$env:HUB_URL/…"` | denied ×4 | **executed** | deny |
| Bash `curl "$HUB_URL/…"` | denied | **executed** | deny |
| **control** — literal URL, no variable | **denied** | **executed** | deny |

**Remove the approval gate and every refusal class disappears.** They are the harness's reasons a
command **needs approval**, not reasons it is forbidden — and on the `cli` path nothing answers, so
needing approval *is* denial. **The control proves it:** a bare literal `curl` with no variable
anywhere is denied identically. F301 is one sentence, not five rows, and
`runner_commands.py:58-60` predicted it on 2026-08-13: *"it still prompts for `Bash`, and headless
there is nothing to answer that prompt either."*

**So F301 needs no containment decision.** It is F299's problem seen on the other path, and it is
closed by telling the truth rather than by widening anything. What it does establish is that the
notice's HTTP branch is **unusable on the `cli` path by construction**, and the notice should stop
implying otherwise.

#### 1d. The remedy for F300 — both, notice first

**DECIDED: change the notice to instruct the `python -c` shape now, and keep 1a's `_decide` fix as
the durable half.**

The measurement found a remedy nobody had considered: **`python -c` reading `os.environ` is the one
shape of the four that `_decide` already allows**, because it puts no absolute path in the command
text for `_ABSOLUTE_PATH_RE` to find. That is a **prose-only** fix — no code, no containment change,
works today on `workspace`.

**Why both and not one.** The notice change is shippable immediately and costs nothing; the `_decide`
change is what makes the plane reachable when an agent improvises a shape rather than following the
notice literally, which is the ordinary case. Rejected: **notice only** (leaves the obvious `curl`
form denied, with the false filesystem reason); **`_decide` only** (correct but needs the full round
discipline before anything improves, and the free half is free).

**Ordering is part of this verdict**: the notice first, because it needs no approver change and is
therefore the smaller and safer of the two.

> **CORRECTED within the hour, 2026-09-10, by checking the carve-out I had just invoked.** The line
> above originally read *"and therefore no proposal round"* — **wrong.** `day-window.md`'s D-6
> carve-out requires that the change *"touches no requirement in `openspec/specs/` — grep the
> capability before believing this."* The notice **is** specified, by
> `agent-capability-plane`'s *"A run whose harness cannot use MCP is told how to reach the plane"*,
> whose scenarios pin what the text must identify — including **how the credential is presented on
> a request**, which is exactly what changing the instructed shape changes. **So the notice change
> needs R1/R2/R3 like anything else**; what it does not need is the approver change. Filed against
> myself rather than left: a verdict that waives the round discipline on a specced capability is the
> same defect as a verdict whose mechanism cannot fire, one paragraph later.

**And the requirement itself now carries a false mechanism**, inherited from F301 and shipped into
the corpus on 2026-09-09: *"the `cli` path's `acceptEdits` has no approver to overrule a harness that
**statically refuses** an interpolated credential (F301)."* The measurement in 1c says the harness
does not statically refuse it — with the approval gate removed, that exact command executes. The
requirement's **conclusion** holds (unreachable on `cli`, and for the reason the sentence's first
half gives), so this is a wording repair, not a reopened requirement. It must be corrected in the
same delta that carries the notice change, and **not by the day window on its own** — the corpus is
openspec's and a spec edit is the spec loop's.

#### 1e. The general form is a new finding, not part of any of these

The control row denies a plain `curl http://127.0.0.1:9/...` under the repo's **default** posture,
with the reason `'p://127.0.0.1:9/…' is outside your workspace` — `_ABSOLUTE_PATH_RE` eating the URL
scheme. **No agent on the default posture can make any network request from a shell command, and is
told a filesystem reason for it.** `pip install` from a URL, `gh api`, fetching a schema: all denied
the same way.

**DECIDED: file it as a new severity-A finding.** It is a capability hole in the product's default,
measured, with a one-line reproduction, and it lands inside the A+B scope decided this morning.
Rejected: **folding it into F300** (risks the general claim being closed when F300's narrow fix
ships — and 1a's verdict explicitly forbids general URL permissiveness, so F300's fix *cannot* close
it); **filing it as B**; **not filing** on the grounds that denying egress is intended — the posture
may well be entitled to forbid egress, but it is not entitled to forbid it by accident and report it
as a filesystem escape.

### The scope of the drain — A and B are drained, C and D are ratcheted

**DECIDED 2026-09-10, by the operator, in session**, on the finding-shaped arithmetic in
`ROADMAP.md` `## Honest arithmetic`. This is the first verdict in this file about **how much of the
ledger is in scope at all**, and it governs where every day window points its proposals from now on.

**DECIDED: drain severity A and severity B. Ratchet C, D and the unlabelled under R-1's model.**

> **AMENDED the same evening, 2026-09-10 — the second sentence's mechanism was wrong and is
> withdrawn.** R-1's model freezes *a count of one homogeneous population*; the 88 open C, D and
> unlabelled findings have no such number and no check can assert them. **Read that clause as: those
> findings are not proposed against, and stay in `FINDINGS.md` as recorded history.** There is no
> ceiling and nothing stops the population growing. The first sentence — drain A and B — is
> unaffected and is what this verdict is for. Full reasoning and the two rejected alternatives are
> in `### F306 and F312, decided 2026-09-10 evening`, above.

As measured 2026-09-10 by `py -3.11 scripts/classify_findings.py` — **run it again rather than
quoting these; they move daily** — the ledger holds **308 sections, 147 open**: 4 A, 59 B, 68 C,
14 D, 2 unlabelled, plus 8 in `CONFLICT`.

> **The counts below moved twice the same day; the verdict did not.** By late morning the ledger
> read **313 sections, 157 open** — 6 A, 63 B, 72 C, 14 D, 2 unlabelled — so *in scope* is **69**
> and *ratcheted* is **88**. Three of the seven new ones were filed that morning; the rest moved
> because `dee508c` **repaired the classifier**, which re-bucketed the ledger and returned
> `UNCLASSIFIED` to 5. **This verdict is severity-based, not count-based** — it says *A and B are
> drained, C and D are ratcheted* — so a moving census resizes the work it implies and changes
> nothing about the decision. The figures above are kept as they stood when it was made.

- **In scope: the 63 open A and B findings.** At the measured rate of one proposal per day window,
  ~9 weeks of unbroken daily cycles. Proposals come from this population and from nowhere else.
- **Out of scope: the 84 open C, D and unlabelled findings.** They get **R-1's already-decided
  treatment** (`### R-1 — Enforce, as a ratchet`, 2026-09-08): freeze today's count as a ceiling that
  may shrink and may never grow. **Existing instances are not repaired before the check may pass.**

**Why this option.** It is the only one of the three that reuses a decision already made rather than
inventing a second policy for the same problem. R-1 settled *conventions are enforced, instances are
not repaired* for the ratchet checks; the low-severity tail is the same question at a larger scale,
and answering it differently would leave the repo with two philosophies about the same ledger.

**The cost, taken knowingly and stated so nobody rediscovers it as a surprise:** those 84 findings
stay wrong, with a passing check blessing them, until something touches them on its own merits. **35
of the 75 read on 2026-09-09 are named nowhere outside `FINDINGS.md`** — for those the ledger is the
only copy, so ratcheting them is the point at which they stop being tracked work and become recorded
history. That is the trade; it was not made by accident.

**Rejected: drain everything open.** ~5 months of daily cycles, and dishonest unless the source term
is accepted — Stage 2 closed two severity-A findings and filed three more, a **net drain of minus
one**. A five-month plan whose input grows as it runs is not a plan.

**Rejected: drain A, then re-measure.** Cheapest, and it defers the same question by about a week
while the day windows keep proposing from wherever the ledger happens to be read from.

**What this does not decide.** ~~It does not schedule the ratchet checks — those are still Stage 6
work with no owner~~ — **corrected 2026-09-10: all three were built on the night of 2026-09-09**
(`6484de4`, `hub/tests/test_surface_ceilings.py` and `test_dependency_ceilings.py`). It does not
touch the `CONFLICT` findings, which need a hand read regardless of severity. And it does
not re-open the drain gate's own rule: `.claude/loops/day-window.md` step 6 still governs *whether*
a day proposes, while this verdict governs *what from*.

> **OPEN — raised 2026-09-10, after the verdict, and it is about this verdict's own mechanism.**
> **"Ratchet C and D" cites R-1's model, and R-1's model cannot carry these 88 findings.** A ratchet
> freezes *a count of one homogeneous, countable population* — 35 clientless routes, 52 MISREPORT
> surfaces, 100 unhandled query sites, the dependency ceilings. Each is a single number that may
> shrink and may never grow. **The 88 open C, D and unlabelled findings are heterogeneous**: there is
> no one number to freeze, and no check can assert them.
>
> So as built, this verdict means **"stop scheduling them"**, not **"hold a line under them"**. Those
> are different promises and only the first is currently kept. It may well be the one intended — but
> the verdict cites R-1, and R-1 promises the second. **The operator should say which**, because the
> difference decides whether anything at all stops that population growing. The cost noted above
> lands harder under the first reading: **35 of the 75 read on 2026-09-09 are named nowhere outside
> `FINDINGS.md`**, so "unscheduled" is very close to "forgotten".

> **FOOTNOTE — DECIDED 2026-09-22 by the operator, in session:** *"the draining of the others is
> manual execution guided by me."* The C and D findings are no longer only recorded history: they
> are drained, but **only by interactive sessions the operator directs**, following
> `spec-queue/ROUNDS.md`. **For the unattended windows nothing changes.** The FILL window still
> proposes from A and B alone, and the FIX window builds only what `APPROVALS.md` names. A C or D
> finding reaches a window only if the operator puts it into an ORDER by name. This also answers the
> OPEN note above in practice: what stops the C/D population being forgotten is the operator-guided
> rounds, not a ratchet.

### The day window's two, 2026-09-09 evening — and one it asked that was already answered

**DECIDED 2026-09-09 ~17:45, by the operator, in session**, from
`spec-queue/review/review-2026-09-09.html`. That page raised three decisions. **`DAY-3` was not
one** — it is the `F299` posture question the operator answered at **08:51 the same morning**,
recorded in the section below, and re-published as open at 10:55. Filed as **`F305` (B, harness)**:
the windows carry `decisions_for_user` in their `STATE-*.json` and nothing reconciles it against
this file, so an answered question is re-asked indefinitely. **The verdict below stands and needs no
restating** — the earlier section is the authority for it.

#### DAY-1 — a dev constraints file, not a pin

**DECIDED: keep `hub/pyproject.toml`'s published range as it is, and add a development
constraints file pinned to CI's resolution.**

The problem measured today: `hub/pyproject.toml` constrains only `starlette<2.0` and
`fastapi>=0.110`, so CI resolved **starlette 1.6.0 / fastapi 0.141.1** against this machine's
**0.52.1 / 0.136.3**. `{r.path for r in create_app().routes}` yields **161 paths here and 7 on CI**
— which is why a test that could never pass on CI and never fail locally survived **thirteen
commits**.

**Why this option.** It is the only one that keeps both halves. Local and CI agree, so this class of
failure reproduces before a push; and the published range stays loose, so upstream incompatibilities
still surface early — which is exactly what happened today and is worth keeping. Rejected: **pinning
`pyproject.toml`**, which buys agreement by freezing the Hub on a version and converting upstream
drift into an upgrade nobody is prompted to do; and **changing nothing**, which leaves any test that
reads a framework data structure unverifiable locally by default.

**Two constraints on whoever builds it.** The constraints file is **not** a second source of truth
for what the Hub supports — `pyproject.toml` remains that, and the file must be documented as
development-only. And it is worth nothing if it is not used: the CI job and `CLAUDE.md`'s documented
local commands must both install through it, or local and CI drift apart again silently, which is
the whole defect.

**This does not close the related gap, deliberately.** The review page records that there is still
**no guard against a fourth occurrence** of the `app.routes` mistake — a grep-based test would
false-positive on the three files whose comments document the trap, `_routing.py` included. That is
unbuilt and unowned, and this verdict does not cover it.

#### DAY-2 / F302 — the notice stops asserting, and does not start trusting

**DECIDED: drop the `no MCP tools this turn` sentence. Do not give a fresh agent the MCP rendering
on trust.**

The requirement the notice shipped against asks only that the HTTP form be described and that tools
not be claimed. **It never asked for the denial** — that sentence is a positive claim about the
run's tool list, made on no evidence, and it is false: a probe agent called
`mcp__agentweave__create_task` on exactly the turn it was told it had nothing, and the row exists.

**Why not the other direction.** Granting the MCP rendering on trust asserts *presence* with no
observable ground — the same disease pointed the other way — and would be wrong on precisely the
harness the notice exists for. Describing without claiming is the only branch that states nothing it
cannot know.

**What makes this cheaper than it was this morning.** The `F299` verdict below has the workspace
approver learn to recognise the run's own Hub URL, so the HTTP form the notice steers a fresh agent
toward is one the agent can actually use. Before that verdict, removing the denial would have left
a first turn pointed at a path `F300`/`F301` measured it could not take.

Rejected: leaving it. It is bounded — one turn per agent, healing on the second, with
`hub_client: "mcp"` fixing turn 1 today — but it is a falsehood in the first thing every new agent
is told, and the fix is a wording change inside a requirement that never asked for the words.

### Four verdicts, 2026-09-09 morning — and three of them are second answers

**DECIDED 2026-09-09 ~08:55, by the operator, in session**, on a RESUME session's reading of the
night window's result and of the verification pass immediately below.

**Three of these four had already been decided once.** Each was re-put because checking the verdict
against the code found something the verdict did not know — which is the verification pass working
as designed, and the reason a decided-but-unbuilt item is not the same as a closed one.

#### 1. ~~F299 / F300 / F301~~ **F300 only** — the workspace approver learns to recognise a URL

> **NARROWED 2026-09-10, by the operator.** This verdict is correct and stays — **for F300 alone.**
> It **cannot fire for F299 or F301**, because in both of those configurations the MCP server that
> hosts `_decide` never starts: `_decide` is reachable only through `approve_tool_call`, an
> `@mcp.tool()` in `mcp_server.py`, which is spawned only when `_build_claude_command` emits
> `--mcp-config` *and* the harness honours it (`runner_commands.py:236-241`). F299 is a harness that
> ignores the flag; F301 sets `hub_client: "cli"`, so the flag is never emitted at all. Teaching a
> function about URLs does nothing in a process that does not exist. **The title carried three
> finding numbers and the mechanism reached one.** See `### The access path, re-decided 2026-09-10`
> for F299's and F301's own verdicts, and for a measurement that corrects this one's closing note.

**DECIDED: teach `_decide` that the run's own Hub address is not a filesystem path.** Raised by the
night window at iteration 12 and **enlarged the same night** by the `c2-verify` drives, which
established there is **no posture on this machine on which a `claude` run can use the HTTP form of
the capability plane under its own power.**

The mechanism, verified in code this morning: `_ABSOLUTE_PATH_RE` (`hub/hub/mcp_server.py:936`)
matches `(?:[A-Za-z]:[\\/]|/)[^\s"'|;&><)]*`, so the `//127.0.0.1:8010/...` inside a URL is captured
as an absolute path, checked against the run's workspace, and denied for being outside it. That is
why `hub_client: "cli"` — documented at `src/agentweave/config.py:714` as *"uncomment if MCP is
blocked by company policy"* — **restores writes and not access.**

**Why this option and not the other two.** It is the only one that widens nothing: filesystem
containment is untouched, and what changes is a *misclassification*, not a policy. The rejected
alternatives, both defensible:

- **Fall back to `acceptEdits` when the plane is unreachable.** It has a rationale already in the
  code — `DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER = "acceptEdits"`
  (`hub/hub/runner_commands.py:73`), whose comment says naming an absent approver *"would refuse
  everything, which is precisely the failure `acceptEdits` was introduced to end."* Rejected because
  `acceptEdits` **has no path check at all**, so it answers a reachability problem by widening
  filesystem containment, and `agent-capability-plane` reserves containment to the operator.
- **Leave the posture and document the workaround.** Rejected: it leaves F299 open and still gives
  the run no way to reach the plane.

**What the implementing change must not do:** it must not make the approver permissive about URLs in
general. The recognised case is the run's *own* Hub base URL, which the Hub knows because it minted
the run's credential. Anything broader is a second decision and is not covered by this verdict.

**Note for whoever specs it.** The Hub cannot today detect that a harness blocks MCP — the config
declares MCP available and the code believes it. This verdict deliberately does **not** ask for that
detection; it makes the declared-and-blocked case survivable instead.

#### 2. Entry 19 — re-decided, narrowed to the hazard that still exists

**DECIDED: refuse to start when no profile is named, not when a relative default is used.** The
original verdict (2026-09-08) was taken against a world repaired by `44a1ae5` on **2026-08-17** —
`_default_database_url()` has been absolute for three weeks and `hub/data/` does not exist. See the
verification pass below for the full evidence.

What survives: a bare `uvicorn hub.main:app` with **`DATABASE_URL` unset** still opens
`~/.agentweave/hub/data/agentweave.db` rather than the profile database everything else uses. Fixed,
not cwd-dependent, so it can no longer produce a different database per launch directory — a much
smaller defect, and still one that has cost time. `CLAUDE.md` already treats a reappearing
`hub/data/` as *"a symptom, not a database to preserve"*, which is this defect leaving a trace.

**The binding constraint on any implementation:** `CLAUDE.md`'s own documented trial-Hub start
command **is** a bare `uvicorn hub.main:app` from `hub/`, with `DATABASE_URL` set explicitly. The
refusal must key on the variable being unset and must leave that command working. A change that
breaks the documented start command has implemented the retired verdict, not this one.

#### 3. `PATCH /queue/settings` — move the reschedule into the PUT, then remove the route

**DECIDED: close the gap first, then delete.** The 2026-09-08 verdict said *remove*; the
verification pass found the route also re-schedules every queued agent (`inbound_queue.py:104-107`),
and `schedule_agent` appears **0 times** in `projects.py`. So `PUT /projects/{id}/settings` writes
the same four columns and **does not reschedule** — a real gap that exists today, independent of
this route and independent of whether it is removed.

Order matters and is part of the verdict: **the reschedule moves into the PUT before the route
goes.** Removing first and porting later leaves a window in which neither path reschedules.

Rejected: dropping route and side effect together. It is defensible — the UI never calls the route,
confirmed independently by `n10`'s no-client-anywhere list — but it would delete a behaviour the
surviving endpoint lacks, and the operator's standing preference is the cleanest design rather than
the least work.

#### 4. The overseer artifacts — the logs stay, the OV review page goes

**DECIDED: keep `.claude/autonomous/2026-09-07-overseer-log.md` and `STATE-overseer.json`; delete
`2026-09-07-sidequest-review.html`.** Raised on 2026-09-08 and unanswered until now.

The split is by *subject*, not by file type. The overseer log and its state are records of a window
run of **this** repository's own loop, the same class as the day and night logs that stay tracked.
The sidequest review page is `OV-` content, and the `OV-` series left this repo on 2026-09-08 under
*"I want only things for agentweave here in this repo."*

### Verification pass, 2026-09-08 — do the 2026-09-08 verdicts still hold?

At the operator's instruction, *"review all of those works to make sure they still hold."* Every
decided-but-unbuilt item re-checked **against the code**, not against the entry that describes it.
**Seven of eight hold. One was decided on a premise that had already been repaired three weeks
earlier.**

| Item | Verdict | Evidence |
|---|---|---|
| **R-3.1 — F209's `reason`** | **HOLDS, exactly** | `spec.py:615 accept_proposal_route` passes `expected_digest=` and **no `reason=`**; `reject_proposal_route` at `:665` passes `reason=body.reason`. Both take the same body carrying `reason: str = Field(default="", max_length=2000)` (`:607`). |
| **R-3.2 — remove `PATCH /queue/settings`** | **HOLDS, with one thing the verdict missed** | Route is real at `inbound_queue.py:81`, writes exactly the four columns (`hop_budget`, `turn_delivery_cap`, `agent_budget`, `allow_agent_jobs`) that `ProjectSettingsUpdate` (`projects.py:76-80`) also owns, and **the UI never calls it** — independently confirmed by `n10`, which lists `/queue/settings` under *no client anywhere*. **But it also re-schedules every queued agent** (`schedule_agent` per queued agent, `:105-108`), and `schedule_agent` appears **0 times** in `projects.py`. Removing the route deletes that side effect. It is already unreachable from the UI, so nothing an operator does today depends on it — but an agent or script calling the route would notice. **Either drop it knowingly or move the reschedule into the PUT; do not remove it without deciding which.** |
| **R-3.3 — entry 19, bare `uvicorn` must refuse to start** | **PREMISE IS STALE** | See below. |
| **R-3.4 — entry 21, the model catalog** | **HOLDS** | `model_catalog.py` contains **no runtime read** of `~/.codex/models_cache.json` — the only mention is in the module docstring (`:34`), describing how the literal was *derived*. It is a compile-time literal, as F267 says. The cache file exists and was last written **2026-08-29**, ten days ago. Nothing re-checks it. |
| **R-2 — archive collision check** | **HOLDS — not built** | No script, no skill hook. Its recorded weakness (it only fires if whoever archives remembers to run it) is unchanged. |
| **R-1a — route reachability ceiling 35** | **REPRODUCES EXACTLY** | Re-run 2026-09-08: **187** declared `/api/v1` route+method pairs, **35** with no client anywhere. |
| **R-1b — query error surface ceiling 51** | **REPRODUCES EXACTLY** | Re-run 2026-09-08: 54 MISREPORT total, **51 on a surface an operator can reach** (12 an empty picker, 39 a sentence/number/terminal skeleton). |
| **R-1c — dependency ceilings** | **HOLDS** | Exactly **three** `fastmcp>=2.0,<4` declarations — `pyproject.toml:47`, `pyproject.toml:71`, `hub/pyproject.toml:24` — and `starlette<2.0` at `hub/pyproject.toml:32`. The count the check would freeze is correct. |

**Entry 19 is the one that did not survive, and it is the day's pattern again.** The verdict asks
whether a bare `uvicorn hub.main:app` from `hub/` should refuse to start *"on the relative default
rather than silently opening a second database beside the one everything else uses."*
**There is no relative default.** `_default_database_url()` (`hub/hub/config.py:9-17`) returns
`Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db"` — absolute, and its own docstring
says *"Same absolute, home-relative path native mode (cli.py's HUB_DIR) already computes."* It was
fixed by **`44a1ae5`, 2026-08-17** — *"fix config.py's database_url default (D1)"* — **three weeks
before the decision was taken.** `hub/data/` does not exist on disk.

**What survives of it, narrowed.** The default is still not the *trial profile* database
(`~/.agentweave/hub/profiles/trial/agentweave.db`), so a bare `uvicorn` without `DATABASE_URL` still
opens a database nobody meant — but a **fixed** one, not a cwd-dependent one, so it can no longer
produce a different database per launch directory. That is a much smaller defect than the verdict
describes. **And any refusal must not break `CLAUDE.md`'s own documented trial-Hub start command,
which is a bare `uvicorn hub.main:app` from `hub/` with `DATABASE_URL` set explicitly.** Re-decide
the narrowed question or drop it; do not build the verdict as written.

**The two overseer items that were in this list are gone from this repo**, along with the rest of
the `OV-` series — they were decisions about a separate repository. Their verification finding
travelled with them to `witness/DECISIONS.md`: that work is **reconciliation, not implementation**,
because the code there predates the verdicts. Nothing about it is AgentWeave's to schedule.

### Trial-profile key rotation — the loop may do it itself

**DECIDED 2026-09-08 ~09:55, by the operator, in session.** The day window raised this on
2026-09-08 (`decisions_for_user` entry `day1`) and rotating the one disclosed key closed the
*instance* without closing the *policy*. Asked as a standing rule for the next one.

**Operator's words:** *"No problem with keys on trial hubs I regularly destroy and create new
ones."*

**So: an unattended window may rotate a trial-profile Hub key without asking, and need not stop or
raise a decision to do it.** The reasoning is the operator's own and is about what the credential
protects: trial profiles are destroyed and recreated as a matter of routine, so a trial key
guards nothing durable and the cost of a rotation is a file rewrite.

**The boundary this does not move.** The `live` profile on port 8000 is the operator's real usage
(`C:\Users\huida\agentweave-live`), and nothing here authorises a window to touch its credential,
its database or its process. This decision is scoped to *trial* profiles by its own wording.

Rejected: *every rotation is the operator's* — it re-raises the same block on each disclosure and
costs a window to answer something the operator has now said they do not care about at this scope.
Also rejected: *rotate, then surface it as a decision anyway* — that is the same interruption with
extra steps, and the operator's answer was that there is no problem to surface.

**Supersedes** the open half of `day1`. That entry is now closed in both halves.

### Delete the merged remote branches — done

**DECIDED 2026-09-08 ~09:55, by the operator, in session** (*"Delete the 13 merged"*), and executed
the same minute. **The count was 12, not 13** — re-measured with `git branch -r --merged master`
after a `--prune` fetch; one of 0116's 13 had already gone. Deleted, with their tips recorded in the
commit message so any of them can be resurrected by SHA:

`2026-08-24-stress-test-remediation` `bef90ff` · `2026-08-26-drive-everything-and-fix-it` `3c3e851` ·
`2026-08-27-fix-and-drive` `25469ac` · `2026-08-27-the-rest-of-the-work` `4f5db93` ·
`2026-08-30-decided-work-and-drive` `0d3974c` · `2026-08-31-the-flow-lands-its-work` `1b46110` ·
`2026-08-31-the-turn-must-end-first` `a4b2833` · `2026-09-04-daily` `9fd9853` · `2026-09-07-daily`
`3c918b9` · `2026-09-07-sidequest` `c54b2d2` · `fix/2026-08-23-design-audit-remediation` `969b7b9` ·
`panel-shell/2026-08-18-tab-store` `8d52a93`

**Kept:** `autonomous/2026-08-19-project-portability` and `autonomous/2026-08-27-build-everything-decided`
(both genuinely unmerged and carrying work `master` does not have), and
`autonomous/2026-09-08-daily`, which is today's live cycle branch.

### F140 + F142 — split them; the decision they were waiting for did not exist

**DECIDED 2026-09-08 01:50, by the operator, in session**, after the code was measured rather than
the plan re-read. `ROADMAP.md` Stage 4 held these as *"one decision, not two"* — F142 changes which
of F140's two defensible repairs is worth building — and both as blocked on the operator.

**Neither was.** F140's repair 1 shipped `1b4c730` (2026-08-30) and was **driven live 2026-08-31**,
before the choice was ever put to anyone: both Haiku agents made the `update_task(...,
status="completed")` call unprompted, both tasks reached `approved`, both commits verified ancestors
of `master`. `_briefing_completion_lines` is byte-identical to the driven version. That makes F142's
"which repair" premise moot, and the coupling with it.

**The decision taken: treat them separately, because their evidence differs.** F140 **retired** on
the 2026-08-31 drive. F142 **stays open** with its reason narrowed from *awaiting an operator
decision* to *awaiting a drive* — its fix shipped `f3a778f` (2026-08-31) and its own change document
says group 7 was *"written, compiled, and not driven"*, deferred to `DRIVE-1`, which has not
happened. One drive closes it: `t_row12_review_leg.py` with `AW_COMPLETE_BY=operator`, plus its
uncovered row four.

**Rejected: retire all four on the shipped code.** It would have taken the severity-A count from six
to two in one move, and it would have retired an A on *the tests pass* — the failure mode this
repository is worst at, and the reason the 2026-09-03 banners exist at all. **Also rejected:
re-drive F140 too.** A drive of byte-identical code buys nothing that the 2026-08-31 run has not
already bought.

**Settles nothing about F154 and F155.** They carry the same 2026-09-03 banner and have **not** been
re-checked the way F140 was. Do that search before believing them.

**Also corrected, not decided: F14 and F60.** Stage 4 listed F60 as blocked on F14's *"undecided fix
shape"*. Both are `FIXED 2026-08-30`, shipped together in `a-task-waits-while-its-run-waits`, and
`FINDINGS.md` had said so for nine days. Verified in code this session. No decision was needed and
none was taken.

---

### day1 — the disclosed key is rotated; the general question is still unanswered

**CLOSED 2026-09-08 09:20 by the operator, in session: *"forget that key. It's rotated as well."***
Raised by the day window at iteration 1 this morning, and it did not block anything — the window had
already carved ROADMAP 6.3 out of its queue rather than waiting.

**What the window actually asked is broader than the key, and remains open:** *"Say whether the loop
may rotate trial-profile keys itself, or whether every rotation is yours."* Its reasoning was sound
and is worth keeping — rotating a credential invalidates whatever still holds the old one, and the
holder most likely to matter is the operator's live instance on port 8000, which every unattended
window is forbidden to touch. **This closure answers the instance, not the policy.** If a window
meets another disclosed credential it will ask again, correctly.

**Residual, recorded rather than reopened.** 18 real-shaped 32-character `aw_live_` literals survive
in **16 tracked files** — `hub/.env.example`, `hub/hub/db/engine.py`, two under `hub/tests/`, eight
drive harnesses under `scripts/drive/`, and four documents including `FINDINGS.md` itself. Every one
is dead against a rotated key. Classified by shape, without any value being printed or quoted.

**The point of noting it is the practice, not these strings.** A rotation is final only if nothing
commits a live key again, and this repository has produced the situation twice — the disclosed key
in public history, and the two trial-Hub keys that rode the tracked half of `.claude/handoffs/`
until 2026-09-04, which is why that directory is now ignored in full. Drive harnesses reading a key
from the environment rather than carrying a literal would remove the largest bucket of the sixteen.
**Not queued** — it is a hygiene sweep nobody has asked for, and it is worth exactly one decision
from the operator before anyone spends a window on it.

---

### R-3 — the four small product calls, all four answered

**DECIDED 2026-09-08 02:15, by the operator, in session.** Each was one question with two defensible
answers, open since 2026-09-01. **None is implemented** — these are verdicts, and the work is
ordinary product work that still has to be queued.

- **F209 — thread the `reason` through.** `accept` declares a 2000-character `reason` and stores
  nothing while `reject`, three functions away, keeps it. Storing it makes the pair symmetric, and
  an accepted-with-reasons record is what an operator wants when re-reading why evidence was let
  through. Rejected: deleting the field, which would leave `accept` the only decision in the pair
  with no recorded rationale.
- **F196 + F198 — remove `PATCH /queue/settings`.** It writes four columns
  `PUT /projects/{id}/settings` already owns, with a weaker contract on both ends, and the UI never
  calls it. One owner for those columns. **Check for external callers before deleting** — the UI
  not calling it is not the same as nothing calling it.
- **Entry 19 — a bare `uvicorn hub.main:app` from `hub/` must refuse to start.** No `DATABASE_URL`
  and no named profile currently falls through to `config.py`'s relative default and silently opens
  a second database beside the one everything else uses; it has cost time twice, and `hub/data/`
  reappearing is the documented symptom. Exit with a message naming the candidates instead.
  Rejected: warn-and-start, which leaves the divergence possible.
- **Entry 21 — a `scripts/` tool, not a test.** `model_catalog.py` names
  `~/.codex/models_cache.json` as its source of truth, nothing re-checks it, and it has drifted. A
  command that diffs catalog against cache has nothing to skip in CI and is the shape that actually
  gets run when someone suspects the catalog is wrong. Rejected: a skip-if-missing test, which is
  invisible in CI — exactly where a green suite would most misleadingly bless a drifted catalog.

**Note the shape of entry 19's answer against `R-1`.** Refusing to start is an *enforcement* call,
consistent with R-1's ratchet decision of the same week, and it is the only one of these four that
changes whether a command works. It is also the one whose blast radius is any script relying on the
default — find those before building it.

---

### R-2 — a repo script

**DECIDED 2026-09-08 02:15, by the operator, in session.** Open since 2026-09-01. A collision check
under `scripts/`, run before archiving: applying a delta warns about nothing when two changes both
carry a `## MODIFIED` block for the same requirement, and archiving the second **reverted the
first**, dropping a qualification that had just landed. One collision in a batch of seven, and two
changes in flight against one requirement is not rare here.

**The known weakness of this answer, recorded because it will be the next finding if it bites.** A
script only fires if whoever archives remembers to run it — which is the same weakness the missing
check already had. Rejected alternatives that do not share it: the `openspec-archive-change` skill
(fires for every window and session following the documented path, but does nothing for a bare
`openspec archive`) and upstream openspec (the correct home, since the tool applying the delta is
the only thing that sees both blocks, but on someone else's release cycle). **If the script is
written and then not run, that is evidence for moving it into the skill, not for writing a second
script.**

---

### The `OV-` overseer decisions — MOVED OUT of this repository, 2026-09-08

**All six `OV-` verdicts now live in `C:\Users\huida\Documents\projects\witness\DECISIONS.md`.**
Moved at the operator's instruction — *"take all of those OVs ones out of this repo and leave at
that other one. That is separate work"*, and *"I want only things for agentweave here in this
repo."*

They were operator decisions about **`witness`**, a separate sibling repository, and were recorded
here only because the spec loop that raised them ran in this checkout. Five are answered (OV-1 yes,
OV-2 redact at write, OV-3 split out, OV-4 the operator only, OV-6 a command); **OV-5, the name
collision check, is still open** and is tracked there now, not here.

**One outcome of OV-3 did land in this repository and stays**, because it is AgentWeave's:
`scripts/snapshot-corpus.ps1` and the `ClaudeCorpusSnapshot` scheduled task. The retention half was
deliberately moved *outside* Witness to a plain file copy, which is why OV-6 and OV-3 were split
rather than chosen between.

---

### F295 task 1.6 — left to the night window, deliberately

**DECIDED 2026-09-08 02:05, by the operator, in session: no override.** The `close_detached` gap —
write the two-line listener so the delta's *"every path"* is literally true, or narrow the
requirement to the paths the pool dispatches `close` for — was offered and declined in favour of
letting tonight's FIX window choose. The task states both options with the measurement attached
(`grep -rn "\.detach()" hub/hub/` returns nothing; a probe's `close_detached` counter fired zero
times), and `APPROVALS.md` records that either satisfies the approval.

**Recorded so tomorrow reads this as a choice, not an oversight.** Check what the window picked; if
it wrote the listener, confirm it carried the deliberately-unreachable comment task 1.6 asks for.

---

### The day window stops proposing while the night is behind — a self-releasing gate

**DECIDED 2026-09-08 01:40, by the operator, in session.** Changes a **standing default**, not one
day's queue: `.claude/loops/day-window.md` step 6 now counts unbuilt specced changes before it
composes anything, and at **2 or more there is no spec loop** — no D-2/D-3/D-4, no new proposal.
At 0 or 1 the spec loop runs as it always has.

**The arithmetic it exists for.** FILL writes one change a day; FIX builds one per one-to-two
nights. Those rates diverge, and by 2026-09-08 the divergence was four fully specced changes, three
rounds each, **129 tasks with two ticked, neither an implementation.** Stage 0.1 of `ROADMAP.md`
cancelled the mismatch for 2026-09-08 with a dated `DIRECTION.md` section; that fix expired at
midnight and reverted the window to proposing.

**Rejected alternative: date a `DIRECTION.md` section per day through the drain.** It keeps the
default intact and is reversible per day, but every day nobody remembers to write one silently
reverts to proposing — the failure mode is invisible and the cost is a day. The gate needs no
operator action in either direction and releases itself when the nights catch up.

A dated `DIRECTION.md` section still overrides the gate **both ways**; that file outranks the
playbook, as it always has.

---

### R-1 — Enforce, as a ratchet

**DECIDED 2026-09-08 00:30, by the operator, in session.** Written up in full at `### R-1` above,
which stays where it is because its evidence is the justification for the three frozen ceilings.

In one line: **the repo writes a check, and the check freezes today's count as a ceiling that may
shrink and may never grow.** Existing instances are not repaired before the check may pass. Three
checks authorised — route reachability (ceiling 35), query error surface (ceiling 51), dependency
ceilings agree — all three promoting scripts that already exist. Scheduled as Stage 6 of
`ROADMAP.md`, behind the four approved changes and the F292 instrument repair.

Settles the old **D-2** and answers **D-6(b)** *no*. Does **not** settle F190's payload-ordering
rule; that needs a way to enumerate payload-shaped consumers, and nothing does that today.

---

### D-1 — Ratify or widen the `fastmcp <4` bound

**DECIDED 2026-09-01 — RATIFIED by the operator, in session.** The bound stands as taken. Absorbs entries 17, 31. Severity: low, reversible in one line.

FastMCP 4.0.0 reached PyPI 2026-08-31T18:20:31Z. This repo declared `fastmcp>=2.0` **unbounded** in
three places, and CI resolves fresh with no lockfile — so CI and this machine had already diverged
on the process that starts every agent turn (`pip index versions fastmcp`: LATEST 4.0.0, INSTALLED
3.1.0). The night bounded it to `>=2.0,<4` unattended and added
`hub/tests/test_fastmcp_api_contract.py` (6 tests, verified passing again 2026-09-01 08:09).

**Nothing was measured broken.** The research probed all four FastMCP APIs `mcp_server.py` uses
against 4.0.0 and all four survive. The bound was taken because v4 additionally pulls
`pydantic>=2.12`, `FastAPI>=0.133.0` and `httpx2` — a transitive set this suite has never run
against.

**Recommendation: ratify.** The cost of the bound is a deliberate upgrade later; the cost of no
bound is an unannounced major crossing under the agent runtime. If you widen it instead, run the
contract test first and read what it says.

**Coupling:** fastmcp 4 requires `FastAPI>=0.133.0`. The old D-2 tracked that; it is now part
of **R-1**, since `fastmcp<4` and `starlette<2.0` are the same unwritten rule applied twice.

---

## Closed by measurement, 2026-09-01

- **Entry 32 — "the hub suite has not run on this branch."** Answered by measurement, not decided.
  Run in the 2026-09-01 morning session before merging:

  | Suite | Result |
  |---|---|
  | `hub/tests/` | **3831 passed, 84 skipped, 1 xpassed** in 14:39 |
  | `tests/` | **440 passed, 3 skipped** |
  | `ruff` / `black --target-version py311` / `mypy src/` | clean over CI's own path lists |
  | `hub/ui` | **not run, and not needed** — the branch's product-code diff is three files (`pyproject.toml`, `hub/pyproject.toml`, `hub/tests/test_fastmcp_api_contract.py`); `hub/ui` is untouched. Measured with `git diff --name-only`, not inferred. |

  The baseline at `9fa4c4b` was 3,825 / 84 / 1, so **+6 is exactly the six new contract tests**.
  CI was also confirmed green on `master@ad60b7b`, the merge base.
