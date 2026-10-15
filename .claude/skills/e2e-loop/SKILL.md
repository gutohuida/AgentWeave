---
name: e2e-loop
description: Drive AgentWeave end to end as a real operator would — a live Hub, real agents, real runs — and report what breaks at the seams. Runs either scoped to a recent change or as a full-surface sweep across every feature area, the knowledge vault and the Hub's manager jobs included. Use when the user says "test the whole flow", "test this end to end", "drive the product", "e2e test", "does the loop actually work", "test what we just shipped", "test everything", "find the bugs", or after a change that touches how agents, specs, tasks, runs or the vault fit together. Finds defects unit tests structurally cannot: every serious finding lives between two features, not inside one.
---

Drive the product the way a user does, and report what the seams do.

This is not a test suite and does not replace one. The Hub suite has thousands of passing tests,
and the first real run of this loop still found ten defects — including a tool no agent could
call, and an agent that could write code but never execute it. **Both were invisible to every
test in the repository, because both live between features rather than inside one.** The ledger
(`scripts/drive/FINDINGS.md`, numbered F1… continuously) is past F659, almost all from driving;
the four sweeps of 2026-10-13 alone filed twelve.

*Checklist last refreshed 2026-10-15 against `master` c1178cc (every change archived through
2026-10-13, all 52 capabilities, 35 MCP tools, 42 `/agent-actions` routes).*

## Pick a mode first

| Mode | When | Shape |
|---|---|---|
| **Scoped** | After a change. "Test what we just shipped." | Steps 1–8. Scope comes from the user, then reconciles against the diff. |
| **Sweep** | "Test everything." "Find all the bugs." A release. | Steps 0, 2–8 over the whole **checklist** below. Budget hours, not minutes. |

A sweep trades depth for breadth deliberately: each area gets one representative path driven
honestly, and **not reached** is a real result, recorded, never quietly omitted. An area is not
covered because a route returned 200 — see Step 5.

## The rules that govern everything here

- **Drive a Hub you started, on its own profile and port** — `e2e.py hub-up <profile> <port>`
  (8030 and up; it refuses a port something already listens on). **Never :8000** (the operator's
  real instance: never call it, restart it or write its database). Leave the trial Hub on :8010
  alone too unless the operator says otherwise.
- **Never point a Hub whose code you are editing at this repository.** Test projects go under
  `~/Documents/`. `.agentweave/` and `spec/` at the repo root are the migration's work product,
  not test output — never delete them as cleanup.
- **Cheap models only**: Haiku, `claude-haiku-4-5-20251001` or its alias `haiku` (aliases are
  accepted choices since 2026-09-28; only an undeclared name is a 400). **Codex is undrivable on
  this machine** — every Codex-only path is *not reached*; say so. Copilot runs over ACP; a stub
  provider (`testbed/drive1005-*/stub_provider.py`) drives Copilot runners and whole flows at zero
  spend when a path needs no real judgement.
- **The Hub spends money on its own, too.** Manager jobs (conversation titles, vault distillation,
  vault reports, spec-vault check) are off on a fresh project; once enabled with a runner, every
  upload, proposal and completed turn is a paid model call. Say how many you expect (Step 2), and
  turn them off when the row is done.
- **Don't fix while testing.** Findings go in the ledger; fixing mid-drive contaminates the rest.

## The checklist — what "everything" means

Areas have **names, not numbers** — findings cite the name (two numbering schemes already
collided: the old 19-row matrix and `scripts/drive/SURVEY.md`'s 17-area map). A sweep reports a
verdict for every row: **held · works with problems · broken · not reached · not shipped**.

| Area | The representative path — and the seams inside it |
|---|---|
| **Projects** | Open a folder (native dialog and typed path); settings page groups (Collaboration, Integration, Checkpointing, Project) and the Overview **Collaboration** block showing the live values; main-branch suggestion; relocate onto a path another project claims (refused); delete-project dialog — and what it leaves behind (the private vault, F592). Project instructions: edit, *clear asks first*, a failed load must not render an empty savable editor; a failed settings query shows a named failure with Retry (F197). |
| **Runners & models** | Create per CLI (claude, codex, copilot); launchability, and "This agent will run, but cannot collaborate: <reason>" where a runner is bound; catalog (Opus 5.5, **Sonnet 5.5 default**, Haiku 4.5, Fable 5.1, plus previous generation); an alias (`sonnet`, `haiku`) accepted on the runner, Add-agent, per-run and loop doors and stored as written; an undeclared model refused naming the declared ones; every runner select reads "{name} - {model} ({cli})". Codex models come from its CLI's cache (*not reached*). Delete a runner a job, an agent or the settings' checkpoint runner holds → 409 naming every holder (F589/F595); a runner only archived agents hold can be deleted. |
| **Agents** | Create from the dialog; bind runner + charter; reserved names (`operator`, `user`) and route words (`conflicts`, `settings`, `sessions`) refused at creation *with a sentence*; an unknown agent name refused on every agent-keyed route; a PATCH of a removed field (`contact_mode`, `self_registered`, …) → 400 "Unknown agent field(s)"; archive → gone from every picker; unarchive from the old conversation's notice. There is **no agent delete route** (the archived change named "delete" did not ship one). `request_agent` from an agent needs a named open template agent and copies its runner/charter/config, not its grants; it counts only **open** agents against `agent_budget` (archived free a slot, never a name). A `read_only` agent can hold no task work. |
| **Charters** | Seeded starters; create, edit, bind, delete dialog; an empty charter says so in context (in flight in openspec, so *not shipped* until it moves). |
| **Conversations & composer** | A real turn; rename, archive, unarchive; generated title (a manager job); lineage. Composer: `@file`, `$skill`, `/model`, model / permissions / effort pills, spec pill; drafts survive reload; an `@` an *agent* wrote reaches a runner escaped (`\@`) and reads no file; a refused first send deletes the exploration it created. Live thinking stays open while a turn runs; **Hide diagnostics** preference. Side panel: all six tab kinds (specs, files, loops + each detail); Insert-into-composer; narrow window turns it into a drawer. Ctrl+K palette. |
| **Runs** | Stop a turn; turn-end labels survive navigation; sessions; recent divergences; the first turn of a new agent is *not* told it has no tools; the tool server is the copy the Hub pinned at start (`~/.agentweave/hub/tool-server/<digest>/`; edit `mcp_server.py` → no effect until restart); `harness_mcp_status` connected / failed / absent, and a run without MCP still reaches the Hub through `aw-tool` call files. A run claims only an unassigned task or its own agent's. |
| **Inbound queue & messages** | Agent→agent chain under a low hop budget, sender told it was suspended (`held_by_hop_budget` + `delivery_note` on the send); operator message injected mid-chain; **Withdraw**, **Continue** (the entry's deliver-now; there is no control named Deliver now; with its "not started — reason" text); an abandoned message's block says "Last attempt failed: …"; `send_message` to the Operator refused with where they read; a message to an agent with no runner is held, not destroyed — and **binding a runner later drains it and spends** (F96). |
| **Tasks** | Create (with `depends_on`); board; rename in the drawer (Enter saves, Esc cancels; agents 403); walk the transition machine; **provoke a refusal at every actor boundary** — an agent approving its own work, finishing *another agent's* task, PATCHing assignee/priority/description (403 before the write). Transition history attributes moves (operator / agent / loop / **flow**); `task_history` agrees. Delete a task. Filters and cross-tab links. A list past 100 rows reports `total`; an oversized `list_tasks` page is written to the workspace (F523). |
| **Dependencies** | Hand-authored A→B→C, and `depends_on` declared at creation and in the drawer's "Depends on"; a planner chains same-file tasks (`files`) and the submit names tasks that declared none. Start B while A is unapproved; reject the middle one; reopen. B's checkout already exists when A is approved later: **B's next turn merges A's commit in**, and a conflicting prerequisite refuses the turn naming it. |
| **Spec documents** | create → explore → close → propose → approve → archive → reopen (to `exploring`; `proposed` is 409). The journey: one step at a time (`advance_spec_step`, `set_spec_size`), a project's own steps (`spec/journey.json`, Settings `spec-steps-*`); an exploring turn asks in its reply, not through `ask_user`. Propose answers 200 with a `blocking` list; **approve lists the gaps (409 `approval_warnings`) and Approve anyway records them** (`spec-approval-report`); approving a change with a `delivery` section starts its flow and names its reviewer. Roadmaps (`kind=roadmap`, slices; a change names its slice). Enforcement select with a reason, **History (n)** of rigor changes, retired requirements on screen. Proposals: repeat answers `already_pending`, withdraw, superseded. Re-approving an amended document refreshes its open tasks. A large agent `read_spec_document` comes back as a file in the agent's workspace (`written_to`), or bounded with `continue_with` where there is none; `identifiers=` reads named requirements; `submit_spec_document` round trip preserves nested fields; `rename_spec_document`; `amend_spec_document` lands visible but "not reviewed"; `report_cannot_satisfy`. Delete a document. |
| **Corpus & folding** | From the app: document browser index strip, **Rebuild index**, **Adopt** an untracked document, **Place under** a parent. Fold a finished change into its capability (dialog, one audited merge; archive refused until tasks are done and folded) with retire-what-it-supersedes; reconcile pass and its gaps (`record_reconcile`); retire a capability with an absorber. After a fold, read the capability's coverage (F593). |
| **Requirements, evidence & coverage** | Record evidence mid-turn (`record_evidence`); decide it only after the run ends (`recording_run_live` 409), from the coverage bar's **Evidence** toggle (Reject needs a reason; a typo'd decision is 422 — the words are `accepted`/`rejected`); `list_evidence` / `decide_evidence` from an agent; a sibling task's evidence counts only once that task is approved; a rejected requirement blocks approval at every rigor. Evidence goes `stale` when its requirement is reworded. Land refuses awaiting evidence (`gate_unsatisfied`). |
| **Drift** | Evidence accepted → change an unwatched file (no drift) → change a file the evidence watches (from its locator / commit / line of work) → **Scan for drift** on the document's drift strip (manual only: no scheduler) → answer it (three answers, once only). |
| **Knowledge vault** | The **Vault** tab. Add text (tracked, private, `dated` YYYY-MM-DD — another format is 400), a PDF and an image (`POST /vault/files`, raw body; 415 other types, 413 above 10 MiB; fake bytes 400); the file shows inline; a private one leaves only a stub under `knowledge/` and lives in the private location (`PUT /vault/settings`; a location inside the repo is 400). Distillation (needs the `vault-distillation` job on a runner): facts quote their source and cite lines; a Read-only worker transcribes files first; **Distil** re-runs it (409 when off / no runner / text on another machine). Two sources that disagree → a **contradiction**, the later-*dated* fact presumed, both disputed; **resolve** writes a `decision` source and supersedes the loser (second resolve 409); a re-distil must not reopen it (F586) and gives new fact ids (F587). An agent turn's context names the vault in one line; the agent uses `vault_map` / `vault_read` (paged, counted as a fetch — maps are not) and `vault_report`; the `vault-reports` job answers stands / corrected / referred, and the operator closes a referred one. The map orders areas and facts by reads. Specs cite facts: **Vault warnings** panel on the spec page (cited-fact warnings live; `spec-vault-check` on propose and **check now**), `vault_warning` gaps at approve. |
| **Manager jobs** | Environment → **Manager**: four jobs (`conversation-titles` borrows the agent's runner; the three vault jobs need their own), enable / runner / model per job, firings listed with outcome `written` / `empty` / `failed`. Turn a vault job on with no runner and read what each door then says. A runner from another project → 400. A worker's answer is not kept (F581) — the activity line is all there is. |
| **Jobs & loops** | A loop that fires, claims, works, drains (at approved/rejected) and stops — both endings. Its tab: **Settings** (staged to the next firing; no stop condition refused), **Stop** with a reason, **Archive**, **Delegate / Take back**, history of creation and queue additions. Badge reads "{n} fired". Pressing Run names the reason that held (queue empty / one named agent / none free); a firing whose agent has no runner **waits** (200 with `waiting_reason`), it does not fail; a failed firing leaves a failed row. Job events carry `job_run_id`, not `run_id`. A new loop on a document adopts what an archived loop left. Loop tab in the side panel. The concurrent-run cap (`the-agent-budget-caps-concurrent-runs`) is approved but **not shipped**. |
| **Flows & review** | A flow on an approved document (from **Start flow** or its `delivery`): parallel firing; the dispatch, not the firing, stages review; the reviewer is never the evidence author and reviews the branch tip; a verdict withdraws the waiting review turns; a task held by an idle agent is released; a review no reviewer can approve goes to the operator with the gate's sentence; a flow's review turn can be a **tester** turn whose amendments land "not reviewed". No dedicated flow screen exists — say what you had to read instead. |
| **Questions** | `ask_user` blocks the run and parks the bound task *during* it; answer releases it; decline; let one time out (timeouts under 10 s are 400); answer *after* timeout but before the run ends (delivered as new input); `get_answer`. Number keys pick options on the ask card. "May agents schedule work?" after the operator grants it in settings (F597). Leave one unanswered on purpose. |
| **Permissions & sandbox** | `manual`: approve one, deny one, let one expire; the Ask-me card shows what *Workspace only* would decide. **Default workspace-only posture**: `cp x ..`, `~`, `$HOME`, `C:`, `Z:foo`, `$x..`, a quoted slash — refused; brace patterns expanded; a URL argument allowed; a relative name with a colon later judged by its names (F446); PowerShell `Set-Content` writing the Hub's own call file allowed. A write outside the workspace *recorded*. Workspace-only with no tool server falls back to acceptEdits. The pill matches the posture the run got (`permission_mode_at_rest`). Permission decisions list in the Questions panel. |
| **Capability plane** | `allow_agent_jobs` off → an agent's `create_job` / `create_loop` / `create_flow` refused → the refusal reaches the operator as a question → grant → retry succeeds. Claude runs get only the Hub's tool server (`--strict-mcp-config`) and are told their tools as `mcp__agentweave__<tool>`. The agent HTTP plane (`/agent-actions/*`, 42 routes) agrees with the MCP tool for the same act. |
| **Checkpoints** | Drive past the threshold; banner; Checkpoint now; cut over **once** (a second press, or unarchive-then-press, refused naming the successor; a spent checkpoint is not offered); Continue on a named conversation; grants closed by default, and one grant reaches every checkpoint in the project; `recall` / `list_checkpoints` / `read_checkpoint` / `submit_checkpoint_notes` across agents with and without it. A Copilot compaction counts as the threshold. |
| **Worktrees & integration** | Per-*task* checkouts (plus per agent); two writers, one file; conflict report; the approval preview's merge verdict (with the conflicting paths) equals the gate's; **project checks** (Settings: named commands) run on completion and an approval reads their result; approve → merge; **Land it**; Retry a failed integration; footprints name a line of work, never `HEAD`; flipping an agent's isolation under held work → 409 `isolation_change_under_held_work`. |
| **Accounting & allowance** | Per-project and per-conversation usage; "excludes N turns with no reported cost"; Copilot credits; set a budget and exhaust it — including via an *operator* turn (F456) and a firing on a spent budget; title/checkpoint/manager worker spend counted; a spent provider allowance holds the queue rather than abandoning it (hard to provoke: not reached is honest). Quiet hours. |
| **Logs, events & SSE** | Logs page back and filter; `/events/history`; the activity strip shows only this project (F419); an event is announced only after its write commits; a live view that fell behind gets `stream_gap` and the Activity feed says events were not delivered; secrets redacted (one split across two events too) while file paths are not. |
| **Resilience** | Stop mid-flight; kill the Hub with a run in flight → restart → reconciled, operator message returned (Stop on an orphaned run is in flight in openspec, *not shipped*); two concurrent triggers for one agent answer accepted input as accepted, never a 500 "database is locked" (F349); unknown API route 404 not 405; **failure injection — what does each route return when the function it calls raises?** |
| **CLI & lifecycle** | `agentweave doctor` / `status` (need both `--profile` and `--port`; `--port` follows the profile serving it), `stop`, `reset` on a throwaway profile; a Hub with no `DATABASE_URL` refuses and names the file. |
| **Keyboard & dialogs** | Keyboard only: Ctrl+K, a dialog takes focus on open (confirm dialogs on Cancel), one Escape closes one layer, focus returns to the opener, Enter doesn't re-fire it. Drive in a real browser. |
| **Agent environment** | What a Hub-launched agent actually sees: does it load the operator's `~/.claude/skills` (F454)? Does "use send_message" reach AgentWeave's tool or the host's `SendMessage` (the turn now warns)? Are trivial commands pre-approved past `manual` (F453)? The one-line vault index; the onboarding context for `aw-tool` call mode. |

**Cross-cutting, checked on every row:** is every refusal *legible* (Step 4 rule 6); does the
effect read back, not just the echo; does the screen show it.

**A backend feature with no UI is a finding** unless the ledger already has it. Since 2026-10-07
drift, evidence decisions, corpus adopt/arrange, rigor history and retired requirements all have
screens; what remains is **a flow view** (only Start flow and the Loop tab) and **a worker's own
answer** (F581). Check new routes against the app before assuming either way.

**Screens to actually open.** Project tabs (six): Overview (Collaboration block, budget summary,
and the Questions takeover), Tasks (Board **and** Dependencies, the task drawer with its title,
"Depends on", checks row and transition history), Spec (rail, document browser with the corpus
strip, phase bar with History, coverage bar with Evidence, proposals and amendments panels,
approval report, **Vault warnings**, drift strip, retired requirements, fold / retire / start-flow
dialogs), **Vault** (entries, entry detail with its facts, upload form, "where entries go"
settings, Contradictions with the resolve form, Reports with the close form), Jobs (form, cards,
recent runs), Activity (**and** its Logs view). Environment (nine): Quality, Instructions,
Runners, Charters, **Manager**, Worktrees, Diagnostics, Budgets, Settings. The seven
agent-settings sections (identity, execution, charter, interaction, context, access, workspace).
The conversation: banner stack, ask card, permission card, queued entries, live work block, side
panel. There is **no** Permissions, Checkpoints, Contradictions or Reports page: permissions are
an inline card, checkpoints are banners, contradictions and reports live inside Vault.

**Least-driven paths — go here first in a sweep.** Not exercised by the 2026-10-15 full sweep
(seven parallel groups, F598–F659): an agent amending from a tester turn; `report_cannot_satisfy`;
`list_evidence` / `decide_evidence` from an agent; a rejected requirement at contract or gate
rigor; a parallel or multi-agent flow, a verdict withdrawing waiting reviews, an idle holder's
release; integration **Retry**; the planner's same-file warning; the agent HTTP plane for jobs;
a new loop adopting an archived loop's leftovers; quiet hours and the provider-allowance hold;
a Copilot compaction and the Copilot stub; checkpoint grants across agents; the Loop tab in the
side panel and the checkpoint banner on screen; the Activity feed's gap notice and F419;
`vault_read` paging, a `corrected` report, "Neither stands"; the native folder dialog and the
Delete-project dialog in a browser; an agent-written `@` reaching a runner escaped; live
thinking staying open; an abandoned entry's "Last attempt failed".

## Step 0 — Refresh the checklist *(sweep only)*

The product moves faster than this file. **`spec/` owns the corpus since 2026-10-07** —
`openspec/` is history. Before driving:

```bash
git log --oneline --since=<date of the checklist line at the top>   # what landed
ls spec/changes                                                      # change documents
py -3.11 -c "import json,glob; [print(json.load(open(f,encoding='utf-8'))['hub']['phase'], f) for f in sorted(glob.glob('spec/changes/*/spec.json'))]"
ls spec/capabilities                                                 # current behaviour
grep -n '^\*\*Status:\*\* *open' scripts/drive/FINDINGS.md | tail -30
```

`archived` changes are shipped and folded: each must land in some row's path — add it if not.
**`approved` is not proof of shipped** — `the-agent-budget-caps-concurrent-runs` is approved and
unbuilt; grep the code before driving one. `exploring` / `proposed` are not shipped. The changes
still in `openspec/changes/` are leftovers to be moved across, not in flight: treat their behaviour
as not shipped. Re-verifying an open finding on a row you touch is cheap and tells the operator
whether it still bites.

## Step 1 — Establish scope before looking at anything *(scoped mode only)*

**Ask the user what to test, in their own words, first.** Do not read `git log`, the change in
flight, or the session's own work before asking. A tester who starts from what was just built
inherits the builder's blind spots. Ask plainly: **"What should this run exercise?"**

**Then reconcile, and only then:** *"You asked for X. This session also touched Y. Include it?"*
Never silently widen the scope you were given.

## Step 2 — Derive the operator gates for *this* scope

The scope decides where a human is genuinely required — a spec run stops for close, propose and
approve; a permissions run stops at a card; a queue run may need no stop at all. Say what you found
and ask how much to drive unattended.

**Money is a gate.** Say roughly how many real turns **and manager firings** the run will spend
before starting (the 2026-10-13 vault sweep: two agent turns, about fourteen firings).

## Step 3 — Prepare, and check the Hub is really on your code

```bash
cd .claude/skills/e2e-loop                              # or ~/.claude/skills/e2e-loop
py -3.11 e2e.py hub-up sweep$(date +%m%d) 8030          # fresh profile, own port; prints health
py -3.11 e2e.py setup aw-sweep-$(date +%m%d)            # git repo under ~/Documents, opened as a project
py -3.11 e2e.py agent <project> alpha "Spec" claude claude-haiku-4-5-20251001
py -3.11 e2e.py manager <project> vault-distillation on <runner-id>   # only for vault rows
```

`hub-up` refuses :8000, :8010 and a port already in use, starts the Hub from `hub/` from source,
and records the Hub, its database and its PID so later commands find them. Two failure modes cost
an hour each:

1. **A Hub on older code.** Anything under `hub/` changed since it started → `hub-down`, `hub-up`.
2. **`ui_stale: true`** (the key is absent when the bundle is fresh). The dashboard bundle is older
   than `hub/ui/src`; every UI finding from it is worthless. `cd hub/ui && npm run build`, then
   `py -3.11 scripts/refresh_ui_bundle.py`, restart.

**Give the project real subject matter** — a small library with a test suite and a seeded defect or
two. A make-work fixture never exercises the parts that decide whether work is *good* (review,
evidence, gates). Add what the rows need: two modules that collide for Worktrees, an untracked
`spec/**/spec.json` for Corpus (Adopt takes only `.json`), a file outside the project for the sandbox, non-ASCII content for Step 6,
and for the vault two sources that disagree with different `dated` days plus a real PDF and PNG
(`reportlab` / `PIL`, as `scripts/drive/s1013_vault_sweep.py` makes them). **Keep the answer an
agent should find out of a source's first 300 characters** — that is the map's `opening`, and Haiku
answers from the map without ever calling `vault_read`.

## Step 4 — Drive it, and hold to these

Each of these produced findings. They are the method, not decoration.

1. **Use the real surface. Never simulate a step.** If something has no API, that absence *is* the
   finding. **No row inserts, ever** — a fixture assembled by writing to the database tests the
   database, not the product. (The vault's records are files: never write them by hand either.)
2. **Play the operator honestly, and leave something unanswered.** Answer decisively, in prose,
   with real constraints — then deliberately let one question go unanswered.
3. **Watch the seams** — exploring→proposing, approved document→task, completed→reviewed, one
   agent→the next, upload→distil→contradiction→spec warning. The defects are there, not inside a
   phase.
4. **Read what the agent actually said.** The transcript is evidence. Don't dismiss an agent's
   account of its own failure; verify it.
5. **Follow peer-triggered and Hub-triggered work**, not just what you triggered — a peer's
   message and a manager firing each take a different path.
6. **Provoke every refusal you can, and judge its legibility.** A gate that refuses correctly but
   says only "forbidden" is a defect. Each refusal must say *what would work instead* — and must
   *reach the screen* (several refusals happened and were never shown).
7. **Read the effect back, never the echo.** A 200 whose input was silently dropped (F451 path vs
   id, F452 nested keys) is the commonest class of bug here.
8. **Ask what a route returns when the thing it calls raises.** A bare 500 is a finding.
9. **Probe past every boundary** — lists at their limit, a document past 40,000 characters, a vault
   entry past one page, a file at 10 MiB, a name at 32 characters, a path with a colon or a space.
10. **Record friction, not just failure.** Something that works but takes six calls to discover is
    a finding. Count the calls.

## Step 5 — Verify independently

**Never accept "the tests pass" as evidence.** Run them yourself (`py -3.11 -m pytest hub/tests/`
and `tests/` separately — together they fail collection). Recompute a result by hand.

**Check the database and the files, not just the chat** — task transitions, document events,
conversation records, `job_runs.status`, `event_logs where event_type='manager_job_fired'`, and the
vault's own records under `<project>/knowledge/` and the private location:
`py -3.11 e2e.py ro "select ..."`. An agent's summary is a claim; the rows are the fact. A route's
200 is a claim it accepted the call, not that the effect happened.

**Don't let the harness lie.** Every green check states its reason. Match rendered text with
`text_content()` — `inner_text()` returns CSS-uppercased text — never `page.content()`. Read
`/openapi.json` before assuming a route (guessed routes produced five false 404s). A transition map
imported from the product asserts it against itself. A test fixture in an order the route never
emits is not evidence (F190).

## Step 6 — Vary one axis

Change one environmental thing and re-run the verification: encoding (`PYTHONIOENCODING=utf-8`),
locale, a path with a space or non-ASCII character, working directory, **`claude` absent from
PATH** (CI's runners have none; a local green can hide CI-only failures). The first run's tests
passed 99/99 and failed 9 under a different encoding. **A review where author and reviewer share an
environment is blind to this whole class.**

## Step 7 — Record it

Append to `scripts/drive/FINDINGS.md`, continuing the F-numbering. Rank **by what each cost**. For
each: what happens in a sentence · the evidence (transcript quote, row, command and real output) ·
the **area name** · one defect or a design gap · whether an open finding or a change already covers
it (`ls spec/changes`, and grep `openspec/changes/` for leftovers) · severity **A** blocks a real
user · **B** wrong or misleading · **C** friction · **D** noted. Status goes on a line starting
`**Status:**` — the backlog page reads only that.

**Also record what held.** A gate that correctly refused is a result; a report that lists only
defects describes a different product. List what you exercised and what you did not, so the next
sweep widens instead of repeating.

For a sweep, the deliverable is a **report**: every checklist row with its verdict, the findings
ranked, and a strong-suits / weak-suits verdict. Publish it as an Artifact. Then run `/backlog`.

## Step 8 — Clean up

```bash
py -3.11 e2e.py clean <project>     # archives jobs, disables manager jobs, DELETEs the project,
                                    # removes its dir and the private vault F592 leaves behind
py -3.11 e2e.py hub-down            # stops exactly the PID hub-up started
```

**A live loop or an enabled manager job spends money, and a loop can launch agents that run this
very skill** (F454). Archive each scratch job and disable each manager job the moment its row is
done; `clean` does the rest. Jobs can't be deleted, only archived. Confirm no listener is left on
your port. Keep a project only when rebuilding its state (an approved document, accepted evidence,
a resolved contradiction) is the expensive part — and say so.

## The harness — `e2e.py`, in this skill's directory

Always `py -3.11`. Parallel sweeps each set `AW_E2E_STATE=<own file>.json` so their Hub records
don't overwrite each other. Every call goes through the Hub's HTTP surface with a real key (from
`/setup/token` unless `AW_KEY` is set); database access is read-only.

```
hub-up <profile> <port>                         start a Hub from source; refuses a busy port
hub-down                                        stop that Hub by its exact PID
setup <name>                                    git repo under ~/Documents, opened as a project
agent <project> <name> <charter|-> <cli> [model] create (or rebind) through the operator route
doc-new <project> [title]                       new document; the Hub mints the path
turn <project> <agent> <msg> [--doc P] [--task T] [--perm MODE] [--fresh]
                                                continues the newest *open* conversation
watch <run-id> [minutes]                        wait, then dump the whole turn
answer <project> <agent> [choice]               answer an open ask_user batch
close|propose <project> <path>                  operator gates
phase <project> <path> <to> [reason] [--anyway] --anyway = Approve anyway over approval_warnings
tasks <project> / task-set <project> <id> <st>  the board / move a task (prints refusals)
manager <project> [<key> on|off [runner|-] [model]]   list or set the Hub's own model jobs
vault <project> map | read <id> | contradictions | reports | settings
vault <project> add <name> <type> <text|@file> [--private] [--dated YYYY-MM-DD]
vault <project> file <path.pdf|png|jpg> [type] [--private] [--dated YYYY-MM-DD]
api <METHOD> <path> [json | @file]              any route; @file sends raw bytes (.json as JSON); never raises
ro "<sql>"                                      read-only query on the Hub's database
state <project>                                 documents, events, runs, jobs, manager jobs, tasks
clean <project>                                 archive jobs, disable manager jobs, delete, remove
```

`api` is for refusal probes: it prints the status and body whatever they are. Extend the harness
when a row needs it — but if a step has no API to call, that's Step 4 rule 1, and it's a finding.
`scripts/drive/sweep_client.py` (used by the 2026-10-13 sweeps, `scripts/drive/s1013_*_sweep.py`)
has a generic `poll`, a `turn` that waits out the run, and per-call tokens — borrow from it when a
phased drive script is the better tool; it has no Hub lifecycle and no :8000 guard.

## Reference — traps that each cost a session

- **Interpreter:** `py -3.11`. Bare `python` is a venv that runs and produces false failures.
- **Git Bash mangles `/projects/...` arguments** into `C:/Program Files/Git/projects/...`. The
  harness repairs it; in your own scripts pass paths without the leading slash.
- **`DATABASE_URL` must be a `C:/` path.** A `/c/Users/...` form silently creates a stray database.
  A drive script that imports hub modules must set it first. Never start a Hub on a copy of the
  :8000 database.
- **Holding a turn open:** Claude Code blocks a standalone `sleep` / `Start-Sleep` in an agent turn,
  so a "kill the Hub mid-run" drive kills nothing. Have the agent run
  `py -3.11 -c "import time\nfor i in range(120): time.sleep(1)"` under `--perm workspace`, and
  confirm the run is `running` with its tool call recorded before killing.
- **A live turn cannot carry literal escape text** — shell-judge escapes need a wire-level probe.
- **`/events` is SSE and never returns** — history is `/events/history`. Never pipe a drive script
  through `head`: SIGPIPE skips its `finally` and leaves a job enabled. Never end your own turn on a
  backgrounded drive: it leaves a live Hub and a dirty tree.
- **`GET /jobs` hides archived jobs** — `?include_archived=true`. A failed job create (409 on the
  document claim) still leaves a job row: archive it. The create response nests the loop under
  `loop` (no top-level `loop_id`); re-`GET` for queue and tasks. One loop per spec document.
- **`POST /jobs/{id}/run` on a drained loop answers 409 while still emitting its event** — the
  stop happened; read the event, not the status.
- **An agent with a runner consumes operator mail at once**, so a later firing is refused "already
  running a turn". To hold mail queued, put a non-empty directory where the agent's worktree goes.
- **`PATCH /tasks/{id}` with `{"assignee": null}` now clears the assignee** (fixed, F78); an omitted
  field is left alone. Probe the other direction: a priority-only PATCH must not unassign.
- **A loop's queue drains at approved/rejected, not completed** — it stalls until someone reviews.
- **Document routes take the path in the query** (a JSON body is 422); a document written in one
  PUT always warns `steps_skipped` on approve (F574) — use `phase … approved --anyway`; propose
  can answer 200 while blocking (read `blocking`); the fold's `into` is a capability *path*.
- **Worktrees:** per agent at `.agentweave/worktrees/<agent>`, **plus per-task checkouts**.
  Code an agent writes is there, not on the main branch, until integration lands it.
- **Scratch-Hub agents use `aw-tool` call mode, not MCP**; the first bare-path call often gets a
  usage error and recovers. To measure an agent's MCP path, use its second run. Tool calls are in
  `agent_outputs` only as "Called PowerShell" — read the transcript through `runs.session_id`.
- **Haiku wanders:** it records evidence for another task's requirement (coverage accepts it),
  edits files outside its task, and two agents will ping each other until the hop budget stops them.
- **`task_transitions.actor_kind` is `run`** for an agent's move; DB timestamps are UTC.
- **Printing agent replies through cp1252** crashes on `→`/`▾` — `PYTHONIOENCODING=utf-8`.
- **The auto-mode classifier refuses a trigger with `bypassPermissions`** — drive with `workspace`.

### Driving the dashboard

- Playwright, seeded via `add_init_script`: `sessionStorage['agentweave-session'] =
  {"apiKey":…,"hubUrl":…}` and `localStorage['agentweave-selected-project'] = <project id>`.
  `scripts/uishot.py` cannot authenticate.
- `wait_until="domcontentloaded"` — `networkidle` never arrives because of SSE.
- Navigation is store state mirrored into the URL; drive it by clicking. There is no `?doc=`
  parameter: click `spec-tree-document-<path>`. The side-panel control is `aria-label="Show
  panel"`; the job card expander is `aria-label="Expand job details"`.
- Vault testids: `vault-page`, `vault-upload-{open,name,type,visibility,dated,binary,content,file,
  submit}`, `vault-settings-{default,location,save}`, `vault-entry-<id>`, `vault-fact-<id>` (with
  `data-disputed`), `vault-distil`, `vault-file-{pdf,image}`, `vault-contradiction-<id>`,
  `vault-resolve-<id>-{stands,note,submit}`, `vault-report-<id>-{note,close}`. Manager:
  `manager-job-<key>[-enabled|-runner|-model]`, `manager-firing-<i>`. Spec page:
  `spec-vault-warnings`, `spec-vault-warnings-check`, `spec-vault-warning-<key>`,
  `spec-approval-report`, `spec-rigor-history-toggle`.
