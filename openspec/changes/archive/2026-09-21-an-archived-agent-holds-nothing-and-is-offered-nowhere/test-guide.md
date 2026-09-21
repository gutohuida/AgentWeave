# Test guide — an archived agent holds nothing and is offered nowhere

Written by **R1, 2026-09-20**, alongside `tasks.md`. Split the way this repo requires: what an
agent can verify on its own, and what only the operator can judge. Nothing here is a plan for
ticking a task — a task closes on a test that fails with its mutation applied, not on this guide.

## Agent-verifiable (run by IMPL and by the drive)

| # | check | how |
|---|---|---|
| A1 | Archiving clears `charter_id` and leaves `runner_id` alone | Tasks 1.3, and the row read directly after `POST /agents/{name}/archive` |
| A2 | F185's own reproduction now ends in `204` | Task 1.4 — charter → agent bound → archive → `GET /agents` omits it → `DELETE /charters/{id}` |
| A3 | The fix cannot be undone through the API | Tasks 1.6–1.8 — `PATCH` with a `charter_id` on an archived agent is refused; `charter_id: null` still succeeds; an open agent is unaffected |
| A4 | The **API** states what was released and states nothing false (R2: no screen renders it — `design.md` D9) | Task 2.3 — archive names the charter; unarchive returns `charter_id: null` with the standing sentence; an agent that never had one gets the same sentence and no claim about its history |
| A5 | Agents archived before this change are repaired, and open agents are not touched | Task 3.5 — seed at `0104`, upgrade to `0105`, assert both directions |
| A6 | An archived agent is absent from the default launchability report, present when asked for | Task 4.3, including the name that arrives only from session config |
| A7 | The probe and the trigger agree | Task 4.4 — for **every** agent the default probe reports `runnable: true`, `POST /agent/trigger` does not refuse it as archived. This is the assertion F181 violates; a single hand-picked agent does not count |
| A8 | The runner refusal names an archived holder as archived, and leaves the open-holder sentence unchanged | Task 5.2's three cases |
| A9 | Nothing that held stopped holding | `pytest hub/tests/ -v` green under `py -3.11`; specifically the existing charter-bound-delete refusal for an **open** holder, and the roster's own lifecycle filter |
| A10 | No UI bundle is involved, and nothing has begun reading the two responses | `grep -rn "useAgentLaunchability" hub/ui/src` still returns only the definition; `useArchiveAgent`’s `onSuccess` still takes no argument (`hub/ui/src/api/agents.ts`), so neither response is rendered; `git status` shows nothing under `hub/ui/src` or `hub/hub/static/ui` |

The drive (task 6.3) runs against a throwaway Hub from source, on a port that is not `8000` or
`8010`, against a fresh profile directory. Any real agent turn binds `claude-haiku-4-5-20251001`.
Nothing is archived on a real project.

## Human-only (for the operator, on their own Hub after a restart)

These need judgement, not an assertion.

1. **Is losing the charter on archive what you expect?** Bind a charter to an agent you do not
   need, archive it, then unarchive it. *Expect:* after unarchiving, the agent's Charter section
   reads "No charter" — **and the app tells you nothing about why**, because nothing renders the
   archive or unarchive response (R2, `design.md` D9). That silence is the honest expectation, not
   an oversight in this guide. *Judge:* is losing the binding the right trade for being able to
   delete the charter — or would you rather the binding came back and the charter route filtered
   archived holders instead? The second option is written up as the rejected alternative in
   `design.md` D1, with what it costs.

2. **Does the unarchive sentence read as true for an agent that never had a charter?** **R2: you
   cannot do this one from the app** — the sentence exists only in the API response, which
   `useArchiveAgent` discards. Read it here instead, or call `POST /agents/{name}/unarchive`
   directly on a throwaway Hub. The sentence, as revised by R2:

   > *"No charter is bound. Archiving releases an agent's charter and unarchiving does not restore
   > it. An agent with no charter still runs — bind one only if this agent should have one."*

   *Judge:* read it as an agent that **never** had a charter. Does it read as a statement of the
   rule and of the agent's current state, or as a claim that **this** agent's charter was taken
   away? Does the last clause read as permission or as an instruction? If it reads as either a
   claim about history or an instruction to bind one, D2 needs redoing. (R1's wording ended *"so
   bind one before this agent's next turn"* and failed the second test — it implied a charter was
   required, which `design.md` D8 measured to be false.)

3. **The migration touches your live data.** Restarting `:8000` after this ships clears
   `charter_id` on every agent you have already archived, and the downgrade cannot put it back.
   *Before approving:* look at what that is, on your own database, read-only:
   `SELECT name, charter_id FROM agents WHERE lifecycle = 'archived' AND charter_id IS NOT NULL;`
   opened through a `mode=ro` URI. *Judge:* is that list one you are content to lose the bindings
   from?

4. **The one open decision, widened by R2 (`design.md` D7 and D9).** Bind a charter to an
   archived agent from its settings page after this ships. *Expect:* the picker is still enabled,
   the save fails, and it says only *"Could not update charter binding."* — the server's actual
   sentence is dropped by the client, which is the F187 shape. R2 found a second half of the same
   wall: nothing renders the archive or unarchive response either, so everything this change adds
   to those two routes is invisible in the app.

   *Decide, as one decision:* does this change accept a `hub/ui/src` bundle refresh — which reaches
   your live `:8000` app — in order to (a) disable the picker for an archived agent and render the
   server's detail, and (b) render what archive and unarchive now say? Or does it ship API-only,
   with both halves filed as their own findings? The change is complete and shippable either way.

5. **Does anything you use go quiet?** The launchability report loses archived agents by default.
   Nothing in the app reads it today (A10), so the expected answer is *nothing changes on screen*.
   *Judge:* if something did change, that is a reader nobody knew about and it outranks this whole
   change.
