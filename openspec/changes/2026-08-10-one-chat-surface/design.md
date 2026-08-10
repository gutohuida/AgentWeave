# Design — One chat surface

## Decision 1 — Reuse the agent's conversation; produce no `origin="spec"`

**Chosen:** the Spec pane shows the selected agent's conversation. `conversationId` starts `null`
and the first message creates one, exactly as `NewConversationSurface` does — *"a conversation is
created by its first message… Nothing is written to the Hub here."*

**Rejected: a spec-scoped conversation now.** `Conversation.origin` accepts `spec` and nothing
produces it — the only writers are `peer` (`agents.py:1147`, `messages.py:185`), `operator`
(`agent_trigger.py:598`), and `handoff` (`checkpoint_cutover.py:94`). Producing it here would mean
choosing its scope — per document? per change? — before B2 defines what a change is.

Worse, the exploration of 2026-08-10 concluded that **phase belongs to the document, not the
thread**, which makes the interesting relationship *which document a thread is bound to* — a link,
not an enum value. Writing `origin="spec"` rows now risks creating data on the wrong axis that B5
must migrate. Leaving the field unproduced is the honest state: spec-scoped conversations do not
exist yet.

**Cost, accepted:** the Spec page and the agent page show the same thread for the same agent. Under
the document-owns-phase model that is correct, not a compromise — there is no separate spec identity
for the thread to belong to.

## Decision 2 — Conversation history replaces the output tail

`SpecChatPane` renders `useAgentOutput(agentName)`, the raw agent output stream. `Composer` pairs
with a conversation. Keeping the tail would show a transcript that does not correspond to what the
composer is writing into.

Both surfaces already share `SharedStreamRenderer`, so this changes the data source, not the
rendering.

## Decision 3 — The open document goes into the turn context, not into the message

The agent is told which document the operator is viewing. Two ways:

**Chosen:** a line in the canonical context, through the existing per-turn materialisation at
`agent_trigger.py:352` (`.agentweave/context/<agent>.md`). It is rebuilt every turn, so the value
tracks navigation without the operator resending anything, and it reaches Claude and Codex
identically because both consume that file.

**Rejected: prefixing the operator's message.** It would put UI state into the durable message
record, so the transcript would read as though the operator typed it, and re-reading an old
conversation would show a document reference that was never said.

## Decision 4 — Remove the repair button rather than reimplement it here

`SpecPage.buildRepairMessage` composes `"Run aw-spec-reindex to repair spec/index.json"` and sends
it to *"an idle agent named `spec` first, else the selected chat agent"* — instructing a skill
nothing installs, at an agent identified by a hardcoded name convention.

Three options were weighed:

| | Outcome |
|---|---|
| Leave it | Knowingly ships a button that instructs an absent tool |
| Reimplement deterministically here | Right *eventually* — `aw-spec-reindex`'s own spec describes deterministic mechanical repair, which is an algorithm, not a judgement. But it would mean writing a manifest repairer before B2 defines the manifest format and parser it repairs against |
| **Remove it** ✅ | The drift it responds to cannot occur while nothing produces documents. Restored in B2 as code |

Recorded so B2 does not lose it: **`aw-spec-reindex` is the clearest case in the product of a
"skill" that should never have been a model prompt.** Its own spec requires it to *"deterministically
add the files and refresh intrinsic fields"* and to *ask* before anything semantic — a specification
of a function.

## Decision 5 — Shared `PaneResizer` replaces fixed widths

`SpecWorkspace` uses fixed 260 / ≥520 / 360 with drawer collapse below 1140px, and its own comment
says *"the splitter is an explicit non-goal of this change."* That non-goal belonged to the change
that wrote it; `layout/PaneResizer.tsx` now exists and is what the rest of the app uses.

The compact-mode drawers stay. They solve a different problem (narrow viewport) than the resizer
(operator preference), and `useWorkspaceMode`'s measured-container approach is correct — a media
query would report "wide" while the rail crushes the document.

## Decision 6 — Watchdog cleanup is scoped to touched files

29 references remain across the UI. This change removes those in `SpecChatPane` (5, by deletion),
`SpecPage` (1), and `specChatSession.test.tsx` (5). The other 18 — `eventSummary.ts` (10),
`LogLine`, `LogsView`, `streamModel`, `useSSE`, `useSSE-lifecycle.test.tsx` — are untouched. They are
real staleness, but bundling them makes the diff harder to review and they carry no operator-facing
defect on this surface.

## Testing note — how a document gets onto the page at all

Nothing authors spec documents today: the six `aw-spec-*` skills are uninstalled, and
`hub/hub/api/v1/spec.py` reads `ProjectSpec` rows whose only former producer, the watchdog, is
deleted. On the live testbed the endpoint returned `{"specs":[],"home":null,"manifest":null}`.

**`POST /api/v1/projects/{id}/project/specs/sync` still works** and was verified live on
2026-08-10: pushing `{path, content}` returned 200, the document then listed with
`state: "unindexed"`, `home` resolved to it, and `GET .../project/spec?path=…` returned the content.

That is this change's fixture mechanism. It is not a user journey and must not be presented as one —
it exists so A1 can be verified against a real rendered document before B0/B2 give documents a real
producer.
