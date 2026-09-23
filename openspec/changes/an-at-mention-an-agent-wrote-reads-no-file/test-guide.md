# Test guide — an `@`-mention an agent wrote reads no file

## Agent-verifiable

| What | How | Passes when |
|---|---|---|
| Non-operator text is neutralised | `py -3.11 -m pytest hub/tests/test_inbound_queue.py -q` (tasks 1.1, 1.3, 1.5) | every at-sign in an `agent`, `job`, `checkpoint`, `divergence` or unknown-origin block has a backslash in front of it, including after U+FEFF |
| Operator text is untouched | same file (tasks 1.2, 1.4) | an operator-only turn is byte-identical to today, with no explanatory sentence |
| The question echo | the questions tests (task 1.6) | the agent's question is escaped and the operator's answer is not |
| The question echo explains itself | `test_inbound_queue.py` (task 1.3a) | an operator-only turn carrying an escaped question gets the D6 sentence once |
| The one-shot workers are neutralised | `test_checkpoint_generation.py`, `test_title_generation.py` (tasks 1.7 to 1.10) | both builders escape every at-sign for both CLIs; the templates hold none; a changed file under `@scope/` still passes the probe; the prompt version is `checkpoint/2` |
| The workers, against the real CLI | `py -3.11 scripts/drive/d3_0923_worker_at_mention.py` (task 3.1) | before the fix both workers show `expanded=True`; after it both show `expanded=False`; the system-prompt-file control is `expanded=False` both times |
| Nothing else moved | full `hub/tests/` (task 2.5) | the count is recorded; every moved assertion is named |
| The CLI still behaves as measured | `py -3.11 scripts/drive/d2_0923_at_mention_tokeniser.py` (task 3.1) | `N/N match the 2026-09-23 measurement`; the `escaped` and `escaped_twice` rows say `expanded=False` |
| The product, end to end | the scratch-Hub drive (tasks 4.1, 4.2, 4.2a) | B's CLI transcript has no file attachment for a peer's `@<outside path>`; the operator's `@<inside path>` still attaches |

## Human-only

These need the operator's own Hub, after it has restarted past the commit that ships group 2. This
is Hub process code, so unlike an MCP-server change it does not reach `:8000` until a restart.

1. In a conversation with an agent, pick a workspace file with the composer's `@` picker and ask
   what it says. **Expect:** it answers from the file's contents with no read tool call, exactly as
   before.
2. Ask agent A to send agent B a message that mentions a file by `@<absolute path outside B's
   workspace>`, and ask B to quote it. **Expect:** B does not quote it. B sees the path written as
   `\@…`, and if it tries to read the file, the "Workspace only" posture refuses the tool call and
   the refusal is visible.
3. Watch B's view of messages that contain email addresses or code with decorators. **Expect:** a
   backslash before each at-sign in what B was sent, and **no** backslash in what B writes to files
   when it reuses that code. Report it if B copies the backslash into a file (design Risks, first
   bullet).
4. If you run scheduled jobs whose prompt you wrote with an `@path` in it, **expect** the agent to
   read that file with a tool call rather than receive it attached (design D3, Q1).
5. In a conversation where an agent has written a path with an at-sign in front of it, take a
   checkpoint. **Expect:** the checkpoint describes the conversation and does not quote the
   file's contents, and its text shows the at-sign without a backslash (design D7).
