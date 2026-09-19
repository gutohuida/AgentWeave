# Requests — what the operator asked for

**The operator's own channel into the backlog.** `FINDINGS.md` is a defect ledger: every row there
is something the product does wrong, found by driving it or reading it. A request is different — it
is work nobody has established is broken, wanted because the operator wants it. Filing one as a
finding forces it to pretend to be a defect, and filing a defect here hides it from the night
window's severity queue. So they are separate files, and `BACKLOG.html` merges them into one page.

Read by `scripts/backlog_page.py`. Add a request by appending a section; nothing else is required.

## Format

```
## R<n> — <one line, in your words>
**Asked:** YYYY-MM-DD
**Theme:** <one of the themes below, or anything — unknown themes get their own group>
**Ready:** proposed | ready | thinking
**Finding:** F<n>              (optional)

Whatever you want to say. Prose, a sketch, a half-formed idea. This file has no
standard to meet.
```

**`Finding:` is what stops double-counting.** When a request names a finding, the page does not add
a second row for it — it marks that finding as **operator-sourced** and shows your words alongside
it. Use it whenever an ask has already been measured into a finding. Leave it off and the request
stands as its own backlog row.

**`Ready:`** — `thinking` means it is not ready for anyone to work (the default, and no criticism);
`ready` means it is well enough understood for a spec loop to take it; `proposed` means a change
directory already exists.

**Themes** currently in use: Flows & loops · Task ledger · Spec & requirements · Evidence ·
Agents & runners · Messaging & queue · Workspace & permissions · Git & worktrees ·
Operator surfaces · Runs & turns · Harness & CI · Hub plumbing. A theme not on that list is fine —
it becomes its own group on the page.

---

## R1 — A button on the spec that starts the flow for it
**Asked:** 2026-09-17
**Theme:** Flows & loops
**Ready:** ready
**Finding:** F377

"It would probably be good if I had a button that I could create a flow on the spec. It creates a
flow from that spec. I have nothing that I can do easily."

From an approved document, the only way to start a flow today is to ask an agent to call
`create_flow` — which is the call that was refused in F376 and lost the LoopEngine_2 night.

---

## R2 — The settings that actually matter, on the project page
**Asked:** 2026-09-17
**Theme:** Operator surfaces
**Ready:** ready
**Finding:** F379

"We need to add the most useful options on the control page of the project and some of the agent
settings as well. For example an agent accepting evidence etc. We need to make a list of those
things to make it more apparent to the user. They are core functionalities buried in the settings."

The list is the `Buried Controls` page (published 2026-09-17) and F379's own table.

---

## R3 — A backlog page I can actually work with
**Asked:** 2026-09-18
**Theme:** Operator surfaces
**Ready:** proposed

"Make that file interactable. Also point out the source of each thing on the backlog — things found
on the run, new ideas and improvements requested by me, also the status if they're ready or not, and
try and group them by theme."

Shipped in the same sitting: filters, search, theme grouping, source and readiness on every row.
Kept here because it is the reason this file exists, and because the next person to wonder why
`REQUESTS.md` is separate from `FINDINGS.md` should find the answer attached to a request.


## R4 — A button that resets the Hub to a clean slate
**Asked:** 2026-09-19
**Theme:** Operator surfaces
**Ready:** thinking

"A button to restart the hub from scratch clears the database and restart everything from the hub."

Filed as an idea to develop later, not as work ready to take. The operator's own framing is one
button doing two things — wipe the database and restart the process — from inside the Hub itself,
so the current alternative (stop the app, delete or move
`~/.agentweave/hub/data/agentweave.db`, start it again from a terminal) stops being the only path.

Not yet argued, and each of these changes what the button is:

- **What "from scratch" includes.** The database only, or also `.agentweave/project.json` in every
  registered working directory, the API keys, the instance identity, the worktrees? A reset that
  leaves project registrations pointing at a database that no longer has those rows is a worse
  state than either end.
- **Restarting the process from inside itself.** The Hub is a windowed desktop app
  (`src/agentweave/cli.py`, pywebview); the server it would be restarting is the one serving the
  page the button is on. Whether that is a true restart, a re-exec, or the app closing itself and
  relying on the operator to reopen it, is the substance of the change.
- **What stops an accident.** This destroys the operator's whole corpus with one click, and the
  same motion is one row away from things that must never be reachable that way.

Related: `.claude/reference/hubs.md` documents the manual profile-swap procedure this would
replace for trial use; `F385` is the other half of the same session's observation that the app's
own state does not survive a close and reopen.
