# Catch-up — 2026-08-15 run

**Read this first.** Newest entry at the top. Every iteration appends here before it commits, so
this stays current even if an iteration dies on a quota limit.

Run window: **12:21 → 22:00 BST**, branch `autonomous/2026-08-15-spec-flow-hardening`, cut from
`hub-native-experience` at `a40ac5b`.

Operator's intent, verbatim: *"I want to finish the integration with the spec. I want the spec/dev
flow in agentweave to be strong and working. Find all the bugs, correct them, find improvements,
frictions and work on them."*

---

## Needs your decision

Nothing blocks the loop. These are yours whenever you get to them — full text in `STATE.json`
under `decisions_for_user`.

| | question |
|---|---|
| **d1** | The ~40 human-only judgement calls. `2026-08-15-judgement-evidence.md` now holds the artefacts so you can answer them without re-driving the product. **This is what unblocks archiving 13 of the 14 in-flight changes.** |
| **d2** | `2026-07-30-hub-native-experience` has 69 open tasks and looks partly superseded. Drop, split, or resume? |
| **d3** | Carried: does an abandoned queue entry read as "the Hub gave up"? Do two exit codes on one event read as informative or noise? |
| **d4** | Carried: should `.claude/handoffs/` stay tracked, now 134 files? |

---

## The short version so far

**The spec flow's authoring half works, and this is the first time anyone has watched it work.** An
agent interviewed you, you answered, and it wrote a real 23KB specification with 8 requirements. Two
openspec tasks had been sitting open specifically because that had never been observed.

**One genuine bug found and fixed**, in the change that exists to prevent exactly it: the tool list
told agents `submit_spec_document(path, document)`, a signature the tool has never had. Any agent
following its own tool list would have failed the call.

**Four things that looked like serious bugs were my own query errors** — written up as such in
`2026-08-15-spec-flow-findings.md` so nobody re-files them.

**Still untested:** everything after the document exists — propose, approve, build, evidence, merge.
That is now the longest-standing untested claim in the product, and it is what the loop does next.

---

## 12:21 — handover from the interactive session

**Done**

- `/loop-prep` run properly: intent interviewed *before* reading the handoff, so the queue is not
  an echo of last session's. Environment measured, not assumed — the Hub had been running since
  00:40 and was one real commit stale, so it was restarted onto current code.
- **Driver stand-down guard** (`a40ac5b`). You chose session + backup driver; nothing stopped the
  two colliding on one branch. A firing now skips when `last_heartbeat` is under 25 minutes old.
  Verified five ways with a stubbed `claude`, then **verified for real** at 11:52:35.
- **`submit_spec_document` fixed** (`95f8fa4`). Two new tests compare every described argument
  against the real schema; mutation-checked. 18 of 19 tool entries were already correct.
  `the-tool-list-matches-the-tools` went from 6 done / 17 open to **22 / 4**.
- **Spec flow driven live** in a fresh project `aw-loop10` (`f31e90e`). Run 1 interviewed you in
  prose and wrote nothing — which is *correct*, per `SPEC_PHASE_DUTIES`. Run 2, after your answers,
  called `submit_spec_document` and wrote the document. Total cost $0.74.
- Full suites measured **both sides**: hub 631+686+712 → 631+686+**714**, CLI 360 both. This also
  settles handoff 0047's outstanding "full suite not run since `55bfadb`".
- Handoff `0048` written and chained to `0047`.

**Found**

- The activity log is **65% duplicate `context_warning` rows** — 15 of 23 events, the same
  measurement repeated up to four times in two seconds. Real friction, filed for the QoL phase.
- `POST /projects/create` correctly refuses an existing directory but does not name `/open` as the
  alternative.
- The minted spec directory name is 66 characters, and kept the agent's *first* phrasing while the
  document title was later refined to something better. Path and title now disagree in quality.

**Nearly went wrong**

Git Bash `date` on this machine prints UTC while labelling it `+0100`. The handover heartbeat was
therefore stamped an hour in the future; the driver would have computed a negative age, concluded a
live session held the branch, and stood down until ~13:31 — losing roughly seventy minutes of the
run you asked for. Caught by cross-checking against PowerShell, fixed, and recorded in `dead_ends`.

**Next**

Take the document through propose → approve → tasks → build → `record_evidence` → accept →
approve → merge, and confirm the work is genuinely reachable from main.
