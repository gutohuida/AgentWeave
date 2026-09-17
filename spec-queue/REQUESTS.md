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
