# Operator UX findings — spec screen, task board, ticket generation

**2026-08-16, from the operator reviewing `aw-loop10`'s spec document and task board in the UI.**

These came from the first time a person looked at the spec surfaces with real content in them. None
of it was findable by the loop: every item is either a visual judgement or a question about whether
the output is *usable*, which is exactly the class `2026-08-15-nothing-asks-whether-the-artefact-is-usable`
was written about.

Verdict on `17.2` / `5.2` / `6.1` ("is the rendered document as readable as the skill-written ones?"):
**readable, but uglier.** Not ticked — the items below are what "uglier" means concretely.

---

## 1. The rendered document is too "texty" — colour carries no meaning

**Operator, verbatim:** *"It's readable but I think it's uglier. The other one was more colorful.
What you needed to look at popped with color. this one is much too 'texty'."*

The skill-written documents used colour to make the thing you needed to find findable. The
renderer's output is uniform prose, so scanning it means reading it. Requirement identifiers,
MUST/SHOULD modals, phase badges and the acceptance table are all candidates for carrying visual
weight.

**Where:** `hub/hub/spec_render.py`.

## 2. The document background is navy blue and ignores the app theme

**Operator, verbatim:** *"Also the background is navy blue. I want it to match the background of the
agentweave (light or dark mode)."*

The rendered document does not participate in AgentWeave's theming, so it sits in the UI as a
foreign object. It should take the app's light/dark background like every other surface.

**Where:** `hub/hub/spec_render.py` (the document's own CSS) and whatever embeds it in the Spec view.
Note the constraint from `2026-08-12-hub-owns-the-spec-document` 16.12: the rendered document must
carry **no external resource reference**, so this has to be done with inherited CSS variables rather
than a stylesheet link.

## 3. Coverage labels are misleading — the counts are right, the words are wrong

**Operator, verbatim:** *"on the spec screen is showing 4 in progress and 5 verified but I don't
think that's true right?"*

**The counts are correct.** Verified against `GET /project/spec/coverage` for `proj-ff695d96`:
9 requirements, `{'verified': 5, 'in_progress': 4}`, `{'integrated': 5, 'not_applicable': 4}`. That
maps exactly onto the verifier's decisions — it accepted 5 evidence rows and rejected 4.

**But the labels are wrong**, and the operator's disbelief is the finding:

| shown | actual situation |
|---|---|
| `in_progress` | evidence was recorded and **rejected**. Nothing is in progress; a claim was refused. |
| `not_applicable` (integration) | reads as "doesn't apply", means "never got merged because its evidence was rejected". |

A rejected requirement is indistinguishable on this screen from one somebody is actively working on.
**This is the answer to open task `a-requirement-knows-its-work` 8.1, "Is the coverage state
legible?" — no.** Suggest a distinct state (`rejected` / `evidence_refused`) rather than folding it
into `in_progress`.

## 4. The task board does not show which part of the spec a task serves

**Operator, verbatim:** *"it's hard to understand on the task board to which parts of the spec that
relates too and the navigation between the two is hard."*

The data exists and the API already returns it — `GET /tasks/{id}` carries `requirement_ids`,
`requirement_links`, `unresolved_requirements` and `spec_document_id`, and `task_requirement_links`
is populated (19 rows for this project). The `tasks.requirements` **column** is `null`, which is a
red herring; the links live in their own table.

So this is a **UI gap, not a data gap**: the board renders none of it. Two directions —
show `FR-n` chips on the card, and make them navigate to the anchor in the document
(`spec_requirements.anchor` is already `#FR-n`). Navigation back from a requirement to its tasks is
the same problem in reverse; `coverage` already returns `linked_task_ids`.

## 5. Task cards are unreadable when expanded — open them properly

**Operator, verbatim:** *"the task is tough to check. If has a lot of text but expanding looks to
narrow. Maybe we should be able to open the task like jira."*

A full-height detail view (or modal/drawer) rather than in-card expansion. This is where §4's
requirement chips, the acceptance criteria and the evidence rows would actually fit.

## 6. Generated tickets are far too coarse — measured, not guessed

**Operator, verbatim:** *"are the tasks too condensed? Can you validate that is not too much things
to do per ticket? How does the ticket generation works?"*

**Validated: yes, too coarse.** From `task_requirement_links` in `proj-ff695d96`:

| ticket | requirements | description |
|---|---|---|
| Deadline-based admission decision (`task-1f82d976`, approved) | **6 of 9** — FR-1,2,3,4,7,9 | 311 chars / 42 words |
| Deferred-notification digest delivery (`task-0d3c8cb5`, approved) | 2 — FR-5, FR-8 | 216 chars / 33 words |
| Verify no notification is ever silently lost (`task-553c2c37`, completed) | 1 — FR-6 | 256 chars / 37 words |
| *(earlier batch, both rejected)* `task-aa8a3f3b` | 5 — FR-1,2,3,4,9 | 463 chars / 64 words |
| *(earlier batch)* `task-8b82e372` | 4 — FR-5,6,7,8 | 436 chars / 61 words |

**One ticket carries two-thirds of the specification on 42 words of description.** Nine
requirements became three live tickets.

**This has a demonstrated cost, not just an aesthetic one.** `task-1f82d976` links FR-9, whose
evidence the verifier **rejected** — and the task was still approved and merged, because the
approval gate does not block below `gate` rigor and gave no signal. A finer-grained ticket would
have isolated FR-9 and made the rejection visible as a blocked ticket instead of an invisible
caveat inside an approved one. This is the concrete argument for the "approve gives no signal about
rejected evidence" fix already made, and for splitting tickets.

**How generation works** (for the record): `hub/hub/spec_tasks.py` derives tickets from the
document's `tasks` array — i.e. **the authoring agent decides the granularity**, and the Hub mints
what it is given. So "too coarse" is a prompt/charter problem as much as a code one: nothing
enforces a ceiling on requirements-per-ticket. Options are guidance in the Spec Author charter, a
validator warning above N requirements per task, or splitting at mint time.

---

## Deferred — the operator wants to judge these first-hand

Not answered, deliberately, and **not to be answered by a loop**:

- **`17.1` — does the authoring flow feel like authoring?** *"Skip this one. I did not interact with
  it at all. I'll try by my self tomorrow probably then I'll give my honest opinions."*
- **`17.3` — does the interview feel like the old skill's interview?** *"Can't attest to that. Will
  try this later."*

Both need the operator driving the composer themselves, not an API-driven reconstruction. Leave
open.

## Answered

- **`9.1` — is the placeholder pleasant?** **Yes, keep it.** `ivory-salamander` / "Untitled
  exploration", visible 71 seconds. Ticked.
