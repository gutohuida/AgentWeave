# Test guide — an `@`-mention an agent wrote reads no file

## Agent-verifiable

| What | How | Passes when |
|---|---|---|
| Non-operator text is neutralised | `py -3.11 -m pytest hub/tests/test_inbound_queue.py -q` (tasks 1.1, 1.3, 1.5) | every at-sign in an `agent`, `job`, `checkpoint`, `divergence` or unknown-origin block has a backslash in front of it, including after U+FEFF |
| Operator text is untouched | same file (tasks 1.2, 1.4) | an operator-only turn is byte-identical to today, with no explanatory sentence |
| The question echo | the questions tests (task 1.6) | the agent's question is escaped; an answer made of chosen options is escaped, single, multi-select and batch; a typed answer is unchanged; a mixed answer is escaped whole; the stored `Question` row keeps its text |
| The question echo explains itself | `test_inbound_queue.py` (task 1.3a) | an operator-only turn carrying an escaped question, or an escaped option answer, gets the D6 sentence once |
| The one-shot workers are neutralised | `test_checkpoint_generation.py`, `test_title_generation.py` (tasks 1.7 to 1.10) | both builders escape every at-sign in the prompt argument for both CLIs, whatever other flags they carry; the templates hold none; a changed file under `@scope/` passes the probe in plain, escaped and Windows-separator form; a parsed worker answer and a stored title carry no `\@`; the prompt versions are unchanged |
| Start work escapes an agent's title | the UI test (task 1.11) and `npm run lint` | a title with an at-sign is posted escaped; one without is byte-identical |
| The spec-turn notice escapes the path | `test_launchability.py` (task 1.12) | an at-sign path is escaped at both places and the notice ends with the D6 sentence; an ordinary path is byte-identical |
| The picker offers no double mention | the UI tests (tasks 1.13, 1.14) | `x @/…`, `notes@home.md` and a U+FEFF form are not offered by `@`, `$` or "Insert into composer"; `packages/@scope/x.ts` still is |
| How a worker answers an escaped prompt | `py -3.11 scripts/drive/d4_0923_worker_json_escape.py 3` | every row `outcome: ok`; no generation row stores `\@` once the restore is applied |
| The workers, against the real CLI | `py -3.11 scripts/drive/d3_0923_worker_at_mention.py` (task 3.1) | before the fix both workers show `expanded=True`; after it both show `expanded=False`; the system-prompt-file control is `expanded=False` both times |
| Nothing else moved | full `hub/tests/` (task 2.5) | the count is recorded; every moved assertion is named |
| The CLI still behaves as measured | `py -3.11 scripts/drive/d2_0923_at_mention_tokeniser.py` (tasks 3.1, 3.1a) | `N/N match`; the `escaped`, `escaped_twice`, `after_002f` and `picker_quoted_slash_at` rows say `expanded=False` |
| The product, end to end | the scratch-Hub drive (tasks 4.1 to 4.2c) | B's CLI transcript has no file attachment for a peer's `@<outside path>`, a Start work title, or a clicked option; the operator's `@<inside path>` still attaches |

## Human-only

These need the operator's own Hub, after it has restarted past the commit that ships group 2. The
Hub part is process code, so it does not reach `:8000` until a restart. The UI part (Start work, the
picker) reaches it on the next browser reload.

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
6. Have an agent create a task whose title contains an at-sign (an email address will do), then
   press **Start work** on its card. **Expect:** the opening message in the new conversation shows
   the title with a backslash before the at-sign, and the card keeps the title as written (design
   D8).
7. Ask an agent to ask you a non-blocking question with an option containing an at-sign (an email
   address will do), then click that option. **Expect:** the echo in the chat shows the option with a
   backslash before the at-sign, the Questions view shows it as offered, and a typed answer with an
   `@path` from the picker still attaches (design D4).
8. Create a file named `notes@home.md` in a project. **Expect:** the composer's `@` picker does not
   offer it, and its file tab has no "Insert into composer". A file under a `@scope/` directory is
   still offered (design D10, Q4).
