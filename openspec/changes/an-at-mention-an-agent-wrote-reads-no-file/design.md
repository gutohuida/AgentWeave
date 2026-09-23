# Design — an `@`-mention an agent wrote reads no file

**R1, 2026-09-23** (day window). I read every file:line below in this round. Every "measured" row
was run in this round against `claude` 2.1.280 (`claude --version`), from
`testbed/scratch/atpath0923/`. The rows are consolidated in
`scripts/drive/d2_0923_at_mention_tokeniser.py`. Each measurement is one real Haiku turn with every
file tool disallowed.

**How expansion was detected.** The model's reply is not used. The CLI writes a session transcript
(`~/.claude/projects/<cwd-slug>/<session_id>.jsonl`), and it contains an
`"attachment":{"type":"file"` record exactly when the harness read the file. That is deterministic.
Several unexpanded variants got a reply that called the message a prompt injection, and the reply
alone could not have told "not read" apart from "read and withheld".

## Context

**One choke point.** Every agent turn's prompt is built in one place. `turn_scheduler.py:408-411`
is the only caller of `trigger_agent_directly`, and it passes
`message=format_turn_prompt(selected)`. `agent_trigger.py:1091` then prepends the Hub's notices
(`prompt = "\n\n".join([*notices, message])`). `runner_commands.py:283` appends `["-p", prompt]` for
Claude. The later `prompt=prompt` sites in `agent_trigger.py` (`:1282`, `:2017`, `:2867`) pass the
same string on to the executor and the Codex app-server path. They do not compose a new one.

**`format_turn_prompt`** (`inbound_queue.py:101-130`) labels each entry by `origin_type`: `operator`
becomes "Operator", `job` becomes "Scheduled job", and anything else becomes `Agent "<origin_agent>"`.
It then appends `entry.content` unescaped (`:129`).

**Who writes each origin's content** (the call sites of `new_entry`):

| origin_type | Site | Content, and who authored it |
|---|---|---|
| `operator` | `agent_trigger.py:1498` (`POST /agent/trigger`, Hub key only) | the operator's composer text |
| `operator` | `messages.py:268` when `by_operator` (`run_id is None`, `:62`) | the operator's chat text |
| `operator` | `questions.py:165` | `_batch_delivery_text`: **the agent's own question** plus the operator's answer |
| `agent` | `messages.py:268` | another agent's `send_message` (`mcp_server.py:237`) |
| `agent` | `agents.py:2185` | the delegation task text from a spawning agent |
| `job` | `scheduler.py:3314` / `:3335`, `:3664-3668` | `f"{briefing}\n{job.message}"`. The briefing (`scheduler.py:2556-2731`) interpolates the loop's `purpose` (`:2661`), the claimed task's title (`:2666`, `:2674`), description (`:2677`) and acceptance criteria (`:2682`), and a prior checkpoint (`:2691-2696`). `job.message` comes from `POST /jobs` or MCP `create_job`/`create_loop`, by the operator or by an agent when `allow_agent_jobs` is on (`jobs.py:560-570`, `created_by_run_id` at `:693`) |
| `checkpoint` | `checkpoint_cutover.py:136` | `delivery_content(checkpoint)`, built from the agent's `submit_checkpoint_notes` |
| `checkpoint` | `checkpoint_trigger.py:242` | the fixed `_NOTES_REQUEST` (Hub text) |
| `divergence` | `run_divergence.py:262` | Hub-composed divergence text (R1 did not read whether it quotes agent text; R2 should check) |

`origin_type == "operator"` is trustworthy. An agent reaches the queue only through a run credential
(`agent_auth.py`), and `messages.py:62` marks a message as the operator's only when no run is bound.
One operator-origin entry carries agent text: the question echo.

**The operator relies on expansion.** The composer's `@` trigger inserts
`@` + `quoteMentionValue(value)` (`hub/ui/src/lib/composerTrigger.ts:69-72`, `:81-83`, `:91-99`).
The value is a workspace path from `git ls-files` (`workspace_paths.py:31`). The CLI's expansion of
that token is what makes the picker attach the file.

**What the tokeniser does**, measured (`E` = the file was attached):

| Text before the path | E | | Text before the path | E |
|---|---|---|---|---|
| `@<abs>` (after a space) | **E** | | `\@<abs>` | — |
| `@../secret/secret.txt` | **E** | | `\\@<abs>` | — |
| `@"<abs>"` | **E** | | `ops\@example.com and \@<abs>` | — |
| `@C:\…\secret.txt` | **E** | | `@ <abs>`, `@@<abs>` | — |
| newline, tab, U+00A0, U+3000 or U+2028, then `@` | **E** | | U+200B or U+2060, then `@` | — |
| **U+FEFF**, then `@` | **E** | | `＠<abs>` (U+FF20) | — |
| inside a ```` ``` ```` fence, after `> ` | **E** | | `` `@ ``, `"@`, `(@`, `x@` | — |
| `@<abs>.` (trailing dot) | **E** | | `:` `,` `;` `=` `[` `{` `<` `'` `\|` `*` `-` `/` `_` `1` `#` `!` then `@` | — |

A relative `@inside.txt` of a file in the working directory also expands (**E**). That is harmless,
because the agent can read it anyway, but it shows expansion is not limited to absolute paths.

**`client_composed`**, measured with the Hub's own `--mcp-config` (the canonical `mcp_server.py`,
`HUB_URL` pointed at a dead port, no tool called):

| Frame | file attached | `mcp__agentweave__*` in the deferred-tools listing | Model could name the Hub's tools |
|---|---|---|---|
| plain stream-json user frame | yes | 27 tools (81 name hits) | yes, it listed them |
| `"client_composed": true` | **no** | **0** | **no**: *"No visible tools start with `mcp__agentweave`"* |

The attachments that remained under `client_composed` were `instructions`, `session_context`, `date`
and `prompt_snapshot`. The ones dropped were `environment`, `model`, `deferred_tools_delta`,
`deferred_tools_record`, `mcp_instructions_delta`, `skill_listing` and `total_tokens_reminder`.

## Decisions

### D1 — Neutralise at composition, by origin; do not change the transport

Put the fix in `format_turn_prompt`, where the origin of each block is still known. By
`runner_commands.py:283` the prompt is one flat string, and nothing can tell the operator's `@`
from a peer's.

Rejected: shape (a) of the research file, stream-json input with `client_composed` on agent frames.
It works for the file read, and it blinds the agent to the Hub. The measured table above is the
reason. Another variant would send a plain frame first (the Hub preamble) and a composed frame
second. R1 did not measure it: a second frame on stdin is a second user message, and possibly a
second turn. It would also change how every Claude run is spawned in order to fix one tokeniser.

### D2 — Escape every `@`, unconditionally: `text.replace("@", "\\@")`

Three rules were considered:

1. **Mention position only** (`(?<!\S)@`). This depends on matching the CLI's whitespace set.
   Measured: U+FEFF expands a mention, and Python's `\S` counts it as non-space, so this rule leaks
   today.
2. **Only paths that leave the workspace.** This needs the CLI's path resolution copied at compose
   time: `@"…"` quoting, `~`, Windows separators, symlinks inside the workspace that point out, and
   `@server:resource` MCP mentions. Each one is a place to be wrong. Leaving in-workspace mentions
   expandable also buys nothing, because the agent can read those files with a tool.
3. **Every `@`.** This depends on one measured fact: the character before a neutralised `@` is
   always the inserted `\`, and a `\` before `@` blocks expansion whatever precedes it (`\\@` and
   `ops\@x and \@<abs>` are measured). It needs no mirror of the tokeniser.

Rule 3 is chosen. It costs readability: `a@b.com` reaches the agent as `a\@b.com`, and a decorator in
a pasted snippet as `\@pytest.fixture`. See Risks.

### D3 — Every origin except `operator` is neutralised, including `job`

The rule is default-deny: `content if entry.origin_type == "operator" else neutralise(content)`. A
future origin is neutralised until someone decides otherwise.

`job` is neutralised as a whole, even when the operator wrote `job.message`. Three reasons:
- The entry's content is the Hub briefing with agent-authored task fields interpolated, joined to
  `job.message` in one string at two firing sites (`scheduler.py:3314`, `:3668`).
- Exempting operator-authored jobs would mean escaping field by field at both sites and trusting
  `created_by_run_id`.
- What is lost is small. The job editor has no `@` picker (the trigger lives only in
  `Composer.tsx`/`ComposerTriggerMenu.tsx`). A hand-typed `@path` in a job prompt still names the
  file, and the agent reads it with a tool call that the posture judges, which is how the boundary
  is meant to work.

**This is an open question for the operator (Q1).**

### D4 — The question echo neutralises only the question

`_batch_delivery_text` builds `Question: {q}\n\nAnswer: {a}` for one question and a numbered list
for several. Both forms interpolate `row.question`, which the agent wrote through `ask_user`, and
`row.answer`, which the operator wrote. Neutralise `row.question` at both interpolations
(`questions.py:229`, `:233`) and leave `row.answer` alone. This case has an agent reading a file
through its own text: it can turn its next turn into a read outside the posture's view, which the
posture exists to prevent even for the agent itself.

### D5 — Stored text is untouched

`agent_chat.py:195` renders queue entries from stored `content`. Neutralising at write time would
put `\@` in the operator's view of a peer's message and would corrupt round-trips (a checkpoint's
notes read back by `read_checkpoint`). Only the runner prompt changes.

### D6 — Say so once, in the queue preamble

When the neutralisation actually inserted a backslash anywhere in a turn, add one sentence after
the preamble line: *"In text the operator did not write, every at-sign is shown with a backslash
before it, so that the text cannot make your harness attach a file; the original has no
backslash."* Without it, the agent sees an unexplained backslash. With it, the agent knows the text
is quoted content and not an escape to reproduce. The sentence is Hub text, so it is not itself
neutralised. It spells the character as "at-sign" and uses no literal `@`, so it has nothing to
expand. A turn with no inserted backslash, which includes every turn that holds only operator text,
is byte-identical to today.

## Risks

- **An agent copies `\@` into a file.** A peer's message with a decorator or an email reaches the
  agent as `\@…`, and an agent pasting a snippet verbatim could write the backslash. It is
  mitigated by D6, which names the notation once per turn. The residual risk is real and low:
  peer messages are prose far more often than code. R2 should judge whether the notice is worth its
  tokens.
- **The CLI changes its tokeniser.** Suppose a future CLI treats `\@` as an escape for a literal `@`
  and expands whatever follows. `\\@` would still be blocked, but `\@` would not. The probe's
  `escaped` and `escaped_twice` rows exist to catch this. The probe needs a real Haiku turn per row,
  so it is not a CI test. It is a drive step to rerun after a CLI upgrade (tasks 3.2).
- **Hub text interpolating agent text outside the queue.** `agent_trigger.py:1074-1091` prepends
  notices before `message`. The research file and the R1 subagent both read `spec_turn_notice`
  (`launchability.py:316`) as interpolating only a document path. **R1 did not verify this line by
  line**, including whether an agent can choose a spec document path containing `@`. R2 should.

## Open Questions

1. **Q1 (D3):** Is it acceptable that an operator-authored scheduled job's prompt no longer expands a
   hand-typed `@path`? The alternative is field-level escaping in the two job firing sites and
   trusting `created_by_run_id`.
2. **Q2 (D2):** Does the operator accept `a\@b.com` in what agents read, in exchange for a rule that
   does not mirror the CLI's tokeniser?

## Round log

- **R1, 2026-09-23:** explored and proposed. Every tokeniser and `client_composed` claim above was
  measured in this round. The research file's claim that the Hub never sends `client_composed` was
  checked: `grep` for `input-format`, `stream-json` input and `client_composed` in `hub/hub` finds
  none. The research file's recommended shape (a) was **rejected on measurement** (D1). The fallback
  shape (b) was **narrowed to "every `@`"** because the U+FEFF row broke the mention-position rule.
