# One call, several questions, stepped through

**Approved:** 2026-08-07, operator (*"#2: Yes"*)

## Why

`ask_user` asks exactly one question and blocks. An agent that needs three decisions before it can
start — which database, which package manager, whether to write tests — has two bad options: ask
three times in a row, blocking the turn for up to three full timeouts and interrupting the operator
three separate times, or pick two of them itself and ask about the third.

Both are worse than what Claude Code's own `AskUserQuestion` does, which is take a list and let the
operator step through it in one sitting. T3 does the same (`t3src/src/pendingUserInput.ts`).

The panel already hints at this and cannot deliver it. Its `1/2` counter counts *outstanding
questions* — two unrelated questions from two unrelated calls — not steps through one prompt. It
reads like a step counter while being a queue depth.

## What changes

- `ask_user` takes `questions`, a list of 1–4, each with the `question`/`header`/`options`/
  `multi_select` structure already required today. The single-question signature is gone: Claude
  Code's tool always takes a list, and one shape is easier for an agent to get right than two.
- The Hub stores one row per sub-question, sharing a batch identity, and the tool blocks until every
  one is answered.
- The panel steps through them: one question on screen at a time, `2/3` a real step counter, the
  composer answering whichever is active.
- Each answer is saved as it is given, rather than held until the end.

## Impact

- **`hub/hub/mcp_server.py`** — `ask_user`'s signature and its wait.
- **New endpoint** for creating a batch; `Question` gains `batch_id`, `batch_index`, `batch_size`
  (migration 0033).
- **`AgentQuestionCard` / `AgentOutputPanel`** — stepping, and a shared selector so the card and the
  composer cannot disagree about which question is active.
- Existing single questions are a batch of one and behave exactly as they do now.

## Explicitly not in this change

- **Going back to revise an earlier answer.** See design.md — this follows from saving each answer as
  it is given, and the alternative loses the operator's work on a refresh.
- **Batching anything else.** Permission requests stay one at a time; they are answered under a run's
  timeout and arrive when they arrive, so there is nothing to batch.
