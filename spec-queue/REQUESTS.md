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


## R5 — A manager agent the Hub runs behind the scenes
**Asked:** 2026-09-19
**Theme:** Agents & runners
**Ready:** thinking

"Just as we have the adhoc run of an agent to change the name of a thread we could have an agent
that is executed adhoc making all sorts of decisions for the project behind the scene. It has
special permission being able to see everything in the project but it's only invoked by the hub,
never by the user. It does all sorts of things in the project for example: Deciding which message
should hit the user first and changing the order."

**Annotated deliberately, not specced.** The operator's framing is that they want it *touching
everything*, which is the opposite of the self-contained slice the trial takes one at a time. This
row exists so the idea is revisitable, not so a window picks it up. Do not open a change directory
for this without the operator saying so.

**The precedent already exists and is the right one to read first.**
`hub/hub/conversation_titles.py` is a Hub-invoked, one-shot, never-user-invoked agent spawn, and
its module docstring has already settled two constraints a manager would inherit:

- **It records no `Run` row, deliberately.** `turn_scheduler.schedule_agent` and
  `trigger_agent_directly` both gate on `Run.project_id == p, Run.agent == a, Run.status ==
  "running"`, so a background spawn under an agent's own name makes that agent look busy and
  stalls its queue. The titler is recorded as an event instead.
- **"Truncation is the floor."** A conversation is named the moment its first message lands, so
  the model-generated title is an upgrade on a deterministic result that is already correct.
  Everything in that module failing changes nothing structural — which is precisely what lets it
  be best-effort.

**That second rule is the one that matters most for the ordering example.** A model deciding what
the operator sees first is nondeterministic, and its failure mode is burying something urgent —
which is the defect it would be built to fix (`F387`). So the deterministic rule stays the floor
(blocking first, then newest) and the manager is an upgrade on top of it. A manager that *is* the
ordering, rather than an improvement to it, can fail into exactly the state it exists to prevent.

**Open, and each changes what this is:** what else "all sorts of decisions" covers, and whether
those are advisory (it reorders, annotates, suggests) or authoritative (it closes, assigns,
answers); what it costs per firing and what triggers one, given the flow already spends 58% of its
turns on coordination (`openspec/explorations/2026-09-16-the-flow-costs-more-than-the-work.md`);
what "sees everything in the project" means against the workspace and permission boundaries; and
how the operator inspects or overrides a decision it made, since a background agent whose
reasoning is invisible is the hardest kind to trust.

**Related:** `F387` (the ordering defect that prompted the example), `R4`.

## R6 — A knowledge vault: everything known about a project, indexed, and fetched rather than read
**Asked:** 2026-09-20
**Theme:** Spec & requirements
**Ready:** thinking

"Create a new session for the project where agentweave acts called knowledge vault. That is going to
be all the documents with knowledge about the project. Transcripts from meetings, pdfs, excel files,
anything that gives context and knowledge from the project. The manager AI will also create md files
to distil that information and also a guide to navigate the files with briefing of each information
and where it exists. The files won't be accessed directly so the agent doesn't burn tokens just
reading the entire repo — it will have free access to the index from the files and will request the
knowledge from a mcp server (or some mechanism) that then will give it either access to the files or
give it directly the files."

**Four separable pieces, and they have very different costs.** Written out because the request reads
as one feature and is at least four, and three of them have a verified blocker or precedent in this
repository today (checked 2026-09-20, not recalled):

1. **Ingestion — genuinely new surface.** `grep -rn "UploadFile\|multipart" hub/hub/api/` returns
   **nothing**: the Hub has no file upload anywhere, and no attachment, asset or blob model
   (`db/models.py`'s document-ish classes are `ProjectInstructions`, `CheckpointNote`,
   `SpecDocument`, `SpecDocumentMerge`, `SpecDocumentEvent` — all text or metadata). PDFs, Excel and
   transcripts have no way into the product at all today. This is the largest piece and the one with
   no precedent to copy.
2. **Distillation — this is R5 wearing a different hat.** "The manager AI will create md files to
   distil that information" is a Hub-invoked, never-user-invoked agent, which is exactly R5, and
   R5's row already carries the two constraints such a thing inherits from
   `hub/hub/conversation_titles.py` (record no `Run` row; truncation is the floor). **Whatever is
   decided for R5 decides this.** Do not design them apart.
3. **The index in every turn — the slot already exists.** `_render_hub_agent_context`
   (`hub/hub/api/v1/agents.py:1495`) renders `## Project Instructions` into every turn's canonical
   context; `openspec/explorations/2026-09-14-project-notes-inside-the-product.md` already argues for
   a second, agent-writable section beside it, from the LoopEngine observation that four agents kept
   their shared knowledge in the harness's own memory directory where the operator could never see
   it — **including one note that was simply wrong about the guard, which nobody who could correct it
   could read.** The vault's "guide to navigate the files" is that brief, generalised. Read that
   exploration before designing this.
4. **Retrieval by request rather than by reading — and F354 is the live constraint.** The mechanism
   the request describes is an MCP tool. Every agent turn spawns its tool server **fresh from this
   working tree** (`agent_trigger.py` ~L1086), which is F354 (B): an uncommitted edit to
   `hub/hub/mcp_server.py` reaches the operator's live `:8000` agents mid-edit, with no restart in
   between. Adding a vault tool means touching the one file with that property. F354 is worth fixing
   *before* this, not after.

**The token argument is the strongest part of the request and is already measured.**
`openspec/explorations/2026-09-16-the-flow-costs-more-than-the-work.md` found the flow spends 58% of
its turns on coordination; "don't burn tokens reading the whole repo" is the same economics one
layer down. An index-plus-fetch shape is the right instinct.

**Not argued, and each changes what this is:** whether the vault is project-scoped storage the Hub
owns or a pointer into the operator's own filesystem (the second is far cheaper and loses the
"anything that gives context" ambition); whether distillation is one-shot at ingestion or continuous;
what happens when the distilled md and the source document disagree; whether the index is rendered
into every turn (a fixed context cost on every run, forever) or fetched like everything else; and who
may write to the vault — the manager only, or any agent, which is the question
`project-notes-inside-the-product` answers with "any agent, and the operator can correct it".

**Related:** `R5` (the manager agent — same agent, decide together), `R4`,
`openspec/explorations/2026-09-14-project-notes-inside-the-product.md`,
`openspec/explorations/2026-08-16-a-corpus-at-scale.md`, `F354` (the MCP tool-surface blocker).
