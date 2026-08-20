# Exploration — Showing the reasoning chain (2026-08-20)

**Status:** Stub. One of eight explore pages opened 2026-08-20 covering the open backlog. Nothing
decided.

**Origin:** item 1 of the operator's twelve, from the first live session:

> *"Composer does not show the reasoning chain. T3 shows the whole chain then collapses to one
> message; AgentWeave stays on 'working' until that final collapse. Wants the chain visible, and
> better still an expandable 'rationalization' block like the work one."*

---

## What is already built — this is not a plumbing gap

Handoff 0063 filed this as a missing feature. It is narrower than that. Checked 2026-08-20:

- `thinking` is a **first-class stream event kind** — `src/agentweave/stream_events.py:29,34`, with
  `thinking_event()` at line 459 producing "provider-exposed readable reasoning/status prose". The
  boundary deliberately refuses encrypted reasoning blobs, so what crosses is already readable text.
- `hub/ui/src/lib/agentTimelineModel.ts:8` puts `thinking` in `WORK_OUTPUT_KINDS` alongside
  `tool_use` and `tool_result`.
- `hub/ui/src/components/agents/AgentTimeline.tsx:625` renders it as a `WorkRow` labelled
  **"Thinking"**, collapsed, expandable — structurally the "expandable block like the work one" the
  operator asked for, because it *is* the work block.

So the reasoning text arrives, is stored, and has a renderer. The complaint is about **when and how
prominently it appears**, not whether it exists.

## What the actual gap might be — to be established, not assumed

Candidate readings, in the order they seem likely. The exploration should determine which is true by
watching a real run, not by reading code:

1. **It is not visible while it streams.** T3 shows the chain unfolding live, then collapses it once
   the answer lands. AgentWeave may only surface the row after the fact, leaving "working" as the
   only signal during the wait — which is what the operator describes.
2. **It is collapsed by default and reads as nothing.** A row labelled just "Thinking" among tool
   calls does not announce that there is a chain of argument inside it.
3. **The thinking events may not be emitted at all for this runner/model combination.** The adapter
   decides what it forwards; a run that produces no `thinking` events would look exactly like a
   missing feature. **Check this first** — it would change the whole shape of the work.
4. **"Rationalization" may be a distinct thing from `thinking`** — the operator's word suggests a
   summarized *why did I do that* block, not the raw chain. Worth asking.

## Open questions

1. **Which of the four above is it?** Requires a live run with the operator's own runner and model.
2. **Live-streaming reasoning versus after-the-fact display** — these are different builds. The first
   touches the SSE path and the timeline's live behaviour; the second is presentation only.
3. **Does the chain collapse after the answer, as T3 does?** Collapsing is a deliberate act; leaving
   a long chain expanded above every answer would bury the conversation.
4. **Should reasoning be visually distinct from tool calls?** It is currently peer to them in
   `WORK_OUTPUT_KINDS`. Reasoning is prose about intent; a tool call is an action. Same row type may
   be the wrong call.
5. **Does this interact with the working indicator?** Items 6 and 8 were both about that indicator,
   and a visible chain is arguably a better "still working" signal than a spinner.

## Size

Unknown until question 1 is answered. Reading 2 is an afternoon; reading 1 or 3 is a real change.
