# Design — a message to the operator is told where the operator reads

**Built on the recommended answer to D10/F77**: *no new operator-addressing channel; the refusal
names the channels that already exist.* **If the operator answers otherwise** (a `notify_operator`
tool that files a non-blocking, durable note on an operator surface), this change still ships as its
first half — the refusal would then name that tool — and the tool is a separate change needing its
own surface design (there is no inbox today; F259/F260 under D6 are the dead Messages screen).

## Context — re-verified on HEAD `404c7d5`

- The refusal: `messages.py:94-117` (event `agent_action_rejected`, reason `unknown_recipient`, then
  404). No special case for reserved names: the only operator logic in the file is on the sender side
  (`OPERATOR_SENDER`, `by_operator` at `:62`, `:329-337`).
- Reserved names: `worktrees._RESERVED_AGENT_NAMES` (`:73`), checked case-insensitively by
  `validate_agent_name` (`:148`). The CLI's copy (`constants.py:79-83`) agrees.
- `ask_user` takes `blocking=False` (`mcp_server.py:355-358`) — a non-blocking question, still a
  question.
- The retired backstop: `0082_drop_unasked_questions.py`'s docstring records the operator's
  retirement; `agent-capability-plane/spec.md:323-384` still describes it as live.

## D1 — Options

1. **The refusal names what works** (recommended). Honest, one branch, reintroduces nothing.
2. **A `notify_operator` tool.** An explicit call is not a guess, so it would not breach the
   no-backstop rule (F77 says as much). But it needs somewhere the operator reliably looks, and the
   candidates are the Questions destination (for questions) and a Messages screen D6 is deciding
   whether to delete. Premature until D6 is answered.
3. **Route `send_message(to="operator")` into the conversation as an operator-visible note.** Blurs
   the agent's reply with a second channel into the same view; rejected.

## D2 — Placement and wording

Checked **before** the recipient lookup, so the answer does not depend on whether a row exists (none
can). A public `is_reserved_agent_name(name) -> bool` in `worktrees.py` wraps
`_RESERVED_AGENT_NAMES.get(name.lower())`; `messages.py` calls it. The sentence names only tools the
agent plane has (`update_task`, `ask_user`) and does not promise the operator will act. The operator's
own sends are untouched.

## D3 — What the route returns when what it calls raises

`persist_event` before the 404 is the same call the unknown-recipient branch makes today; if it
raises, the route answers 500 exactly as that branch would. No new raise path.

## D4 — Removing the retired requirements

REMOVED with reason and migration notes. This reconciles the main spec with shipped code (the
operator retired the behaviour on 2026-08-20); it is here because F77 asks the operator-addressing
question the removed text answers wrongly. If the operator prefers it separate, task group 3 splits
out unchanged.

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
- R2 (2026-09-24): `messages.py:94-117` refusal re-read; reserved names `worktrees.py:73-80`, case-insensitive at `:148`. `grep -rln unasked hub/hub src` finds only migrations `0032/0036/0037/0082` and unrelated prose (`models.py:136`, `repo_hygiene.py`) — nothing implements the two requirements removed here. No agent on `:8000` holds a reserved name (read `mode=ro`), so checking before the lookup strands no existing row.
