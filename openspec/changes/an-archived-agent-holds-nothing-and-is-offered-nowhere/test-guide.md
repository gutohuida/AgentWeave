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
| A4 | The operator is told what was released, and not told a falsehood | Task 2.3 — archive names the charter; unarchive returns `charter_id: null` with the standing sentence; an agent that never had one gets the same sentence and no claim about its history |
| A5 | Agents archived before this change are repaired, and open agents are not touched | Task 3.5 — seed at `0104`, upgrade to `0105`, assert both directions |
| A6 | An archived agent is absent from the default launchability report, present when asked for | Task 4.3, including the name that arrives only from session config |
| A7 | The probe and the trigger agree | Task 4.4 — for **every** agent the default probe reports `runnable: true`, `POST /agent/trigger` does not refuse it as archived. This is the assertion F181 violates; a single hand-picked agent does not count |
| A8 | The runner refusal names an archived holder as archived, and leaves the open-holder sentence unchanged | Task 5.2's three cases |
| A9 | Nothing that held stopped holding | `pytest hub/tests/ -v` green under `py -3.11`; specifically the existing charter-bound-delete refusal for an **open** holder, and the roster's own lifecycle filter |
| A10 | No UI bundle is involved | `grep -rn "useAgentLaunchability" hub/ui/src` still returns only the definition; `git status` shows nothing under `hub/ui/src` or `hub/hub/static/ui` |

The drive (task 6.3) runs against a throwaway Hub from source, on a port that is not `8000` or
`8010`, against a fresh profile directory. Any real agent turn binds `claude-haiku-4-5-20251001`.
Nothing is archived on a real project.

## Human-only (for the operator, on their own Hub after a restart)

These need judgement, not an assertion.

1. **Is losing the charter on archive what you expect?** Bind a charter to an agent you do not
   need, archive it, then unarchive it. *Expect:* the archive response names the charter it
   released; after unarchiving, the agent's Charter section reads "No charter". *Judge:* is that
   the right trade for being able to delete the charter — or would you rather the binding came
   back and the charter route filtered archived holders instead? The second option is written up
   as the rejected alternative in `design.md` D1, with what it costs.

2. **Does the unarchive sentence read as true for an agent that never had a charter?** Unarchive an
   agent you archived without ever binding one. *Expect:* *"No charter is bound. Archiving releases
   an agent's charter, so bind one before this agent's next turn."* *Judge:* does that read as a
   statement of the rule, or as a claim that **this** agent's charter was taken away? If the
   latter, it is wrong and D2 needs redoing.

3. **The migration touches your live data.** Restarting `:8000` after this ships clears
   `charter_id` on every agent you have already archived, and the downgrade cannot put it back.
   *Before approving:* look at what that is, on your own database, read-only:
   `SELECT name, charter_id FROM agents WHERE lifecycle = 'archived' AND charter_id IS NOT NULL;`
   opened through a `mode=ro` URI. *Judge:* is that list one you are content to lose the bindings
   from?

4. **The one open decision (`design.md` D7).** Bind a charter to an archived agent from its
   settings page after this ships. *Expect:* the picker is still enabled, the save fails, and it
   says only *"Could not update charter binding."* — the server's actual sentence is dropped by the
   client, which is the F187 shape. *Decide:* fold the UI half into this change (disable the
   control for an archived agent, render the server detail) and accept a bundle refresh reaching
   your live app — or ship the backend refusal alone and let the picker be filed as its own
   finding.

5. **Does anything you use go quiet?** The launchability report loses archived agents by default.
   Nothing in the app reads it today (A10), so the expected answer is *nothing changes on screen*.
   *Judge:* if something did change, that is a reader nobody knew about and it outranks this whole
   change.
