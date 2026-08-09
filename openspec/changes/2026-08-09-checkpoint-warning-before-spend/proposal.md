# Warn before spending, and let the operator wave it away

## Why

`offered` currently generates a checkpoint the moment the threshold is crossed, then asks whether
to cut over. The generation is a real model call and it happens whether or not the operator wants
it — so an operator who would rather push on a little further has already paid for a summary they
are about to discard, and at a low threshold pays again on the next turn.

The operator's own framing: *"if I want to extend a little longer I can"*. Nothing about the
current design lets them.

## What changes

`offered` becomes a **warning** rather than a generation. Crossing the threshold marks the
conversation as due and says so; the operator either takes the checkpoint or dismisses the
warning, and a dismissed warning does not return for that conversation.

`automatic` is unchanged — it still generates and cuts over, because that is what choosing it
means. `off` is unchanged.

**The staleness argument still holds, and is why this is a warning rather than a deferred offer.**
A checkpoint must be written from the context that is about to be lost, so the Hub still refuses
to promise "I will make one later". It says the moment has arrived and hands the decision over
immediately, which keeps the artifact fresh whenever the operator says yes.

## What this costs

A dismissed warning is silent for the rest of that conversation, which is what was asked for. The
risk that follows: Claude Code auto-compacts near 95%, so a conversation dismissed at 60% and then
run to exhaustion gets no second warning and no checkpoint — the CLI summarises it first, on a
compaction nobody authored. The dismissal is recorded per conversation, so a successor starts
warnable again, but within one conversation dismissal is final.

## Impact

- `Conversation.checkpoint_warning` — one column, three states, no second boolean
- `hub/hub/checkpoint_trigger.py` — `offered` warns instead of generating
- `hub/hub/api/v1/checkpoints.py` — dismissal
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — the warning, with both actions
