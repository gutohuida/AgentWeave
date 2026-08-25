# Group 11 — the runbook

Written 2026-08-25. The third of three documents, and the one with the commands in it:

- `test-guide.md` — **what** to judge, and why each check exists. Written for an operator with a
  fresh project.
- `group-11-staging.md` — **where the trial Hub already stands**, so each check is one action.
- **this file** — **exactly what to type**, against that state, in the order to type it.

Every command below was checked against the running instance on 2026-08-25. Routes, task
transitions and author attributions are read off the live Hub, not from memory.

---

## 0. Setup — five minutes, once

### 0.1 Confirm the Hub is up and on the fixed code

```bash
curl -s http://127.0.0.1:8010/health
```

Expect `{"status":"ok","runtime":"native"}`. The `runtime` field is new in this change, so its
presence is the proof you are on the right code, not just that something is listening.

If nothing answers, start it — **from `hub/`, not the repo root**, and **not** via
`agentweave --port 8010` (the installed console script's migrations lag this branch):

```bash
cd hub
DATABASE_URL="sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/profiles/beta/agentweave.db" \
  py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1
```

### 0.2 The two ways to drive it

**The UI** — open `http://127.0.0.1:8010`. Navigation is by query string, so you can jump straight
to a tab:

| Where | URL |
|---|---|
| Tasks | `http://127.0.0.1:8010/?project=proj-18e5d4e0&tab=tasks` |
| Jobs (the flow lives here) | `http://127.0.0.1:8010/?project=proj-18e5d4e0&tab=jobs` |
| Activity | `http://127.0.0.1:8010/?project=proj-18e5d4e0&tab=activity` |
| Overview | `http://127.0.0.1:8010/?project=proj-18e5d4e0&tab=overview` |

Note this is the **committed bundle** in `hub/hub/static/ui`, not your working copy of
`hub/ui/src`. If you have UI changes in flight, either rebuild (`cd hub/ui && npm run build && py
-3.11 scripts/refresh_ui_bundle.py`) or drive the Vite dev server instead:
`AW_DEV_HUB=http://127.0.0.1:8010 npm run dev`, then `http://localhost:5173/?project=…`.

**The API** — `scripts/drive/aw.py` already holds the URL and key. Every `py -3.11` snippet below
**must be run from `scripts/drive/`**, because `aw` is imported by path:

```bash
cd C:/Users/huida/Documents/projects/AgentWeave/scripts/drive
```

Stay there for the whole session. A `cd` elsewhere silently breaks the next call.

### 0.3 A shell that prints agent output correctly

```bash
export PYTHONIOENCODING=utf-8       # Git Bash
$env:PYTHONIOENCODING = 'utf-8'     # PowerShell
```

Without it, printing an agent's output dies on the first non-ASCII character.

### 0.4 Know what you are about to spend

`builder` and `critic` run `claude-haiku-4-5`; `relay` runs `gpt-5.4-mini`. A firing here is a
small fraction of the 3.5M-token first drive. Check as you go:

```bash
py -3.11 -c "from aw import api; print(api('GET','/projects/proj-18e5d4e0/accounting')[1]['project'])"
```

---

## 1. Do these three first — they cost nothing and need no firing

### 1.1 · Check 11.6 — is the spend visible?

```bash
py -3.11 -c "
import json
from aw import api
c,b = api('GET','/projects/proj-18e5d4e0/accounting')
print(json.dumps(b, indent=1)[:1400])
"
```

Also look at it in the UI: `?project=proj-18e5d4e0&tab=overview`.

**What you should see.** One call, project total plus a per-agent breakdown — 12,976,857 tokens
over 36 measured turns, ≈$2.71, split builder 9.56M / critic 3.28M / relay 137k. No reconstruction
from runs.

**Judge:** does that number arrive early enough to act on? This is the check that decides whether
you can leave a flow running unattended.

**One thing to weigh, not a bug.** `relay` reports tokens but `api_equivalent_usd_micros: null`.
The dollar figure comes from the CLI's own report — `total_cost_usd` for Claude,
`cost` for Codex (`runner_parsing.py:339,641`) — and the Codex CLI does not send one. So a
mixed-CLI flow tells you its tokens in full and its money only in part. Whether that is
honest-and-fine or a hole in "what did that cost" is your call, and worth settling before leaving
anything running overnight.

---

### 1.2 · Check 11.3b — is the reviewer looking at the work?

```bash
git -C C:/Users/huida/Documents/aw-stress worktree list
```

**What you should see:**

```
.../aw-stress/.agentweave/reviews/critic     f10d198 (detached HEAD)
```

Now confirm the author's change is actually in the reviewer's copy, and *not* in master:

```bash
git -C C:/Users/huida/Documents/aw-stress log --oneline -1 f10d198
git -C C:/Users/huida/Documents/aw-stress branch --contains f10d198
grep -n "not postings\|if not self.postings" \
  C:/Users/huida/Documents/aw-stress/.agentweave/reviews/critic/ledger/book.py
grep -n "not postings\|if not self.postings" \
  C:/Users/huida/Documents/aw-stress/ledger/book.py
```

The commit is on `agentweave/builder` with `reachable_from_main: false`. The reviewer's checkout
has builder's change; the main working tree does not.

**Judge:** open that directory and satisfy yourself the reviewer would be reading the work rather
than asking its author. The tasks table already marks this confirmed — this is seeing it once
yourself, and it is the check that would have caught F10.

---

### 1.3 · Check 11.2 — is the handover legible?

The handover to judge already happened: `builder` finished `task-23a0986e7fe9`, sent nobody
anything, and the next firing queued `critic` a review turn carrying that task.

```bash
py -3.11 -c "
import sqlite3
db=r'C:/Users/huida/.agentweave/hub/profiles/beta/agentweave.db'
cx=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
print('review handovers queued, and the messages that caused them:')
for r in cx.execute('''select id, agent, review_task_id, state, conversation_id
                       from inbound_queue_entries where review_task_id is not null'''):
    print(' ', r)
print()
print('any message at all sent while the flow was running (it fired 22:37 onward)?')
for r in cx.execute('''select timestamp, sender, recipient, subject, task_id from messages
                       where project_id='proj-18e5d4e0' and timestamp > '2026-08-24 22:00' '''):
    print(' ', r)
print('  (no rows = the handover involved no messaging at all)')
"
```

The entry to look at is `entry-bdbff2b6d33b` — agent `critic`, `review_task_id`
`task-23a0986e7fe9`, delivered into `conv-200965bb8a64`.

**No message caused it.** The project does hold 15 messages, but every one is from 10:00–11:25
that morning, from earlier messaging probes, and not one carries a `task_id`. The flow fired from
22:37 onward. `builder` finished the task, sent nobody anything, and the next firing routed it.

**Read the query from the database, not the API.** `GET /queue/{agent}` (note: `/queue/critic`, not
`/queue/entries` — the path segment is the agent name) lists the entries, but
`QueueEntryResponse` does not expose `review_task_id`, so the API cannot tell you which entry is a
review. That is worth a moment's thought on its own while you are judging legibility.

Now the actual check, which is a UI one:
`http://127.0.0.1:8010/?project=proj-18e5d4e0&tab=activity`, then the conversation list.

**Judge:** is it obvious from that list that a handover happened, and to whom?

**Something specific to look at.** The list holds **six** conversations all titled `Ledger flow` —
`conv-ad35f0971ebc`, `conv-3b2a74fde1d9`, `conv-c6935fbfd768`, `conv-d047f286c1a3`,
`conv-200965bb8a64`, `conv-9c8d2c8fbd80` — across three agents and two roles. Nothing in the title
distinguishes the review turn from the work turns. That is the concrete form of the 11.2 question.

**What will look wrong and is not.** The flow's history shows two `failed` rows at 2026-08-24
22:45. That was the Hub restart, not the flow: `run-144b3084c4d7` and `run-324e1c9fe1e4` both end
at `22:47:00.3`, the same second, because the process went down under them. Judge the handover, not
those rows.

---

## 2. Before any firing — clear F45, or decide to keep it

**Read this before you enable anything.**

`critic` already reviewed `task-23a0986e7fe9` and left it in `completed`, deferring the evidence
decision to you. `completed` is the only status the flow treats as reviewable, so the ladder picks
`critic` for it again — and the board already shows that decision:

```bash
py -3.11 -c "
from aw import api
c,b = api('GET','/projects/proj-18e5d4e0/jobs/job-bdea22bb0308')
print(b['loop']['current_tasks'])
"
```

`stop_when_queue_empties` cannot end it (the task never becomes terminal) and the project has no
token budget. Enabling the flow as it stands re-runs a finished review every five minutes forever.

### Option A — clear it (recommended, and it is a decision you owed anyway)

Three calls. Note `completed -> approved` is **not** a legal operator transition; the map goes
through `under_review`.

```bash
py -3.11 -c "
from aw import api
P='proj-18e5d4e0'; T='task-23a0986e7fe9'
print(api('POST', f'/projects/{P}/project/spec/evidence/ev-6e7f3bc72c24/decision',
          {'decision':'accepted','reason':'critic reviewed at f10d198 and found it correct'}))
print(api('PATCH', f'/projects/{P}/tasks/{T}', {'status':'under_review'}))
print(api('PATCH', f'/projects/{P}/tasks/{T}', {'status':'approved'}))
"
```

**Approving triggers a merge** of builder's commit into `aw-stress`'s `master`. That is the
intended behaviour and it is how the first drive ended, but it does modify that repository — so
know it is happening. Verify:

```bash
git -C C:/Users/huida/Documents/aw-stress log --oneline -3 master
```

Then re-read the board — `task-23a0986e7fe9` should be gone from `current_tasks`, leaving
`task-3cd54c17faa6` (author `critic`, reviewer `relay`) as the single staged handover.

### Option B — keep it as F45's reproduction

Do nothing, run **no** firing, and read the board output above as the finding's evidence. You lose
the two-reviewer version of 11.5; the last drive's three-agent firing already stands in for it.

---

## 3. Firing the flow **once**, without the cron running away

The job's cron is `*/5 * * * *`. `POST /jobs/{id}/run` refuses a disabled job, so you cannot fire a
disabled one directly. Park the cron somewhere far away first, then enable, fire, and disable:

```bash
py -3.11 -c "
from aw import api
P='proj-18e5d4e0'; J='job-bdea22bb0308'
print(api('PATCH', f'/projects/{P}/jobs/{J}', {'cron':'0 4 1 1 *','enabled':True}))
print(api('POST',  f'/projects/{P}/jobs/{J}/run'))
"
```

`0 4 1 1 *` is 04:00 on 1 January — enabled, schedulable, and not firing on its own today. Watch it:

```bash
py -3.11 -c "
from aw import api
c,b = api('GET','/projects/proj-18e5d4e0/jobs/job-bdea22bb0308')
print('firing_active:', b['loop']['firing_active'], '| stall:', b['loop']['stall_reason'])
for t in b['loop']['current_tasks']: print(' ', t)
for h in b['history'][:4]: print('  run', h['id'], h['status'], h['fired_at'])
"
```

**Always put it back when you are done:**

```bash
py -3.11 -c "
from aw import api
print(api('PATCH','/projects/proj-18e5d4e0/jobs/job-bdea22bb0308',
          {'enabled':False,'cron':'*/5 * * * *'}))
"
```

Stop a run mid-flight if you need to — the Runs view has a stop control, and `stopping -> stopped`
was verified clean in the last drive.

---

### 3.1 · Check 11.5 — is concurrent work comprehensible?

Fire once per §3, with the queue as staged:

| Task | Author | Commit | Reviewer the ladder picks |
|---|---|---|---|
| `task-23a0986e7fe9` Refuse an entry with no postings | `builder` | `f10d198` | `critic` |
| `task-3cd54c17faa6` Make Book.accounts() ordering stable | `critic` | `d8c4355` | `relay` |

Both resolve a real commit through `EvidenceFootprint`, so both review turns get their checkout
rather than refusing. One firing staffs both at once: two `JobRun` rows, two conversations, two
turns.

Watch it on the Jobs tab: `http://127.0.0.1:8010/?project=proj-18e5d4e0&tab=jobs`.

**Judge:** does the board say *what* is happening, or only that a lot is? Two lines of
"task — agent" is the artefact. (If you took Option A, this is a one-line board instead; the
last drive's three-agent firing is the wider version.)

**Correct and not a bug:** two rows for one tick. Each agent's turn succeeds or fails on its own,
and a single row could not say that one finished and one failed.

---

### 3.2 · Check 11.4 — does rung 3 read as staffing or as breakage?

You need finished work whose **author is the only agent left**. `task-23a0986e7fe9`'s author is
`builder` (confirmed from `task_transitions`, sequence 62), so archive the other two and the ladder
has nobody: the author is excluded, rung 2 comes back empty, rung 3 surfaces.

```bash
py -3.11 -c "
from aw import api
P='proj-18e5d4e0'
for a in ('critic','relay'): print(a, api('POST', f'/projects/{P}/agents/{a}/archive'))
"
```

Fire once per §3, then read the notice — on the Jobs tab, and in the raw board:

```bash
py -3.11 -c "
from aw import api
c,b = api('GET','/projects/proj-18e5d4e0/jobs/job-bdea22bb0308')
print('stall_reason:', b['loop']['stall_reason'])
print('current_tasks:', b['loop']['current_tasks'])
"
```

The last drive produced:

> could not staff this step: no agent is free to take it. Every agent on the roster is either
> running a turn, already holding active work, or is the one that completed this task.

**Judge:** does that read as *the flow needs somebody* or as *the flow failed*? It names all three
causes rather than only the one you can act on — that is the specific thing to have an opinion
about. If it reads as breakage, you will restart something that needed no restarting.

**Put the agents back:**

```bash
py -3.11 -c "
from aw import api
P='proj-18e5d4e0'
for a in ('critic','relay'): print(a, api('POST', f'/projects/{P}/agents/{a}/unarchive'))
"
```

**Also produce the quiet state**, which the guide asks for and which is the one most easily
mistaken for a stall: give the flow more ready tasks than agents and fire. Nothing should be
recorded at all — no rows, no notices, no growing history. A tick that does nothing should cost
nothing.

---

### 3.3 · Check 11.1 — is a one-agent flow indistinguishable from a loop?

The guide says lead with this one. It is placed last here for a practical reason: the current
state is a staged handover that cost 3.5M tokens to reach, and 11.1 requires dismantling exactly
what makes 11.2 and 11.5 readable. Do it after you have judged those, or do it first and accept
re-staging.

**Setup.** Archive `critic` and `relay` (as in §3.2). Give `builder` two independent pending tasks
and **no finished work waiting** — a flow reviews before it starts new work, by design, so leaving
completed work in the queue means you will be judging the wrong thing. Three unclaimed tasks are
already in the project:

```bash
py -3.11 -c "
from aw import api
P='proj-18e5d4e0'
for t in ('task-3292072f63c3','task-bb86d53a94d5'):
    print(api('PATCH', f'/projects/{P}/tasks/{t}', {'loop_id':'loop-e4b864459808'}))
"
```

(`Task.loop_id` is write-once — if these already carry a different loop, create two fresh tasks
instead with `POST /projects/{P}/tasks`.)

Then fire two or three times per §3, and confirm everything reads as it did before this change:
one task claimed per firing, one run per firing in the job's history, one current item on the card,
one agent's name, and consecutive firings collapsed into a single conversation row.

**Judge:** if any of that reads differently, D2 has leaked — the default agent has stopped being a
default and become something else.

Un-archive both agents afterwards.

---

## 4. Check 11.3 — do not run it

**It cannot pass, and that is finding F43, not your judgement.**

You can confirm the diagnosis in one call rather than taking my word:

```bash
py -3.11 -c "
import sqlite3
db=r'C:/Users/huida/.agentweave/hub/profiles/beta/agentweave.db'
cx=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
q=lambda s: cx.execute(s).fetchone()[0]
print('notes submitted      :', q('select count(*) from checkpoint_notes'))
print('notes never consumed :', q('select count(*) from checkpoint_notes where consumed_by_checkpoint_id is null'))
print('checkpoints          :', q('select count(*) from checkpoints'))
print('carrying a loop_id   :', q('select count(*) from checkpoints where loop_id is not null'))
"
```

Expect `3 / 3 / 6 / 0`. Every agent complied with the instruction; nothing consumed a single note;
`## Prior checkpoint` has never rendered in any briefing.

And read the note that cannot be delivered:

```bash
py -3.11 -c "
import sqlite3
db=r'C:/Users/huida/.agentweave/hub/profiles/beta/agentweave.db'
cx=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
for r in cx.execute('select agent,intent from checkpoint_notes'):
    print('---', r[0]); print(r[1][:400])
"
```

**The check inverts.** 11.3 asks whether the implementer's checkpoint reads as notes-to-self.
`note-e8cf4afcb4b1` names the task, the file, the line and the finding, for a reader who is not its
author — **task 6.5 worked.** Delivery is what fails.

### Read both halves of what the reviewer was actually given

A reviewer is briefed through **two** channels, and reading only one will mislead you.

**Channel 1 — the queue entry** (`entry-bdbff2b6d33b`, printed by the snippet in §3.3 above). This
is the loop briefing plus the job's own message, and on its own it reads like an *implementation*
instruction: "## Current task: Refuse an entry with no postings … change the code, add one test …
move the task to completed." It contains no `## Prior checkpoint` section — that absence is F43.

**Channel 2 — the canonical context file**, written into the reviewer's checkout at turn start:

```bash
sed -n '1,20p' \
  C:/Users/huida/Documents/aw-stress/.agentweave/reviews/critic/.agentweave/context/critic.md
```

That one is unambiguous:

> - **This is a review turn. You are reviewing someone else's work, not doing your own.**
> - Under review: task `task-23a0986e7fe9` — Refuse an entry with no postings, at commit
>   `f10d198…` from branch `agentweave/builder`.
> - Do not fix what you find. Report it. The author makes the change, through `revision_needed` —
>   a reviewer that edits the work has reviewed its own work.
> - Your own working checkout is outside this turn's boundary.

So the reviewer **is** told it is reviewing. Nothing is broken here.

**What is worth your judgement** is that the two channels pull in opposite directions — one says
implement and complete, the other says review and do not edit — and the agent reconciles them
unaided. That is a legibility question of exactly the kind 11.3 exists to raise, and it is yours to
call rather than a defect to file. If you decide it reads badly, that is a finding worth recording;
if you decide the context file is authoritative enough, say so and move on.

**If you want to see the delivered version anyway**, there is a manual path, and it is worth one
run because it is also the closest thing to a proposed fix:

```bash
# 1. give the project a checkpoint runner (it has none, so the button 409s today)
py -3.11 -c "
from aw import api
print(api('PUT','/projects/proj-18e5d4e0/settings', {'checkpoint_runner_id':'runner-a30ddea6'}))
"
# 2. generate builder's checkpoint by hand, from the conversation that holds the note
py -3.11 -c "
from aw import api
print(api('POST','/projects/proj-18e5d4e0/conversations/conv-ad35f0971ebc/checkpoint'))
"
# 3. confirm it consumed the note and got stamped with the loop
py -3.11 -c "
import sqlite3
db=r'C:/Users/huida/.agentweave/hub/profiles/beta/agentweave.db'
cx=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
print(cx.execute('select id,loop_id from checkpoints order by created_at desc limit 1').fetchone())
print(cx.execute('select id,consumed_by_checkpoint_id from checkpoint_notes').fetchall())
"
```

That is a real model call (~19s). If step 3 shows a `loop_id` and a consumed note, the whole
downstream chain works and F43 really is only a missing trigger.

**Then fire once** and read the reviewer's briefing for a `## Prior checkpoint` section:

```bash
py -3.11 -c "
from aw import api
c,b = api('GET','/projects/proj-18e5d4e0/queue/critic')
for e in b:
    if e['content'].startswith('# Loop briefing'):
        print('===', e['id'], e['state']); print(e['content'][:1600]); print()
"
```

**Watch for F44 while you do it.** The briefing selects the loop's *newest* checkpoint, not the
*author's*. With one checkpoint that is the same row. Generate a second from a different agent's
conversation (`conv-c6935fbfd768` is relay's) and the reviewer of builder's task will be briefed
with relay's account of unrelated work — while being told it is what a reviewer will need.

---

## 5. When you are done

```bash
py -3.11 -c "
from aw import api
P='proj-18e5d4e0'
print(api('PATCH', f'/projects/{P}/jobs/job-bdea22bb0308', {'enabled':False,'cron':'*/5 * * * *'}))
for a in ('critic','relay'): print(a, api('POST', f'/projects/{P}/agents/{a}/unarchive'))
print(api('GET', f'/projects/{P}/accounting')[1]['project'])
"
```

Leave the flow **disabled**. Nothing should keep spending between sessions — and while F45 stands,
an enabled flow spends on a conclusion it has already reached.

## 6. Recording what you decide

Ticking a box in `tasks.md` is the output for 11.1, 11.2, 11.3b, 11.4, 11.5 and 11.6. For anything
that reads wrong, append to `scripts/drive/FINDINGS.md` in the same shape as F43–F45 — what you
did, what you expected, what happened, and the row or route that proves it. 11.3 stays unticked
until F43 and F44 are decided.
