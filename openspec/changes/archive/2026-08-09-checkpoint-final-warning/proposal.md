# A dismissal cannot cost the whole conversation

## Why

`2026-08-09-checkpoint-warning-before-spend` made dismissal final, and named the risk it was
accepting in its own "What this costs" section:

> Claude Code auto-compacts near 95%, so a conversation dismissed at 60% and then run to
> exhaustion gets no second warning and no checkpoint — the CLI summarises it first, on a
> compaction nobody authored.

That is the failure the whole capability was built to remove, reintroduced through the one door
the warning change had to leave open. A dismissal means *"not yet"*, and the Hub currently reads
it as *"not ever"*. The distance between those two readings is a conversation lost to a summary
nobody wrote and nothing can inspect.

The operator, asked directly, chose a single final non-dismissible warning.

## What changes

A dismissed conversation warns **once more**, near the window, and that warning cannot be
dismissed.

`Conversation.checkpoint_warning` gains a fourth state, `final`. A conversation sitting in
`dismissed` is promoted to `final` when its usage reaches a point close enough to the provider's
own compaction that acting is still possible but delay is not. The surface renders that warning
with the checkpoint action alone — no dismiss.

**Only where a percentage is known.** In token mode against a model whose window the Hub cannot
resolve there is no "near the window" to be near, and every other decision in this module refuses
to invent a denominator rather than act on one.

**Only out of `dismissed`.** A conversation still sitting on an undismissed `due` already has the
warning on screen; promoting it would replace a banner with the same banner.

Dismissal stays final in the sense that was asked for: the operator is not re-asked at 65%, or
70%, or on every turn. They are told once, at the point where the next thing to happen is the
loss itself.

## What this costs

The operator loses the ability to run a conversation to exhaustion in silence. That is the
intended trade: silence there is indistinguishable from the defect this capability exists to
remove, and it is the one place where respecting the earlier "not yet" produces the exact outcome
the operator was trying to avoid when they dismissed.

A conversation in token mode with an unresolvable window still gets no final warning. That is
honest rather than complete — the alternative is picking a denominator and calling a number a
percentage of it.

## Impact

- `hub/hub/checkpoint_policy.py` — where "near the window" is defined and justified
- `hub/hub/checkpoint_trigger.py` — the `dismissed` branch stops being a dead end
- `hub/hub/api/v1/checkpoints.py` — taking a checkpoint clears `final` as it clears `due`;
  dismissal refuses to act on `final`
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — a warning with one action, which the
  local dismissed-flag must not suppress
- No migration: the column is already `String(16)`, nullable, with no constraint on its values
