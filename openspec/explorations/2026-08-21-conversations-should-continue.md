# Exploration — A reply should continue the conversation, not start one (2026-08-21)

**Status:** OPEN. Diagnosed, not designed. Operator asked for this to be specced.
**Raised by:** operator, 2026-08-21, watching two agents talk on the trial Hub.

## The observation

> "A message exchanged by agents always start a new conversation. That shouldn't be the case.
> They should keep talking in the same conversation until a checkpoint is reached and an agent
> delegates its conversations to a new one or someone says it explicitly."

Measured on `proj-5e960453`. Three messages produced three new conversations:

```
speccer  conv-527bb75d ──▶ builder  conv-3b97a7d3   (new)
builder  conv-3b97a7d3 ──▶ speccer  conv-e4afb6f5   (new — not conv-527bb75d)
speccer  conv-e4afb6f5 ──▶ builder  conv-ae90c8a5   (new — not conv-3b97a7d3)
```

A later exchange in the same session repeated it: one operator conversation plus two messages
produced three conversations again.

## Cause

`conversations.py::peer_bound_conversation` binds delivery on
`Conversation.bound_sender_conversation_id == <the sender's conversation>`. That is
**one-directional**. When B replies, B is writing from its *own* conversation, whose id is not
what A's thread was bound to — so the lookup misses, and `messages.py:196` mints another
conversation. The link needed to find the original is present in the row; nothing follows it
backwards.

## What already agrees with the operator

`checkpoint_cutover.py` exists and does precisely the thing the operator named as the *legitimate*
reason to start a successor: "a successor conversation exists, it has been given the checkpoint,
and the predecessor is closed." So this is not a missing feature — it is peer messaging opening
threads outside the one mechanism that is supposed to open them.

## Sketch of a fix

Before minting: if the sender's own conversation is bound to an **open** conversation whose
`agent` is the recipient, deliver into that one. Roughly a symmetric read of a link already stored.

## What the one-liner does not settle — the real spec questions

1. **Three or more agents.** A binds to B; B messages C; C replies to A. Which thread?
2. **Deliberate branching.** Can an agent choose to open a fresh thread, and how does it say so?
   The operator allowed for "someone says it explicitly."
3. **Cutover interaction.** After a checkpoint hands a conversation to its successor, where does a
   peer reply bound to the *predecessor* land?
4. **Archived threads.** Today an archived binding resolves to a successor bound to the same
   sender. Does continuing-backwards inherit that rule?

"When does a new conversation start" is currently answered in two places that do not know about
each other. That is the thing to fix, and it is why this is a spec rather than a patch.
