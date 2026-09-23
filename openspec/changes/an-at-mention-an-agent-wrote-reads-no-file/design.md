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

**R2: the choke point is one for agent turns, not for every `claude -p` the Hub runs.** There are
exactly three `"-p"` sites in `hub/hub` (`grep`): `runner_commands.py:283` (agent turns),
`worker.py:139` (`build_worker_command`) and `conversation_titles.py:71` (`build_title_command`).
The last two are one-shot workers with no permission posture at all, and both put recorded text on
the command line:

- **The checkpoint worker.** `checkpoint_generation.build_generation_prompt` (`:230-240`)
  interpolates the conversation transcript (`_transcript_since`, `:166-227`: every inbound entry's
  `content`, so operator and peer text, and the agent's own `text` outputs), the previous
  checkpoint's body and the agent's `submit_checkpoint_notes` text. `run_worker` spawns it in a
  fresh temp directory (`worker.py:436-454`). The same checkpoint's probe
  (`_PROBE_PROMPT.format(rendered=render_checkpoint(checkpoint))`, `:633`) interpolates the body
  that worker wrote.
- **The conversation titler.** `_PROMPT.format(excerpt=excerpt)` (`conversation_titles.py:198`),
  the opening message and the agent's first reply, spawned with the project directory as `cwd`.

**Measured in R2** (`scripts/drive/d3_0923_worker_at_mention.py`, argv built by the Hub's own
`build_generation_prompt`/`build_worker_command`/`build_title_command`, `claude` 2.1.280, run twice
on fresh markers): **both expand** an agent's `@<outside path>`. The checkpoint worker's own JSON
reply carried the marker, so the file's contents reach the stored checkpoint body, which the
operator reads and `delivery_content` (`checkpoint_cutover.py:58-60`) hands to the successor
agent. D7 covers both workers.

**The context file is not a vector.** An agent turn's canonical context reaches the CLI through
`--append-system-prompt-file` (`runner_commands.py:244-245`). Measured in R2, same probe: an
`@<outside path>` in mention position in that file is **not** expanded (no attachment, marker
absent from the transcript).

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
| `divergence` | `run_divergence.py:262` | `_response_prompt` (`:192-214`) or `_failed_review_prompt` (`:489-506`). Hub text, but both interpolate `task.title`, which an agent can author (`create_task`). R2: agent text, so D3's default-deny is needed here, not merely harmless |

`origin_type == "operator"` is trustworthy. An agent reaches the queue only through a run credential
(`agent_auth.py`), and `messages.py:62` marks a message as the operator's only when no run is bound.
One operator-origin entry carries agent text: the question echo. (R2 checked the one route that
queues `operator` with no run: `POST /agent/trigger` depends on `get_project`, which calls
`_operator_from_credential` (`auth.py:134-159`), so a run credential cannot reach it.) `new_entry`
accepts a closed set of five origins (`inbound_queue.py:41-44`), so "an origin added later" means
someone edits that tuple; D3's default-deny makes that edit safe by default.

Two line numbers corrected in R2: the loopless job path sets `content = job.message`
(`scheduler.py:3157`) and reaches the same `new_entry` at `:3335`; the loop path's second site is
`:3660-3668`. The chat view renders stored entry content at `api/v1/agent_chat.py:205` (R1 cited
`agent_chat.py:195`).

**A pre-existing mislabel, out of scope here:** `format_turn_prompt` has no label for `checkpoint`
or `divergence`, so both fall through to `f'Agent "{entry.origin_agent}"'`, and `new_entry`
forbids `origin_agent` for them (`:45-46`). The agent reads `Agent "None" (hop 0):` above a
checkpoint or a divergence response. Filed as F410; not fixed here, because it changes every
checkpoint and divergence prompt for a reason unrelated to F409.

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

**R2, a consequence D5 did not state.** The echo is escaped where it is composed
(`questions.py:162-170` stores `_batch_delivery_text`'s result as the entry's `content`), not where
the turn is composed, because by then the question and the answer are one string. So this one
entry's *stored* content carries `\@`, and the chat view renders stored content
(`api/v1/agent_chat.py:205`): the operator sees `\@` inside the echoed question. The `Question` row
itself keeps the original. Accepted: the alternative is a column or a second entry to keep the two
halves apart, for a cosmetic difference in an echo of the agent's own words.

### D5 — Stored text is untouched

`agent_chat.py:195` renders queue entries from stored `content`. Neutralising at write time would
put `\@` in the operator's view of a peer's message and would corrupt round-trips (a checkpoint's
notes read back by `read_checkpoint`). Only the runner prompt changes.

### D6 — Say so once, in the queue preamble

When the composed blocks contain the two characters `\@` anywhere, add one sentence after the
preamble line: *"In text the operator did not write, every at-sign is shown with a backslash
before it, so that the text cannot make your harness attach a file; the original has no
backslash."* Without it, the agent sees an unexplained backslash. With it, the agent knows the text
is quoted content and not an escape to reproduce. The sentence is Hub text, so it is not itself
neutralised. It spells the character as "at-sign" and uses no literal `@`, so it has nothing to
expand.

**R2 changed the trigger** from "`format_turn_prompt` inserted a backslash" to "the blocks contain
`\@`". R1's trigger missed the question echo: D4 escapes it in `questions.py`, before
`format_turn_prompt` runs, inside an `operator` entry that `format_turn_prompt` passes through
untouched, so R1's rule would have delivered an escaped question with no explanation. The new
trigger catches it without the two modules sharing any state. Its only other effect: an operator who
types `\@` themselves also gets the sentence, which is still true and harmless. The constant lives
beside `neutralise_file_mentions` (D7) so both composers can use it. A turn whose blocks contain no
`\@` is byte-identical to today; that includes every operator-only turn except a question echo that
had an at-sign to escape.

### D7 — The one-shot workers neutralise their whole prompt (R2)

`worker.build_worker_command` and `conversation_titles.build_title_command` apply
`neutralise_file_mentions` to the entire `prompt` they are given, in both the `claude` and the
`codex` branch, before placing it in argv.

- **The whole prompt, not per interpolation.** No worker has a use for expansion. Every byte after
  the fixed template is recorded text, the operator's included, and no composer picker feeds a
  worker. The three templates (`_GENERATION_PROMPT`, `_PROBE_PROMPT`, the titler's `_PROMPT`)
  contain no at-sign, and a test pins that, so neutralising the whole string never alters Hub
  text.
- **At the builder.** There is one builder per spawn kind. The two checkpoint kinds share
  `build_worker_command`, and any future worker prompt gets the same treatment without having to opt in.
- **Codex too**, for D3's reason. Whether `codex exec` expands `@` is unverified, and `\@` is
  harmless text.
- **The module.** `neutralise_file_mentions` and the D6 sentence go in a new
  `hub/hub/file_mentions.py`. They do not go in `inbound_queue.py`, so `worker.py` and
  `conversation_titles.py` do not import queue code for a string function.

Two consequences need their own lines:

- **The generation template gains one fixed rule:** *"At-signs in the material below have a
  backslash in front of them that the original did not have; write them without it."* This keeps
  the stored body's text (which the operator reads) free of `\@`. The body is then escaped again
  wherever it next reaches a CLI: as a `checkpoint`-origin delivery (D3) and inside the probe's
  prompt (this decision). `CHECKPOINT_PROMPT_VERSION` goes from `checkpoint/1` to `checkpoint/2`
  (`checkpoint_generation.py:57`), because the template changed.
- **The probe's grading undoes the escape before comparing.** The probe asks for file paths
  "exactly as written", and the rendered checkpoint lists `files_changed` (`:293-294`). A path such
  as `packages/@scope/x` reaches the probe as `packages/\@scope/x`. `_normalise` (`:370-373`) then
  turns every `\` into `/`, which gives `packages//@scope/x`. That never matches the envelope, so a
  good checkpoint would be graded `failed`. `grade_probe` therefore maps `\@` to `@` in the
  **answers** before `_normalise`. The envelope is Hub truth and was never escaped. The probe
  template is unchanged, so `PROBE_PROMPT_VERSION` stays.

## Risks

- **A Windows-separator probe answer before a scoped directory (R2, from D7).** Today a reply of
  `node_modules\@types\x` normalises to `node_modules/@types/x`. After D7's undo it reads
  `node_modules@types/x`, which counts as missing and invented. It needs the model to answer with
  separators the rendered checkpoint does not contain (the envelope paths come from git, which uses
  POSIX separators). Accepted. R3 should judge whether the undo should be limited to `/\@` and a
  leading `\@`.
- **An agent copies `\@` into a file.** A peer's message with a decorator or an email reaches the
  agent as `\@…`, and an agent pasting a snippet verbatim could write the backslash. It is
  mitigated by D6, which names the notation once per turn. The residual risk is real and low:
  peer messages are prose far more often than code. R2 should judge whether the notice is worth its
  tokens.
- **The CLI changes its tokeniser.** Suppose a future CLI treats `\@` as an escape for a literal `@`
  and expands whatever follows. `\\@` would still be blocked, but `\@` would not. The probe's
  `escaped` and `escaped_twice` rows exist to catch this. The probe needs a real Haiku turn per row,
  so it is not a CI test. It is a drive step to rerun after a CLI upgrade (tasks 3.2).
- **Hub text interpolating agent text outside the queue. R2 closed it for the notices.**
  `agent_trigger.py:1074-1091` prepends three notices. `access_path_notice` and
  `auto_snapshot_notice` (`launchability.py:383-440`) interpolate nothing. `spec_turn_notice`
  (`:316-381`) interpolates only `path`, at `:369-373`, inside a backtick span and a quoted
  argument. That path is the controlling **operator** entry's `spec_document`
  (`turn_scheduler.py:400`). An agent cannot choose one containing an at-sign:
  `create_spec_document` takes no path, and the Hub mints a placeholder
  (`mcp_server.py:1723-1742`, `spec_service.py:95-112`). `rename_spec_document` takes prose and
  derives the path from `slugify`, which is `[a-z0-9-]` only (`spec_naming.py:98-121`,
  `agent_actions.py:1360-1368`). `validate_spec_path` (`spec_manifest.py:61-83`) does not itself
  forbid `@` or spaces, so an operator-typed path could carry one. That is operator text, so it is
  out of scope. R2 found the real outside-the-queue case elsewhere: the one-shot workers (Context,
  D7).

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
- **R2, 2026-09-23 (day window, D-3):** a fresh comparison against the code. I read every site
  again, starting from `grep` rather than from R1's table. Nine results:
  - **R2-1, scope: R1's "one choke point" held for agent turns only.** `grep '"-p"'` finds three
    spawn sites, not one. The checkpoint worker and the conversation titler put recorded agent text
    on `claude -p` with no posture at all. **Measured to expand**, and the checkpoint worker's reply
    carried the file's contents into what becomes the stored checkpoint
    (`scripts/drive/d3_0923_worker_at_mention.py`, twice). Added D7, a Context section, a second
    requirement paragraph with two scenarios, and tasks 1.7 to 1.10, 2.3a and 4.2a.
  - **R2-2, a regression D7 would have caused and now avoids.** The probe copies file paths
    "exactly as written", and `_normalise` turns `\` into `/`. So a changed file under `@scope/`
    would have been graded missing and invented, and the checkpoint marked `failed`. D7 undoes the
    escape in the answers first (task 1.9). The residual Windows-separator case is in Risks.
  - **R2-3, the D6 trigger moved.** R1's "`format_turn_prompt` inserted a backslash" never fires
    for the question echo. D4 escapes it upstream, inside an `operator` entry. The trigger is now
    "the blocks contain `\@`" (task 1.3a).
  - **R2-4, D5 was not quite true.** The question echo's *stored* content carries `\@`, and the
    chat renders stored content (`api/v1/agent_chat.py:205`). This is stated in D4 and accepted.
  - **R2-5, notices closed.** `access_path_notice` and `auto_snapshot_notice` interpolate nothing.
    `spec_turn_notice` interpolates only the operator entry's `spec_document`, and an agent cannot
    mint a path containing an at-sign. Details are in Risks, third bullet.
  - **R2-6, divergence is agent text.** `task.title` is interpolated. D3 already covered it, and the
    table row is corrected.
  - **R2-7, the context file is not a vector.** `--append-system-prompt-file` with an
    `@<outside path>` in mention position was measured: no attachment. It is left alone.
  - **R2-8, trust and tests.** `/agent/trigger` accepts only an operator credential. `new_entry`'s
    origin set is closed. No test in `test_inbound_queue.py`, `test_delivery_attempts.py`,
    `test_checkpoint_generation.py`, `test_title_generation.py` or the questions tests puts an
    at-sign in content these composers would change, so no existing exact-string assertion is
    expected to move. Line numbers were corrected (`scheduler.py:3157`, `:3660-3668`,
    `agent_chat.py`'s path). Out of scope: `checkpoint`/`divergence` blocks are labelled
    `Agent "None"`, filed as **F410**.
  - **R2-9, tokeniser rerun:** **41/41 rows match** (exit 0, fresh marker) on `claude` 2.1.280. D2 stands.
  - `openspec validate --strict`: valid after these edits. **R3 must not start from these notes.**
